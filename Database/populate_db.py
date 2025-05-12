# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 11-MAY-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import email
import pickle

from utils import load_secrets, load_config, escape_special_chars
from Logging import logger_init
from Database import connect_to_dataset
from MailServer import imap_auth, check_smtp_auth
from LLM import BaseEmbedder

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("Database")

# ================================= CONSTANTS ================================ #
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

EMB_MODEL = "NomicEmbedV2"

# ================================= FUNCTIONS ================================ #

def populate_clients():
	count = 0
	db = connect_to_dataset()
	for (name, email) in zip(CLIENTNAMES, CLIENTS):
		db.begin()
		try:
			db['clients'].insert(dict(
				name  = name,
				email = email
			))
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
	# conn, curr = connect_to_db()
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
				db.rollback()
				continue
		else:
			LOGGER.debug(f"Mail with msg_id {msg_id} exists in table 'emails'")

# =================================== MAIN =================================== #
if __name__ == "__main__":
	populate_clients()
	populate_emails()
