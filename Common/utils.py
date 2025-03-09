# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 05-MAR-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import json
import yaml

from Common.Logging import logger_init

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