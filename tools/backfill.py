"""
backfill.py — Ingest historical SEEN emails and rebuild memories.

Usage:
    cd ~/Blueberry
    python tools/backfill.py [--since YYYY-MM-DD] [--hard_reset]

Phases:
  0. [--hard_reset] Truncate all DB tables (not Obsidian vault), then exit.
     Re-run without --hard_reset to re-ingest after a reset.
  1. Fetch SEEN emails from IMAP → insert to emails + email_embeddings
  2. Run extraction pipeline (goals, knowledge, patterns) for each
     email not yet marked extracted=1
  3. Run summaries daily → weekly → monthly → quarterly → yearly
     for all periods from the earliest email date to today
"""

import os
import sys
import email
import time
import pickle
import argparse
from datetime import datetime, timedelta, date

import numpy as np
from dateutil.relativedelta import relativedelta

# Allow running from repo root without installing as a package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Logging import logger_init
from Database import connect_to_dataset, get_or_create_client
from MailServer import imap_auth
from LLM import OllamaChat, OllamaEmbed
from LLM.extract_goals import extract_and_save_goals
from LLM.extract_knowledge import extract_and_save_knowledge
from LLM.extract_patterns import extract_and_save_pattern
from LLM.summarize import summarize
from utils import load_secrets, strip_quoted_reply, EMB_MODEL, LLM_MODEL

LOGGER = logger_init("Backfill")

# Order matters: child tables before parents for DELETE to respect FK constraints
RESET_TABLES = [
    'memory_membership',
    'memory_embeddings',
    'email_embeddings',
    'obsidian_changes_history',
    'vault_index',
    'client_goals',
    'memories',
    'emails',
    'clients',
]

# (summary_type, relativedelta step) — must go from fine to coarse
# so higher-level summaries can consume lower-level ones
SUMMARY_SCHEDULE = [
    ('daily',     relativedelta(days=1)),
    ('weekly',    relativedelta(weeks=1)),
    ('monthly',   relativedelta(months=1)),
    ('quarterly', relativedelta(months=3)),
    ('yearly',    relativedelta(years=1)),
]


# ── Schema migration ───────────────────────────────────────────────────────────

def ensure_extracted_column(db):
    """Add 'extracted' column to emails table if not present (idempotent)."""
    try:
        db.query("ALTER TABLE emails ADD COLUMN extracted BOOLEAN NOT NULL DEFAULT 0")
        LOGGER.info("Added 'extracted' column to emails table.")
        print("  [migration] Added 'extracted' column to emails table.")
    except Exception:
        pass  # Column already exists — expected on all runs after the first


# ── Hard reset ─────────────────────────────────────────────────────────────────

def hard_reset(db):
    """Truncate all data from every table, preserving schema and vault files."""
    print("Hard reset: clearing all tables (Obsidian vault is untouched)...")
    for table in RESET_TABLES:
        try:
            db.query(f"DELETE FROM {table}")
            print(f"  cleared  {table}")
            LOGGER.info(f"hard_reset: cleared {table}")
        except Exception as e:
            LOGGER.warning(f"hard_reset: could not clear {table}: {e}")
            print(f"  WARNING: could not clear {table}: {e}")
    try:
        db.query("DELETE FROM sqlite_sequence")
    except Exception:
        pass
    print("Hard reset complete. Re-run without --hard_reset to backfill.")


# ── Phase 1: Ingest ────────────────────────────────────────────────────────────

