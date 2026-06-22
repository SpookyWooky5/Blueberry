# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 13-JUL-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import re
import json
import pickle
import numpy as np
from numpy.linalg import norm
from Logging import logger_init
from Database import connect_to_dataset
from LLM import OllamaChat, OllamaEmbed
from LLM.extract_habits import infer_and_save_habit
from Obsidian import write_goal
from utils import read_prompt_from_file, remove_think_blocks, LLM_MODEL, EMB_MODEL

GOAL_SIM_THRESHOLD = 0.75  # cosine similarity above this → treat as duplicate

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")


def _is_duplicate_goal(db, emb, goal_text: str, client_id: int) -> bool:
    """Returns True if a semantically near-identical goal already exists in vault_index."""
    try:
        existing = list(db['vault_index'].find(file_type='goal', client_id=client_id))
        if not existing:
            return False
        new_vec = emb.embed(goal_text)
        if new_vec is None or len(new_vec) == 0:
            return False
        new_vec = np.array(new_vec)
        for row in existing:
            ev = np.array(pickle.loads(row['embedding']))
            sim = np.dot(new_vec, ev) / (norm(new_vec) * norm(ev))
            if sim >= GOAL_SIM_THRESHOLD:
                LOGGER.info(f"Goal '{goal_text[:50]}' similar to existing (sim={sim:.2f}), skipping.")
                return True
    except Exception as e:
        LOGGER.warning(f"Goal similarity check failed: {e}")
    return False


# ================================== FUNCTIONS ================================ #
def extract_and_save_goals(client_id: int, conversation_text: str, source_email_id: int):
    """
    Analyzes a conversation to extract goals and saves them to the database.
    Each goal is checked for similarity against existing goals before inserting.
    Habit inference runs per-goal so different goals can map to different habits.
    """
    LOGGER.info(f"Starting goal extraction for client {client_id}")

    prompt_template = read_prompt_from_file("goal_extraction_prompt.txt")
    if not prompt_template:
        LOGGER.error("Could not read goal extraction prompt. Aborting.")
        return

    prompt = prompt_template.format(conversation_text=conversation_text)

    try:
        llm = OllamaChat(LLM_MODEL)
        llm.init_history([{"role": "system", "content": prompt}])
        response = llm.generate_response()
        if not response:
            LOGGER.warning("Goal extraction: empty response from LLM.")
            return
        clean_response = remove_think_blocks(response)
        clean_response = re.sub(r'^```(?:json)?\s*|\s*```$', '', clean_response.strip(), flags=re.MULTILINE).strip()
        goals = json.loads(clean_response)
        if not isinstance(goals, list):
            LOGGER.warning(f"LLM returned non-list for goals: {goals}")
            return
    except json.JSONDecodeError:
        LOGGER.error(f"Failed to decode JSON from LLM response: {response}")
        return
    except Exception as e:
        LOGGER.error(f"An error occurred during goal extraction LLM call: {e}")
        return

    if not goals:
        LOGGER.info("No new goals identified.")
        return

    db = connect_to_dataset()
    goals_table = db['client_goals']
    emb = OllamaEmbed(EMB_MODEL)

    # Look up the email's sent date for accurate created timestamps
    email_date = None
    try:
        row = db['emails'].find_one(id=source_email_id)
        if row and row.get('time_received'):
            email_date = row['time_received']
    except Exception as e:
        LOGGER.warning(f"Could not look up email date for email {source_email_id}: {e}")

    count = 0
    new_goals = []  # (goal_text, context) pairs that passed dedup
    db.begin()
    try:
        for goal_obj in goals:
            # Accept both old string format and new {"goal": ..., "context": ...} format
            if isinstance(goal_obj, str):
                goal_text, context = goal_obj.strip(), ""
            elif isinstance(goal_obj, dict):
                goal_text = goal_obj.get('goal', '').strip()
                context   = goal_obj.get('context', '').strip()
            else:
                continue
            if not goal_text:
                continue

            # Similarity dedup: skip if a close match already exists in vault_index
            if _is_duplicate_goal(db, emb, goal_text, client_id):
                continue

            goals_table.insert_ignore(dict(
                client_id=client_id,
                goal_text=goal_text,
                source_email_id=source_email_id,
                status='active'
            ), keys=['client_id', 'goal_text'])
            new_goals.append((goal_text, context))
            count += 1
        db.commit()
        if count > 0:
            LOGGER.info(f"Successfully inserted {count} new goal(s) for client {client_id}.")
    except Exception as e:
        db.rollback()
        LOGGER.error(f"Failed to insert goals into database: {e}")
        return

    for goal_text, context in new_goals:

        try:
            rel_path = write_goal(goal_text, client_id, source_email_id,
                                  context=context, email_date=email_date)
            # Index in vault_index so future similarity checks can find it
            embedding = emb.embed(goal_text)
            if embedding is not None and len(embedding) > 0:
                db['vault_index'].upsert(dict(
                    file_path=rel_path,
                    file_type='goal',
                    client_id=client_id,
                    model=EMB_MODEL,
                    embedding=pickle.dumps(np.array(embedding)),
                ), ['file_path'])
        except Exception as e:
            LOGGER.error(f"Could not write goal to vault: {e}")

        # Habit inference per-goal so each goal maps to its own habit category
        try:
            infer_and_save_habit(client_id, [goal_text], conversation_text,
                                 email_date=email_date)
        except Exception as e:
            LOGGER.error(f"Habit inference failed for '{goal_text[:40]}': {e}")

# =================================== MAIN =================================== #
if __name__ == "__main__":
    # Example Usage
    # This requires a sample conversation and a client in the database.
    # For testing, you would manually set these up.
    # client_id_to_test = 1
    # source_email_id_to_test = 1 # An email ID that exists in your db
    # sample_conversation = """
    # User: Thanks for the weekly summary. It was helpful. My main goal for next week is to finalize the Q3 budget. I also need to remember to schedule a meeting with the marketing team.
    # Assistant: You're welcome! I've noted your goals.
    # """
    # extract_and_save_goals(client_id_to_test, sample_conversation, source_email_id_to_test)
    pass
