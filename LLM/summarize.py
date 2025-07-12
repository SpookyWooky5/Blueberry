# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 15-MAY-2025  Initial Draft
# 12-JUL-2025  Refactor for thematic context summarization
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import sys
import email
import pickle
import smtplib
import numpy as np
from email.mime.text import MIMEText
from datetime import timedelta, datetime
from email.mime.multipart import MIMEMultipart

from dateutil.relativedelta import relativedelta

from Logging import logger_init
from LLM.cosine import cosine
from LLM import BaseChatbot, BaseEmbedder
from Database import connect_to_dataset, get_or_create_client
from utils import (
    load_config,
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
LOGGER = logger_init("LLM")

# ================================= CONSTANTS ================================ #
LLMCFG = load_config()["LLM"]

# ================================== CLASSES ================================= #

# ================================= FUNCTIONS ================================ #
def get_relevant_past_memories(db, emb, client_id, current_period_text, top_k=3):
    """Retrieves past memories thematically relevant to the current period's text."""
    if not current_period_text:
        return []

    LOGGER.debug("Finding relevant past memories...")
    try:
        # Embed the summary of the current period's content
        current_embedding = emb.embed("Current Period Summary", current_period_text)

        # Fetch all past memory embeddings for the client
        past_memories = list(db['memory_embeddings'].find(client_id=client_id))
        if not past_memories:
            LOGGER.info("No past memories found to compare against.")
            return []

        # Calculate cosine similarity
        similarities = []
        for mem in past_memories:
            past_embedding = pickle.loads(mem['embedding'])
            sim = cosine(np.array(current_embedding), np.array(past_embedding))
            similarities.append((sim, mem['memory_id']))

        # Sort by similarity and get top_k
        similarities.sort(key=lambda x: x[0], reverse=True)
        top_memory_ids = [mem_id for sim, mem_id in similarities[:top_k]]

        if not top_memory_ids:
            return []

        # Retrieve the text of the most relevant memories
        relevant_memories = list(db['memories'].find(id=top_memory_ids))
        LOGGER.info(f"Found {len(relevant_memories)} relevant past memories.")
        return relevant_memories

    except Exception as e:
        LOGGER.error(f"Could not retrieve relevant past memories: {e}")
        return []


def summarize(summary_type, start_date, llm, emb, respond=True):
	if summary_type not in ("daily", "weekly", "monthly", "quarterly"):
		LOGGER.warning(f"Invalid summary type {summary_type}! Ignoring.")
		return
	
	LOGGER.debug(f"Creating {summary_type} summaries")

	cfg = load_config()["Summarizer"][summary_type]
	period_start = start_date - relativedelta(**cfg["delta"])
	period_end = start_date

	# Connect to DB
	db = connect_to_dataset()
	table = db[cfg['source_table']]
	mem_table = db['memories']
	mem_emb_table = db['memory_embeddings']

	# Build filter dict
	query = {**cfg.get("source_filter", {}),
			 "client_id": None}
	# add date filters
	if cfg["source_table"] == "emails":
		query["time_received"] = {
			'gt': period_start,
			'lt': period_end
		}
	else:
		query["period_start"] = {
			'gte': period_start,
			'lte': period_end
		}

	if summary_type != "daily":
		today = period_end
		subject = f'{summary_type.capitalize()} Summary from {period_start.strftime("%a, %d %B")} to {period_end.strftime("%a, %d %B")}'
	else:
		today = period_start
		subject = f'{summary_type.capitalize()} Summary {period_start.strftime("%a, %d %B")}'

	for client, client_name in zip(CLIENTS, CLIENTNAMES):
		client_id = get_or_create_client(client, client_name)
		if client_id == -1:
			continue
		query["client_id"] = client_id

		try:
			records = tuple(table.find(**query, order_by='id'))
		except Exception as e:
			LOGGER.error(f"Could not retrieve data for the current period, {e}")
			continue
		if len(records) == 0:
			LOGGER.info(f"No data to summarize for client {client_id} in the current period.")
			continue

		# --- Build Current Period Context ---
		current_period_content_list = []
		if summary_type == "daily":
			for r in records:
				current_period_content_list.append(f'''[EMAIL]
From: {r["from_name"]}
To: {r["to_name"]}
Date: {r["time_received"]}
Subject: {r["subject"]}
Body:
{r["body"]}
[/EMAIL]''')
		else:
			for r in records:
				current_period_content_list.append(f"[SUMMARY FROM {r['created_at']}]\n{r['text']}\n[/SUMMARY]")
		
		current_period_text = "\n\n".join(current_period_content_list)

		# --- Get Relevant Past Memories ---
		relevant_memories = get_relevant_past_memories(db, emb, client_id, current_period_text)
		
		past_memories_text = ""
		if relevant_memories:
			past_memories_list = []
			for mem in relevant_memories:
				past_memories_list.append(f"[PAST MEMORY from {mem['period_start'].strftime('%Y-%m-%d')}]\n{mem['text']}\n[/PAST MEMORY]")
			past_memories_text = "\n\n".join(past_memories_list)

		# --- Construct Final Content for Prompt ---
		final_content = "--- DATA FOR CURRENT PERIOD ---\n"
		final_content += current_period_text
		if past_memories_text:
			final_content += "\n\n--- RELEVANT PAST MEMORIES FOR CONTEXT ---\n"
			final_content += past_memories_text
		
		final_content = remove_think_blocks(final_content)

		prompt_template = read_prompt_from_file("summary_prompt.txt")
		if not prompt_template:
			LOGGER.error("Failed to read summary prompt, aborting summarization for this client.")
			continue

		prompt = prompt_template.format(
			client_name=client_name,
			today=today.strftime("%a, %d %B"),
			summary_type=summary_type,
			header=cfg["header"].format(client_name=client_name),
			content=final_content
		)

		history = [{"role": "system", "content": prompt}]
		llm.init_history('summary', history)

		LOGGER.info("Calling LLM to generate a reply")
		llm_output = llm.generate_response()
		if llm_output is None:
			continue
		
		llm_output = remove_think_blocks(llm_output)

		# Add summary to Memory DB
		db.begin()
		try:
			LOGGER.debug(f'Inserting {subject} for client {client_id} to memory')

			memory_id = mem_table.insert(dict(
				client_id=client_id,
				memory_type=summary_type,
				text=llm_output,
				period_start=period_start,
				period_end=period_end,
			))
			# Embed the combination of the subject and the generated text for better semantic meaning
			embedding_text = f"Subject: {subject}\n\nSummary:\n{llm_output}"
			embedding = emb.embed("Summary Embedding", embedding_text)
			mem_emb_table.insert(dict(
				memory_id=memory_id,
				client_id=client_id,
				model=EMB_MODEL,
				embedding=pickle.dumps(embedding)
			))
			db.commit()
			LOGGER.debug(f"Inserted {summary_type} summary in table 'memories'")
		except Exception as e:
			LOGGER.error(f"Could not insert memory in table 'memories': {e}")
			db.rollback()
		
		# Send summary to client
		if respond:
			response_mail = MIMEMultipart()
			response_mail["From"] = EMAIL
			response_mail["To"] = client
			response_mail["Subject"] = subject
			response_mail["Message-ID"] = email.utils.make_msgid()

			response_mail.attach(MIMEText(llm_output, "plain"))
			LOGGER.debug("Response mail formatted")

			try:
				LOGGER.debug("Sending mail to client...")
				with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp_server:
					smtp_server.login(EMAIL, PASSWORD)
					smtp_server.sendmail(EMAIL, client, response_mail.as_string())
			except Exception as e:
				LOGGER.error(f"Error occured while sending mail, {e}")
				continue

# =================================== MAIN =================================== #
if __name__ == "__main__":
	if len(sys.argv) < 2:
		print("Usage: python -m LLM.summarize <summary_type>")
		sys.exit(1)
	summary_type = sys.argv[1]

	# Init LLM
	llm = BaseChatbot(LLM_MODEL)
	# Init Embedder
	emb = BaseEmbedder(EMB_MODEL)

	today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
	summarize(summary_type, today, llm, emb, True)
	sys.exit(0)