def fetch_seen_emails(since: date | None = None) -> list[dict]:
    """Connect to IMAP and return parsed SEEN emails for all configured clients."""
    secrets = load_secrets()
    clients = secrets["Mail"]["Clients"]

    imap = imap_auth()
    imap.select('inbox')

    all_ids: set[bytes] = set()
    for client in clients:
        criteria = ['SEEN', 'FROM', client]
        if since:
            criteria += ['SINCE', since.strftime('%d-%b-%Y')]
        status, data = imap.search(None, *criteria)
        if status == 'OK' and data[0]:
            all_ids.update(data[0].split())

    mail_ids = sorted(map(int, all_ids))
    print(f"Phase 1: {len(mail_ids)} SEEN emails found on IMAP.")
    LOGGER.info(f"Fetching {len(mail_ids)} SEEN emails.")

    parsed = []
    for i, mid in enumerate(mail_ids):
        try:
            _, raw = imap.fetch(str(mid).encode(), "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])

            subject             = msg.get("Subject", "")
            msg_id              = msg.get("Message-ID", email.utils.make_msgid())
            references          = msg.get("References", "")
            to_name,  to_addr   = email.utils.parseaddr(msg.get("To",   ""))
            from_name, from_addr = email.utils.parseaddr(msg.get("From", ""))

            date_tuple = email.utils.parsedate(msg.get("Date"))
            if date_tuple:
                mail_dt = datetime.fromtimestamp(
                    time.mktime(date_tuple) - timedelta(hours=5, minutes=30).seconds
                )
            else:
                mail_dt = datetime.utcnow()

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors='replace')
                        break
            else:
                body = msg.get_payload(decode=True).decode(errors='replace')

            body = body.replace("=E2=80=AF", " ")
            clean_body = strip_quoted_reply(body)

            parsed.append({
                'msg_id':      msg_id,
                'subject':     subject,
                'to_name':     to_name,
                'to_addr':     to_addr,
                'from_name':   from_name,
                'from_addr':   from_addr,
                'references_': references,
                'body':        clean_body,
                'time_received': mail_dt,
            })
        except Exception as e:
            LOGGER.error(f"Could not parse IMAP message {mid}: {e}")

        if (i + 1) % 20 == 0:
            print(f"  parsed {i + 1}/{len(mail_ids)}...")

    imap.logout()
    print(f"  parsed {len(parsed)} emails successfully.")
    return parsed


def ingest_emails(db, emb, parsed_emails: list[dict]) -> int:
    """
    Insert emails not already in DB.
    Returns count of newly inserted rows.
    """
    inserted = 0
    skipped  = 0

    for p in parsed_emails:
        if db['emails'].find_one(message_id=p['msg_id']):
            skipped += 1
            continue

        client_id = get_or_create_client(p['from_addr'], p['from_name'])
        if client_id == -1:
            LOGGER.warning(f"Could not get/create client for {p['from_addr']}, skipping.")
            continue

        db.begin()
        try:
            embedding = emb.embed(f"Subject: {p['subject']}\nBody: {p['body']}")
            email_id = db['emails'].insert(dict(
                client_id    = client_id,
                message_id   = p['msg_id'],
                to_addr      = p['to_addr'],
                to_name      = p['to_name'],
                from_addr    = p['from_addr'],
                from_name    = p['from_name'],
                subject      = p['subject'],
                body         = p['body'],
                time_received= p['time_received'],
                references_  = p['references_'],
                responded    = 1,
                extracted    = 0,
            ))
            if embedding is not None and len(embedding) > 0:
                db['email_embeddings'].insert(dict(
                    email_id  = email_id,
                    client_id = client_id,
                    model     = EMB_MODEL,
                    embedding = pickle.dumps(np.array(embedding)),
                ))
            db.commit()
            inserted += 1
        except Exception as e:
            LOGGER.error(f"Could not insert email {p['msg_id']}: {e}")
            db.rollback()

    print(f"  inserted {inserted} new, skipped {skipped} already in DB.")
    return inserted


# ── Phase 2: Extract ───────────────────────────────────────────────────────────

