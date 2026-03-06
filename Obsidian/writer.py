import os
import re
import frontmatter
from pathlib import Path
from datetime import datetime

from utils import VAULT_DIR


def _fmt_date(email_date) -> str:
    """Format a date for frontmatter. Falls back to today if None."""
    if email_date is None:
        return datetime.now().strftime("%Y-%m-%d")
    if hasattr(email_date, 'strftime'):
        return email_date.strftime("%Y-%m-%d")
    return str(email_date)[:10]  # handle ISO string from DB

LOCK_FILE = "/tmp/blueberry_bot_writing.lock"


def _slugify(text: str, maxlen: int = 60) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:maxlen]


def _write(abs_path: str, metadata: dict, content: str):
    """Create parent dirs, set lock, write file atomically, release lock."""
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    post = frontmatter.Post(content, **metadata)
    Path(LOCK_FILE).touch()
    try:
        with open(abs_path, 'wb') as f:
            frontmatter.dump(post, f)
    finally:
        Path(LOCK_FILE).unlink(missing_ok=True)


def memory_relpath(summary_type: str, period_start) -> str:
    """Returns relative vault path for a memory file. Used for idempotency checks."""
    if summary_type == "weekly":
        key = f"{period_start.year}-W{period_start.strftime('%U').zfill(2)}"
    elif summary_type == "quarterly":
        q = (period_start.month - 1) // 3 + 1
        key = f"{period_start.year}-Q{q}"
    elif summary_type == "monthly":
        key = period_start.strftime("%Y-%m")
    elif summary_type == "yearly":
        key = period_start.strftime("%Y")
    else:  # daily
        key = period_start.strftime("%Y-%m-%d")
    return f"Memories/{summary_type}/{key}.md"


def write_memory(summary_type: str, period_start, period_end, content: str,
                 client_id: int) -> str:
    """Writes memory summary to vault. Returns relative path."""
    rel = memory_relpath(summary_type, period_start)
    abs_path = os.path.join(VAULT_DIR, rel)
    _write(abs_path, {
        "client_id": client_id,
        "summary_type": summary_type,
        "period_start": str(period_start),
        "period_end": str(period_end),
    }, content)
    return rel


def write_goal(goal_text: str, client_id: int, source_email_id: int,
               context: str = "", email_date=None, status: str = "active") -> str:
    """Writes a goal note to vault. Returns relative path. No-op if file exists."""
    slug = _slugify(goal_text)
    rel = f"Goals/{slug}.md"
    abs_path = os.path.join(VAULT_DIR, rel)
    if os.path.exists(abs_path):
        return rel
    body = f"{goal_text}\n\n{context}".strip() if context else goal_text
    _write(abs_path, {
        "status": status,
        "client_id": client_id,
        "created": _fmt_date(email_date),
        "deadline": None,
        "last_reminded": None,
        "reminder_count": 0,
        "source_email_id": source_email_id,
        "tags": [],
    }, body)
    return rel


def update_goal(slug: str, **fields) -> str:
    """Updates frontmatter fields on an existing goal file. Returns relative path."""
    rel = f"Goals/{slug}.md"
    abs_path = os.path.join(VAULT_DIR, rel)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Goal vault file not found: {rel}")
    post = frontmatter.load(abs_path)
    for k, v in fields.items():
        post[k] = v
    Path(LOCK_FILE).touch()
    try:
        with open(abs_path, 'wb') as f:
            frontmatter.dump(post, f)
    finally:
        Path(LOCK_FILE).unlink(missing_ok=True)
    return rel


def write_habit(name: str, client_id: int, email_date=None) -> str:
    """Creates a Habits/<slug>.md file. No-op if already exists. Returns relative path."""
    slug = _slugify(name)
    rel = f"Habits/{slug}.md"
    abs_path = os.path.join(VAULT_DIR, rel)
    if os.path.exists(abs_path):
        return rel
    _write(abs_path, {
        "client_id": client_id,
        "created": _fmt_date(email_date),
        "status": "active",
    }, name)
    return rel


def write_observation(content: str, date) -> str:
    """Writes a self-reflection to Observations/YYYY-MM-DD-<slug>.md."""
    date_str = date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date)
    slug = _slugify(content[:40])
    rel = f"Observations/{date_str}-{slug}.md"
    abs_path = os.path.join(VAULT_DIR, rel)
    _write(abs_path, {"date": date_str}, content)
    return rel


def write_knowledge(title: str, content: str, is_profile: bool = False, email_date=None) -> str:
    """Writes to Knowledge/profile.md (append) or Knowledge/topics/<slug>.md (create-once)."""
    if is_profile:
        rel = "Knowledge/profile.md"
        abs_path = os.path.join(VAULT_DIR, rel)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        Path(LOCK_FILE).touch()
        try:
            with open(abs_path, 'a', encoding='utf-8') as f:
                f.write(f"\n{content}\n")
        finally:
            Path(LOCK_FILE).unlink(missing_ok=True)
        return rel
    else:
        slug = _slugify(title)
        rel = f"Knowledge/topics/{slug}.md"
        abs_path = os.path.join(VAULT_DIR, rel)
        if os.path.exists(abs_path):
            return rel
        _write(abs_path, {"title": title, "created": _fmt_date(email_date)}, content)
        return rel


def write_pattern(title: str, content: str, email_date=None) -> str:
    """Writes a detected pattern to Patterns/<slug>.md. No-op if slug already exists."""
    slug = _slugify(title)
    rel = f"Patterns/{slug}.md"
    abs_path = os.path.join(VAULT_DIR, rel)
    if os.path.exists(abs_path):
        return rel
    _write(abs_path, {"title": title, "detected": _fmt_date(email_date)}, content)
    return rel
