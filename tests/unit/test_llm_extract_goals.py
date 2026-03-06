import pytest
import numpy as np
from unittest.mock import patch, MagicMock

_TWO_GOALS = '[{"goal": "Goal A", "context": "ctx A"}, {"goal": "Goal B", "context": "ctx B"}]'
_ONE_GOAL  = '[{"goal": "Goal A", "context": "ctx A"}]'


def _mock_db_no_existing_goals():
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find.return_value = []
    mock_db.__getitem__.return_value.find_one.return_value = None
    return mock_db


@patch("LLM.extract_goals.infer_and_save_habit")
@patch("LLM.extract_goals.write_goal", return_value="Goals/goal-a.md")
@patch("LLM.extract_goals.OllamaEmbed")
@patch("LLM.extract_goals.connect_to_dataset")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_two_valid_goals_inserted_and_written(
    mock_prompt, mock_llm_cls, mock_db_cls, mock_emb_cls, mock_wg, mock_habit
):
    mock_llm_cls.return_value.generate_response.return_value = _TWO_GOALS
    mock_db = _mock_db_no_existing_goals()
    mock_db_cls.return_value = mock_db
    mock_emb_cls.return_value.embed.return_value = np.array([0.1, 0.2, 0.3])

    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "User: I want Goal A and Goal B", 10)

    assert mock_db.__getitem__.return_value.insert_ignore.call_count == 2
    assert mock_wg.call_count == 2
    assert mock_habit.call_count == 2  # once per goal


@patch("LLM.extract_goals.infer_and_save_habit")
@patch("LLM.extract_goals.write_goal")
@patch("LLM.extract_goals.OllamaEmbed")
@patch("LLM.extract_goals.connect_to_dataset")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_empty_list_no_db_inserts_no_habit(
    mock_prompt, mock_llm_cls, mock_db_cls, mock_emb_cls, mock_wg, mock_habit
):
    mock_llm_cls.return_value.generate_response.return_value = "[]"
    mock_db = _mock_db_no_existing_goals()
    mock_db_cls.return_value = mock_db
    mock_emb_cls.return_value.embed.return_value = np.array([0.1, 0.2, 0.3])

    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "Just chatting", 10)

    mock_db.__getitem__.return_value.insert_ignore.assert_not_called()
    mock_wg.assert_not_called()
    mock_habit.assert_not_called()


@patch("LLM.extract_goals.write_goal")
@patch("LLM.extract_goals.OllamaEmbed")
@patch("LLM.extract_goals.connect_to_dataset")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_non_list_response_warns_and_returns(
    mock_prompt, mock_llm_cls, mock_db_cls, mock_emb_cls, mock_wg
):
    mock_llm_cls.return_value.generate_response.return_value = '"just a string"'
    mock_db_cls.return_value = _mock_db_no_existing_goals()
    mock_emb_cls.return_value.embed.return_value = np.array([0.1])

    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "message", 1)

    mock_wg.assert_not_called()


@patch("LLM.extract_goals.write_goal")
@patch("LLM.extract_goals.OllamaEmbed")
@patch("LLM.extract_goals.connect_to_dataset")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_json_decode_error_early_return(
    mock_prompt, mock_llm_cls, mock_db_cls, mock_emb_cls, mock_wg
):
    mock_llm_cls.return_value.generate_response.return_value = "not json at all"
    mock_db_cls.return_value = _mock_db_no_existing_goals()
    mock_emb_cls.return_value.embed.return_value = np.array([0.1])

    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "message", 1)

    mock_wg.assert_not_called()


@patch("LLM.extract_goals.infer_and_save_habit")
@patch("LLM.extract_goals.write_goal")
@patch("LLM.extract_goals.OllamaEmbed")
@patch("LLM.extract_goals.connect_to_dataset")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_db_error_triggers_rollback(
    mock_prompt, mock_llm_cls, mock_db_cls, mock_emb_cls, mock_wg, mock_habit
):
    mock_llm_cls.return_value.generate_response.return_value = _ONE_GOAL
    mock_db = _mock_db_no_existing_goals()
    mock_db.__getitem__.return_value.insert_ignore.side_effect = Exception("DB error")
    mock_db_cls.return_value = mock_db
    mock_emb_cls.return_value.embed.return_value = np.array([0.1])

    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "message", 1)

    mock_db.rollback.assert_called_once()


@patch("LLM.extract_goals.OllamaEmbed")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value=None)
def test_missing_prompt_file_early_return(mock_prompt, mock_llm_cls, mock_emb_cls):
    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "message", 1)
    mock_llm_cls.assert_not_called()


@patch("LLM.extract_goals.infer_and_save_habit")
@patch("LLM.extract_goals.write_goal")
@patch("LLM.extract_goals.OllamaEmbed")
@patch("LLM.extract_goals.connect_to_dataset")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_write_goal_exception_continues(
    mock_prompt, mock_llm_cls, mock_db_cls, mock_emb_cls, mock_wg, mock_habit
):
    mock_llm_cls.return_value.generate_response.return_value = _TWO_GOALS
    mock_db = _mock_db_no_existing_goals()
    mock_db_cls.return_value = mock_db
    mock_emb_cls.return_value.embed.return_value = np.array([0.1, 0.2, 0.3])
    mock_wg.side_effect = Exception("vault error")

    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "message", 1)

    assert mock_wg.call_count == 2  # tried both goals despite errors


@patch("LLM.extract_goals.infer_and_save_habit")
@patch("LLM.extract_goals.write_goal", return_value="Goals/goal-a.md")
@patch("LLM.extract_goals.OllamaEmbed")
@patch("LLM.extract_goals.connect_to_dataset")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_duplicate_goal_skipped(
    mock_prompt, mock_llm_cls, mock_db_cls, mock_emb_cls, mock_wg, mock_habit
):
    """A goal with cosine similarity >= 0.85 to existing should not be inserted."""
    import pickle
    mock_llm_cls.return_value.generate_response.return_value = _ONE_GOAL
    existing_vec = np.array([1.0, 0.0, 0.0])
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find.return_value = [
        {"file_type": "goal", "client_id": 1,
         "embedding": pickle.dumps(existing_vec)}
    ]
    mock_db.__getitem__.return_value.find_one.return_value = None
    mock_db_cls.return_value = mock_db
    # New goal is nearly identical to existing
    mock_emb_cls.return_value.embed.return_value = np.array([1.0, 0.0, 0.0])

    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "message", 1)

    mock_db.__getitem__.return_value.insert_ignore.assert_not_called()
    mock_wg.assert_not_called()