def extract_unprocessed(db):
    """
    Run goal/knowledge/pattern extraction for every email with extracted=0.
    Marks each email extracted=1 on completion (even if some extractions fail).
    Each extractor creates its own OllamaChat instance internally.
    """
    rows = list(db['emails'].find(extracted=0))
    if not rows:
        print("Phase 2: No unextracted emails — skipping.")
        return

    print(f"Phase 2: Extracting from {len(rows)} email(s)...")
    for i, row in enumerate(rows):
        email_id  = row['id']
        client_id = row['client_id']
        subject   = row.get('subject') or ''
        body      = row.get('body')    or ''
        text      = f"Subject: {subject}\n\n{body}"

        try:
            extract_and_save_goals(client_id, text, email_id)
        except Exception as e:
            LOGGER.error(f"Goal extraction failed for email {email_id}: {e}")

        try:
            extract_and_save_knowledge(client_id, text, email_id)
        except Exception as e:
            LOGGER.error(f"Knowledge extraction failed for email {email_id}: {e}")

        try:
            extract_and_save_pattern(client_id, text, email_id)
        except Exception as e:
            LOGGER.error(f"Pattern extraction failed for email {email_id}: {e}")

        # Mark extracted regardless of individual extractor failures so we
        # don't retry on every run — use --hard_reset to force a redo.
        db['emails'].update({'id': email_id, 'extracted': 1}, ['id'])

        if (i + 1) % 5 == 0 or (i + 1) == len(rows):
            print(f"  extracted {i + 1}/{len(rows)}")


# ── Phase 3: Summarize ─────────────────────────────────────────────────────────

def run_summaries(llm, emb, db):
    """
    Run all summary types for every period from the earliest email date to today.
    summarize() is already idempotent — it skips periods that already exist in vault.
    """
    row = db.query("SELECT MIN(time_received) AS t FROM emails").next()
    if not row or not row['t']:
        print("Phase 3: No emails in DB — skipping summaries.")
        return

    earliest = datetime.fromisoformat(str(row['t'])).date()
    today    = date.today()
    print(f"Phase 3: Summarising {earliest} → {today}...")

    for stype, step in SUMMARY_SCHEDULE:
        current = earliest
        written = 0
        errors  = 0
        while current <= today:
            period_end = datetime.combine(current + step, datetime.min.time())
            try:
                if summarize(stype, period_end, llm, emb, respond=False, db=db):
                    written += 1
            except Exception as e:
                LOGGER.error(f"summarize({stype}, {current}) failed: {e}")
                errors += 1
            current += step
        suffix = f"  ({errors} errors)" if errors else ""
        print(f"  {stype:<12} {written} written{suffix}")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Backfill historical emails and rebuild Blueberry memories."
    )
    parser.add_argument(
        '--since', metavar='YYYY-MM-DD',
        help="Only process emails on or after this date (Phase 1 filter)."
    )
    parser.add_argument(
        '--hard_reset', action='store_true',
        help="Truncate all DB tables before backfilling. Obsidian vault is untouched."
    )
    parser.add_argument(
        '--summarize-only', action='store_true',
        help="Skip Phase 1 (ingest) and Phase 2 (extract). Only run Phase 3 summaries."
    )
    args = parser.parse_args()

    since = date.fromisoformat(args.since) if args.since else None

    db = connect_to_dataset()
    ensure_extracted_column(db)

    # ── Phase 0: hard reset (optional) ────────────────────────────────────────
    if args.hard_reset:
        confirm = input(
            "\nWARNING: --hard_reset will DELETE all rows from every table.\n"
            "Obsidian vault files are NOT affected.\n"
            "Type 'yes' to confirm: "
        )
        if confirm.strip().lower() != 'yes':
            print("Aborted.")
            sys.exit(0)
        hard_reset(db)
        sys.exit(0)

    emb = OllamaEmbed(EMB_MODEL)

    if not args.summarize_only:
        # ── Phase 1: Ingest ────────────────────────────────────────────────────
        parsed = fetch_seen_emails(since=since)
        ingest_emails(db, emb, parsed)

        # ── Phase 2: Extract ───────────────────────────────────────────────────
        extract_unprocessed(db)

    # Unload both models so Phase 3 always starts with clean Ollama memory
    print("Flushing Ollama model memory before summarisation...")
    OllamaChat(LLM_MODEL).unload()
    emb.unload()

    # ── Phase 3: Summarize ─────────────────────────────────────────────────────
    llm = OllamaChat(LLM_MODEL)
    run_summaries(llm, emb, db)

    print("\nBackfill complete.")


if __name__ == "__main__":
    main()
