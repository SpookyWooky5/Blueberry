import pytest
from unittest.mock import patch, MagicMock, call


@patch("LLM.extract_goals.infer_and_save_habit")
@patch("LLM.extract_goals.write_goal")
@patch("LLM.extract_goals.connect_to_dataset")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_two_valid_goals_inserted_and_written(
    mock_prompt, mock_llm_cls, mock_db_cls, mock_wg, mock_habit
):
    mock_llm_cls.return_value.generate_response.return_value = '["Goal A", "Goal B"]'
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.insert_ignore = MagicMock()
    mock_db_cls.return_value = mock_db

    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "User: I want Goal A and Goal B", 10)

    assert mock_db.__getitem__.return_value.insert_ignore.call_count == 2
    assert mock_wg.call_count == 2
    mock_habit.assert_called_once()


@patch("LLM.extract_goals.infer_and_save_habit")
@patch("LLM.extract_goals.write_goal")
@patch("LLM.extract_goals.connect_to_dataset")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_empty_list_no_db_inserts_no_habit(
    mock_prompt, mock_llm_cls, mock_db_cls, mock_wg, mock_habit
):
    mock_llm_cls.return_value.generate_response.return_value = "[]"
    mock_db = MagicMock()
    mock_db_cls.return_value = mock_db

    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "Just chatting", 10)

    mock_db.__getitem__.return_value.insert_ignore.assert_not_called()
    mock_wg.assert_not_called()
    mock_habit.assert_not_called()


@patch("LLM.extract_goals.write_goal")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_non_list_response_warns_and_returns(mock_prompt, mock_llm_cls, mock_wg):
    mock_llm_cls.return_value.generate_response.return_value = '"just a string"'

    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "message", 1)

    mock_wg.assert_not_called()


@patch("LLM.extract_goals.write_goal")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_json_decode_error_early_return(mock_prompt, mock_llm_cls, mock_wg):
    mock_llm_cls.return_value.generate_response.return_value = "not json at all"

    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "message", 1)

    mock_wg.assert_not_called()


@patch("LLM.extract_goals.infer_and_save_habit")
@patch("LLM.extract_goals.write_goal")
@patch("LLM.extract_goals.connect_to_dataset")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_db_error_triggers_rollback(
    mock_prompt, mock_llm_cls, mock_db_cls, mock_wg, mock_habit
):
    mock_llm_cls.return_value.generate_response.return_value = '["Goal A"]'
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.insert_ignore.side_effect = Exception("DB error")
    mock_db_cls.return_value = mock_db

    from LLM.extract_goals import extract_and_save_goals
    # Should not raise
    extract_and_save_goals(1, "message", 1)

    mock_db.rollback.assert_called_once()


@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value=None)
def test_missing_prompt_file_early_return(mock_prompt, mock_llm_cls):
    from LLM.extract_goals import extract_and_save_goals
    extract_and_save_goals(1, "message", 1)
    mock_llm_cls.assert_not_called()


@patch("LLM.extract_goals.infer_and_save_habit")
@patch("LLM.extract_goals.write_goal")
@patch("LLM.extract_goals.connect_to_dataset")
@patch("LLM.extract_goals.OllamaChat")
@patch("LLM.extract_goals.read_prompt_from_file", return_value="Prompt: {conversation_text}")
def test_write_goal_exception_continues(
    mock_prompt, mock_llm_cls, mock_db_cls, mock_wg, mock_habit
):
    mock_llm_cls.return_value.generate_response.return_value = '["Goal A", "Goal B"]'
    mock_db = MagicMock()
    mock_db_cls.return_value = mock_db
    mock_wg.side_effect = Exception("vault error")

    from LLM.extract_goals import extract_and_save_goals
    # Should not propagate the exception
    extract_and_save_goals(1, "message", 1)

    assert mock_wg.call_count == 2  # tried both goals despite errors
