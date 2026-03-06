import numpy as np
import pytest
from unittest.mock import patch, MagicMock


@patch("LLM.extract_patterns.connect_to_dataset")
@patch("LLM.extract_patterns.write_pattern")
@patch("LLM.extract_patterns.OllamaEmbed")
@patch("LLM.extract_patterns.OllamaChat")
@patch("LLM.extract_patterns.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_clear_pattern_calls_write_pattern(
    mock_prompt, mock_llm_cls, mock_emb_cls, mock_wp, mock_db_cls
):
    mock_llm_cls.return_value.generate_response.return_value = (
        '{"title": "Exercise and Focus", "content": "They are strongly correlated."}'
    )
    mock_emb_cls.return_value.embed.return_value = np.array([0.1])
    mock_wp.return_value = "Patterns/exercise-and-focus.md"
    mock_table = MagicMock()
    mock_table.find_one.return_value = None
    mock_db_cls.return_value.__getitem__.return_value = mock_table

    from LLM.extract_patterns import extract_and_save_pattern
    extract_and_save_pattern(1, "I notice I focus better after exercise")

    mock_wp.assert_called_once_with("Exercise and Focus", "They are strongly correlated.", email_date=None)


@patch("LLM.extract_patterns.write_pattern")
@patch("LLM.extract_patterns.OllamaChat")
@patch("LLM.extract_patterns.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_null_title_does_not_write(mock_prompt, mock_llm_cls, mock_wp):
    mock_llm_cls.return_value.generate_response.return_value = (
        '{"title": null, "content": "some content"}'
    )

    from LLM.extract_patterns import extract_and_save_pattern
    extract_and_save_pattern(1, "message")

    mock_wp.assert_not_called()


@patch("LLM.extract_patterns.write_pattern")
@patch("LLM.extract_patterns.OllamaChat")
@patch("LLM.extract_patterns.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_missing_title_key_does_not_write(mock_prompt, mock_llm_cls, mock_wp):
    mock_llm_cls.return_value.generate_response.return_value = '{"content": "some content"}'

    from LLM.extract_patterns import extract_and_save_pattern
    extract_and_save_pattern(1, "message")

    mock_wp.assert_not_called()


@patch("LLM.extract_patterns.write_pattern")
@patch("LLM.extract_patterns.OllamaChat")
@patch("LLM.extract_patterns.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_empty_content_does_not_write(mock_prompt, mock_llm_cls, mock_wp):
    mock_llm_cls.return_value.generate_response.return_value = (
        '{"title": "Some Pattern", "content": ""}'
    )

    from LLM.extract_patterns import extract_and_save_pattern
    extract_and_save_pattern(1, "message")

    mock_wp.assert_not_called()


@patch("LLM.extract_patterns.write_pattern")
@patch("LLM.extract_patterns.OllamaChat")
@patch("LLM.extract_patterns.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_llm_returns_none_no_crash(mock_prompt, mock_llm_cls, mock_wp):
    mock_llm_cls.return_value.generate_response.return_value = None

    from LLM.extract_patterns import extract_and_save_pattern
    extract_and_save_pattern(1, "message")
    mock_wp.assert_not_called()


@patch("LLM.extract_patterns.write_pattern")
@patch("LLM.extract_patterns.OllamaChat")
@patch("LLM.extract_patterns.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_json_decode_error_no_crash(mock_prompt, mock_llm_cls, mock_wp):
    mock_llm_cls.return_value.generate_response.return_value = "not json"

    from LLM.extract_patterns import extract_and_save_pattern
    extract_and_save_pattern(1, "message")
    mock_wp.assert_not_called()


@patch("LLM.extract_patterns.OllamaChat")
@patch("LLM.extract_patterns.read_prompt_from_file", return_value=None)
def test_missing_prompt_early_return(mock_prompt, mock_llm_cls):
    from LLM.extract_patterns import extract_and_save_pattern
    extract_and_save_pattern(1, "message")
    mock_llm_cls.assert_not_called()


@patch("LLM.extract_patterns.connect_to_dataset")
@patch("LLM.extract_patterns.write_pattern", return_value="Patterns/test.md")
@patch("LLM.extract_patterns.OllamaEmbed")
@patch("LLM.extract_patterns.OllamaChat")
@patch("LLM.extract_patterns.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_embed_none_skips_vault_index_upsert(
    mock_prompt, mock_llm_cls, mock_emb_cls, mock_wp, mock_db_cls
):
    mock_llm_cls.return_value.generate_response.return_value = (
        '{"title": "Pattern A", "content": "Description."}'
    )
    mock_emb_cls.return_value.embed.return_value = None
    mock_table = MagicMock()
    mock_db_cls.return_value.__getitem__.return_value = mock_table

    from LLM.extract_patterns import extract_and_save_pattern
    extract_and_save_pattern(1, "message")

    mock_table.upsert.assert_not_called()
