import pytest
from unittest.mock import MagicMock
from LLM.classify import classify_email


@pytest.fixture()
def llm():
    return MagicMock()


def test_classify_valid_json(llm):
    llm.generate_response.return_value = '{"labels": ["goal_set"], "tags": ["project"]}'
    result = classify_email(llm, "Subject", "I want to finish the report")
    assert result["labels"] == ["goal_set"]
    assert result["tags"] == ["project"]


def test_classify_none_response_defaults_to_casual(llm):
    llm.generate_response.return_value = None
    result = classify_email(llm, "Hi", "What's up?")
    assert result == {"labels": ["casual"], "tags": []}


def test_classify_invalid_json_defaults_to_casual(llm):
    llm.generate_response.return_value = "not valid json"
    result = classify_email(llm, "Hi", "msg")
    assert result == {"labels": ["casual"], "tags": []}


def test_classify_missing_labels_key_defaults_to_casual(llm):
    llm.generate_response.return_value = '{"tags": ["work"]}'
    result = classify_email(llm, "Hi", "msg")
    assert result == {"labels": ["casual"], "tags": []}


def test_classify_markdown_fenced_json(llm):
    llm.generate_response.return_value = (
        "```\n{\"labels\": [\"emotional\"], \"tags\": [\"stress\"]}\n```"
    )
    result = classify_email(llm, "Subject", "body")
    assert result["labels"] == ["emotional"]


def test_classify_json_prefix_after_fence(llm):
    llm.generate_response.return_value = (
        "```json\n{\"labels\": [\"knowledge\"], \"tags\": [\"tech\"]}\n```"
    )
    result = classify_email(llm, "Subject", "body")
    assert result["labels"] == ["knowledge"]


def test_classify_multiple_labels(llm):
    llm.generate_response.return_value = (
        '{"labels": ["emotional", "goal_set"], "tags": ["work", "stress"]}'
    )
    result = classify_email(llm, "Subject", "body")
    assert "emotional" in result["labels"]
    assert "goal_set" in result["labels"]


def test_classify_sets_history_on_llm(llm):
    llm.generate_response.return_value = '{"labels": ["casual"], "tags": []}'
    classify_email(llm, "Subj", "Body")
    llm.init_history.assert_called_once()
    call_args = llm.init_history.call_args[0][0]
    assert any(m["role"] == "system" for m in call_args)
    assert any(m["role"] == "user" for m in call_args)
