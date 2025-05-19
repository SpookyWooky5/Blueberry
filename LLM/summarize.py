# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 15-MAY-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import sys
import email
import pickle
import smtplib
from email.mime.text import MIMEText
from datetime import timedelta, datetime
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv
from dateutil.relativedelta import relativedelta

from Logging import logger_init
from LLM import BaseChatbot, BaseEmbedder
from Database import connect_to_dataset, get_or_create_client
from utils import (
    load_config,
    load_secrets,
    read_file_from_cfg,
	remove_think_blocks,
    escape_special_chars,
)

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")

# ================================= CONSTANTS ================================ #
CFGDIR = os.environ["Xml"]
load_dotenv(dotenv_path=os.path.join(CFGDIR, ".env"))

LLMCFG = load_config()["LLM"]

secrets   = load_secrets()
EMAIL     = secrets["Mail"]["Zoho"]["email"]
PASSWORD  = secrets["Mail"]["Zoho"]["password"]
SMTP_HOST = secrets["Mail"]["Zoho"]["smtp"]["host"]
SMTP_PORT = secrets["Mail"]["Zoho"]["smtp"]["port"]
CLIENTS   = secrets["Mail"]["Clients"]
CLIENTNAMES = secrets["Mail"]["ClientNames"]
del secrets

LLM_MODEL = os.getenv("LLM_MODEL")
EMB_MODEL = os.getenv("EMB_MODEL")

# ================================== CLASSES ================================= #

