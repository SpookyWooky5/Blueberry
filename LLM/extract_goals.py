# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 13-JUL-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import json
from Logging import logger_init
from Database import connect_to_dataset
from LLM import OllamaChat
from Obsidian import write_goal
from utils import read_prompt_from_file, remove_think_blocks, LLM_MODEL

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")

# ================================== FUNCTIONS ================================ #
def extract_and_save_goals(client_id: int, conversation_text: str, source_email_id: int):
    """
    Analyzes a conversation to extract goals and saves them to the database.

    Args:
        client_id: The ID of the client.
        conversation_text: The full text of the conversation to analyze.
        source_email_id: The ID of the email that triggered this analysis.
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
        clean_response = remove_think_blocks(response)

        # The response should be a JSON list of strings.
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
    count = 0
    db.begin()
    try:
        for goal in goals:
            if isinstance(goal, str) and goal.strip():
                goals_table.insert_ignore(dict(
                    client_id=client_id,
                    goal_text=goal.strip(),
                    source_email_id=source_email_id,
                    status='active'
                ), keys=['client_id', 'goal_text'])
                count += 1
        db.commit()
        if count > 0:
            LOGGER.info(f"Successfully inserted {count} new goal(s) for client {client_id}.")
    except Exception as e:
        db.rollback()
        LOGGER.error(f"Failed to insert goals into database: {e}")
        return

    for goal in goals:
        if isinstance(goal, str) and goal.strip():
            try:
                write_goal(goal.strip(), client_id, source_email_id)
            except Exception as e:
                LOGGER.error(f"Could not write goal to vault: {e}")

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
