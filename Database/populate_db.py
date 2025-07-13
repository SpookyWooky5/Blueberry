# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 11-MAY-2025  Initial Draft
# 13-JUL-2025  Refactor to be fully idempotent and use latest features.
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import time
import email
import pickle
from datetime import timedelta, datetime

import numpy as np
from dateutil.relativedelta import relativedelta

from Logging import logger_init
from Database import connect_to_dataset, get_or_create_client
from LLM import BaseEmbedder, BaseChatbot
from LLM.extract_goals import extract_and_save_goals
from MailServer import imap_auth
from utils import (
    strip_quoted_reply,
    LLM_MODEL,
    EMB_MODEL,
    EMAIL,
    CLIENTS,
    CLIENTNAMES
)

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("Database")

# ================================= FUNCTIONS ================================ #
def populate_clients():
    """Inserts all clients from utils into the database, ignoring duplicates."""
    count = 0
    db = connect_to_dataset()
    for name, client_email in zip(CLIENTNAMES, CLIENTS):
        try:
            # insert_ignore is idempotent
            result = db['clients'].insert_ignore(dict(
                name=name,
                email=client_email
            ), keys=['email'])
            if result:
                count += 1
        except Exception as e:
            LOGGER.error(f"Could not insert client {client_email} into table: {e}")
    LOGGER.info(f"Verified all clients. Inserted {count} new client(s).")

def populate_emails():
    """
    Performs a full historical scan of emails, inserting only those not
    already present in the database.
    """
    imap_server = imap_auth()
    db = connect_to_dataset()
    email_table = db['emails']
    email_embed_table = db['email_embeddings']
    emb = BaseEmbedder(EMB_MODEL)
    new_mails_count = 0

    all_mails = []
    for mailbox in ('inbox', 'sent'):
        LOGGER.debug(f"Scanning historical mails from '{mailbox}'...")
        imap_server.select(mailbox)
        for client in CLIENTS:
            try:
                search_criterion = 'FROM' if mailbox == 'inbox' else 'TO'
                status, data = imap_server.search(None, search_criterion, client)
                if status != 'OK': continue
                for mail_id in data[0].split():
                    # Check existence before fetching, which is more efficient
                    _, raw_mail_data = imap_server.fetch(mail_id, "(BODY[HEADER.FIELDS (MESSAGE-ID)])")
                    header = raw_mail_data[0][1].decode()
                    msg_id_match = email.header.make_header(email.header.decode_header(header))
                    msg_id = str(msg_id_match).split('<')[-1].split('>')[0]
                    
                    if not email_table.find_one(message_id=msg_id):
                        _, raw_mail_data = imap_server.fetch(mail_id, "(RFC822)")
                        raw_mail = email.message_from_bytes(raw_mail_data[0][1])
                        mail_date = email.utils.parsedate_to_datetime(raw_mail.get("Date"))
                        all_mails.append((mail_date, raw_mail))
            except Exception as e:
                LOGGER.error(f"Could not fetch mails for {client} from {mailbox}: {e}")
                imap_server = imap_auth() # Re-auth on error
                imap_server.select(mailbox)

    LOGGER.info(f"Found {len(all_mails)} new historical mails to add.")
    all_mails.sort(key=lambda tup: tup[0])

    for (mail_date, raw_mail) in all_mails:
        try:
            subject = raw_mail.get("Subject")
            msg_id = raw_mail.get("Message-ID")
            to_name, to_addr = email.utils.parseaddr(raw_mail.get("To"))
            from_name, from_addr = email.utils.parseaddr(raw_mail.get("From"))

            if to_addr == EMAIL and not to_name: to_name = "Blueberry"
            if from_addr == EMAIL and not from_name: from_name = "Blueberry"

            body = ""
            if raw_mail.is_multipart():
                for part in raw_mail.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors='ignore')
                        break
            else:
                body = raw_mail.get_payload(decode=True).decode(errors='ignore')

            clean_body = strip_quoted_reply(body)
            if "summary" in (subject.lower() if subject else "") and from_addr == EMAIL:
                continue

            client_email = from_addr if to_addr == EMAIL else to_addr
            client_id = get_or_create_client(client_email, "")
            if client_id == -1: continue

            db.begin()
            email_id = email_table.insert(dict(
                client_id=client_id, message_id=msg_id,
                to_addr=to_addr, to_name=to_name,
                from_addr=from_addr, from_name=from_name,
                subject=subject, body=clean_body,
                time_received=mail_date, responded=1
            ))
            embedding = emb.embed(subject, clean_body)
            email_embed_table.insert(dict(
                email_id=email_id, client_id=client_id,
                model=EMB_MODEL, embedding=pickle.dumps(embedding)
            ))
            db.commit()
            new_mails_count += 1
        except Exception as e:
            LOGGER.error(f"Failed to process mail {msg_id}: {e}")
            db.rollback()
    LOGGER.info(f"Inserted {new_mails_count} new emails.")

def populate_memories():
    """Generates historical summaries only for periods that do not already have one."""
    from LLM import summarize
    LOGGER.info("Starting historical memory population.")
    llm = BaseChatbot(LLM_MODEL)
    emb = BaseEmbedder(EMB_MODEL)
    db = connect_to_dataset()

    earliest = db['emails'].find_one(order_by='time_received')
    if not earliest:
        LOGGER.warning("No emails in database to create memories from.")
        return
    
    min_date = earliest["time_received"].date()
    max_date = datetime.now().date()

    # The summarize function is now idempotent, so we can call it directly.
    # Daily
    day = min_date
    while day < max_date:
        summarize.summarize("daily", day + timedelta(days=1), llm, emb, respond=False)
        day += timedelta(days=1)
    
    # Weekly
    week_start = min_date - timedelta(days=min_date.weekday())
    while week_start < max_date:
        summarize.summarize("weekly", week_start + timedelta(days=7), llm, emb, respond=False)
        week_start += timedelta(weeks=7)

def populate_goals():
    """Extracts and populates goals from all historical emails for each client."""
    LOGGER.info("Starting historical goal population.")
    db = connect_to_dataset()
    for client_email, client_name in zip(CLIENTS, CLIENTNAMES):
        client_id = get_or_create_client(client_email, client_name)
        if client_id == -1: continue

        LOGGER.debug(f"Extracting goals for {client_name}.")
        try:
            user_emails = list(db['emails'].find(client_id=client_id, from_addr=client_email, order_by='time_received'))
            if not user_emails: continue

            full_conversation = "\n\n---\n\n".join(email['body'] for email in user_emails)
            last_email_id = user_emails[-1]['id']
            
            # extract_and_save_goals is idempotent due to UNIQUE constraint in DB
            extract_and_save_goals(client_id, full_conversation, last_email_id)
        except Exception as e:
            LOGGER.error(f"Could not extract goals for client {client_id}: {e}")

# =================================== MAIN =================================== #
if __name__ == "__main__":
    LOGGER.info("--- Starting Idempotent Database Population ---")
    
    LOGGER.info("Step 1: Verifying clients...")
    populate_clients()
    
    LOGGER.info("Step 2: Populating new historical emails...")
    populate_emails()
    
    LOGGER.info("Step 3: Populating missing historical memories...")
    populate_memories()

    LOGGER.info("Step 4: Populating missing historical goals...")
    populate_goals()

    LOGGER.info("--- Database Population Complete ---")
