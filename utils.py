# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 05-MAR-2025  Initial Draft
# 12-JUL-2025  Add shared constants and prompt reader
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import re
import json
import yaml

from dotenv import load_dotenv
from Logging import logger_init

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("Common")

# ================================= CONSTANTS ================================ #
# --- Directories ---
CFGDIR = os.environ["Xml"]
PROMPTS_DIR = "/home/mainberry/Dev/prompts"

# --- Environment Variables ---
load_dotenv(dotenv_path=os.path.join(CFGDIR, ".env"))
LLM_MODEL = os.getenv("LLM_MODEL")
EMB_MODEL = os.getenv("EMB_MODEL")


# ================================= FUNCTIONS ================================ #
def load_secrets(filename="secrets.yml"):
	with open(os.path.join(os.environ["Xml"], filename), "r") as fp:
		try:
			LOGGER.debug(f"Opening <{filename}> from Config")
			data = yaml.safe_load(fp)
		except Exception as e:
			LOGGER.error(f"Error while opening <{filename}>, " + e)
	return data

def load_config():
	with open(os.path.join(CFGDIR, "process.json"), "r") as fp:
		try:
			data = json.load(fp)
		except Exception as e:
			print(e)
	return data

def read_file_from_cfg(filepath):
	# filename = filename.strip().lower().replace("_", "").replace(" ", "").split(".")[0]
	LOGGER.debug(f"Opening {filepath} from Config")
	try:
		with open(os.path.join(CFGDIR, filepath)) as f:
			return "\n".join(f.readlines())
	except Exception as e:
		LOGGER.error(f"Unable to open {filepath}, {e}")

def read_prompt_from_file(filename):
    """Reads a prompt from the global prompts directory."""
    path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        LOGGER.error(f"Prompt file not found: {path}")
        return None

def escape_special_chars(s):
	s = re.sub(r'(\r\n|\r|\n)+', '\n', s)
	def replacer(match):
		ch = match.group(0)
		return {
			'\\': '\\\\',
			'\n': '\\n',
			'\r': '\\r',
			'\t': '\\t',
			'"': '""'
		}[ch]
	return re.sub(r'[\\\n\r\t"]', replacer, s)

def remove_think_blocks(s):
	return re.sub(r'<think>[\s\S]*?<\/think>', '', s, flags=re.DOTALL).strip()


# --- Mail Server Configuration ---
SECRETS = load_secrets()
MAIL_CONFIG = SECRETS.get("Mail", {})
ZOHO_CONFIG = MAIL_CONFIG.get("Zoho", {})
SMTP_CONFIG = ZOHO_CONFIG.get("smtp", {})

EMAIL = ZOHO_CONFIG.get("email")
PASSWORD = ZOHO_CONFIG.get("password")
SMTP_HOST = SMTP_CONFIG.get("host")
SMTP_PORT = SMTP_CONFIG.get("port")
CLIENTS = MAIL_CONFIG.get("Clients", [])
CLIENTNAMES = MAIL_CONFIG.get("ClientNames", [])