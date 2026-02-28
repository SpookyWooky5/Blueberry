# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 28-FEB-2026  Initial Draft — email classification module
# ============================================================================ #

# ================================== IMPORTS ================================= #
import json

from Logging import logger_init
from LLM.main import OllamaChat
from utils import read_prompt_from_file

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")

# ================================= FUNCTIONS ================================ #
def classify_email(llm: OllamaChat, subject: str, body: str) -> dict:
    """
    Classifies an email into structural labels and semantic tags.

    Returns {"labels": [...], "tags": [...]}
    labels: one or more from the fixed structural set
    tags: dynamic semantic tags describing the email content
    """
    system_prompt = read_prompt_from_file("classify_prompt.txt")
    if not system_prompt:
        LOGGER.error("Could not read classify_prompt.txt; defaulting to casual")
        return {"labels": ["casual"], "tags": []}

    user_content = f"Subject: {subject}\n\n{body}"
    history = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    llm.init_history(history)

    response = llm.generate_response()
    if not response:
        LOGGER.warning("Classification LLM returned no response; defaulting to casual")
        return {"labels": ["casual"], "tags": []}

    try:
        # Strip markdown fences if the model wraps its output
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        result = json.loads(clean.strip())
        if "labels" not in result:
            raise ValueError("Missing 'labels' key")
        LOGGER.debug(f"Classification result: {result}")
        return result
    except Exception as e:
        LOGGER.warning(f"Failed to parse classification JSON ({e}); defaulting to casual. Raw: {response!r}")
        return {"labels": ["casual"], "tags": []}
