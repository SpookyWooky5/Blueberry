# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 11-MAY-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import time
import email
import pickle
from datetime import timedelta, datetime, date

import numpy as np
from dotenv import load_dotenv
from dateutil.relativedelta import relativedelta

from Logging import logger_init
from Database import connect_to_dataset
from LLM import BaseEmbedder, BaseChatbot
from MailServer import imap_auth, check_smtp_auth
from utils import load_secrets, load_config, escape_special_chars

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("Database")

# ================================= CONSTANTS ================================ #
CFGDIR = os.environ["Xml"]
load_dotenv(dotenv_path=os.path.join(CFGDIR, ".env"))

secrets   = load_secrets()
EMAIL     = secrets["Mail"]["Zoho"]["email"]
PASSWORD  = secrets["Mail"]["Zoho"]["password"]
IMAP_HOST = secrets["Mail"]["Zoho"]["imap"]["host"]
SMTP_HOST = secrets["Mail"]["Zoho"]["smtp"]["host"]
SMTP_PORT = secrets["Mail"]["Zoho"]["smtp"]["port"]
ADMINS    = secrets["Mail"]["Admins"]
CLIENTS   = secrets["Mail"]["Clients"]
CLIENTNAMES = secrets["Mail"]["ClientNames"]
del secrets

MAILCFG   = load_config()["MailServer"]

LLM_MODEL = os.getenv("LLM_MODEL")
EMB_MODEL = os.getenv("EMB_MODEL")

# ================================= FUNCTIONS ================================ #
def populate_clients():
	count = 0
	db = connect_to_dataset()
	for (name, email) in zip(CLIENTNAMES, CLIENTS):
		db.begin()
		try:
			db['clients'].insert_ignore(dict(
				name  = name,
				email = email
			),
			keys=['email'])
			db.commit()
			count += 1
		except Exception as e:
			LOGGER.error(f"Could not insert client into table, {e}")
			db.rollback()
	LOGGER.info(f"Inserted {count} out of {len(CLIENTS)} clients")

def populate_emails():
	# Login to Zoho
	imap_server = imap_auth()
	check_smtp_auth()

	# Connect to DB
	db = connect_to_dataset()
	email_table = db['emails']
	email_embed_table = db['email_embeddings']

	# Init Embedder
	emb = BaseEmbedder(EMB_MODEL)

	all_mails = []
	for mailbox in ('inbox', 'sent'):
		LOGGER.debug(f"Checking mails from '{mailbox}'")
		imap_server = imap_auth()
		imap_server.select(mailbox)

		for client in CLIENTS:
			try:
				if mailbox == 'inbox':
					# Select mails from clients
					status, data = imap_server.search(None, 'FROM', client)
				else:
					# Select mails to clients
					status, data = imap_server.search(None, 'TO', client)
			except Exception as e:
				LOGGER.error(f"Could not select mails from {client}: {e}")
				continue
			
			if status != 'OK':
				LOGGER.error(f"Could not select mails from {client}: {status}")
				continue
		
			mail_ids = data[0].split()
			for mail_id in mail_ids:
				try:
					status, raw_mail = imap_server.fetch(mail_id, "(RFC822)")
					raw_mail = email.message_from_bytes(raw_mail[0][1])
					mail_date = email.utils.parsedate_to_datetime(raw_mail.get("Date"))

					all_mails.append((mail_date, raw_mail))
				except Exception as e:
					LOGGER.error(f"Could not fetch mail {mail_id} from {client}: {e}")
					continue
	
	LOGGER.info(f"Found {len(all_mails)} mails")
	all_mails.sort(key=lambda tup: tup[0])

	for (mail_date, raw_mail) in all_mails:
		try:		
			subject  = raw_mail.get("Subject")
			msg_id   = raw_mail.get("Message-ID", email.utils.make_msgid())
			to_name  , to_addr   = email.utils.parseaddr(raw_mail.get("To"))
			from_name, from_addr = email.utils.parseaddr(raw_mail.get("From"))

			# Add Bot's name
			if to_addr == EMAIL and to_name == "":
				to_name = "Blueberry"
			elif from_addr == EMAIL and from_name == "":
				from_name = "Blueberry"
			
			# To store as UTC Time
			date = email.utils.parsedate(raw_mail.get("Date"))
			mail_datetime = datetime.fromtimestamp(time.mktime(date) - timedelta(hours=5, minutes=30).seconds)
			
			body = ""
			if raw_mail.is_multipart():
				for part in raw_mail.walk():
					content_type = part.get_content_type()
					if content_type == "text/plain":
						body = part.get_payload(decode=True).decode()
						break
			else:
				body = raw_mail.get_payload(decode=True).decode()
			
			body = body.replace("=E2=80=AF", " ")
			body = escape_special_chars(body.strip())
		except Exception as e:
			LOGGER.error(f"Error occured while decoding mail {msg_id}, {e}")
			continue

		# Ignore Summary emails
		if "summary" in subject.lower() and from_addr == EMAIL:
			continue

		data = None
		# Check if mail in DB
		try:
			LOGGER.debug(f"Checking if mail with msg_id {msg_id} exists in table 'emails'")

			data = email_table.find_one(message_id=msg_id)
		except Exception as e:
			LOGGER.error(f"Could not check if mail {msg_id} in table 'emails': {e}")

		# Get Client ID
		try:
			client = to_addr if from_addr == EMAIL else from_addr
			client_id = db['clients'].find_one(email=client)['id']
		except Exception as e:
			LOGGER.error(f"Could not get Client ID for {client}, {e}")
			continue

		# Add mail to DB
		if data is None:
			db.begin()
			try:
				LOGGER.debug(f"Inserting mail {msg_id} into table 'emails'")

				email_id = email_table.insert(dict(
					client_id = client_id,
					message_id = msg_id,
					to_addr = to_addr,
					to_name = to_name,
					from_addr = from_addr,
					from_name = from_name,
					subject = subject,
					body = body,
					time_received = mail_datetime,
					responded = 1
				))
				embedding = emb.model.create_embedding(f"Subject:{subject}\nBody:{body}")['data'][0]['embedding']
				embedding = np.array(embedding)
				email_embed_table.insert(dict(
					email_id = email_id,
					client_id = client_id,
					model = EMB_MODEL,
					embedding = pickle.dumps(embedding)
				))
				db.commit()

				LOGGER.debug("Inserted record in table 'emails'")
			except Exception as e:
				LOGGER.error(f"Could not insert mail {msg_id} in table 'emails': {e}")
				db.rollback()
				continue
		else:
			LOGGER.debug(f"Mail with msg_id {msg_id} exists in table 'emails'")

