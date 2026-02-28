"""
Blueberry Reminder Daemon
Runs daily via cron. Checks active/reminded goals and sends reminder emails.
Run as: LoadEnv.sh reminder_daemon.py
"""
import email
import smtplib
from datetime import datetime, date, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from Logging import logger_init
from Database import connect_to_dataset, get_or_create_client
from LLM import OllamaChat
from Obsidian import update_goal
from Obsidian.writer import _slugify
from utils import (
    read_prompt_from_file,
    remove_think_blocks,
    LLM_MODEL,
    EMAIL,
    PASSWORD,
    SMTP_HOST,
    SMTP_PORT,
    CLIENTS,
    CLIENTNAMES,
)

LOGGER = logger_init("Reminder")

REMINDER_STATUSES = {'active', 'reminded_1', 'reminded_2', 'reminded_3', 'reminded_4', 'reminded_5'}
MAX_REMINDERS = 5
DAYS_BEFORE_FIRST_REMINDER_NO_DEADLINE = 7
REMINDER_INTERVAL_HOURS = 48


def _should_remind(goal: dict, today: date) -> bool:
    """Returns True if this goal is due for a reminder today."""
    reminder_count = goal.get('reminder_count') or 0
    last_reminded = goal.get('last_reminded')
    deadline = goal.get('deadline')
    created_at = goal.get('created_at')

    # Determine first trigger date
    if deadline:
        if isinstance(deadline, str):
            deadline = date.fromisoformat(deadline)
        first_trigger = deadline + timedelta(days=1)
    else:
        if isinstance(created_at, datetime):
            created_at = created_at.date()
        elif isinstance(created_at, str):
            created_at = date.fromisoformat(created_at[:10])
        first_trigger = created_at + timedelta(days=DAYS_BEFORE_FIRST_REMINDER_NO_DEADLINE)

    if today < first_trigger:
        return False

    # Check interval since last reminder
    if last_reminded:
        if isinstance(last_reminded, str):
            last_reminded = date.fromisoformat(last_reminded)
        hours_since = (today - last_reminded).total_seconds() / 3600
        if hours_since < REMINDER_INTERVAL_HOURS:
            return False

    return True


def _send_reminder(client_email: str, client_name: str, goal: dict, llm: OllamaChat) -> bool:
    """Generates and sends a reminder email. Returns True on success."""
    goal_text = goal['goal_text']
    reminder_count = (goal.get('reminder_count') or 0) + 1
    habit_slug = goal.get('habit_slug') or ''
    deadline = goal.get('deadline')

    habit_line = f"Habit area: {habit_slug}." if habit_slug else ""
    deadline_line = f"Their deadline was {deadline}." if deadline else ""

    prompt_template = read_prompt_from_file("reminder_prompt.txt")
    if not prompt_template:
        LOGGER.error("Could not read reminder_prompt.txt")
        return False

    prompt = prompt_template.format(
        client_name=client_name,
        goal_text=goal_text,
        habit_line=habit_line,
        deadline_line=deadline_line,
        reminder_count=reminder_count,
    )

    llm.init_history([{"role": "system", "content": prompt}])
    llm_output = llm.generate_response()
    if not llm_output:
        LOGGER.error(f"LLM returned no output for reminder on goal: {goal_text[:60]}")
        return False
    llm_output = remove_think_blocks(llm_output)

    msg = MIMEMultipart()
    msg["From"] = EMAIL
    msg["To"] = client_email
    msg["Subject"] = f"Checking in on your goal: {goal_text[:60]}"
    msg["Message-ID"] = email.utils.make_msgid()
    msg.attach(MIMEText(llm_output, "plain"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.login(EMAIL, PASSWORD)
            smtp.sendmail(EMAIL, client_email, msg.as_string())
        LOGGER.info(f"Sent reminder #{reminder_count} for goal: '{goal_text[:60]}'")
        return True
    except Exception as e:
        LOGGER.error(f"Failed to send reminder email: {e}")
        return False


def _process_goal(db, llm, client_email: str, client_name: str, goal: dict, today: date):
    reminder_count = goal.get('reminder_count') or 0
    goal_text = goal['goal_text']
    slug = _slugify(goal_text)

    # Auto-ignore after max reminders
    if reminder_count >= MAX_REMINDERS:
        LOGGER.info(f"Goal exceeded {MAX_REMINDERS} reminders, marking ignored: '{goal_text[:60]}'")
        try:
            update_goal(slug, status='ignored')
        except FileNotFoundError:
            pass
        db['client_goals'].update(dict(goal_text=goal_text, status='ignored'), ['goal_text'])
        return

    if not _should_remind(goal, today):
        return

    sent = _send_reminder(client_email, client_name, goal, llm)
    if not sent:
        return

    new_count = reminder_count + 1
    new_status = f"reminded_{new_count}"
    today_str = today.isoformat()

    try:
        update_goal(slug, status=new_status, reminder_count=new_count, last_reminded=today_str)
    except FileNotFoundError:
        LOGGER.warning(f"Goal vault file not found for slug '{slug}'; updating SQLite only.")

    db['client_goals'].update(dict(
        goal_text=goal_text,
        status=new_status,
        reminder_count=new_count,
        last_reminded=today_str,
    ), ['goal_text'])


def run_reminders():
    db = connect_to_dataset()
    llm = OllamaChat(LLM_MODEL)
    today = date.today()

    for client_email, client_name in zip(CLIENTS, CLIENTNAMES):
        client_id = get_or_create_client(client_email, client_name)
        if client_id == -1:
            continue

        goals = list(db['client_goals'].find(client_id=client_id))
        active_goals = [g for g in goals if g.get('status') in REMINDER_STATUSES]

        if not active_goals:
            LOGGER.debug(f"No active/reminded goals for {client_name}")
            continue

        LOGGER.info(f"Checking {len(active_goals)} goal(s) for {client_name}")
        for goal in active_goals:
            _process_goal(db, llm, client_email, client_name, goal, today)


# =================================== MAIN =================================== #
if __name__ == "__main__":
    run_reminders()
