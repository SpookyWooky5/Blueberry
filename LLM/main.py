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

import numpy as np
from llama_cpp import Llama
from dotenv import load_dotenv

from Logging import logger_init
from LLM.parse import remove_commands
from Database import connect_to_dataset
from utils import load_config, load_secrets, read_file_from_cfg

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")

# ================================= CONSTANTS ================================ #
CFGDIR = os.environ["Xml"]
load_dotenv(dotenv_path=os.path.join(CFGDIR, ".env"))

LLMCFG = load_config()["LLM"]

secrets   = load_secrets()
EMAIL     = secrets["Mail"]["Zoho"]["email"]
ADMINS    = secrets["Mail"]["Admins"]
CLIENTS   = secrets["Mail"]["Clients"]
del secrets

# ================================== CLASSES ================================= #
class BaseEmbedder:
	def __init__(
			self,
			model_type,
		):
		self.model_type = model_type

		try:
			self.model = Llama.from_pretrained(
				repo_id=LLMCFG[model_type]["ModelName"],
				filename=LLMCFG[model_type]["ModelFile"],
				local_dir=os.path.join(os.environ["Dev"], "LLM", "models"),
				embedding=True,
				verbose=False
			)
			LOGGER.info(f"Initialized Embedder {model_type}")
		except Exception as e:
			LOGGER.error(f"Error occured while initialzing Embedder {model_type}: {e}")
			sys.exit(1)
	
	def embed(self, subject, body):
		return np.array(
			self.model.create_embedding(f"Subject:{subject}\nBody:{remove_commands(body)}")['data'][0]['embedding']
		)

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
	
	def init_history(self, interface=None, history=None):
		LOGGER.debug(f"Initializing history for interface '{interface}'")

		self.interface = interface
		if history is not None:
			self.history = history
			return
		
		if interface == "mail":
			self.history = [
				{"role": "system", "content": read_file_from_cfg(os.path.join("prompts", "mail_prompt.txt"))},
			]
			
			# Pull Mail History from DB
			db = connect_to_dataset()
			email_table = db['emails']

			client_id = db['clients'].find_one()['id']
			data = email_table.find(client_id=client_id)[-int(os.getenv("NUM_MAILS_TO_REFER")):]
			
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
				# elif "/sudo" in content and row[2] in ADMINS:
				# 	self.history.append(
				# 		{"role": "administrator", "content": row[7]}
				# 	)
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
			LOGGER.critical("History not initialized!")
			return None
		
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