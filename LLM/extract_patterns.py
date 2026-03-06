import json
import pickle
import re
from Logging import logger_init
from Database import connect_to_dataset
from LLM import OllamaChat, OllamaEmbed
from Obsidian import write_pattern
from utils import read_prompt_from_file, remove_think_blocks, LLM_MODEL, EMB_MODEL

LOGGER = logger_init("LLM")


def extract_and_save_pattern(client_id: int, email_text: str, source_email_id: int = None):
    """
    Extracts a user-identified pattern/connection from an email and writes to vault.
    Idempotent: write_pattern() is a no-op if the slug already exists.
    Embeds the result and upserts vault_index.
    """
    LOGGER.info(f"Starting pattern extraction for client {client_id}")

    email_date = None
    if source_email_id is not None:
        try:
            db_tmp = connect_to_dataset()
            row = db_tmp['emails'].find_one(id=source_email_id)
            if row and row.get('time_received'):
                email_date = row['time_received']
        except Exception:
            pass

    prompt_template = read_prompt_from_file("pattern_extraction_prompt.txt")
    if not prompt_template:
        LOGGER.error("Could not read pattern_extraction_prompt.txt. Aborting.")
        return

    prompt = prompt_template.format(email_text=email_text)

    try:
        llm = OllamaChat(LLM_MODEL)
        llm.init_history([{"role": "system", "content": prompt}])
        response = llm.generate_response()
        if not response:
            LOGGER.warning("Pattern extraction: empty response from LLM.")
            return
        clean = remove_think_blocks(response)
        clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', clean.strip(), flags=re.MULTILINE).strip()
        result = json.loads(clean)
    except json.JSONDecodeError:
        LOGGER.error(f"Pattern extraction: failed to parse JSON. Raw: {response!r}")
        return
    except Exception as e:
        LOGGER.error(f"Pattern extraction LLM call failed: {e}")
        return

    title = result.get("title")
    content = result.get("content", "").strip()
    if not title or not content:
        LOGGER.info("No clear pattern detected in email.")
        return

    try:
        rel_path = write_pattern(title, content, email_date=email_date)
        LOGGER.info(f"Wrote pattern to vault: {rel_path}")
    except Exception as e:
        LOGGER.error(f"Could not write pattern to vault: {e}")
        return

    try:
        emb = OllamaEmbed(EMB_MODEL)
        embedding = emb.embed(content)
        if embedding is None:
            return
        db = connect_to_dataset()
        db['vault_index'].upsert(dict(
            file_path=rel_path,
            file_type='pattern',
            client_id=client_id,
            model=EMB_MODEL,
            embedding=pickle.dumps(embedding),
        ), ['file_path'])
        LOGGER.debug(f"Upserted vault_index for {rel_path}")
    except Exception as e:
        LOGGER.error(f"Could not upsert vault_index for pattern: {e}")