def populate_memories():
	from LLM import summarize

	# Init LLM
	llm = BaseChatbot(LLM_MODEL)
	# Init Embedder
	emb = BaseEmbedder(EMB_MODEL)

	# Connect to DB
	db = connect_to_dataset()
	email_table = db['emails']
	memory_table = db['memories']

	earliest = email_table.find_one(order_by='time_received')
	latest = email_table.find_one(order_by='-time_received')
	min_date = earliest["time_received"].date()
	max_date = latest["time_received"].date()

	def memory_exists(memory_type, period_start, period_end):
		return memory_table.find_one(memory_type=memory_type,
									period_start=period_start,
									period_end=period_end) is not None

	def summarize_if_missing(summary_type, period_start, period_end, respond):
		if not memory_exists(summary_type, period_start, period_end):
			summarize.summarize(summary_type, period_end, llm, emb, respond)
	
	# Daily summaries
	day = min_date
	while day < max_date:
		period_start = day
		period_end = day + timedelta(days=1)
		summarize_if_missing("daily", period_start, period_end, False)
		day += timedelta(days=1)

	# Weekly summaries (period ends on Sunday)
	week_end = min_date + timedelta(days=(6 - min_date.weekday()))  # first Sunday
	while week_end < max_date:
		period_start = week_end - timedelta(days=7)
		summarize_if_missing("weekly", period_start, week_end, False)
		week_end += timedelta(weeks=1)

	# Monthly summaries (1st to 1st of next month)
	# month_start = date(min_date.year, min_date.month, 1)
	# while month_start < max_date:
	# 	month_end = month_start + relativedelta(months=1)
	# 	summarize_if_missing("monthly", month_start, month_end, False)
	# 	month_start = month_end

	# Quarterly summaries (first of every 3rd month)
	# q_month = ((min_date.month - 1) // 3) * 3 + 1
	# quarter_start = date(min_date.year, q_month, 1)
	# while quarter_start < max_date:
	# 	quarter_end = quarter_start + relativedelta(months=3)
	# 	summarize_if_missing("quarterly", quarter_start, quarter_end, False)
	# 	quarter_start = quarter_end

# =================================== MAIN =================================== #
if __name__ == "__main__":
	populate_clients()
	populate_emails()
	populate_memories()
