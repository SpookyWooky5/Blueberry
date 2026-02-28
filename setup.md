# Blueberry — Setup Guide

Blueberry is a personal AI email assistant running on a Raspberry Pi 5. It reads your
emails, responds using a local LLM via Ollama, tracks your goals and habits, detects
patterns in your life, and builds a knowledge base — all stored in an Obsidian vault
synced to your devices via Syncthing.

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Directory Layout](#2-directory-layout)
3. [Environment Variables](#3-environment-variables)
4. [Config Files](#4-config-files)
5. [Python Environment](#5-python-environment)
6. [Database Setup](#6-database-setup)
7. [Ollama Setup](#7-ollama-setup)
8. [Obsidian Vault Setup](#8-obsidian-vault-setup)
9. [Syncthing Setup](#9-syncthing-setup)
10. [Email Account Setup (Zoho)](#10-email-account-setup-zoho)
11. [Systemd Services](#11-systemd-services)
12. [Cron Jobs](#12-cron-jobs)
13. [Logs](#13-logs)
14. [First Run Checklist](#14-first-run-checklist)
15. [Assumptions & Constraints](#15-assumptions--constraints)

---

## 1. System Requirements

| Component | Requirement |
|-----------|------------|
| Hardware | Raspberry Pi 5 (or any Linux machine) |
| OS | Linux (tested on Raspberry Pi OS) |
| Python | 3.11 or newer |
| Package manager | `uv` (preferred) or `pip` |
| Local LLM runtime | [Ollama](https://ollama.com) running on `localhost:11434` |
| Email provider | Zoho Mail (IMAP + SMTP) |
| Vault sync | Syncthing |
| Note-taking app | Obsidian (for reading/editing vault on other devices) |

---

## 2. Directory Layout

The deployment root is `/home/mainberry/Blueberry/`. Adjust paths throughout if you use a
different root.

```
/home/mainberry/
├── Blueberry/                  # Deployment root (PYTHONPATH points here)
│   ├── MailServer/             # Email fetch, reply, proactive check-in
│   ├── LLM/                    # Ollama wrappers, summarize, extract_*
│   ├── Database/               # SQLite schema + dataset ORM helpers
│   ├── Obsidian/               # Vault writer API
│   ├── Logging/                # Log rotation + formatters
│   ├── Scripts/                # LoadEnv.sh, blueberry-watchdog.service, crontab
│   ├── Configs/                # secrets.yml, process.json, .env     ← $BCFG
│   ├── prompts/                # All .txt prompt files               ← $PROMPTS_DIR
│   ├── watchdog_daemon.py      # Vault file watcher (systemd service)
│   ├── reminder_daemon.py      # Goal reminder cron
│   └── .venv/                  # Python virtual environment
│
├── Logs/                       # Log files for all processes         ← $LOG_DIR
│   ├── LLM.log
│   ├── MailServer.log
│   ├── Database.log
│   ├── Common.log
│   ├── watchdog.log
│   └── cron.log
│
└── Vault/                      # Obsidian vault root                 ← $VAULT_DIR
    ├── Goals/
    ├── Habits/
    ├── Patterns/
    ├── Observations/
    ├── Knowledge/
    │   ├── profile.md          # Always injected into reply context
    │   └── topics/
    └── Memories/
        ├── daily/
        ├── weekly/
        ├── monthly/
        ├── quarterly/
        └── yearly/
```

The SQLite database lives at `$DB_DIR/db.sqlite3` (see Section 3 for how `$DB_DIR` is set).

---

## 3. Environment Variables

All environment variables must be exported before running any script. They are set in
`~/.bash_aliases` (for interactive shells and the watchdog systemd service) and in
`Scripts/LoadEnv.sh` (for cron jobs).

| Variable | Value | Where used |
|----------|-------|-----------|
| `BCFG` | `/home/mainberry/Blueberry/Configs` | Config directory — `utils.py`, `Logging/utils.py`, `Database/create_db.py` |
| `PROMPTS_DIR` | `/home/mainberry/Blueberry/prompts` | Prompt directory — `utils.read_prompt_from_file()` |
| `VAULT_DIR` | `/home/mainberry/Vault` | Obsidian vault root — `Obsidian/writer.py`, `MailServer/reply.py`, `LLM/summarize.py` |
| `LOG_DIR` | `/home/mainberry/Logs` | Log directory — `Logging/utils.py` |
| `DB_DIR` | `/home/mainberry/Blueberry/Database` | SQLite database dir — `Database/db_utils.py`, `Database/create_db.py` |
| `Data` | `/home/mainberry/Blueberry/Data` | Data directory — `Database/db_utils.py` (currently reserved) |
| `PYTHONPATH` | `/home/mainberry/Blueberry:$PYTHONPATH` | Makes all subpackages importable without installing |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint — `LLM/main.py` (defaults to this if unset) |

### Setting them in `~/.bash_aliases`

```bash
export DEV="/home/mainberry/Blueberry"
export LOG_DIR="/home/mainberry/Logs"
export BCFG="$DEV/Configs"
export PROMPTS_DIR="$DEV/prompts"
export VAULT_DIR="/home/mainberry/Vault"
export DB_DIR="$DEV/Database"
export Data="$DEV/Data"
export PYTHONPATH="$DEV:$PYTHONPATH"
export OLLAMA_BASE_URL="http://localhost:11434"  # optional, this is the default
```

After editing, reload: `source ~/.bash_aliases`

---

## 4. Config Files

All config files live in `$BCFG` (`/home/mainberry/Blueberry/Configs/`).

### 4a. `secrets.yml`

Contains email credentials and client list. **Never commit this file.**

```yaml
Mail:
  Zoho:
    email: blueberry@yourdomain.com       # the address Blueberry sends FROM
    password: YOUR_APP_PASSWORD           # Zoho app password (not account password)
    smtp:
      host: smtp.zoho.com
      port: 465
    imap:
      host: imap.zoho.com
  Clients:
    - you@example.com                     # email addresses Blueberry listens to
    - partner@example.com
  ClientNames:
    - Your Name
    - Partner Name
```

### 4b. `.env`

Contains LLM and embedding model names, loaded via `python-dotenv`.

```dotenv
LLM_MODEL=gemma3:4b-it-qat
EMB_MODEL=nomic-embed-text
```

Use whatever model names match what you have pulled in Ollama (see Section 7).

### 4c. `process.json`

Controls log levels and summarizer configuration. Each key under `Summarizer` maps a
summary type to its data source and time window.

```json
{
  "LLM":       { "LogLevel": "INFO" },
  "MailServer": { "LogLevel": "INFO" },
  "Database":  { "LogLevel": "WARNING" },
  "Common":    { "LogLevel": "INFO" },
  "Summarizer": {
    "daily": {
      "delta":        { "days": 1 },
      "source_table": "emails",
      "source_filter": {},
      "header":       "Daily Summary for {client_name}"
    },
    "weekly": {
      "delta":        { "weeks": 1 },
      "source_table": "memories",
      "source_filter": { "memory_type": "daily" },
      "header":       "Weekly Summary for {client_name}"
    },
    "monthly": {
      "delta":        { "months": 1 },
      "source_table": "memories",
      "source_filter": { "memory_type": "weekly" },
      "header":       "Monthly Summary for {client_name}"
    },
    "quarterly": {
      "delta":        { "months": 3 },
      "source_table": "memories",
      "source_filter": { "memory_type": "monthly" },
      "header":       "Quarterly Summary for {client_name}"
    }
  }
}
```

> **Note:** `yearly` summaries do not read from a DB table — they read quarterly vault
> files directly from `vault_index`, so no config entry is needed for yearly.

---

## 5. Python Environment

### Install `uv`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Create the virtual environment

```bash
cd /home/mainberry/Blueberry
uv venv .venv
```

### Install dependencies

```bash
uv pip install -r pyproject.toml
# or equivalently:
uv sync
```

### Key packages installed

| Package | Purpose |
|---------|---------|
| `requests` | Ollama HTTP API calls |
| `dataset` | High-level SQLite ORM |
| `numpy` | Embedding vectors + cosine similarity |
| `python-frontmatter` | Read/write Obsidian markdown with YAML frontmatter |
| `watchdog` | Filesystem event monitoring (vault watcher) |
| `python-dateutil` | Relativedelta for summary time windows |
| `python-dotenv` | Load `.env` file for model names |
| `pyyaml` | Parse `secrets.yml` |
| `pytest` + `pytest-mock` | Test suite (not needed in production) |

---

## 6. Database Setup

The database is a single SQLite file at `$DB_DIR/db.sqlite3`. Create it fresh:

```bash
cd /home/mainberry/Blueberry
python Database/create_db.py
```

This runs `Database/schema.sql` which creates these tables:

| Table | Purpose |
|-------|---------|
| `clients` | One row per person Blueberry talks to |
| `emails` | Every email in/out with threading metadata |
| `email_embeddings` | Embedding vector per email |
| `memories` | Legacy summary table (pre-Phase 2, kept for reference) |
| `memory_embeddings` | Legacy embedding table |
| `memory_membership` | Legacy link table |
| `obsidian_changes_history` | Audit log of vault writes |
| `vault_index` | Embedding index pointing to vault `.md` files |
| `client_goals` | Active/past goals with reminder state |

### Migrations (if upgrading from an earlier version)

If you have an existing database from before Phase 2/3, run these manually:

```sql
-- Phase 2: vault index
CREATE TABLE IF NOT EXISTS vault_index (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  file_path    VARCHAR(512) UNIQUE NOT NULL,
  file_type    VARCHAR(50)  NOT NULL,
  client_id    INTEGER REFERENCES clients(id),
  model        VARCHAR(100) NOT NULL,
  embedding    BLOB         NOT NULL,
  period_start DATE,
  period_end   DATE,
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Phase 3: goal state machine columns
ALTER TABLE client_goals ADD COLUMN deadline        DATE;
ALTER TABLE client_goals ADD COLUMN last_reminded   DATE;
ALTER TABLE client_goals ADD COLUMN reminder_count  INTEGER NOT NULL DEFAULT 0;
ALTER TABLE client_goals ADD COLUMN habit_slug      VARCHAR(100);
```

---

## 7. Ollama Setup

### Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Pull the required models

```bash
ollama pull gemma3:4b-it-qat     # or whatever LLM_MODEL you set in .env
ollama pull nomic-embed-text      # or whatever EMB_MODEL you set in .env
```

### Verify Ollama is running

```bash
ollama list                      # should show your models
curl http://localhost:11434/api/tags  # should return JSON
```

Ollama runs as a systemd service after installation. If it stops:

```bash
systemctl start ollama
systemctl enable ollama           # to start on boot
```

### Model notes

- The chat model (`gemma3:4b-it-qat`) is quantized to fit in ~5 GB RAM. A Pi 5 with 8 GB
  works well. Swap to a larger model (e.g. `llama3.2:3b`) if you prefer.
- The embedding model (`nomic-embed-text`) produces 768-dimensional vectors.
  The cosine similarity threshold is hardcoded to **0.65** in `MailServer/reply.py`.

---

## 8. Obsidian Vault Setup

### Create the vault directory

```bash
mkdir -p /home/mainberry/vault/{Goals,Habits,Patterns,Observations}
mkdir -p /home/mainberry/vault/Knowledge/topics
mkdir -p /home/mainberry/vault/Memories/{daily,weekly,monthly,quarterly,yearly}
```

### Open in Obsidian

Point Obsidian at `/home/mainberry/vault/` (or whatever `$VAULT_DIR` is set to). Blueberry
writes all its files there using YAML frontmatter compatible with Obsidian.

### Key vault files

| Path | Description |
|------|-------------|
| `Knowledge/profile.md` | Always injected into reply context. Edit freely — Blueberry appends facts here. |
| `Goals/<slug>.md` | One file per goal. Frontmatter tracks `status`, `reminder_count`, `deadline`. |
| `Habits/<slug>.md` | Habit clusters inferred from goals. |
| `Patterns/<slug>.md` | Detected connections between life themes. First write wins; edit freely after. |
| `Memories/{type}/{key}.md` | Hierarchical summaries (daily → weekly → monthly → quarterly → yearly). |
| `Observations/YYYY-MM-DD-<slug>.md` | Self-reflections (not yet auto-routed in Phase 4). |

### Vault lock sentinel

Blueberry uses `/tmp/blueberry_bot_writing.lock` as a sentinel file to prevent the
watchdog from re-embedding files it just wrote. This is ephemeral and cleaned up
automatically. Do not create or delete it manually.

---

## 9. Syncthing Setup

Syncthing syncs the vault between the Pi and your other devices (phone, laptop) so you can
read and edit vault files in Obsidian on any device.

### Install on the Pi

```bash
sudo apt install syncthing
systemctl --user enable syncthing
systemctl --user start syncthing
```

### Configure

1. Open the Syncthing web UI: `http://localhost:8384`
2. Add a new shared folder pointing to `$VAULT_DIR` (`/home/mainberry/vault`)
3. Install Syncthing on your phone/laptop and pair the devices
4. Accept the folder share on each device
5. In Obsidian on each device, open the synced vault folder

### What Syncthing syncs

Everything under `$VAULT_DIR`. The watchdog daemon detects any `.md` changes (including
those from Syncthing) and re-embeds them automatically into `vault_index`.

---

## 10. Email Account Setup (Zoho)

Blueberry uses a dedicated Zoho Mail account as its identity. You can use any IMAP/SMTP
provider, but the code references Zoho config keys. Adapt `secrets.yml` accordingly.

### Create a Zoho Mail account

1. Sign up at [zoho.com/mail](https://www.zoho.com/mail/)
2. Create an app password: **Account Settings → Security → App Passwords**
   (do not use your main account password in `secrets.yml`)
3. Enable IMAP: **Settings → Mail Accounts → IMAP Access**

### Zoho IMAP/SMTP endpoints

| Protocol | Host | Port |
|----------|------|------|
| IMAP SSL | `imap.zoho.com` | 993 |
| SMTP SSL | `smtp.zoho.com` | 465 |

### How Blueberry handles email

- `MailServer/fetch.py` — polls IMAP every 5 min via cron, stores unseen emails in DB
- `MailServer/reply.py` — runs every 10 min, generates and sends replies via SMTP
- `MailServer/proactive_checkin.py` — sends a proactive message every 3 days
- `reminder_daemon.py` — sends goal reminders once per day (if goals are overdue)

Blueberry only reads emails **from addresses listed in `secrets.yml → Mail → Clients`**.
All other emails are ignored.

---

## 11. Systemd Services

### Vault watchdog

The watchdog monitors `$VAULT_DIR` for file changes (from Syncthing or direct Obsidian
edits) and re-embeds the changed files into `vault_index`.

```bash
# Copy the service file
sudo cp /home/mainberry/Blueberry/Scripts/blueberry-watchdog.service \
        /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable blueberry-watchdog
sudo systemctl start blueberry-watchdog

# Check status
sudo systemctl status blueberry-watchdog
journalctl -u blueberry-watchdog -f
```

The service file loads environment variables from `~/.bash_aliases` via `EnvironmentFile`.

### Ollama (auto-installed)

```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

---

## 12. Cron Jobs

Install the crontab from `Scripts/crontab`:

```bash
crontab Scripts/crontab
# or merge with existing:
crontab -l | cat - Scripts/crontab | crontab -
```

All jobs use `flock` to prevent overlapping runs and `LoadEnv.sh` to set up the
environment. Cron does not inherit shell env vars, so `LoadEnv.sh` is mandatory.

### Cron schedule

| Schedule | Script | Purpose |
|----------|--------|---------|
| Every 5 min | `MailServer/fetch.py` | Fetch new emails from IMAP |
| Every 10 min | `MailServer/reply.py` | Generate and send replies |
| Every 3rd day at 08:00 | `MailServer/proactive_checkin.py` | Proactive check-in message |
| Daily at 07:01 | `LLM/summarize.py daily` | Daily summary email |
| Sunday at 23:01 | `LLM/summarize.py weekly` | Weekly summary email |
| 1st of month at 00:01 | `LLM/summarize.py monthly` | Monthly summary + pattern detection |
| 1st of every 3rd month at 01:01 | `LLM/summarize.py quarterly` | Quarterly summary + pattern detection |
| Jan 1 at 02:01 | `LLM/summarize.py yearly` | Yearly summary |
| Daily at 09:00 | `reminder_daemon.py` | Goal reminder emails |

Two flock files are used:
- `/tmp/blueberry.lock` — shared by all main pipeline jobs
- `/tmp/blueberry_reminder.lock` — exclusive to the reminder daemon

---

## 13. Logs

All logs go to `$LOG_DIR` (`/home/mainberry/Logs/`). Log level per process is set in
`process.json`.

| File | Written by |
|------|-----------|
| `LLM.log` | All LLM modules |
| `MailServer.log` | fetch, reply, proactive check-in |
| `Database.log` | DB connection and operations |
| `Common.log` | utils, shared helpers |
| `watchdog.log` | Vault watchdog daemon |
| `cron.log` | Combined stdout/stderr from all cron jobs (via LoadEnv.sh) |

Log files are rotated daily: the previous day's file is renamed to `<name>.log.YYYY-MM-DD`.

---

## 14. First Run Checklist

```
[ ] Install Ollama, pull LLM and embedding models
[ ] Create Python venv and install dependencies (uv sync)
[ ] Create $BCFG directory and write secrets.yml, .env, process.json
[ ] Set all required env vars in ~/.bash_aliases
[ ] Create $LOG_DIR directory
[ ] Create $DB_DIR directory
[ ] Run: python Database/create_db.py   (creates db.sqlite3)
[ ] Create vault directory structure (mkdir -p ...)
[ ] Point Obsidian at the vault directory
[ ] Set up Syncthing and pair devices
[ ] Install and enable blueberry-watchdog systemd service
[ ] Install crontab (crontab Scripts/crontab)
[ ] Send a test email to the Blueberry address and watch MailServer.log
[ ] Verify reply arrives (check LLM.log and cron.log for errors)
```

---

## 15. Assumptions & Constraints

### Hard-coded paths and values

| Item | Value | File |
|------|-------|------|
| Cosine similarity threshold | `0.65` | `MailServer/reply.py` |
| Reminder interval | 48 hours | `reminder_daemon.py` |
| Max reminders per goal | 5 (then auto-ignored) | `reminder_daemon.py` |
| First reminder trigger | `deadline + 1 day` or `created_at + 7 days` | `reminder_daemon.py` |
| LOCK_FILE (bot writing sentinel) | `/tmp/blueberry_bot_writing.lock` | `Obsidian/writer.py` |
| Flock file (main pipeline) | `/tmp/blueberry.lock` | `Scripts/crontab` |
| Flock file (reminder) | `/tmp/blueberry_reminder.lock` | `Scripts/crontab` |
| DB filename | `db.sqlite3` | `Database/db_utils.py` |
| Schema filename | `schema.sql` | `Database/create_db.py` |

### Code assumptions

- **Single user per instance.** The `clients` table and `CLIENTS`/`CLIENTNAMES` lists in
  `secrets.yml` support multiple email addresses, but all share one Blueberry identity.
- **Zoho-specific IMAP/SMTP keys.** `secrets.yml` uses `Zoho`-keyed sections. To use
  another provider, change the key names and update `MailServer/auth.py` and `fetch.py`.
- **Ollama on localhost.** `LLM/main.py` reads `OLLAMA_BASE_URL` from the environment,
  defaulting to `http://localhost:11434`. Remote Ollama works by setting this variable.
- **Bot-initiated pattern detection runs after monthly and quarterly summaries only.**
  Daily and weekly summaries do not trigger pattern detection.
- **Observation files are written but not yet auto-routed.** `write_observation()` exists
  but no cron or email label currently triggers it. It can be called manually.
- **Weekly/monthly/quarterly summaries still read from the `memories` SQLite table**
  (a legacy table). Only yearly summaries read from `vault_index`. This is a known gap
  from Phase 2.
- **Topic knowledge files (`Knowledge/topics/<slug>.md`) are create-once.** After the
  first write Blueberry will not overwrite them; you own the file.
- **Pattern files (`Patterns/<slug>.md`) are create-once.** Same slug = same pattern;
  first detection wins.
- **Profile.md is always appended to, never overwritten.** Edit it directly in Obsidian
  to correct or remove facts.
- **`process.json` must have a `"LLM"` key** because `LLM/summarize.py` reads
  `load_config()["LLM"]` at module import time.
- **The `DB_DIR` env var must point to the directory containing `db.sqlite3`**, not to the
  file itself.
- **The `Data` env var is declared but currently unused** beyond being required at import
  time in `Database/db_utils.py`.

### Prompt files

All 10 prompt files must exist in `$PROMPTS_DIR` before running. They are not bundled in the
package — copy them from `prompts/` in the source repo:

```bash
cp -r /path/to/source/prompts/* $PROMPTS_DIR/
```

| File | Used by |
|------|---------|
| `mail_prompt.txt` | `MailServer/reply.py` |
| `summary_prompt.txt` | `LLM/summarize.py` |
| `goal_extraction_prompt.txt` | `LLM/extract_goals.py` |
| `habit_inference_prompt.txt` | `LLM/extract_habits.py` |
| `reminder_prompt.txt` | `reminder_daemon.py` |
| `knowledge_extraction_prompt.txt` | `LLM/extract_knowledge.py` |
| `pattern_extraction_prompt.txt` | `LLM/extract_patterns.py` |
| `pattern_detection_prompt.txt` | `LLM/summarize.py` |
| `proactive_checkin_prompt.txt` | `MailServer/proactive_checkin.py` |
| `classify_prompt.txt` | Present but currently unused (classification uses a hardcoded prompt in `LLM/classify.py`) |
