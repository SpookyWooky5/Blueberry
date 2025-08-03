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

from Logging import logger_init
from utils import CFGDIR

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")

# ================================= CONSTANTS ================================ #

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
	return re.sub(COMMAND_RE_PATTERN, "", body).strip()

def parse(body):
	LOGGER.debug("Parsing mail body(s) for commands")
	# Start with a deep copy of the defaults
	context_config = {
		"remember": DEFAULT_CONTEXT_CONFIG["remember"].copy(),
		"embeds": DEFAULT_CONTEXT_CONFIG["embeds"].copy(),
		"readobs": DEFAULT_CONTEXT_CONFIG["readobs"].copy()
	}
	
	commands = re.findall(COMMAND_RE_PATTERN, body)
	for command in commands:
		# Extract command and args, filtering out empty strings from split
		parts = [p for p in re.split(r'[\/,\[\]]', command) if p]
		if not parts:
			continue
		
		cmd_name = parts[0]
		cmd_args = parts # Pass the whole list including the command name

		if cmd_name == "remember":
			LOGGER.debug(f"Command '{cmd_name}' found with args: {cmd_args[1:]}")
			context_config["remember"] = parse_remember(cmd_args)
		elif cmd_name == "embeds":
			LOGGER.debug(f"Command '{cmd_name}' found with args: {cmd_args[1:]}")
			context_config["embeds"] = parse_embeds(cmd_args)
		else:
			LOGGER.warning(f"Command {cmd_name} is not recognized!")
			continue
	return context_config

def parse_remember(args):
	config = DEFAULT_CONTEXT_CONFIG["remember"].copy()
	# args[0] is the command name, so iterate from args[1]
	for arg in args[1:]:
		arg = arg.upper()
		# Handle simple enable/disable flags
		if arg == 'T':
			config["enable"] = True
			continue
		if arg == 'F':
			config["enable"] = False
			continue

		value_str = arg[:-1]
		unit = arg[-1]

		if unit == "E":
			config["today_emails"] = (value_str == "T")
		elif unit == "D" and value_str.isnumeric():
			config["time_filters"]["daily"] = int(value_str)
		elif unit == "W" and value_str.isnumeric():
			config["time_filters"]["weekly"] = int(value_str)
		elif unit == "M" and value_str.isnumeric():
			config["time_filters"]["monthly"] = int(value_str)
		elif unit == "Q" and value_str.isnumeric():
			config["time_filters"]["quarterly"] = int(value_str)
		else:
			LOGGER.warning(f"Argument '{arg}' for command '{args[0]}' is invalid!")
	return config

def parse_embeds(args):
	config = DEFAULT_CONTEXT_CONFIG["embeds"].copy()
	if len(args) > 1:
		enable_arg = args[1].upper()
		if enable_arg in ["T", "TRUE"]:
			config["enable"] = True
		elif enable_arg in ["F", "FALSE"]:
			config["enable"] = False
	
	if len(args) > 2 and args[2].isnumeric():
		config["topk"] = int(args[2])
	
	return config
		
# =================================== MAIN =================================== #