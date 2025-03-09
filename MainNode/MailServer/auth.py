# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 07-MAR-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import email
import smtplib
import imaplib

from typing import List

from Common import load_secrets
from Common.Logging import logger_init

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("MailServer")

# ================================= CONSTANTS ================================ #
secrets   = load_secrets()
EMAIL     = secrets["Mail"]["Zoho"]["email"]
PASSWORD  = secrets["Mail"]["Zoho"]["password"]
IMAP_HOST = secrets["Mail"]["Zoho"]["imap"]["host"]
del secrets

# ================================= FUNCTIONS ================================ #
def mailserver_init():
    mailserver = imaplib.IMAP4_SSL(IMAP_HOST)
    mailserver.login(EMAIL, PASSWORD)
    mailserver.select('inbox')

    return mailserver
