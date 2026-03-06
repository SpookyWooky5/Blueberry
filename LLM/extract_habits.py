import os
import re
import json
from Logging import logger_init
from Database import connect_to_dataset
from LLM import OllamaChat
from Obsidian import update_goal, write_habit
from utils import read_prompt_from_file, remove_think_blocks, LLM_MODEL, VAULT_DIR

LOGGER = logger_init("LLM")


def _get_existing_habits() -> list[str]:
    """Returns list of existing habit slugs from the vault Habits/ directory."""
    habits_dir = os.path.join(VAULT_DIR, "Habits")
    if not os.path.isdir(habits_dir):
        return []
    return [f[:-3] for f in os.listdir(habits_dir) if f.endswith('.md')]


def infer_and_save_habit(client_id: int, goals: list, conversation_text: str, email_date=None):
    """
    Infers the habit category for a set of newly extracted goals.
    Creates a habit vault file if needed, links goals to it in vault + SQLite.
    Idempotent: goals already linked are skipped.
    """
    goals = [g for g in goals if isinstance(g, str) and g.strip()]
    if not goals:
        return

    existing_habits = _get_existing_habits()
    existing_str = ", ".join(existing_habits) if existing_habits else "none"
    goals_str = "\n".join(f"- {g}" for g in goals)

    prompt_template = read_prompt_from_file("habit_inference_prompt.txt")
    if not prompt_template:
        LOGGER.error("Could not read habit_inference_prompt.txt. Skipping habit inference.")
        return

    prompt = prompt_template.format(
        existing_habits=existing_str,
        goals_list=goals_str,
    )

    try:
        llm = OllamaChat(LLM_MODEL)
        llm.init_history([{"role": "system", "content": prompt}])
        response = llm.generate_response()
        clean = remove_think_blocks(response)
        clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', clean.strip(), flags=re.MULTILINE).strip()
        result = json.loads(clean)
        if isinstance(result, list):
            result = result[0] if result else {}
    except json.JSONDecodeError:
        LOGGER.error(f"Habit inference: failed to parse JSON from LLM. Raw: {response!r}")
        return
    except Exception as e:
        LOGGER.error(f"Habit inference LLM call failed: {e}")
        return

    habit_val = result.get("habit")
    if not habit_val:
        LOGGER.warning("Habit inference returned no 'habit' key.")
        return

    # Determine slug: existing or new
    if habit_val == "new":
        habit_name = result.get("name", "general")
        try:
            rel = write_habit(habit_name, client_id, email_date=email_date)
            habit_slug = os.path.basename(rel)[:-3]  # strip .md
            LOGGER.info(f"Created new habit: {habit_slug}")
        except Exception as e:
            LOGGER.error(f"Could not write habit vault file: {e}")
            return
    else:
        habit_slug = habit_val

    # Link each goal to the habit in vault + SQLite
    db = connect_to_dataset()
    from utils import VAULT_DIR as _VAULT_DIR
    from Obsidian.writer import _slugify

    for goal_text in goals:
        slug = _slugify(goal_text)
        try:
            update_goal(slug, habit_slug=habit_slug)
        except FileNotFoundError:
            LOGGER.warning(f"Goal vault file not found for slug '{slug}', skipping habit link.")
        except Exception as e:
            LOGGER.error(f"Could not update goal vault for '{slug}': {e}")

        try:
            db['client_goals'].update(
                dict(goal_text=goal_text.strip(), habit_slug=habit_slug),
                ['goal_text']
            )
        except Exception as e:
            LOGGER.error(f"Could not update client_goals habit_slug for '{goal_text[:40]}': {e}")

    LOGGER.info(f"Linked {len(goals)} goal(s) to habit '{habit_slug}'")
