import os
import pytest
from utils import remove_think_blocks, strip_quoted_reply, escape_special_chars, read_prompt_from_file


# ── remove_think_blocks ────────────────────────────────────────────────────────

def test_remove_think_blocks_basic():
    assert remove_think_blocks("before<think>hidden</think>after") == "beforeafter"


def test_remove_think_blocks_no_block():
    assert remove_think_blocks("plain text") == "plain text"


def test_remove_think_blocks_multiline():
    assert remove_think_blocks("a<think>\nsome hidden\nlines\n</think>b") == "ab"


def test_remove_think_blocks_empty_input():
    assert remove_think_blocks("") == ""


def test_remove_think_blocks_multiple_blocks():
    s = "x<think>a</think>y<think>b</think>z"
    assert remove_think_blocks(s) == "xyz"


# ── strip_quoted_reply ─────────────────────────────────────────────────────────

def test_strip_quoted_reply_on_date_wrote():
    body = "My reply here.\n\nOn Monday, Bob wrote:\n> some quoted text"
    result = strip_quoted_reply(body)
    assert "My reply here." in result
    assert "Bob wrote" not in result
    assert "> some quoted text" not in result


def test_strip_quoted_reply_gt_lines():
    body = "My message\n> quoted line\n> another quoted"
    result = strip_quoted_reply(body)
    assert "My message" in result
    assert "> quoted line" not in result


def test_strip_quoted_reply_signature():
    body = "Hi there\n\n--\nSigned, Alice"
    result = strip_quoted_reply(body)
    assert "Hi there" in result
    assert "Signed, Alice" not in result


def test_strip_quoted_reply_clean_body():
    body = "Just a plain message with no quoting."
    assert strip_quoted_reply(body) == body


def test_strip_quoted_reply_earliest_cut_wins():
    # Signature appears before "On ... wrote:" — should cut at signature
    body = "Text\n\n--\nSig\n\nOn Monday, Bob wrote:\n> quote"
    result = strip_quoted_reply(body)
    assert "Text" in result
    assert "On Monday" not in result


# ── escape_special_chars ───────────────────────────────────────────────────────

def test_escape_backslash():
    assert escape_special_chars("a\\b") == "a\\\\b"


def test_escape_newline():
    assert escape_special_chars("a\nb") == "a\\nb"


def test_escape_tab():
    assert escape_special_chars("a\tb") == "a\\tb"


def test_escape_double_quote():
    assert escape_special_chars('say "hi"') == 'say ""hi""'


def test_escape_carriage_return():
    result = escape_special_chars("a\rb")
    assert "\\r" in result


# ── read_prompt_from_file ──────────────────────────────────────────────────────

def test_read_prompt_from_file_found(tmp_prompts, monkeypatch):
    import utils
    monkeypatch.setattr(utils, "PROMPTS_DIR", str(tmp_prompts))
    prompt_file = tmp_prompts / "test_prompt.txt"
    prompt_file.write_text("Hello {name}!")
    result = read_prompt_from_file("test_prompt.txt")
    assert result == "Hello {name}!"


def test_read_prompt_from_file_missing(tmp_prompts, monkeypatch):
    import utils
    monkeypatch.setattr(utils, "PROMPTS_DIR", str(tmp_prompts))
    result = read_prompt_from_file("nonexistent.txt")
    assert result is None
