# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 14-MAY-2025  Initial Draft
# 12-JUL-2025  Refactor to use new prompt and context strategy
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import email
import pickle
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import numpy as np

from Logging import logger_init
from LLM.parse import remove_commands
from LLM import BaseChatbot, BaseEmbedder, cosine
from Database import connect_to_dataset, get_or_create_client
from utils import (
    remove_think_blocks,
    read_prompt_from_file,
    LLM_MODEL,
    EMB_MODEL,
    EMAIL,
    PASSWORD,
    SMTP_HOST,
    SMTP_PORT,
    CLIENTS,
    CLIENTNAMES,
)

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("MailServer")

# ================================== CLASSES ================================= #

# ================================= FUNCTIONS ================================ #
def get_relevant_context(db, emb, client_id, current_email_text, top_k=3):
    """Retrieves relevant past memories based on the current email's content."""
    if not current_email_text:
        return ""

    LOGGER.debug("Finding relevant past memories for context...")
    try:
        current_embedding = emb.embed("Current Email", current_email_text)
        past_memories = list(db['memory_embeddings'].find(client_id=client_id))
        if not past_memories:
            return ""

        similarities = []
        for mem in past_memories:
            past_embedding = pickle.loads(mem['embedding'])
            sim = cosine(np.array(current_embedding), np.array(past_embedding))
            similarities.append((sim, mem['memory_id']))

        similarities.sort(key=lambda x: x[0], reverse=True)
        top_memory_ids = [mem_id for sim, mem_id in similarities[:top_k]]

        if not top_memory_ids:
            return ""

        relevant_memories = list(db['memories'].find(id=top_memory_ids))
        
        context_list = []
        for mem in relevant_memories:
            context_list.append(f"[PAST MEMORY from {mem['period_start'].strftime('%Y-%m-%d')}]\n{mem['text']}\n[/PAST MEMORY]")
        
        return "\n\n".join(context_list)

    except Exception as e:
        LOGGER.error(f"Could not retrieve relevant context: {e}")
        return ""

def reply():
	# Connect to DB
	db = connect_to_dataset()
	email_table = db['emails']
	email_embed_table = db['email_embeddings']

	# Init LLM
	llm = BaseChatbot(LLM_MODEL)
	# Init Embedder
	emb = BaseEmbedder(EMB_MODEL)
	
	for client, client_name in zip(CLIENTS, CLIENTNAMES):
		client_id = get_or_create_client(client, client_name)
		if client_id == -1:
			continue
		
		# Get unreplied emails from DB
		try:
			LOGGER.debug(f"Retrieving unreplied mails from DB for client {client_id}")
			unresponded = tuple(email_table.find(
				client_id=client_id,
				responded=0,
				order_by='id'
			))
		except Exception as e:
			LOGGER.error(f"Could not collect unreplied mails from DB, {e}")
			continue
		
		if not unresponded:
			LOGGER.info(f"No unreplied mails for client {client_id}")
			continue
		
		LOGGER.info(f"Found {len(unresponded)} unreplied mails from client {client_id}")

		# Consolidate all unread messages into one block
		current_email_text = "\n\n---\n\n".join(
			f"From: {mail['from_name']}\nSubject: {mail['subject']}\n\n{remove_commands(mail['body'])}"
			for mail in unresponded
		)

		# Get relevant context from past memories
		context = get_relevant_context(db, emb, client_id, current_email_text)

		# Load the prompt
		prompt_template = read_prompt_from_file("mail_prompt.txt")
		if not prompt_template:
			LOGGER.error("Failed to read mail prompt, skipping reply for this client.")
			continue

		# Format the prompt
		final_prompt = prompt_template.format(
			context=context,
			current_email=current_email_text
		)

		history = [{"role": "system", "content": final_prompt}]
		llm.init_history('mail', history)

		LOGGER.info("Calling LLM to generate a reply")
		llm_output = llm.generate_response()
		if llm_output is None:
			continue

		llm_output = remove_think_blocks(llm_output)
		response_msg_id = email.utils.make_msgid()
		last_mail = unresponded[-1]

		# Add LLM response to DB
		db.begin()
		try:
			LOGGER.debug(f"Inserting response for thread '{last_mail['subject']}' into table 'emails'")
			email_id = email_table.insert(dict(
				client_id=client_id,
				message_id=response_msg_id,
				to_addr=last_mail['from_addr'],
				to_name=last_mail['from_name'],
				from_addr=last_mail['to_addr'],
				from_name=last_mail['to_name'],
				subject=last_mail['subject'],
				body=llm_output,
				child_of=last_mail['message_id'],
				responded=1
			))
			embedding = emb.embed(last_mail['subject'], llm_output)
			email_embed_table.insert(dict(
				email_id=email_id,
				client_id=client_id,
				model=EMB_MODEL,
				embedding=pickle.dumps(embedding)
			))
			db.commit()
			LOGGER.debug("Inserted record in table 'emails'")
		except Exception as e:
			LOGGER.error(f"Could not insert mail into 'emails': {e}")
			db.rollback()
			continue

		# Reply to client
		references = last_mail.get("References", "")
		parent_refs = [ref.strip() for ref in references.split() if ref.strip().startswith("<") and ref.strip().endswith(">")]
		if last_mail['message_id'] not in parent_refs:
			parent_refs.append(last_mail['message_id'])

		response_mail = MIMEMultipart()
		response_mail["From"] = EMAIL
		response_mail["To"] = last_mail['from_addr']
		response_mail["Subject"] = f"Re: {last_mail['subject']}"
		response_mail["Message-ID"] = response_msg_id
		response_mail["In-Reply-To"] = last_mail['message_id']
		response_mail["References"] = " ".join(parent_refs)
		response_mail.attach(MIMEText(llm_output, "plain"))
		
		LOGGER.debug("Response mail formatted. Sending...")
		try:
			with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp_server:
				smtp_server.login(EMAIL, PASSWORD)
				smtp_server.sendmail(EMAIL, last_mail['from_addr'], response_mail.as_string())
			LOGGER.info(f"Successfully sent reply to {last_mail['from_addr']}")
		except Exception as e:
			LOGGER.error(f"Error occurred while sending mail: {e}")
			continue
		
		# Mark unresponded mails as responded
		try:
			ids_to_update = [mail['id'] for mail in unresponded]
			email_table.update_many([dict(id=id, responded=1) for id in ids_to_update], ['id'])
			LOGGER.debug(f"Marked {len(ids_to_update)} mails as responded")
		except Exception as e:
			LOGGER.error(f"Could not mark mails as responded: {e}")

# =================================== MAIN =================================== #
if __name__ == "__main__":
	reply()