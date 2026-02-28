import os
import pytest
import frontmatter
from datetime import date
from unittest.mock import patch, MagicMock

from Obsidian.writer import (
    _slugify,
    memory_relpath,
    write_memory,
    write_goal,
    update_goal,
    write_habit,
    write_observation,
    write_knowledge,
    write_pattern,
    LOCK_FILE,
)


# ── _slugify ───────────────────────────────────────────────────────────────────

def test_slugify_lowercases_and_replaces_spaces():
    assert _slugify("Hello World") == "hello-world"


def test_slugify_removes_special_chars():
    assert _slugify("Hello World!") == "hello-world"


def test_slugify_strips_leading_trailing_dashes():
    result = _slugify("  --test--  ")
    assert not result.startswith("-")
    assert not result.endswith("-")
    assert "test" in result


def test_slugify_truncates_to_maxlen():
    long = "a" * 100
    assert len(_slugify(long)) <= 60


def test_slugify_custom_maxlen():
    result = _slugify("hello world example", maxlen=5)
    assert len(result) <= 5


def test_slugify_collapses_consecutive_special_chars():
    result = _slugify("hello & world")
    assert "--" not in result


# ── memory_relpath ─────────────────────────────────────────────────────────────

def test_memory_relpath_daily():
    d = date(2025, 3, 15)
    assert memory_relpath("daily", d) == "Memories/daily/2025-03-15.md"


def test_memory_relpath_weekly():
    d = date(2025, 3, 10)  # Week 10
    result = memory_relpath("weekly", d)
    assert result.startswith("Memories/weekly/2025-W")
    assert result.endswith(".md")


def test_memory_relpath_monthly():
    d = date(2025, 3, 15)
    assert memory_relpath("monthly", d) == "Memories/monthly/2025-03.md"


def test_memory_relpath_quarterly_q1():
    d = date(2025, 1, 1)
    assert memory_relpath("quarterly", d) == "Memories/quarterly/2025-Q1.md"


def test_memory_relpath_quarterly_q2():
    d = date(2025, 4, 1)
    assert memory_relpath("quarterly", d) == "Memories/quarterly/2025-Q2.md"


def test_memory_relpath_quarterly_q3():
    d = date(2025, 7, 1)
    assert memory_relpath("quarterly", d) == "Memories/quarterly/2025-Q3.md"


def test_memory_relpath_quarterly_q4():
    d = date(2025, 10, 1)
    assert memory_relpath("quarterly", d) == "Memories/quarterly/2025-Q4.md"


def test_memory_relpath_yearly():
    d = date(2025, 1, 1)
    assert memory_relpath("yearly", d) == "Memories/yearly/2025.md"


# ── write_memory ───────────────────────────────────────────────────────────────

def test_write_memory_creates_file_with_correct_frontmatter(tmp_vault):
    d = date(2025, 3, 15)
    rel = write_memory("daily", d, d, "Today was great.", 1)
    abs_path = tmp_vault / rel
    assert abs_path.exists()
    post = frontmatter.load(str(abs_path))
    assert post["summary_type"] == "daily"
    assert post["client_id"] == 1
    assert post.content.strip() == "Today was great."


def test_write_memory_returns_relative_path(tmp_vault):
    d = date(2025, 3, 15)
    rel = write_memory("daily", d, d, "content", 1)
    assert not os.path.isabs(rel)
    assert rel.startswith("Memories/daily/")


# ── write_goal ─────────────────────────────────────────────────────────────────

def test_write_goal_creates_file(tmp_vault):
    rel = write_goal("Finish the report", 1, 10)
    abs_path = tmp_vault / rel
    assert abs_path.exists()
    post = frontmatter.load(str(abs_path))
    assert post["status"] == "active"
    assert post["source_email_id"] == 10
    assert post["client_id"] == 1


def test_write_goal_idempotent_first_write_wins(tmp_vault):
    rel1 = write_goal("Finish the report", 1, 10)
    rel2 = write_goal("Finish the report", 1, 99)
    assert rel1 == rel2
    post = frontmatter.load(str(tmp_vault / rel1))
    assert post["source_email_id"] == 10  # first write wins


def test_write_goal_default_status_is_active(tmp_vault):
    rel = write_goal("Exercise daily", 1, 5)
    post = frontmatter.load(str(tmp_vault / rel))
    assert post["status"] == "active"


def test_write_goal_sets_reminder_count_to_zero(tmp_vault):
    rel = write_goal("Read more books", 1, 1)
    post = frontmatter.load(str(tmp_vault / rel))
    assert post["reminder_count"] == 0


# ── update_goal ────────────────────────────────────────────────────────────────

