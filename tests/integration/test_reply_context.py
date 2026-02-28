"""
Integration tests for get_context_from_config() in MailServer/reply.py.

Uses tmp_vault fixture (isolated vault dir with VAULT_DIR patched),
a mocked database, and a mocked embedder. No SMTP or real LLM calls.
"""
import pickle
import numpy as np
import pytest
from unittest.mock import MagicMock

from MailServer.reply import get_context_from_config


@pytest.fixture()
def no_goals_db():
    """Mock DB that returns no active goals and no vault_index records."""
    db = MagicMock()
    table = MagicMock()
    table.find.return_value = []
    db.__getitem__ = MagicMock(return_value=table)
    return db


# ── Profile injection ──────────────────────────────────────────────────────────

def test_profile_injected_when_file_exists(tmp_vault, no_goals_db, mock_emb):
    profile = tmp_vault / "Knowledge" / "profile.md"
    profile.write_text("- Uses Python\n- Lives in Canada")
    config = {"remember": {"enable": False}, "embeds": {"enable": False}}
    context = get_context_from_config(no_goals_db, mock_emb, 1, "test email", config)
    assert "[USER PROFILE]" in context
    assert "- Uses Python" in context
    assert "- Lives in Canada" in context


def test_profile_skipped_when_missing(tmp_vault, no_goals_db, mock_emb):
    # Don't create profile.md
    config = {"remember": {"enable": False}, "embeds": {"enable": False}}
    context = get_context_from_config(no_goals_db, mock_emb, 1, "test email", config)
    assert "[USER PROFILE]" not in context


def test_empty_profile_file_not_injected(tmp_vault, no_goals_db, mock_emb):
    profile = tmp_vault / "Knowledge" / "profile.md"
    profile.write_text("")
    config = {"remember": {"enable": False}, "embeds": {"enable": False}}
    context = get_context_from_config(no_goals_db, mock_emb, 1, "test email", config)
    assert "[USER PROFILE]" not in context


# ── Active goals injection ─────────────────────────────────────────────────────

def test_active_goals_injected(tmp_vault, mock_emb):
    db = MagicMock()
    table = MagicMock()
    table.find.return_value = [
        {"goal_text": "Finish the report"},
        {"goal_text": "Exercise daily"},
    ]
    db.__getitem__ = MagicMock(return_value=table)
    config = {"remember": {"enable": False}, "embeds": {"enable": False}}
    context = get_context_from_config(db, mock_emb, 1, "test email", config)
    assert "[ACTIVE GOALS]" in context
    assert "Finish the report" in context
    assert "Exercise daily" in context


def test_no_active_goals_no_goals_block(tmp_vault, no_goals_db, mock_emb):
    config = {"remember": {"enable": False}, "embeds": {"enable": False}}
    context = get_context_from_config(no_goals_db, mock_emb, 1, "test email", config)
    assert "[ACTIVE GOALS]" not in context


def test_active_goals_appear_first(tmp_vault, mock_emb):
    profile = tmp_vault / "Knowledge" / "profile.md"
    profile.write_text("- Some profile info")
    db = MagicMock()
    table = MagicMock()
    table.find.return_value = [{"goal_text": "My goal"}]
    db.__getitem__ = MagicMock(return_value=table)
    config = {"remember": {"enable": False}, "embeds": {"enable": False}}
    context = get_context_from_config(db, mock_emb, 1, "test email", config)
    # Active goals should appear before user profile
    assert context.index("[ACTIVE GOALS]") < context.index("[USER PROFILE]")


# ── Similarity-based RAG ───────────────────────────────────────────────────────

