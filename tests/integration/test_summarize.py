"""
Integration tests for LLM/summarize.py.

Tests focus on:
1. _detect_and_write_pattern() — bot-initiated pattern detection helper
2. get_relevant_past_memories() — RAG over vault_index
3. summarize() yearly path behaviour
"""
import os
import pickle
import numpy as np
import pytest
from unittest.mock import patch, MagicMock, call
from datetime import datetime, date


# ── _detect_and_write_pattern ──────────────────────────────────────────────────

@patch("LLM.summarize.write_pattern")
@patch("LLM.summarize.read_prompt_from_file", return_value="Detect: {summary_type}\n{summary_text}")
def test_detect_pattern_writes_when_found(mock_prompt, mock_wp, tmp_vault):
    from LLM.summarize import _detect_and_write_pattern
    mock_table = MagicMock()
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=mock_table)
    llm = MagicMock()
    emb = MagicMock()
    emb.embed.return_value = np.array([0.1])  # length-1 avoids numpy bool ambiguity
    llm.generate_response.return_value = '{"title": "Stress and Work", "content": "They co-occur."}'
    mock_wp.return_value = "Patterns/stress-and-work.md"

    _detect_and_write_pattern(db, llm, emb, client_id=1, summary_text="...", summary_type="monthly")

    mock_wp.assert_called_once_with("Stress and Work", "They co-occur.")
    mock_table.upsert.assert_called_once()


@patch("LLM.summarize.write_pattern")
@patch("LLM.summarize.read_prompt_from_file", return_value="Detect: {summary_type}\n{summary_text}")
def test_detect_pattern_skips_on_null_response(mock_prompt, mock_wp):
    from LLM.summarize import _detect_and_write_pattern
    db = MagicMock()
    llm = MagicMock()
    emb = MagicMock()
    llm.generate_response.return_value = "null"

    _detect_and_write_pattern(db, llm, emb, 1, "summary text", "monthly")

    mock_wp.assert_not_called()


@patch("LLM.summarize.write_pattern")
@patch("LLM.summarize.read_prompt_from_file", return_value="Detect: {summary_type}\n{summary_text}")
def test_detect_pattern_skips_on_empty_title(mock_prompt, mock_wp):
    from LLM.summarize import _detect_and_write_pattern
    db = MagicMock()
    llm = MagicMock()
    emb = MagicMock()
    llm.generate_response.return_value = '{"title": "", "content": "something"}'

    _detect_and_write_pattern(db, llm, emb, 1, "summary text", "monthly")

    mock_wp.assert_not_called()


@patch("LLM.summarize.write_pattern")
@patch("LLM.summarize.read_prompt_from_file", return_value=None)
def test_detect_pattern_skips_when_prompt_missing(mock_prompt, mock_wp):
    from LLM.summarize import _detect_and_write_pattern
    db = MagicMock()
    llm = MagicMock()
    emb = MagicMock()

    _detect_and_write_pattern(db, llm, emb, 1, "summary text", "monthly")

    mock_wp.assert_not_called()
    llm.generate_response.assert_not_called()


@patch("LLM.summarize.write_pattern")
@patch("LLM.summarize.read_prompt_from_file", return_value="Detect: {summary_type}\n{summary_text}")
def test_detect_pattern_no_crash_on_json_error(mock_prompt, mock_wp):
    from LLM.summarize import _detect_and_write_pattern
    db = MagicMock()
    llm = MagicMock()
    emb = MagicMock()
    llm.generate_response.return_value = "bad json here"

    # Should not raise
    _detect_and_write_pattern(db, llm, emb, 1, "summary text", "monthly")
    mock_wp.assert_not_called()


@patch("LLM.summarize.write_pattern")
@patch("LLM.summarize.read_prompt_from_file", return_value="Detect: {summary_type}\n{summary_text}")
def test_detect_pattern_skips_vault_index_when_embed_falsy(mock_prompt, mock_wp):
    from LLM.summarize import _detect_and_write_pattern
    db = MagicMock()
    llm = MagicMock()
    emb = MagicMock()
    emb.embed.return_value = None  # embed failed
    llm.generate_response.return_value = '{"title": "Pattern X", "content": "Desc."}'
    mock_wp.return_value = "Patterns/pattern-x.md"

    _detect_and_write_pattern(db, llm, emb, 1, "summary text", "monthly")

    mock_wp.assert_called_once()
    db['vault_index'].upsert.assert_not_called()