def test_update_goal_merges_fields(tmp_vault):
    write_goal("Lose weight", 1, 5)
    slug = _slugify("Lose weight")
    update_goal(slug, status="completed", reminder_count=3)
    post = frontmatter.load(str(tmp_vault / f"Goals/{slug}.md"))
    assert post["status"] == "completed"
    assert post["reminder_count"] == 3


def test_update_goal_preserves_existing_fields(tmp_vault):
    write_goal("Learn piano", 1, 7)
    slug = _slugify("Learn piano")
    update_goal(slug, status="paused")
    post = frontmatter.load(str(tmp_vault / f"Goals/{slug}.md"))
    assert post["client_id"] == 1  # unchanged
    assert post["status"] == "paused"


def test_update_goal_raises_if_file_missing(tmp_vault):
    with pytest.raises(FileNotFoundError):
        update_goal("nonexistent-goal-slug", status="completed")


# ── write_habit ────────────────────────────────────────────────────────────────

def test_write_habit_creates_file(tmp_vault):
    rel = write_habit("Morning exercise", 1)
    abs_path = tmp_vault / rel
    assert abs_path.exists()
    post = frontmatter.load(str(abs_path))
    assert post["client_id"] == 1
    assert post["status"] == "active"


def test_write_habit_idempotent(tmp_vault):
    rel1 = write_habit("Morning exercise", 1)
    rel2 = write_habit("Morning exercise", 1)
    assert rel1 == rel2


# ── write_observation ──────────────────────────────────────────────────────────

def test_write_observation_creates_file(tmp_vault):
    d = date(2025, 3, 15)
    rel = write_observation("Felt very productive today", d)
    abs_path = tmp_vault / rel
    assert abs_path.exists()


def test_write_observation_path_format(tmp_vault):
    d = date(2025, 3, 15)
    rel = write_observation("Felt very productive today", d)
    assert rel.startswith("Observations/2025-03-15-")
    assert rel.endswith(".md")


def test_write_observation_stores_content(tmp_vault):
    d = date(2025, 3, 15)
    content = "I noticed I work better in the morning."
    rel = write_observation(content, d)
    post = frontmatter.load(str(tmp_vault / rel))
    assert content in post.content


# ── write_knowledge ────────────────────────────────────────────────────────────

def test_write_knowledge_profile_appends(tmp_vault):
    write_knowledge("", "- Uses Python", is_profile=True)
    write_knowledge("", "- Uses Nix", is_profile=True)
    content = (tmp_vault / "Knowledge" / "profile.md").read_text()
    assert "- Uses Python" in content
    assert "- Uses Nix" in content


def test_write_knowledge_profile_does_not_overwrite(tmp_vault):
    write_knowledge("", "- First fact", is_profile=True)
    write_knowledge("", "- Second fact", is_profile=True)
    content = (tmp_vault / "Knowledge" / "profile.md").read_text()
    assert "- First fact" in content


def test_write_knowledge_topic_creates_file(tmp_vault):
    rel = write_knowledge("Nix Flakes", "Nix flakes are reproducible.", is_profile=False)
    abs_path = tmp_vault / rel
    assert abs_path.exists()
    assert rel.startswith("Knowledge/topics/")


def test_write_knowledge_topic_idempotent_first_write_wins(tmp_vault):
    rel1 = write_knowledge("Nix Flakes", "Original content.", is_profile=False)
    rel2 = write_knowledge("Nix Flakes", "Different content.", is_profile=False)
    assert rel1 == rel2
    text = (tmp_vault / rel1).read_text()
    assert "Different content" not in text


def test_write_knowledge_topic_stores_title_in_frontmatter(tmp_vault):
    rel = write_knowledge("Docker Compose", "DC allows multi-container apps.", is_profile=False)
    post = frontmatter.load(str(tmp_vault / rel))
    assert post["title"] == "Docker Compose"


# ── write_pattern ──────────────────────────────────────────────────────────────

def test_write_pattern_creates_file(tmp_vault):
    rel = write_pattern("Exercise and Focus", "They are correlated.")
    abs_path = tmp_vault / rel
    assert abs_path.exists()
    assert rel.startswith("Patterns/")


def test_write_pattern_idempotent_first_write_wins(tmp_vault):
    rel1 = write_pattern("Exercise and Focus", "First content.")
    rel2 = write_pattern("Exercise and Focus", "Different content.")
    assert rel1 == rel2
    text = (tmp_vault / rel1).read_text()
    assert "Different content" not in text


def test_write_pattern_stores_title_in_frontmatter(tmp_vault):
    rel = write_pattern("Sleep and Mood", "Better sleep leads to better mood.")
    post = frontmatter.load(str(tmp_vault / rel))
    assert post["title"] == "Sleep and Mood"
