# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 05-MAR-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import sys
import time
import email
import imaplib
import smtplib

from Common import load_secrets, load_config
from Common.Logging import logger_init
from Common.Database import connect_to_db

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("MailServer")

# ================================= CONSTANTS ================================ #
secrets   = load_secrets()
EMAIL     = secrets["Mail"]["Zoho"]["email"]
PASSWORD  = secrets["Mail"]["Zoho"]["password"]
IMAP_HOST = secrets["Mail"]["Zoho"]["imap"]["host"]
ADMINS    = secrets["Mail"]["Admins"]
CLIENTS   = secrets["Mail"]["Clients"]
del secrets

MAILCFG   = load_config()["MailServer"]
# ================================= FUNCTIONS ================================ #
def imap_auth():
	LOGGER.debug("Logging into blueberry IMAP...")

	try:
		mailserver = imaplib.IMAP4_SSL(IMAP_HOST)
		mailserver.login(EMAIL, PASSWORD)
		mailserver.select('inbox')
		LOGGER.info("Logged in to blueberry IMAP")
	except Exception as e:
		LOGGER.error(f"Could not log into IMAP: {e}")
		sys.exit(1)
	return mailserver

def main():
	# Login to Zoho
	imap_server = imap_auth()

	# Connect to DB
	conn, curr = connect_to_db()

	# Select unseen mails from clients
	criteria = f'FROM "{CLIENTS[0]}"'
	for client in CLIENTS[1:]:
		criteria += f' OR FROM "{client}"'
	criteria += ' UNSEEN'
	LOGGER.debug(f"Querying unseen mails from {len(CLIENTS)} client(s)")

	while True:
		try:
			_, mail_ids = imap_server.search(None, criteria)
			mail_ids = mail_ids[0].split()
			LOGGER.info(f"Found {len(mail_ids)} mails")
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
				_, raw_mail = imap_server.fetch(mail_id, "(RFC822)")

				# Mark mail as SEEN
				imap_server.store(mail_id, "+FLAGS", "\\Seen")
			except Exception as e:
				LOGGER.error(f"Could not fetch mail {mail_id} from {IMAP_HOST}: {e}")
				continue

			raw_mail = email.message_from_bytes(raw_mail[0][1])
			
			subject  = raw_mail.get("Subject")
			msg_id   = raw_mail.get("Message-ID")
			to_name, to_addr     = email.utils.parseaddr(raw_mail.get("To"))
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
			body = body.strip()

			try:
				LOGGER.debug("Inserting mail into table 'emails'")
				curr.execute(
					'''
				 	INSERT INTO emails(message_id, to_addr, to_name, from_addr,
				 	from_name, subject, body) VALUES (?, ?, ?, ?, ?, ?, ?)
				 	''',
					(msg_id, to_addr, to_name,
	  				 from_addr, from_name, subject, body)
				)
				conn.commit()
				LOGGER.debug("Inserted record in table 'emails'")
			except Exception as e:
				LOGGER.error(f"Could not insert mail {mail_id} in table 'emails': {e}")
				conn.rollback()
			break
		break
		

# =================================== MAIN =================================== #
if __name__ == "__main__":
	# pass
	main()