# ── get_relevant_past_memories ─────────────────────────────────────────────────

def test_get_relevant_past_memories_returns_empty_when_no_vault_index(tmp_vault):
    from LLM.summarize import get_relevant_past_memories
    db = MagicMock()
    db['vault_index'].find.return_value = []
    emb = MagicMock()
    emb.embed.return_value = np.array([0.5, 0.5])

    result = get_relevant_past_memories(db, emb, 1, "some text", top_k=3)
    assert result == []


def test_get_relevant_past_memories_returns_empty_for_empty_text(tmp_vault):
    from LLM.summarize import get_relevant_past_memories
    db = MagicMock()
    emb = MagicMock()

    result = get_relevant_past_memories(db, emb, 1, "", top_k=3)
    assert result == []
    emb.embed.assert_not_called()


def test_get_relevant_past_memories_top_k(tmp_vault, monkeypatch):
    from LLM.summarize import get_relevant_past_memories
    import LLM.summarize as summarize_mod
    monkeypatch.setattr(summarize_mod, "VAULT_DIR", str(tmp_vault))

    # Write stub memory files
    for i in range(3):
        p = tmp_vault / "Memories" / "daily" / f"2025-01-0{i+1}.md"
        p.write_text(f"---\n---\nMemory content {i}\n")

    vecs = [
        np.array([0.9, 0.1]),   # closest to query
        np.array([0.5, 0.5]),
        np.array([0.1, 0.9]),
    ]
    query_vec = np.array([1.0, 0.0])

    db = MagicMock()
    db['vault_index'].find.return_value = [
        {"file_path": f"Memories/daily/2025-01-0{i+1}.md",
         "period_start": date(2025, 1, i+1),
         "embedding": pickle.dumps(vecs[i])}
        for i in range(3)
    ]
    emb = MagicMock()
    emb.embed.return_value = query_vec

    results = get_relevant_past_memories(db, emb, 1, "Some text", top_k=2)
    assert len(results) <= 2
    # The first result should be the most similar
    assert "Memory content 0" in results[0]["text"]


# ── summarize() — yearly path ──────────────────────────────────────────────────

@patch("LLM.summarize.get_or_create_client", return_value=1)
@patch("LLM.summarize.connect_to_dataset")
def test_summarize_yearly_skips_when_no_quarterly_files(
    mock_db_cls, mock_client, tmp_vault, monkeypatch
):
    import LLM.summarize as summarize_mod
    monkeypatch.setattr(summarize_mod, "CLIENTS",      ["client@test.com"])
    monkeypatch.setattr(summarize_mod, "CLIENTNAMES",  ["Test"])
    monkeypatch.setattr(summarize_mod, "VAULT_DIR",    str(tmp_vault))

    db = MagicMock()
    # vault_index returns no quarterly records and no existing yearly
    db['vault_index'].find_one.return_value = None
    db['vault_index'].find.return_value = []
    mock_db_cls.return_value = db

    llm = MagicMock()
    emb = MagicMock()

    today = datetime(2025, 12, 31)
    from LLM.summarize import summarize
    summarize("yearly", today, llm, emb, respond=False)

    # LLM should not have been called since there are no quarterly summaries
    llm.generate_response.assert_not_called()


@patch("LLM.summarize.get_or_create_client", return_value=1)
@patch("LLM.summarize.connect_to_dataset")
def test_summarize_yearly_skips_if_already_exists(
    mock_db_cls, mock_client, tmp_vault, monkeypatch
):
    import LLM.summarize as summarize_mod
    monkeypatch.setattr(summarize_mod, "CLIENTS",      ["client@test.com"])
    monkeypatch.setattr(summarize_mod, "CLIENTNAMES",  ["Test"])
    monkeypatch.setattr(summarize_mod, "VAULT_DIR",    str(tmp_vault))

    db = MagicMock()
    # find_one returns a row → summary already exists
    db['vault_index'].find_one.return_value = {"id": 1}
    mock_db_cls.return_value = db

    llm = MagicMock()
    emb = MagicMock()

    today = datetime(2025, 12, 31)
    from LLM.summarize import summarize
    summarize("yearly", today, llm, emb, respond=False)

    llm.generate_response.assert_not_called()


def test_summarize_invalid_type_returns_early():
    from LLM.summarize import summarize
    llm = MagicMock()
    emb = MagicMock()
    # Should not raise
    summarize("hourly", datetime.now(), llm, emb, respond=False)
    llm.generate_response.assert_not_called()