def test_similarity_rag_returns_closest_memory(tmp_vault, no_goals_db):
    # Write stub vault files
    for name in ["2025-01-01.md", "2025-01-02.md"]:
        p = tmp_vault / "Memories" / "daily" / name
        p.write_text(f"---\n---\nContent of {name}\n")

    db = MagicMock()
    close_emb  = np.array([1.0, 0.0, 0.0])
    far_emb    = np.array([0.0, 1.0, 0.0])
    query_emb  = np.array([0.95, 0.05, 0.0])  # close to close_emb

    table = MagicMock()
    table.find.return_value = [
        {
            "id": 1,
            "file_path": "Memories/daily/2025-01-01.md",
            "period_start": "2025-01-01",
            "embedding": pickle.dumps(close_emb),
        },
        {
            "id": 2,
            "file_path": "Memories/daily/2025-01-02.md",
            "period_start": "2025-01-02",
            "embedding": pickle.dumps(far_emb),
        },
    ]
    db.__getitem__ = MagicMock(return_value=table)

    emb = MagicMock()
    emb.embed.return_value = query_emb

    config = {
        "remember": {"enable": False},
        "embeds": {"enable": True, "topk": 1},
    }
    context = get_context_from_config(db, emb, 1, "test email", config)
    assert "2025-01-01.md" in context or "Content of 2025-01-01.md" in context


def test_similarity_rag_deduplicates_with_remember(tmp_vault):
    """Same vault_index row should not appear twice even when both embeds and remember enabled."""
    p = tmp_vault / "Memories" / "daily" / "2025-01-01.md"
    p.write_text("---\nfile_type: daily\nperiod_start: '2025-01-01'\n---\nShared content\n")

    emb_vec = np.array([1.0, 0.0])
    db = MagicMock()
    row = {
        "id": 1,
        "file_path": "Memories/daily/2025-01-01.md",
        "period_start": "2025-01-01",
        "file_type": "daily",
        "embedding": pickle.dumps(emb_vec),
    }
    db.__getitem__.return_value.find.return_value = [row]

    emb = MagicMock()
    emb.embed.return_value = emb_vec

    config = {
        "remember": {
            "enable": True,
            "time_filters": {"daily": 1, "weekly": 0, "monthly": 0, "quarterly": 0},
            "today_emails": False,
        },
        "embeds": {"enable": True, "topk": 1},
    }
    context = get_context_from_config(db, emb, 1, "test email", config)
    # "Shared content" should appear at most once
    assert context.count("Shared content") <= 1


# ── Goal acknowledgment ────────────────────────────────────────────────────────

def test_goal_acknowledge_label_triggers_handler(tmp_vault, no_goals_db, mock_emb):
    """goal_acknowledge label should call _handle_goal_acknowledgment without raising."""
    # Create a stub goal file so the function has something to find
    goal_file = tmp_vault / "Goals" / "finish-the-report.md"
    goal_file.write_text(
        "---\nstatus: active\nreminder_count: 2\n---\nFinish the report\n"
    )
    emb_vec = np.array([1.0, 0.0])
    no_goals_db.__getitem__.return_value.find.return_value = [
        {
            "id": 1,
            "file_path": "Goals/finish-the-report.md",
            "file_type": "goals",
            "embedding": pickle.dumps(emb_vec),
        }
    ]
    mock_emb.embed.return_value = emb_vec
    config = {"remember": {"enable": False}, "embeds": {"enable": False}}

    # Should not raise
    context = get_context_from_config(
        no_goals_db, mock_emb, 1, "Yes, I'm working on it", config,
        labels=["goal_acknowledge"]
    )
    assert "[GOAL ACKNOWLEDGED" in context


# ── Goal update ambiguous ──────────────────────────────────────────────────────

def test_goal_update_ambiguous_adds_note(tmp_vault, no_goals_db, mock_emb):
    config = {"remember": {"enable": False}, "embeds": {"enable": False}}
    context = get_context_from_config(
        no_goals_db, mock_emb, 1, "I started working on things", config,
        labels=["goal_update_ambiguous"]
    )
    assert "NOTE" in context or "clarifying question" in context.lower() or "goal" in context.lower()