# ================================= FUNCTIONS ================================ #
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
		subject = f'{summary_type.capitalize()} Summary from {period_start.strftime("%a, %d %B")} to {period_end.strftime("%a, %d %B")}'
	else:
		subject = f'{summary_type.capitalize()} Summary {period_end.strftime("%a, %d %B")}'

	for client, client_name in zip(CLIENTS, CLIENTNAMES):
		client_id = get_or_create_client(client, client_name)
		if client_id == -1:
			continue
		query["client_id"] = client_id

		try:
			records = tuple(table.find(**query, order_by='id'))
		except Exception as e:
			LOGGER.error(f"Could not retrieve data, {e}")
			continue
		if len(records) == 0:
			LOGGER.info(f"No data to summarize for client {client_id}")
			continue

		content = [cfg["begin_tag"]]
		if summary_type == "daily":
			for r in records:
				# content.append(f"\nTo: {r['to_name']}\nDatetime: {r['time_received']}\nSubject: {r['subject']}\nBody:\n{r['body']}\nFrom: {r['from_name']}")
				content.append(f'''[EMAIL]
From: {r["from_name"]}
To: {r["to_name"]}
Date: {r["time_received"]}
Subject: {r["subject"]}
Body:
{r["body"]}\n''')
		else:
			for r in records:
				content.append(f"\nDate: {r['created_at']}\nSummary:\n{r['text']}")
		content.append(cfg["begin_tag"].replace("BEGIN", "END"))
		content = "\n".join(content)
		content.replace("/think", "")
		content = remove_think_blocks(content)

		prompt = escape_special_chars(read_file_from_cfg(os.path.join("prompts", "summary_prompt.txt")))
		prompt = prompt.format(
			client_name = client_name,
			today = period_end.strftime("%a, %d %B"),
			summary_type = summary_type,
			header = cfg["header"].format(
				client_name = client_name
			),
			content = content
		)

		history = [{
			"role": "system",
			"content": prompt
		}]
		llm.init_history('summary', history)

		LOGGER.info("Calling LLM to generate a reply")
		llm_output = llm.generate_response()
		if llm_output is None:
			continue
		llm_output = escape_special_chars(llm_output)

		# Add summary to Memory DB
		db.begin()
		try:
			LOGGER.debug(f'Inserting {subject} for client {client_id} to memory')

			memory_id = mem_table.insert(dict(
				client_id = client_id,
				memory_type = summary_type,
				text = llm_output,
				period_start = period_start,
				period_end = period_end,
			))
			embedding = emb.embed(subject, llm_output)
			mem_emb_table.insert(dict(
				memory_id = memory_id,
				client_id = client_id,
				model = EMB_MODEL,
				embedding = pickle.dumps(embedding)
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

			response_mail.attach(
				MIMEText(llm_output, "plain")
			)
			LOGGER.debug("Response mail formatted")

			try:
				LOGGER.debug("Sending mail to client...")
				with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp_server:
					smtp_server.login(EMAIL, PASSWORD)
					smtp_server.sendmail(EMAIL, client, response_mail.as_string())
			except Exception as e:
				LOGGER.error(f"Error occured while sending mail, {e}")
				continue

def old_summ(summary_type, start_date, llm, emb, respond = True):
	# Connect to DB
	db = connect_to_dataset()
	email_table = db['emails']
	memory_table = db['memories']
	memory_embed_table = db['memory_embeddings']

	for client, client_name in zip(CLIENTS, CLIENTNAMES):
		client_id = get_or_create_client(client, client_name)
		if client_id == -1:
			continue

		match summary_type:
			case "daily":
				period_start = start_date - timedelta(days=1)
				period_end = start_date

				# Fetch all mails from client from period
				try:
					data = email_table.find(
						client_id = client_id,
						responded = 1,
						time_received = {
							'gt': period_start,
							'lt': period_end
						},
						order_by  = 'id'
					)
					data = tuple(data)
				except Exception as e:
					LOGGER.error(f"Could not find previous day's mails, {e}")
					continue

				if len(data) == 0:
					LOGGER.info(f"No data to summarize for client {client_id}")
					continue

				content = f'Below are the previous day\'s emails exchanged between you and the client {client_name}. The emails are ordered from oldest to newest:\n'
				content += '--- BEGIN EMAILS ---'
				for row in data:
					content += f'\nTo: {row["to_name"]}\nDatetime: {row["time_received"]}\nSubject: {row["subject"]}\nBody:\n{row["body"]}\nFrom: {row["from_name"]}'
				content += '--- END EMAILS ---'

			case "weekly":
				period_start = start_date - timedelta(days=7)
				period_end = start_date

				# Fetch all summaries from client from period
				try:
					data = memory_table.find(
						client_id = client_id,
						memory_type = 'daily',
						period_start__gte = period_start,
						period_end__lte = period_end,
						order_by  = 'id'
					)
					data = tuple(data)
				except Exception as e:
					LOGGER.error(f"Could not find previous daily summaries, {e}")
					continue

				if len(data) == 0:
					LOGGER.info(f"No data to summarize for client {client_id}")
					continue

				content = f'Below are the previous daily summaries recorded by you for the client {client_name}. The summaries are ordered from oldest to newest:\n'
				content += '--- BEGIN DAILY SUMMARIES ---'
				for row in data:
					content += f'\nDate: {row["created_at"]}\nSummary:\n{row["text"]}'
				content += '--- END DAILY SUMMARIES ---'

			case "monthly":
				period_start = start_date - relativedelta(months=1)
				period_end = start_date

				# Fetch all summaries from client from period
				try:
					data = memory_table.find(
						client_id = client_id,
						memory_type = 'daily',
						period_start__gte = period_start,
						period_end__lte = period_end,
						order_by  = 'id'
					)
					data = tuple(data)
				except Exception as e:
					LOGGER.error(f"Could not find previous daily summaries, {e}")
					continue

				if len(data) == 0:
					LOGGER.info(f"No data to summarize for client {client_id}")
					continue

				content = f'Below are the previous daily summaries recorded by you for the client {client_name}. The summaries are ordered from oldest to newest:\n'
				content += '--- BEGIN DAILY SUMMARIES ---'
				for row in data:
					content += f'\nDate: {row["created_at"]}\nSummary:\n{row["text"]}'
				content += '--- END DAILY SUMMARIES ---'

			case "quarterly":
				period_start = start_date - relativedelta(months=3)
				period_end = start_date

				# Fetch all summaries from client from period
				try:
					data = memory_table.find(
						client_id = client_id,
						memory_type = 'weekly',
						period_start__gte = period_start,
						period_end__lte = period_end,
						order_by  = 'id'
					)
					data = tuple(data)
				except Exception as e:
					LOGGER.error(f"Could not find previous weekly summaries, {e}")
					continue

				if len(data) == 0:
					LOGGER.info(f"No data to summarize for client {client_id}")
					continue

				content = f'Below are the previous weekly summaries recorded by you for the client {client_name}. The summaries are ordered from oldest to newest:\n'
				content += '--- BEGIN WEEKLY SUMMARIES ---'
				for row in data:
					content += f'\nDate: {row["created_at"]}\nSummary:\n{row["text"]}'
				content += '--- END WEEKLY SUMMARIES ---'

		content.replace("/think", "")
		content += "\n/nothink"

		history = [{
			"role": "system",
			"content": read_file_from_cfg(os.path.join("prompts", "summary_prompt.txt")) + content
		}]
		llm.init_history('summary', history)

		LOGGER.info("Calling LLM to generate a reply")
		llm_output = llm.generate_response()
		if llm_output is None:
			continue
		
		llm_output = escape_special_chars(llm_output)
		
		if summary_type != "daily":
			subject = f'{summary_type.capitalize()} Summary from {period_start.strftime("%a, %d %B")} to {period_end.strftime("%a, %d %B")}'
		else:
			subject = f'{summary_type.capitalize()} Summary {period_end.strftime("%a, %d %B")}'

		# Add summary to Memory DB
		db.begin()
		try:
			LOGGER.debug(f'Inserting {subject} for client {client_id} to memory')

			memory_id = memory_table.insert(dict(
				client_id = client_id,
				memory_type = summary_type,
				text = llm_output,
				period_start = period_start,
				period_end = period_end,
			))
			embedding = emb.embed(subject, llm_output)
			memory_embed_table.insert(dict(
				memory_id = memory_id,
				client_id = client_id,
				model = EMB_MODEL,
				embedding = pickle.dumps(embedding)
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

			response_mail.attach(
				MIMEText(llm_output, "plain")
			)
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
	# Init LLM
	llm = BaseChatbot(LLM_MODEL)
	# Init Embedder
	emb = BaseEmbedder(EMB_MODEL)

	today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
	summarize(sys.argv[1], today, llm, emb, True)