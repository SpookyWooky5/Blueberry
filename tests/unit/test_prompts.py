"""
test_prompts.py — Validate that every prompt file exists and is correctly
                  formatted (all required template variables present).

Tests run against the REAL prompt files in the repo's prompts/ directory,
not the temp mock directory used by other tests. This ensures that:
  1. All prompt files exist in the repo.
  2. Every prompt can be str.format()-ed with its expected variables
     without raising a KeyError (missing placeholder) or IndexError.
  3. The prompt content is non-empty.
"""
import os
import pytest

# Resolve the repo's actual prompts directory relative to this test file.
# tests/unit/test_prompts.py -> tests/ -> repo_root -> prompts/
_REPO_ROOT   = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
PROMPTS_DIR  = os.path.join(_REPO_ROOT, "prompts")


def _read(filename: str) -> str:
    path = os.path.join(PROMPTS_DIR, filename)
    assert os.path.isfile(path), f"Prompt file missing: {path}"
    content = open(path, encoding="utf-8").read()
    assert content.strip(), f"Prompt file is empty: {filename}"
    return content


# ── mail_prompt.txt ────────────────────────────────────────────────────────────

def test_mail_prompt_exists_and_formats():
    tmpl = _read("mail_prompt.txt")
    result = tmpl.format(
        context="[ACTIVE GOALS]\n- Finish report",
        client_name="Alice",
        current_email="Hey, just checking in!",
    )
    assert "Alice" in result
    assert "checking in" in result


def test_mail_prompt_formats_with_empty_context():
    tmpl = _read("mail_prompt.txt")
    result = tmpl.format(context="", client_name="Bob", current_email="Hello!")
    assert "Bob" in result


# ── summary_prompt.txt ─────────────────────────────────────────────────────────

def test_summary_prompt_exists_and_formats():
    tmpl = _read("summary_prompt.txt")
    result = tmpl.format(
        client_name="Alice",
        today="Mon, 03 March",
        summary_type="daily",
        header="Daily Summary for Alice",
        content="[EMAIL]\nSubject: Test\nBody: ...\n[/EMAIL]",
    )
    assert "Alice" in result
    assert "daily" in result
    assert "Daily Summary for Alice" in result


# ── goal_extraction_prompt.txt ─────────────────────────────────────────────────

def test_goal_extraction_prompt_exists_and_formats():
    tmpl = _read("goal_extraction_prompt.txt")
    result = tmpl.format(
        conversation_text="User: I need to finish the budget by Friday.\nAssistant: Got it."
    )
    assert "budget" in result
    # Must instruct LLM to return JSON
    assert "JSON" in result


# ── proactive_checkin_prompt.txt ───────────────────────────────────────────────

def test_proactive_checkin_prompt_exists_and_formats():
    tmpl = _read("proactive_checkin_prompt.txt")
    result = tmpl.format(
        client_name="Alice",
        goals_list="- Finish the report\n- Exercise daily",
        memory_context="Last week was busy with the Q3 review.",
    )
    assert "Alice" in result
    assert "Finish the report" in result


# ── reminder_prompt.txt ────────────────────────────────────────────────────────

def test_reminder_prompt_exists_and_formats():
    tmpl = _read("reminder_prompt.txt")
    result = tmpl.format(
        client_name="Alice",
        goal_text="Finish the budget spreadsheet",
        habit_line="Habit area: work.",
        deadline_line="Their deadline was 2025-03-01.",
        reminder_count=2,
    )
    assert "Alice" in result
    assert "Finish the budget spreadsheet" in result
    assert "2" in result


def test_reminder_prompt_formats_with_empty_optional_lines():
    """habit_line and deadline_line can be empty strings (no habit/deadline set)."""
    tmpl = _read("reminder_prompt.txt")
    result = tmpl.format(
        client_name="Bob",
        goal_text="Read one book per month",
        habit_line="",
        deadline_line="",
        reminder_count=1,
    )
    assert "Bob" in result
    assert "Read one book per month" in result


# ── habit_inference_prompt.txt ─────────────────────────────────────────────────

def test_habit_inference_prompt_exists_and_formats():
    tmpl = _read("habit_inference_prompt.txt")
    result = tmpl.format(
        existing_habits="fitness, reading",
        goals_list="- Go to the gym 3x per week\n- Run a 5K",
    )
    assert "fitness" in result
    assert "gym" in result
    # Must instruct LLM to return JSON
    assert "JSON" in result


def test_habit_inference_prompt_formats_with_no_existing_habits():
    tmpl = _read("habit_inference_prompt.txt")
    result = tmpl.format(
        existing_habits="none",
        goals_list="- Learn Rust",
    )
    assert "none" in result


# ── knowledge_extraction_prompt.txt ───────────────────────────────────────────

def test_knowledge_extraction_prompt_exists_and_formats():
    tmpl = _read("knowledge_extraction_prompt.txt")
    result = tmpl.format(email_text="I switched to NixOS last month.")
    assert "NixOS" in result
    assert "JSON" in result


# ── pattern_extraction_prompt.txt ─────────────────────────────────────────────

def test_pattern_extraction_prompt_exists_and_formats():
    tmpl = _read("pattern_extraction_prompt.txt")
    result = tmpl.format(
        email_text="I've noticed I always procrastinate on creative work when stressed."
    )
    assert "procrastinate" in result
    assert "JSON" in result


# ── pattern_detection_prompt.txt ──────────────────────────────────────────────

def test_pattern_detection_prompt_exists_and_formats():
    tmpl = _read("pattern_detection_prompt.txt")
    result = tmpl.format(
        summary_type="monthly",
        summary_text="This month had a lot of late nights and missed gym sessions.",
    )
    assert "monthly" in result
    assert "late nights" in result


# ── classify_prompt.txt ────────────────────────────────────────────────────────

def test_classify_prompt_exists_and_is_valid():
    content = _read("classify_prompt.txt")
    assert "casual" in content
    assert "goal_set" in content
    assert "JSON" in content
    # Should have no template variables — email content goes in the user message
    assert "{subject}" not in content
    assert "{body}" not in content


# ── Integration: read_prompt_from_file with real prompts dir ──────────────────

def test_read_prompt_from_file_reads_real_prompts(monkeypatch):
    """read_prompt_from_file() should return the real prompt content when
    PROMPTS_DIR is pointed at the repo's prompts/ directory."""
    import utils
    monkeypatch.setattr(utils, "PROMPTS_DIR", PROMPTS_DIR)

    from utils import read_prompt_from_file
    content = read_prompt_from_file("mail_prompt.txt")
    assert content is not None
    assert "{client_name}" in content
    assert "{current_email}" in content
    assert "{context}" in content


def test_read_prompt_from_file_returns_none_for_missing(monkeypatch):
    import utils
    monkeypatch.setattr(utils, "PROMPTS_DIR", PROMPTS_DIR)

    from utils import read_prompt_from_file
    assert read_prompt_from_file("totally_nonexistent_file.txt") is None


def test_all_prompt_files_are_present():
    """Smoke test: every prompt file the code tries to load must exist."""
    required = [
        "mail_prompt.txt",
        "summary_prompt.txt",
        "goal_extraction_prompt.txt",
        "proactive_checkin_prompt.txt",
        "reminder_prompt.txt",
        "habit_inference_prompt.txt",
        "knowledge_extraction_prompt.txt",
        "pattern_extraction_prompt.txt",
        "pattern_detection_prompt.txt",
        "classify_prompt.txt",
    ]
    missing = [f for f in required if not os.path.isfile(os.path.join(PROMPTS_DIR, f))]
    assert missing == [], f"Missing prompt files: {missing}"
