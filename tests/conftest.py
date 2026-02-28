"""
conftest.py — Blueberry test suite bootstrap

IMPORTANT: env vars must be set and mock config files written BEFORE any Blueberry
module is imported, because utils.py reads env vars and calls load_secrets() at
module import time. This file sets everything up at module level, not inside fixtures.
"""
import os
import json
import tempfile
import numpy as np
import pytest
from unittest.mock import MagicMock

# ── Bootstrap ──────────────────────────────────────────────────────────────────
_tmpdir  = tempfile.mkdtemp(prefix="blueberry_test_")
_cfg     = os.path.join(_tmpdir, "config")
_prompts = os.path.join(_tmpdir, "prompts")
_vault   = os.path.join(_tmpdir, "vault")
os.makedirs(_cfg)
os.makedirs(_prompts)
os.makedirs(_vault)

_SECRETS_YAML = """\
Mail:
  Zoho:
    email: blueberry@test.com
    password: testpass
    smtp:
      host: smtp.test.com
      port: 465
  Clients: [client@test.com]
  ClientNames: [Test Client]
"""
with open(os.path.join(_cfg, "secrets.yml"), "w") as f:
    f.write(_SECRETS_YAML)
with open(os.path.join(_cfg, ".env"), "w") as f:
    f.write("LLM_MODEL=test-model\nEMB_MODEL=test-embed\n")
with open(os.path.join(_cfg, "process.json"), "w") as f:
    json.dump({
        "LLM": {},
        "Summarizer": {
            "daily":     {"delta": {"days": 1},    "source_table": "emails",    "source_filter": {}, "header": "Daily Summary for {client_name}"},
            "weekly":    {"delta": {"weeks": 1},   "source_table": "memories",  "source_filter": {}, "header": "Weekly Summary for {client_name}"},
            "monthly":   {"delta": {"months": 1},  "source_table": "memories",  "source_filter": {}, "header": "Monthly Summary for {client_name}"},
            "quarterly": {"delta": {"months": 3},  "source_table": "memories",  "source_filter": {}, "header": "Quarterly Summary for {client_name}"},
        },
    }, f)

os.environ.setdefault("Xml",             _cfg)
os.environ.setdefault("Prompts",         _prompts)
os.environ.setdefault("VAULT_DIR",       _vault)
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
# ── End bootstrap ──────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_vault(tmp_path, monkeypatch):
    """Isolated vault dir per test; patches VAULT_DIR in utils and Obsidian.writer."""
    vault = tmp_path / "vault"
    for d in [
        "Goals", "Habits", "Patterns", "Observations",
        "Knowledge", "Knowledge/topics",
        "Memories/daily", "Memories/weekly", "Memories/monthly",
        "Memories/quarterly", "Memories/yearly",
    ]:
        (vault / d).mkdir(parents=True, exist_ok=True)

    import utils
    import Obsidian.writer as writer
    monkeypatch.setattr(utils,  "VAULT_DIR", str(vault))
    monkeypatch.setattr(writer, "VAULT_DIR", str(vault), raising=False)
    return vault


@pytest.fixture()
def tmp_prompts(tmp_path, monkeypatch):
    """Isolated prompts dir per test; patches PROMPTS_DIR in utils."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    import utils
    monkeypatch.setattr(utils, "PROMPTS_DIR", str(prompts))
    return prompts


@pytest.fixture()
def mock_llm():
    m = MagicMock()
    m.generate_response.return_value = '{"labels": ["casual"], "tags": []}'
    return m


@pytest.fixture()
def mock_emb():
    m = MagicMock()
    m.embed.return_value = np.array([0.1, 0.2, 0.3])
    return m


@pytest.fixture()
def mock_db():
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=MagicMock())
    return db
