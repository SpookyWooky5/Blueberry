# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 23-MAR-2025  Initial Draft
# 12-JUL-2025  Refactor to use shared constants from utils
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import sys

import numpy as np
from llama_cpp import Llama

from Logging import logger_init
from LLM.parse import remove_commands
from Database import connect_to_dataset
from utils import (
    load_config,
    read_prompt_from_file,
    PROMPTS_DIR,
    LLM_MODEL,
    EMB_MODEL,
    EMAIL,
)

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")

# ================================= CONSTANTS ================================ #
LLMCFG = load_config()["LLM"]

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
			# This path is now primarily handled by MailServer/reply.py, 
			# which constructs the full context. This is a fallback.
			self.history = [
				{"role": "system", "content": read_prompt_from_file("mail_prompt.txt")},
			]
		
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
	llm = BaseChatbot(LLM_MODEL)
