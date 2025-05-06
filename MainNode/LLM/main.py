# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 23-MAR-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import sys

from llama_cpp import Llama

from Common import load_config, load_secrets, read_file_from_cfg
from Common.Logging import logger_init
from Common.Database.utils import connect_to_db

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")

# ================================= CONSTANTS ================================ #
CFGDIR = os.environ["Xml"]

LLMCFG = load_config()["LLM"]

secrets   = load_secrets()
EMAIL     = secrets["Mail"]["Zoho"]["email"]
ADMINS    = secrets["Mail"]["Admins"]
CLIENTS   = secrets["Mail"]["Clients"]
del secrets

# ================================== CLASSES ================================= #
class BaseChatbot:
	def __init__(
			self,
			model_type,
		):
		self.model_type = model_type

		try:
			self.model = Llama.from_pretrained(
				repo_id=LLMCFG[model_type]["ModelName"],
				filename=LLMCFG[model_type]["ModelFile"],

				n_ctx=LLMCFG[model_type]["ContextLength"],
				chat_format=LLMCFG[model_type]["ChatFormat"] if LLMCFG[model_type]["ChatFormat"] else None,
				verbose=False
			)
			LOGGER.info(f"Initialized LLM {model_type}")
		except Exception as e:
			LOGGER.error(f"Error occured while initialzing LLM {model_type}: {e}")
			sys.exit(1)

		self.history = None
		self.interface = None
	
	def init_history(self, interface=None, client=None):
		LOGGER.debug(f"Initializing history for interface '{interface}'")
		self.interface = interface
		
		if interface == "mail":
			self.history = [
				{"role": "system", "content": read_file_from_cfg(os.path.join(CFGDIR, "prompts", "mail_prompt.txt"))},
			]
			
			# Pull Mail History from DB
			conn, curr = connect_to_db()
			curr.execute(f"SELECT * from emails WHERE to_addr='{client}' OR from_addr='{client}'")

			data = curr.fetchall()
			for i, row in enumerate(data):
				content = f"Datetime: {row[8]}\nSubject: {row[6]}\nBody:\n{row[7]}\From:{row[5]}"
				
				# Only think if latest mail has think
				if i + 1 != len(data):
					content.replace("/think", "")
				
				# Dont think be default
				if "/think" not in content:
					content += "\n/nothink"
				
				if row[2] != EMAIL:
					self.history.append(
						{"role": "assistant", "content": row[7]}
					)
				elif "/sudo" in content and row[2] in ADMINS:
					self.history.append(
						{"role": "administrator", "content": row[7]}
					)
				else:
					self.history.append(
						{"role": "user", "content": content}
					)
		
		elif interface in (None, "chat"):
			self.history = [
				{"role": "system", "content": LLMCFG["Prompts"]["ChatPrompt"]},
			]
		else:
			LOGGER.error(f"Invalid interface '{interface}'!")
			return
		
		LOGGER.debug(f"Added {len(self.history)} records to history")

	def generate_response(self, input=None):
		if self.history is None:
			# TODO error, please init history first
			LOGGER.error("Please initalize history first by calling self.init_history")
		
		try:
			LOGGER.debug(f"Generating response from history for interface '{self.interface}'")
			output = self.model.create_chat_completion(
				self.history,
				max_tokens=8196,
			)['choices'][0]['message']['content']
		except Exception as e:
			LOGGER.error(f"Could not generate a response! {e}")
			return None
		
		LOGGER.debug(f"Response generated")
		return output
		

# ================================= FUNCTIONS ================================ #

# =================================== MAIN =================================== #
if __name__ == "__main__":
	llm = BaseChatbot()