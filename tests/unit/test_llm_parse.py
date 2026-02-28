import pytest
from LLM.parse import parse, remove_commands, parse_remember, parse_embeds, DEFAULT_CONTEXT_CONFIG


# ── remove_commands ────────────────────────────────────────────────────────────

def test_remove_commands_strips_inline_command():
    result = remove_commands("hello /remember[T] world")
    assert "/remember" not in result
    assert "hello" in result
    assert "world" in result


def test_remove_commands_no_command():
    assert remove_commands("plain text") == "plain text"


def test_remove_commands_multiple():
    result = remove_commands("/remember[T] /embeds[F,3] message")
    assert "/remember" not in result
    assert "/embeds" not in result
    assert "message" in result


# ── parse ──────────────────────────────────────────────────────────────────────

def test_parse_no_commands_returns_defaults():
    config = parse("hello world")
    assert config["remember"]["enable"] == DEFAULT_CONTEXT_CONFIG["remember"]["enable"]
    assert config["embeds"]["enable"] == DEFAULT_CONTEXT_CONFIG["embeds"]["enable"]


def test_parse_remember_disable():
    config = parse("/remember[F]")
    assert config["remember"]["enable"] is False


def test_parse_remember_daily_and_weekly():
    config = parse("/remember[2D,1W]")
    assert config["remember"]["time_filters"]["daily"] == 2
    assert config["remember"]["time_filters"]["weekly"] == 1


def test_parse_embeds_enable_with_topk():
    config = parse("/embeds[T,5]")
    assert config["embeds"]["enable"] is True
    assert config["embeds"]["topk"] == 5


def test_parse_embeds_disable():
    config = parse("/embeds[F,0]")
    assert config["embeds"]["enable"] is False


def test_parse_unknown_command_returns_defaults():
    config = parse("/unknown[xyz]")
    # Should fall through to defaults (warning logged but not error)
    assert config["remember"]["enable"] == DEFAULT_CONTEXT_CONFIG["remember"]["enable"]


# ── parse_remember ─────────────────────────────────────────────────────────────

def test_parse_remember_T_enables():
    config = parse_remember(["remember", "T"])
    assert config["enable"] is True


def test_parse_remember_F_disables():
    config = parse_remember(["remember", "F"])
    assert config["enable"] is False


def test_parse_remember_TE_today_emails_true():
    config = parse_remember(["remember", "TE"])
    assert config["today_emails"] is True


def test_parse_remember_FE_today_emails_false():
    config = parse_remember(["remember", "FE"])
    assert config["today_emails"] is False


def test_parse_remember_quarterly():
    config = parse_remember(["remember", "3Q"])
    assert config["time_filters"]["quarterly"] == 3


def test_parse_remember_monthly():
    config = parse_remember(["remember", "2M"])
    assert config["time_filters"]["monthly"] == 2


def test_parse_remember_invalid_arg_leaves_defaults():
    config = parse_remember(["remember", "ZZ"])
    assert config["time_filters"] == DEFAULT_CONTEXT_CONFIG["remember"]["time_filters"]


# ── parse_embeds ───────────────────────────────────────────────────────────────

def test_parse_embeds_empty_args_returns_defaults():
    config = parse_embeds(["embeds"])
    assert config == DEFAULT_CONTEXT_CONFIG["embeds"]


def test_parse_embeds_TRUE_string():
    config = parse_embeds(["embeds", "TRUE"])
    assert config["enable"] is True


def test_parse_embeds_FALSE_string():
    config = parse_embeds(["embeds", "FALSE"])
    assert config["enable"] is False


def test_parse_embeds_topk():
    config = parse_embeds(["embeds", "T", "7"])
    assert config["topk"] == 7
