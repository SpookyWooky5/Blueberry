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

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from Common import load_secrets, load_config
from Common.Logging import logger_init
from Common.Database import connect_to_db

from MainNode.LLM.main import BaseChatbot

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

def check_smtp_auth():
	LOGGER.debug("Logging into blueberry SMTP...")
	try:
		mailserver = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
		mailserver.login(EMAIL, PASSWORD)
		LOGGER.info("Logged in to blueberry SMTP")
	except Exception as e:
		LOGGER.error(f"Could not log into SMTP: {e}")
		sys.exit(1)

def main():
	# Login to Zoho
	imap_server = imap_auth()
	check_smtp_auth()

	# Connect to DB
	conn, curr = connect_to_db()

	# Init LLM
	llm = BaseChatbot("Qwen3Full")

	while True:
		try:
			# Select unseen mails from clients
			LOGGER.debug(f"Querying unseen mails from {len(CLIENTS)} client(s)")
			
			status, _ = imap_server.noop()
			if status != 'OK':
				LOGGER.warning("IMAP NOOP Failed. Reconnecting...")
				imap_server.logout()
				imap_server = imap_auth()

			all_ids = set()
			for client in CLIENTS:
				status, data = imap_server.search(None, 'UNSEEN', 'FROM', client)
				if status == 'OK':
					ids = data[0].split()
					all_ids.update(ids)
			mail_ids = list(all_ids)

			LOGGER.info(f"Found {len(mail_ids)} mails")
		except imaplib.IMAP4.abort:
			LOGGER.debug("IMAP Connection aborted. Reconnecting...")
			imap_server = imap_auth()
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

				_, raw_mail = imap_server.fetch(mail_id, "(RFC822)")
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
						from_addr, from_name, subject, body)
					)
					conn.commit()
					LOGGER.debug("Inserted record in table 'emails'")
				except Exception as e:
					LOGGER.error(f"Could not insert mail {msg_id} in table 'emails': {e}")
					conn.rollback()
					continue
			else:
				LOGGER.debug(f"Mail with msg_id {msg_id} exists in table 'emails'")
			
			# Mark mail as SEEN
			status, _ = imap_server.noop()
			if status != 'OK':
				LOGGER.warning("IMAP NOOP Failed. Reconnecting...")
				imap_server.logout()
				imap_server = imap_auth()
			imap_server.store(mail_id, "+FLAGS", "\\Seen")



		# Call LLM for response
		LOGGER.debug("Calling LLM to generate response")
		llm.init_history("mail", from_addr)
		llm_output = llm.generate_response()
		response_msg_id = email.utils.make_msgid()
		
		# Add LLM response to DB
		if llm_output is not None:
			try:
				LOGGER.debug(f"Inserting response of {msg_id} into table 'emails'")
				curr.execute(
					'''
					INSERT INTO emails(message_id, to_addr, to_name, from_addr,
					from_name, subject, body, child_of) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
					''',
					(response_msg_id, from_addr, from_name,
					to_addr, to_name, subject,
					llm_output, mail_id)
				)
				conn.commit()
				LOGGER.debug("Inserted record in table 'emails'")
			except Exception as e:
				LOGGER.error(f"Could not insert mail {msg_id} in table 'emails': {e}")
				conn.rollback()
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
