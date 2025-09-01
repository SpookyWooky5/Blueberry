# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 04-AUG-2025  Initial Draft. Add dry-run option. Add more print details.
# ============================================================================ #

# ================================== IMPORTS ================================= #
import email
import argparse
from Logging import logger_init
from MailServer import imap_auth
from Database import connect_to_dataset
from utils import EMAIL # Import the assistant's email address

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("MailServer")

# ================================= FUNCTIONS ================================ #
def purge_trash(dry_run=False):
    """
    Fetches all mails from the 'Trash' mailbox and removes them from the database.
    It does not delete the emails from the mail server.
    A dry run option is available to list the mails that would be deleted.
    """
    if dry_run:
        LOGGER.info("--- Starting Mail Trash Purge (Dry Run) ---")
    else:
        LOGGER.info("--- Starting Mail Trash Purge ---")

    try:
        imap_server = imap_auth()
        db = connect_to_dataset()
        email_table = db['emails']
    except Exception as e:
        LOGGER.error(f"Failed to initialize connections: {e}")
        return

    deleted_count = 0
    to_be_deleted_count = 0
    try:
        mailbox = 'Trash'
        imap_server.select(mailbox)
        
        status, data = imap_server.search(None, 'ALL')
        if status != 'OK':
            LOGGER.error("Could not search for mails in Trash.")
            return

        mail_ids = data[0].split()
        LOGGER.info(f"Found {len(mail_ids)} emails in '{mailbox}' to check for purging.")

        for mail_id in mail_ids:
            msg_id = None
            try:
                # Fetch the full header to get more info for the dry run
                _, raw_mail_data = imap_server.fetch(mail_id, "(BODY[HEADER])")
                header_text = raw_mail_data[0][1].decode()
                headers = email.message_from_string(header_text)
                
                msg_id = headers.get("Message-ID")
                if not msg_id:
                    LOGGER.warning(f"Could not extract Message-ID for mail {mail_id}. Skipping.")
                    continue

                # Check if the email exists in the database
                db_entry = email_table.find_one(message_id=msg_id)
                if not db_entry:
                    LOGGER.debug(f"Mail with Message-ID {msg_id} was in server trash but not found in DB.")
                    continue

                if dry_run:
                    to_be_deleted_count += 1
                    
                    subject = headers.get("Subject", "No Subject")
                    date = headers.get("Date", "No Date")
                    
                    # Determine client email
                    from_name, from_addr = email.utils.parseaddr(headers.get("From"))
                    to_name, to_addr = email.utils.parseaddr(headers.get("To"))
                    client_email = from_addr if to_addr == EMAIL else to_addr

                    log_msg = (f"DRY RUN: Would delete email with Message-ID: {msg_id} | "
                               f"Subject: '{subject}' | From: {from_addr}")
                    LOGGER.info(log_msg)
                    print(f"  - Subject: {subject}\n    Client: {client_email}\n    Date: {date}\n")

                else:
                    # Delete from database using the message_id
                    LOGGER.debug(f"Deleting email with Message-ID: {msg_id} from database.")
                    result = email_table.delete(message_id=msg_id)
                    
                    if result:
                        deleted_count += 1
                        LOGGER.info(f"Successfully deleted mail {msg_id} from the database.")

            except Exception as e:
                LOGGER.error(f"Failed to process mail {mail_id} (Message-ID: {msg_id}): {e}")

    except Exception as e:
        LOGGER.error(f"An error occurred during the purge process: {e}")
    finally:
        imap_server.logout()
        if dry_run:
            LOGGER.info(f"Purge dry run complete. Found {to_be_deleted_count} email(s) that would be deleted from the database.")
        else:
            LOGGER.info(f"Purge complete. Deleted {deleted_count} email(s) from the database.")

# =================================== MAIN =================================== #
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purge trashed emails from the database.")
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="List emails that would be deleted without actually deleting them."
    )
    args = parser.parse_args()

    purge_trash(dry_run=args.dry_run)
    LOGGER.info("--- Mail Trash Purge Script Finished ---")