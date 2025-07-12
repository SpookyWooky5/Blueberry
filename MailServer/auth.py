# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 07-MAR-2025  Initial Draft
# 12-JUL-2025  Refactor to use shared constants from utils
# ============================================================================ #

# ================================== IMPORTS ================================= #
import sys
import smtplib
import imaplib

from Logging import logger_init
from utils import (
    EMAIL,
    PASSWORD,
    SMTP_HOST,
    SMTP_PORT,
)

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("MailServer")

# ================================= CONSTANTS ================================ #
# Note: IMAP_HOST is loaded from secrets within imap_auth for now
# to avoid circular dependency if we move imap_auth to utils.

# ================================= FUNCTIONS ================================ #
def imap_auth():
	LOGGER.debug("Logging into blueberry IMAP...")
	try:
		# IMAP_HOST is intentionally loaded here to keep auth logic separate
		from utils import load_secrets
		IMAP_HOST = load_secrets()["Mail"]["Zoho"]["imap"]["host"]
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