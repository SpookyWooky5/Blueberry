# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 13-MAY-2025  Initial Draft
# 12-JUL-2025  Refactor to use shared constants and add threading logic
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import time
import email
import pickle
from datetime import timedelta, datetime

import numpy as np

from LLM import BaseEmbedder
from Logging import logger_init
from MailServer import imap_auth
from Database import connect_to_dataset, get_or_create_client
from utils import (
    load_secrets,
    strip_quoted_reply,
    EMB_MODEL,
    CLIENTS,
)

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("MailServer")

# ================================= CONSTANTS ================================ #
IMAP_HOST = load_secrets()["Mail"]["Zoho"]["imap"]["host"]

# ================================== CLASSES ================================= #

# ================================= FUNCTIONS ================================ #
def fetch_mails():
	# Login to Zoho
	imap_server = imap_auth()
	imap_server.select('inbox')

	mail_ids = None
	try:
		# load clients in case of any change
		current_clients = load_secrets()["Mail"]["Clients"]
		LOGGER.debug(f"Querying unseen mails from {len(current_clients)} client(s)")

		status, _ = imap_server.noop()
		if status != 'OK':
			LOGGER.warning("IMAP NOOP Failed. Reconnecting...")
			imap_server.logout()
			imap_server = imap_auth()
			imap_server.select('inbox')

		# Select unseen mails from clients
		all_ids = set()
		for client in current_clients:
			status, data = imap_server.search(None, 'UNSEEN', 'FROM', client)
			if status == 'OK':
				ids = data[0].split()
				if ids:
					all_ids.update(ids)
		mail_ids = sorted(map(int, all_ids))

		LOGGER.info(f"Found {len(mail_ids)} mails")
	except Exception as e:
		LOGGER.debug(f"Could not fetch mails: {e}")
		return None

	imap_server.logout()

	return mail_ids

def insert_mails_to_db(mail_ids):
	if mail_ids is None or len(mail_ids) == 0:
		return
	
	# Login to Zoho
	imap_server = imap_auth()
	imap_server.select('inbox')

	# Connect to DB
	db = connect_to_dataset()
	email_table = db['emails']
	email_embed_table = db['email_embeddings']
	
	# Init Embedder
	emb = BaseEmbedder(EMB_MODEL)

	for mail_id in mail_ids:
		try:
			LOGGER.debug(f"Fetching mail {mail_id}")

			status, _ = imap_server.noop()
			if status != 'OK':
				LOGGER.warning("IMAP NOOP Failed. Reconnecting...")
				imap_server.logout()
				imap_server = imap_auth()
				imap_server.select('inbox')

			_, raw_mail_data = imap_server.fetch(str(mail_id).encode(), "(RFC822)")
		except Exception as e:
			LOGGER.error(f"Could not fetch mail {mail_id} from {IMAP_HOST}: {e}")
			continue

		try:
			raw_mail = email.message_from_bytes(raw_mail_data[0][1])
			
			subject    = raw_mail.get("Subject")
			msg_id     = raw_mail.get("Message-ID", email.utils.make_msgid())
			references = raw_mail.get("References")
			to_name,   to_addr   = email.utils.parseaddr(raw_mail.get("To"))
			from_name, from_addr = email.utils.parseaddr(raw_mail.get("From"))

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
			
			clean_body = strip_quoted_reply(body)

		except Exception as e:
			LOGGER.error(f"Error occured while decoding mail {msg_id}, {e}")
			continue

		# Check if mail in DB
		data = None
		try:
			LOGGER.debug(f"Checking if mail with msg_id {msg_id} exists in table 'emails'")
			data = email_table.find_one(message_id=msg_id)
		except Exception as e:
			LOGGER.error(f"Could not check if mail {msg_id} in table 'emails': {e}")

		# Get Client ID
		client_id = get_or_create_client(from_addr, from_name)
		if client_id == -1:
			continue

		# Add Mail to DB
		if data is None:
			db.begin()
			try:
				LOGGER.debug(f"Inserting mail {mail_id} into table 'emails'")

				email_id = email_table.insert(dict(
					client_id=client_id,
					message_id=msg_id,
					to_addr=to_addr,
					to_name=to_name,
					from_addr=from_addr,
					from_name=from_name,
					subject=subject,
					body=clean_body,
					references=references,
					time_received=mail_datetime,
					responded=0
				))
				embedding = emb.embed(subject, clean_body)
				embedding = np.array(embedding)
				email_embed_table.insert(dict(
					email_id=email_id,
					client_id=client_id,
					model=EMB_MODEL,
					embedding=pickle.dumps(embedding)
				))
				db.commit()

				LOGGER.debug("Inserted record in table 'emails'")
			except Exception as e:
				LOGGER.error(f"Could not insert mail {msg_id} in table 'emails': {e}")
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
	
# =================================== MAIN =================================== #
if __name__ == "__main__":
	insert_mails_to_db(fetch_mails())
