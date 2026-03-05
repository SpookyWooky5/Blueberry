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
import frontmatter
from email.mime.text import MIMEText
from datetime import timedelta, datetime
from email.mime.multipart import MIMEMultipart

from dateutil.relativedelta import relativedelta

from Logging import logger_init
from LLM.cosine import cosine
from LLM import OllamaChat, OllamaEmbed
from Database import connect_to_dataset, get_or_create_client
from Obsidian import write_memory, write_pattern, memory_relpath
from utils import (
    load_config,
	remove_think_blocks,
    read_prompt_from_file,
    LLM_MODEL,
    EMB_MODEL,
    VAULT_DIR,
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
        current_embedding = emb.embed(current_period_text)

        past = list(db['vault_index'].find(
            client_id=client_id,
            file_type={'in': ['daily', 'weekly', 'monthly', 'quarterly']}
        ))
        if not past:
            LOGGER.info("No past memories found in vault_index.")
            return []

        similarities = []
        for row in past:
            sim = cosine(np.array(current_embedding), np.array(pickle.loads(row['embedding'])))
            similarities.append((sim, row['file_path'], row['period_start']))

        similarities.sort(key=lambda x: x[0], reverse=True)
        top = similarities[:top_k]

        results = []
        for sim, rel_path, period_start in top:
            abs_path = os.path.join(VAULT_DIR, rel_path)
            post = frontmatter.load(abs_path)
            results.append({'text': post.content, 'period_start': period_start})

        LOGGER.info(f"Found {len(results)} relevant past memories.")
        return results

    except Exception as e:
        LOGGER.error(f"Could not retrieve relevant past memories: {e}")
        return []


def _detect_and_write_pattern(db, llm, emb, client_id: int, summary_text: str, summary_type: str):
    """Secondary LLM call after monthly/quarterly summaries to detect non-obvious patterns."""
    try:
        prompt_template = read_prompt_from_file("pattern_detection_prompt.txt")
        if not prompt_template:
            return
        prompt = prompt_template.format(summary_type=summary_type, summary_text=summary_text)
        llm.init_history([{"role": "system", "content": prompt}])
        response = llm.generate_response()
        if not response:
            return
        clean = remove_think_blocks(response).strip()
        if clean.lower() in ("null", "none", ""):
            return
        import json as _json
        result = _json.loads(clean)
        title = result.get("title")
        content = result.get("content", "").strip()
        if not title or not content:
            return
        rel_path = write_pattern(title, content)
        LOGGER.info(f"Bot-detected pattern written: {rel_path}")
        embedding = emb.embed(content)
        if embedding is not None and len(embedding) > 0:
            db['vault_index'].upsert(dict(
                file_path=rel_path,
                file_type='pattern',
                client_id=client_id,
                model=EMB_MODEL,
                embedding=pickle.dumps(embedding),
            ), ['file_path'])
    except Exception as e:
        LOGGER.error(f"Bot-initiated pattern detection failed: {e}")


def summarize(summary_type, start_date, llm, emb, respond=True):
	if summary_type not in ("daily", "weekly", "monthly", "quarterly", "yearly"):
		LOGGER.warning(f"Invalid summary type {summary_type}! Ignoring.")
		return
	
	LOGGER.debug(f"Creating {summary_type} summaries")

	# Yearly summaries read quarterly vault files directly; skip config source_table
	is_yearly = (summary_type == "yearly")
	if not is_yearly:
		cfg = load_config()["Summarizer"][summary_type]
	period_start = start_date - relativedelta(years=1) if is_yearly else start_date - relativedelta(**cfg["delta"])
	period_end = start_date

	# Connect to DB
	db = connect_to_dataset()
	if not is_yearly:
		table = db[cfg['source_table']]

	# Build filter dict (non-yearly only)
	if not is_yearly:
		query = {**cfg.get("source_filter", {}),
				 "client_id": None}
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

	if summary_type == "daily":
		today = period_start
		subject = f'Daily Summary {period_start.strftime("%a, %d %B")}'
	elif summary_type == "yearly":
		today = period_end
		subject = f'Yearly Summary {period_start.strftime("%Y")}'
	else:
		today = period_end
		subject = f'{summary_type.capitalize()} Summary from {period_start.strftime("%a, %d %B")} to {period_end.strftime("%a, %d %B")}'

	for client, client_name in zip(CLIENTS, CLIENTNAMES):
		client_id = get_or_create_client(client, client_name)
		if client_id == -1:
			continue
		if not is_yearly:
			query["client_id"] = client_id

		# --- Check if summary already exists ---
		rel_path = memory_relpath(summary_type, period_start)
		if db['vault_index'].find_one(file_path=rel_path, client_id=client_id):
			LOGGER.info(f"{summary_type.capitalize()} summary already exists at {rel_path}, skipping.")
			continue

		# --- Build Current Period Context ---
		current_period_content_list = []

		if is_yearly:
			# Read quarterly vault files for this year
			year = period_start.year
			all_quarterly = list(db['vault_index'].find(client_id=client_id, file_type='quarterly'))
			year_records = [r for r in all_quarterly
							if r['period_start'] and str(r['period_start']).startswith(str(year))]
			if not year_records:
				LOGGER.info(f"No quarterly summaries for {year}, skipping yearly summary.")
				continue
			for r in year_records:
				try:
					post = frontmatter.load(os.path.join(VAULT_DIR, r['file_path']))
					current_period_content_list.append(
						f"[QUARTERLY SUMMARY from {r['period_start']}]\n{post.content}\n[/QUARTERLY]"
					)
				except Exception as e:
					LOGGER.error(f"Could not load quarterly vault file {r['file_path']}: {e}")
		else:
			try:
				records = tuple(table.find(**query, order_by='id'))
			except Exception as e:
				LOGGER.error(f"Could not retrieve data for the current period, {e}")
				continue
			if len(records) == 0:
				LOGGER.info(f"No data to summarize for client {client_id} in the current period.")
				continue

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

		header = cfg["header"].format(client_name=client_name) if not is_yearly else f"Yearly Summary for {client_name}"
		prompt = prompt_template.format(
			client_name=client_name,
			today=today.strftime("%a, %d %B"),
			summary_type=summary_type,
			header=header,
			content=final_content
		)

		history = [{"role": "system", "content": prompt}]
		llm.init_history(history)

		LOGGER.info("Calling LLM to generate a reply")
		llm_output = llm.generate_response()
		if llm_output is None:
			continue
		
		llm_output = remove_think_blocks(llm_output)

		# Write summary to vault and index
		rel_path = write_memory(summary_type, period_start, period_end, llm_output, client_id)
		LOGGER.debug(f"Wrote {summary_type} summary to vault: {rel_path}")

		embedding_text = f"Subject: {subject}\n\nSummary:\n{llm_output}"
		embedding = emb.embed(embedding_text)
		db.begin()
		try:
			db['vault_index'].insert(dict(
				file_path=rel_path,
				file_type=summary_type,
				client_id=client_id,
				model=EMB_MODEL,
				embedding=pickle.dumps(embedding),
				period_start=period_start,
				period_end=period_end,
			))
			db.commit()
			LOGGER.debug(f"Inserted vault_index row for {rel_path}")
		except Exception as e:
			LOGGER.error(f"Could not insert into vault_index: {e}")
			db.rollback()

		# Bot-initiated pattern detection (monthly + quarterly only)
		if summary_type in ("monthly", "quarterly"):
			_detect_and_write_pattern(db, llm, emb, client_id, llm_output, summary_type)

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
	llm = OllamaChat(LLM_MODEL)
	# Init Embedder
	emb = OllamaEmbed(EMB_MODEL)

	today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
	summarize(summary_type, today, llm, emb, True)
	sys.exit(0)