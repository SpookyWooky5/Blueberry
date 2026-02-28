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

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")

# ================================= CONSTANTS ================================ #
_CLASSIFY_SYSTEM_PROMPT = """\
You are Blueberry, an AI email assistant. Classify the email below.

LABELS (choose one or more):
- emotional      — emotional dump, needs empathetic reply
- goal_set       — states a new goal or intention
- goal_update    — updates progress on an existing goal
- goal_acknowledge — explicitly acknowledges a reminder ("yes I'm working on it")
- goal_update_ambiguous — mentions something that MIGHT be a goal update but confidence is low
- observation    — self-reflection, doesn't need a deep reply
- knowledge      — technical note or fact to store
- casual         — greeting, small talk, or simple question

TAGS: 2-4 short thematic tags describing the email content (e.g. work-stress, project-name).

Return ONLY valid JSON, nothing else: {"labels": ["..."], "tags": ["..."]}

Example:
Email: "I'm exhausted after the sprint review but really proud we shipped it."
Output: {"labels": ["emotional", "observation"], "tags": ["work", "shipping", "exhaustion"]}
"""

# ================================= FUNCTIONS ================================ #
def classify_email(llm: OllamaChat, subject: str, body: str) -> dict:
    """
    Classifies an email into structural labels and semantic tags.

    Returns {"labels": [...], "tags": [...]}
    labels: one or more from the fixed structural set
    tags: dynamic semantic tags describing the email content
    """
    user_content = f"Subject: {subject}\n\n{body}"
    history = [
        {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
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
