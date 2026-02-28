"""
Blueberry Vault Watchdog
Monitors VAULT_DIR for user edits (or Syncthing-pushed changes).
Re-embeds changed files and syncs goal frontmatter back to SQLite.
Run as: systemd service (see Scripts/blueberry-watchdog.service)
"""
import os
import pickle
import time
import frontmatter
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from Logging import logger_init
from Database import connect_to_dataset
from LLM import OllamaEmbed
from utils import VAULT_DIR, EMB_MODEL

LOGGER = logger_init("Watchdog")
LOCK_FILE = "/tmp/blueberry_bot_writing.lock"


class VaultHandler(FileSystemEventHandler):
    def __init__(self):
        self.emb = OllamaEmbed(EMB_MODEL)

    def on_modified(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith('.md'):
            return
        if Path(LOCK_FILE).exists():
            LOGGER.debug("Bot is writing — skipping event")
            return
        self._handle(event.src_path)

    on_created = on_modified  # treat new files the same way

    def _handle(self, abs_path: str):
        try:
            rel_path = os.path.relpath(abs_path, VAULT_DIR)
            LOGGER.info(f"Vault change detected: {rel_path}")

            post = frontmatter.load(abs_path)
            embedding = self.emb.embed(post.content)
            if embedding is None:
                LOGGER.error(f"Could not embed {rel_path}")
                return

            db = connect_to_dataset()
            db['vault_index'].upsert(dict(
                file_path=rel_path,
                file_type=self._file_type(rel_path),
                client_id=post.get('client_id'),
                model=EMB_MODEL,
                embedding=pickle.dumps(embedding),
                period_start=post.get('period_start'),
                period_end=post.get('period_end'),
                updated_at=datetime.now(),
            ), ['file_path'])
            LOGGER.debug(f"vault_index updated for {rel_path}")

            if rel_path.startswith("Goals/"):
                self._sync_goal(post)
        except Exception as e:
            LOGGER.error(f"Error handling vault event for {abs_path}: {e}")

    def _file_type(self, rel_path: str) -> str:
        parts = rel_path.split('/')
        if parts[0] == 'Memories' and len(parts) >= 2:
            return parts[1]  # 'daily', 'weekly', etc.
        return parts[0].lower()  # 'goals', 'knowledge', etc.

    def _sync_goal(self, post):
        goal_text = post.content.strip()
        status = post.get('status', 'active')
        db = connect_to_dataset()
        db['client_goals'].update(
            dict(goal_text=goal_text, status=status),
            ['goal_text']
        )
        LOGGER.info(f"Synced goal status '{status}' → SQLite")


if __name__ == "__main__":
    LOGGER.info(f"Starting vault watchdog on {VAULT_DIR}")
    handler = VaultHandler()
    observer = Observer()
    observer.schedule(handler, VAULT_DIR, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
