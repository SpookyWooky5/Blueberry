# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 05-MAR-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import re
import json
import yaml

from Logging import logger_init

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("Common")

# ================================= CONSTANTS ================================ #
CFGDIR = os.environ["Xml"]

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
	return re.sub(r'<think>.*?</think>', '', s, flags=re.DOTALL)