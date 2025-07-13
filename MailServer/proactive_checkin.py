# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 13-JUL-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import email
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from Logging import logger_init
from LLM import BaseChatbot
from Database import connect_to_dataset, get_or_create_client
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

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("MailServer")

# ================================= CONSTANTS ================================ #
CHECK_IN_INTERVAL_HOURS = os.getenv("CHECK_IN_INTERVAL_HOURS", 12)

# ================================= FUNCTIONS ================================ #
def proactive_checkin():
    """
    Checks if a client has been inactive for a certain period and sends a
    proactive check-in email reminding them of their goals.
    """
    LOGGER.info("Starting proactive check-in process...")
    db = connect_to_dataset()
    email_table = db['emails']
    goals_table = db['client_goals']
    memory_table = db['memories']

    for client_email, client_name in zip(CLIENTS, CLIENTNAMES):
        client_id = get_or_create_client(client_email, client_name)
        if client_id == -1:
            continue

        # 1. Check for client's last communication
        try:
            last_email = email_table.find_one(
                from_addr=client_email,
                order_by='-time_received'
            )
            if not last_email:
                LOGGER.info(f"No emails found from {client_name}. Skipping check-in.")
                continue

            time_since_last_email = datetime.now() - last_email['time_received']

            if time_since_last_email < timedelta(hours=CHECK_IN_INTERVAL_HOURS):
                LOGGER.info(f"Client {client_name} is active. No check-in needed.")
                continue
            
            LOGGER.info(f"Client {client_name} has been inactive for {time_since_last_email}. Preparing check-in.")

        except Exception as e:
            LOGGER.error(f"Could not retrieve last email for {client_name}: {e}")
            continue

        # 2. Fetch active goals
        try:
            active_goals = list(goals_table.find(client_id=client_id, status='active'))
            if not active_goals:
                LOGGER.info(f"No active goals found for {client_name}. Skipping check-in.")
                continue
            goals_list_str = "\n".join([f"- {g['goal_text']}" for g in active_goals])
        except Exception as e:
            LOGGER.error(f"Could not retrieve goals for {client_name}: {e}")
            continue

        # 3. Fetch recent memory for context
        try:
            latest_memory = memory_table.find_one(client_id=client_id, order_by='-period_end')
            memory_context = latest_memory['text'] if latest_memory else "No recent activity to summarize."
        except Exception as e:
            LOGGER.error(f"Could not retrieve memory for {client_name}: {e}")
            memory_context = "Could not retrieve recent context."

        # 4. Generate the check-in email
        prompt_template = read_prompt_from_file("proactive_checkin_prompt.txt")
        if not prompt_template:
            continue

        prompt = prompt_template.format(
            client_name=client_name,
            goals_list=goals_list_str,
            memory_context=memory_context
        )

        try:
            llm = BaseChatbot(LLM_MODEL)
            llm.init_history(history=[{"role": "system", "content": prompt}])
            llm_output = llm.generate_response()
            llm_output = remove_think_blocks(llm_output)
        except Exception as e:
            LOGGER.error(f"Failed to generate check-in email from LLM: {e}")
            continue

        # 5. Send the email
        try:
            response_mail = MIMEMultipart()
            response_mail["From"] = EMAIL
            response_mail["To"] = client_email
            response_mail["Subject"] = "Just checking in!"
            response_mail["Message-ID"] = email.utils.make_msgid()
            response_mail.attach(MIMEText(llm_output, "plain"))

            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp_server:
                smtp_server.login(EMAIL, PASSWORD)
                smtp_server.sendmail(EMAIL, client_email, response_mail.as_string())
            
            LOGGER.info(f"Successfully sent proactive check-in to {client_name}")

        except Exception as e:
            LOGGER.error(f"Failed to send proactive check-in email: {e}")

# =================================== MAIN =================================== #
if __name__ == "__main__":
    proactive_checkin()
