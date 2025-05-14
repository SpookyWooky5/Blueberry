# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 14-MAY-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import re

from dotenv import load_dotenv

from Logging import logger_init

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")

# ================================= CONSTANTS ================================ #
CFGDIR = os.environ["Xml"]
load_dotenv(dotenv_path=os.path.join(CFGDIR, ".env"))

DEFAULT_CONTEXT_CONFIG = {
	# /remember[TE,2D,1W,1M,1Q]
	"remember": {
		"enable": True,
		"time_filters": {
			"daily": 2,
			"weekly": 0,
			"monthly": 0,
			"quarterly": 0
		},
		"today_emails": True
	},
	# /embeds[T/F,3]
	"embeds": {
		"enable": True,
		"topk": 3
	},
	# /readobs[T/F]
	"readobs": {
		"enable": False
	}
}

COMMAND_RE_PATTERN = r'\/.+\[.*\]'
# ================================== CLASSES ================================= #

# ================================= FUNCTIONS ================================ #
def remove_commands(body):
	return re.sub(COMMAND_RE_PATTERN, "", body)

def parse(body):
	LOGGER.debug("Parsing mail body(s) for commands")
	context_config = DEFAULT_CONTEXT_CONFIG.copy()
	
	commands = re.findall(COMMAND_RE_PATTERN, body)
	for command in commands:
		args = re.split(r'[\/,\[\]]', command)[1:-1]

		if args[0] == "remember":
			LOGGER.debug(f"Command '{args[0]}' found with args: {args[1:]}")
			context_config["remember"] = parse_remember()
		elif args[0] == "embeds":
			LOGGER.debug(f"Command '{args[0]}' found with args: {args[1:]}")
			context_config["embeds"] = parse_embeds()
		else:
			LOGGER.warning(f"Command {args[0]} is not recognized!")
			continue
	return context_config

def parse_remember(args):
	config = DEFAULT_CONTEXT_CONFIG["remember"].copy()
	for arg in args[1:]:
		match arg[-1]:
			case "":
				config["enable"] = False
			case "E":
				if arg[:-1] == "T":
					config["today_emails"] = True
				else:
					config["today_emails"] = False
			case "D":
				if arg[:-1].isnumeric():
					config["time_filters"]["daily"] = int(arg[:-1])
			case "W":
				if arg[:-1].isnumeric():
					config["time_filters"]["weekly"] = int(arg[:-1])
			case "M":
				if arg[:-1].isnumeric():
					config["time_filters"]["monthly"] = int(arg[:-1])
			case "Q":
				if arg[:-1].isnumeric():
					config["time_filters"]["quarterly"] = int(arg[:-1])
			case _:
				LOGGER.warning(f"Argument {arg} of Command {args[0]} is invalid!")
	return config

def parse_embeds(args):
	config = DEFAULT_CONTEXT_CONFIG["embeds"].copy()
	if args[1] == "T":
		config["enable"] = True
	else:
		config["enable"] = False
	if len(args) > 2 and args[2].isnumeric():
		config["topk"] = int(args[2])
	else:
		LOGGER.warning(f"Argument {args[1:]} of Command {args[0]} is invalid!")
	return config
		
# =================================== MAIN =================================== #