import json
import pickle
from Logging import logger_init
from Database import connect_to_dataset
from LLM import OllamaChat, OllamaEmbed
from Obsidian import write_knowledge
from utils import read_prompt_from_file, remove_think_blocks, LLM_MODEL, EMB_MODEL

LOGGER = logger_init("LLM")


def extract_and_save_knowledge(client_id: int, email_text: str, source_email_id: int):
    """
    Extracts knowledge from an email and writes to vault.
    Profile facts → Knowledge/profile.md (append)
    Topic notes   → Knowledge/topics/<slug>.md (create-once)
    Embeds the result and upserts vault_index.
    """
    LOGGER.info(f"Starting knowledge extraction for client {client_id}")

    prompt_template = read_prompt_from_file("knowledge_extraction_prompt.txt")
    if not prompt_template:
        LOGGER.error("Could not read knowledge_extraction_prompt.txt. Aborting.")
        return

    prompt = prompt_template.format(email_text=email_text)

    try:
        llm = OllamaChat(LLM_MODEL)
        llm.init_history([{"role": "system", "content": prompt}])
        response = llm.generate_response()
        clean = remove_think_blocks(response)
        result = json.loads(clean.strip())
    except json.JSONDecodeError:
        LOGGER.error(f"Knowledge extraction: failed to parse JSON. Raw: {response!r}")
        return
    except Exception as e:
        LOGGER.error(f"Knowledge extraction LLM call failed: {e}")
        return

    kind = result.get("type")
    if kind == "none" or not kind:
        LOGGER.info("No knowledge worth storing detected.")
        return

    is_profile = (kind == "profile")
    title = result.get("title", "knowledge-note")
    content = result.get("content", "").strip()
    if not content:
        LOGGER.warning("Knowledge extraction returned empty content.")
        return

    try:
        rel_path = write_knowledge(title, content, is_profile=is_profile)
        LOGGER.info(f"Wrote knowledge to vault: {rel_path}")
    except Exception as e:
        LOGGER.error(f"Could not write knowledge to vault: {e}")
        return

    # Embed and upsert vault_index (profile.md gets upserted each time it's updated)
    try:
        emb = OllamaEmbed(EMB_MODEL)
        embedding = emb.embed(content)
        if embedding is None:
            return
        db = connect_to_dataset()
        db['vault_index'].upsert(dict(
            file_path=rel_path,
            file_type='profile' if is_profile else 'knowledge',
            client_id=client_id,
            model=EMB_MODEL,
            embedding=pickle.dumps(embedding),
        ), ['file_path'])
        LOGGER.debug(f"Upserted vault_index for {rel_path}")
    except Exception as e:
        LOGGER.error(f"Could not upsert vault_index for knowledge: {e}")
