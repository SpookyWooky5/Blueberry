# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 11-MAY-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import email

from Common import load_secrets, load_config, escape_special_chars
from Common.Logging import logger_init
from Common.Database import connect_to_db
from MainNode.MailServer.auth import imap_auth, check_smtp_auth


# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("MailServer")

# ================================= CONSTANTS ================================ #
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

# ================================= FUNCTIONS ================================ #

def populate_db():
	# Login to Zoho
	imap_server = imap_auth()
	check_smtp_auth()

	# Connect to DB
	conn, curr = connect_to_db()

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
			body = body.strip()
		except Exception as e:
			LOGGER.error(f"Error occured while decoding mail {msg_id}, {e}")
			continue

		data = None
		# Check if mail in DB
		try:
			LOGGER.debug(f"Checking if mail with msg_id {msg_id} exists in table 'emails'")
			curr.execute(
				"SELECT * FROM emails WHERE message_id=?",
				(msg_id,)
			)
			data = curr.fetchone()
		except Exception as e:
			LOGGER.error(f"Could not check if mail {msg_id} in table 'emails': {e}")
		
		# Add mail to DB
		if data is None:
			try:
				LOGGER.debug(f"Inserting mail {mail_id} into table 'emails'")
				curr.execute(
					'''
					INSERT INTO emails(message_id, to_addr, to_name, from_addr,
					from_name, subject, body) VALUES (?, ?, ?, ?, ?, ?, ?)
					''',
					(msg_id, to_addr, to_name,
					from_addr, from_name, subject,
					escape_special_chars(body))
				)
				conn.commit()
				LOGGER.debug("Inserted record in table 'emails'")
			except Exception as e:
				LOGGER.error(f"Could not insert mail {msg_id} in table 'emails': {e}")
				conn.rollback()
				continue
		else:
			LOGGER.debug(f"Mail with msg_id {msg_id} exists in table 'emails'")

# =================================== MAIN =================================== #
if __name__ == "__main__":
	populate_db()
