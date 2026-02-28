import numpy as np
import pytest
from unittest.mock import patch, MagicMock, call


@patch("LLM.extract_knowledge.connect_to_dataset")
@patch("LLM.extract_knowledge.write_knowledge")
@patch("LLM.extract_knowledge.OllamaEmbed")
@patch("LLM.extract_knowledge.OllamaChat")
@patch("LLM.extract_knowledge.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_profile_fact_calls_write_knowledge_is_profile(
    mock_prompt, mock_llm_cls, mock_emb_cls, mock_wk, mock_db_cls
):
    mock_llm_cls.return_value.generate_response.return_value = (
        '{"type": "profile", "content": "- Uses Python"}'
    )
    mock_emb_cls.return_value.embed.return_value = np.array([0.1, 0.2])
    mock_db_cls.return_value.__getitem__.return_value.upsert = MagicMock()

    from LLM.extract_knowledge import extract_and_save_knowledge
    extract_and_save_knowledge(1, "I use Python daily", 42)

    mock_wk.assert_called_once_with("knowledge-note", "- Uses Python", is_profile=True)


@patch("LLM.extract_knowledge.connect_to_dataset")
@patch("LLM.extract_knowledge.write_knowledge")
@patch("LLM.extract_knowledge.OllamaEmbed")
@patch("LLM.extract_knowledge.OllamaChat")
@patch("LLM.extract_knowledge.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_topic_note_calls_write_knowledge_not_profile(
    mock_prompt, mock_llm_cls, mock_emb_cls, mock_wk, mock_db_cls
):
    mock_llm_cls.return_value.generate_response.return_value = (
        '{"type": "topic", "title": "Nix Flakes", "content": "Nix flakes are reproducible."}'
    )
    mock_emb_cls.return_value.embed.return_value = np.array([0.1])
    mock_db_cls.return_value.__getitem__.return_value.upsert = MagicMock()

    from LLM.extract_knowledge import extract_and_save_knowledge
    extract_and_save_knowledge(1, "Let me tell you about Nix flakes", 5)

    mock_wk.assert_called_once_with("Nix Flakes", "Nix flakes are reproducible.", is_profile=False)


@patch("LLM.extract_knowledge.write_knowledge")
@patch("LLM.extract_knowledge.OllamaChat")
@patch("LLM.extract_knowledge.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_type_none_does_not_write(mock_prompt, mock_llm_cls, mock_wk):
    mock_llm_cls.return_value.generate_response.return_value = '{"type": "none"}'

    from LLM.extract_knowledge import extract_and_save_knowledge
    extract_and_save_knowledge(1, "Just saying hi!", 1)

    mock_wk.assert_not_called()


@patch("LLM.extract_knowledge.write_knowledge")
@patch("LLM.extract_knowledge.OllamaChat")
@patch("LLM.extract_knowledge.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_empty_content_does_not_write(mock_prompt, mock_llm_cls, mock_wk):
    mock_llm_cls.return_value.generate_response.return_value = (
        '{"type": "profile", "content": ""}'
    )

    from LLM.extract_knowledge import extract_and_save_knowledge
    extract_and_save_knowledge(1, "message", 1)

    mock_wk.assert_not_called()


@patch("LLM.extract_knowledge.write_knowledge")
@patch("LLM.extract_knowledge.OllamaChat")
@patch("LLM.extract_knowledge.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_llm_returns_none_no_crash(mock_prompt, mock_llm_cls, mock_wk):
    mock_llm_cls.return_value.generate_response.return_value = None

    from LLM.extract_knowledge import extract_and_save_knowledge
    # Should not raise
    extract_and_save_knowledge(1, "message", 1)
    mock_wk.assert_not_called()


@patch("LLM.extract_knowledge.write_knowledge")
@patch("LLM.extract_knowledge.OllamaChat")
@patch("LLM.extract_knowledge.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_json_decode_error_no_crash(mock_prompt, mock_llm_cls, mock_wk):
    mock_llm_cls.return_value.generate_response.return_value = "not valid json"

    from LLM.extract_knowledge import extract_and_save_knowledge
    extract_and_save_knowledge(1, "message", 1)
    mock_wk.assert_not_called()


@patch("LLM.extract_knowledge.OllamaChat")
@patch("LLM.extract_knowledge.read_prompt_from_file", return_value=None)
def test_missing_prompt_file_early_return(mock_prompt, mock_llm_cls):
    from LLM.extract_knowledge import extract_and_save_knowledge
    extract_and_save_knowledge(1, "message", 1)
    mock_llm_cls.assert_not_called()


@patch("LLM.extract_knowledge.connect_to_dataset")
@patch("LLM.extract_knowledge.write_knowledge", return_value="Knowledge/profile.md")
@patch("LLM.extract_knowledge.OllamaEmbed")
@patch("LLM.extract_knowledge.OllamaChat")
@patch("LLM.extract_knowledge.read_prompt_from_file", return_value="Prompt: {email_text}")
def test_embed_none_skips_vault_index_upsert(
    mock_prompt, mock_llm_cls, mock_emb_cls, mock_wk, mock_db_cls
):
    mock_llm_cls.return_value.generate_response.return_value = (
        '{"type": "profile", "content": "- Uses Python"}'
    )
    mock_emb_cls.return_value.embed.return_value = None
    mock_table = MagicMock()
    mock_db_cls.return_value.__getitem__.return_value = mock_table

    from LLM.extract_knowledge import extract_and_save_knowledge
    extract_and_save_knowledge(1, "message", 1)

    mock_table.upsert.assert_not_called()
