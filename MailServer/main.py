# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 05-MAR-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import time
import email
import pickle
import imaplib
import smtplib

from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

from Logging import logger_init
from Database import connect_to_dataset
from LLM import BaseChatbot, BaseEmbedder
from MailServer import imap_auth, check_smtp_auth
from Database.populate_db import get_or_create_client
from utils import load_secrets, load_config, escape_special_chars

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("MailServer")

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
del secrets

MAILCFG   = load_config()["MailServer"]

LLM_MODEL = os.getenv("LLM_MODEL")
EMB_MODEL = os.getenv("EMB_MODEL")

# ================================= FUNCTIONS ================================ #

def main():
	# Login to Zoho
	imap_server = imap_auth()
	imap_server.select('inbox')
	check_smtp_auth()

	# Connect to DB
	db = connect_to_dataset()
	email_table = db['emails']
	email_embed_table = db['email_embeddings']

	client_state_dict = defaultdict(int)

	# Init LLM
	llm = BaseChatbot(LLM_MODEL)
	# Init Embedder
	emb = BaseEmbedder(EMB_MODEL)

	while True:
		try:

			# Dynamically read file and load clients in case of any change
			CLIENTS = load_secrets()["Mail"]["Clients"]
			client_state_dict = defaultdict(int)
			LOGGER.debug(f"Querying unseen mails from {len(CLIENTS)} client(s)")
			
			status, _ = imap_server.noop()
			if status != 'OK':
				LOGGER.warning("IMAP NOOP Failed. Reconnecting...")
				imap_server.logout()
				imap_server = imap_auth()
				imap_server.select('inbox')

			# Select unseen mails from clients
			all_ids = set()
			for client in CLIENTS:
				status, data = imap_server.search(None, 'UNSEEN', 'FROM', client)
				if status == 'OK':
					ids = data[0].split()
					if ids:
						all_ids.update(ids)
						client_state_dict[client] = 1
			mail_ids = sorted(map(int, all_ids))

			LOGGER.info(f"Found {len(mail_ids)} mails")
		except imaplib.IMAP4.abort:
			LOGGER.debug("IMAP Connection aborted. Reconnecting...")
			imap_server = imap_auth()
			imap_server.select('inbox')
			continue
		except Exception as e:
			LOGGER.debug(f"Could not fetch mails: {e},\ntrying again in {MAILCFG['CheckInterval']} seconds")
			time.sleep(int(MAILCFG['CheckInterval']))
			continue
		
		if len(mail_ids) == 0:
			LOGGER.debug(f"No new mails found, trying again in {MAILCFG['CheckInterval']} seconds")
			time.sleep(int(MAILCFG['CheckInterval']))
			continue
			
		for mail_id in mail_ids:
			try:
				LOGGER.debug(f"Fetching mail {mail_id}")

				status, _ = imap_server.noop()
				if status != 'OK':
					LOGGER.warning("IMAP NOOP Failed. Reconnecting...")
					imap_server.logout()
					imap_server = imap_auth()
					imap_server.select('inbox')

				_, raw_mail = imap_server.fetch(str(mail_id).encode(), "(RFC822)")
			except Exception as e:
				LOGGER.error(f"Could not fetch mail {mail_id} from {IMAP_HOST}: {e}")
				continue
			
			try:
				raw_mail = email.message_from_bytes(raw_mail[0][1])
				
				subject  = raw_mail.get("Subject")
				msg_id   = raw_mail.get("Message-ID", email.utils.make_msgid())
				to_name  , to_addr   = email.utils.parseaddr(raw_mail.get("To"))
				from_name, from_addr = email.utils.parseaddr(raw_mail.get("From"))
				
				references = raw_mail.get("References", "")
				parent_refs = [
					ref.strip() for ref in references.split() 
					if ref.strip().startswith("<") and ref.strip().endswith(">")
				]
				if msg_id not in parent_refs:
					parent_refs.append(msg_id)
			
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

			data = None
			# Check if mail in DB
			try:
				LOGGER.debug(f"Checking if mail with msg_id {msg_id} exists in table 'emails'")

				data = email_table.find_one(message_id=msg_id)
			except Exception as e:
				LOGGER.error(f"Could not check if mail {msg_id} in table 'emails': {e}")
			
			# Get Client ID
			client_id = get_or_create_client(from_name, from_addr)
			if client_id == -1:
				continue

			# Add mail to DB
			if data is None:
				db.begin()
				try:
					LOGGER.debug(f"Inserting mail {mail_id} into table 'emails'")

					email_id = email_table.insert(dict(
						client_id = client_id,
						message_id = msg_id,
						to_addr = to_addr,
						to_name = to_name,
						from_addr = from_addr,
						from_name = from_name,
						subject = subject,
						body = body,
						responded = 1
					))
					embedding = emb.model.create_embedding(f"Subject:{subject}\nBody:{body}")
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
					# conn.rollback()
					db.rollback()
					continue
			else:
				LOGGER.debug(f"Mail with msg_id {msg_id} exists in table 'emails'")
			
			# Mark mail as SEEN
			status, _ = imap_server.noop()
			if status != 'OK':
				LOGGER.warning("IMAP NOOP Failed. Reconnecting...")
				imap_server.logout()
				imap_server = imap_auth()
				imap_server.select('inbox')
			imap_server.store(str(mail_id).encode(), "+FLAGS", "\\Seen")

		# Call LLM for response
		for client in CLIENTS:
			llm_output = None
			if client_state_dict[client] != 0:
				LOGGER.debug("Calling LLM to generate response")
				llm.init_history("mail")
				llm_output = llm.generate_response()
				response_msg_id = email.utils.make_msgid()
		
			# Add LLM response to DB
			if llm_output is not None:
				client_state_dict[client] = 0
				llm_output = escape_special_chars(llm_output)
				db.begin()
				try:
					LOGGER.debug(f"Inserting response of {msg_id} into table 'emails'")

					email_id = email_table.insert(dict(
						client_id = client_id,
						message_id = response_msg_id,
						to_addr = from_addr,
						to_name = from_name,
						from_addr = to_addr,
						from_name = to_name,
						subject = subject,
						body = llm_output,
						child_of = msg_id,
						responded = 1
					))
					embedding = emb.model.create_embedding(f"Subject:{subject}\nBody:{llm_output}")
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
			else:
				continue

			# Send response in reply
			response_mail = MIMEMultipart()
			response_mail["From"] = EMAIL
			response_mail["To"] = from_addr
			response_mail["Subject"] = subject
			response_mail["Message-ID"] = response_msg_id
			response_mail["In-Reply-To"] = msg_id
			response_mail["References"] = " ".join(parent_refs)

			# Thread Index
			# response_mail["Thread-Index"] = base64.b64encode(hashlib.md5(msg_id.encode()).digest()).decode()
			
			response_mail.attach(
				MIMEText(llm_output, "plain")
			)
			LOGGER.debug("Response mail formatted")

			try:
				LOGGER.debug("Sending mail to client...")
				with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp_server:
					smtp_server.login(EMAIL, PASSWORD)
					smtp_server.sendmail(EMAIL, from_addr, response_mail.as_string())
			except Exception as e:
				LOGGER.error(f"Error occured while sending mail, {e}")
				continue
	

# =================================== MAIN =================================== #
if __name__ == "__main__":
	# pass
	main()
