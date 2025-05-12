# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 07-MAR-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import sys
import smtplib
import imaplib

from Common import load_secrets
from Common.Logging import logger_init

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("MailServer")

# ================================= CONSTANTS ================================ #
secrets   = load_secrets()
EMAIL     = secrets["Mail"]["Zoho"]["email"]
PASSWORD  = secrets["Mail"]["Zoho"]["password"]
IMAP_HOST = secrets["Mail"]["Zoho"]["imap"]["host"]
SMTP_HOST = secrets["Mail"]["Zoho"]["smtp"]["host"]
SMTP_PORT = secrets["Mail"]["Zoho"]["smtp"]["port"]
del secrets

# ================================= FUNCTIONS ================================ #
def imap_auth():
	LOGGER.debug("Logging into blueberry IMAP...")
	try:
		mailserver = imaplib.IMAP4_SSL(IMAP_HOST)
		mailserver.login(EMAIL, PASSWORD)
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
