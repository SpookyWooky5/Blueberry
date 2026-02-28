# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 23-MAR-2025  Initial Draft
# 12-JUL-2025  Refactor to use shared constants from utils
# 28-FEB-2026  Migrate from llama-cpp-python to Ollama HTTP API
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os

import numpy as np
import requests

from Logging import logger_init
from utils import LLM_MODEL, EMB_MODEL

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")

# ================================= CONSTANTS ================================ #
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ================================== CLASSES ================================= #
class OllamaChat:
	def __init__(self, model: str):
		self.model = model
		self.history = None
		LOGGER.info(f"Initialized OllamaChat with model '{model}'")

	def init_history(self, history: list):
		self.history = history
		LOGGER.debug(f"Initialized history with {len(history)} message(s)")

	def generate_response(self) -> str:
		if self.history is None:
			LOGGER.critical("History not initialized!")
			return None

		try:
			resp = requests.post(
				f"{OLLAMA_BASE_URL}/api/chat",
				json={
					"model": self.model,
					"messages": self.history,
					"stream": False,
				},
				timeout=120,
			)
			resp.raise_for_status()
			content = resp.json()["message"]["content"]
			LOGGER.debug("Response generated")
			return content
		except Exception as e:
			LOGGER.error(f"Could not generate a response! {e}")
			return None


class OllamaEmbed:
	def __init__(self, model: str):
		self.model = model
		LOGGER.info(f"Initialized OllamaEmbed with model '{model}'")

	def embed(self, text: str, is_query: bool = False) -> np.ndarray:
		prefix = "search_query: " if is_query else "search_document: "
		prefixed = prefix + text

		try:
			resp = requests.post(
				f"{OLLAMA_BASE_URL}/api/embed",
				json={
					"model": self.model,
					"input": prefixed,
				},
				timeout=60,
			)
			resp.raise_for_status()
			embedding = resp.json()["embeddings"][0]
			return np.array(embedding)
		except Exception as e:
			LOGGER.error(f"Could not generate embedding! {e}")
			return None

# ================================= FUNCTIONS ================================ #

# =================================== MAIN =================================== #
if __name__ == "__main__":
	llm = OllamaChat(LLM_MODEL)
