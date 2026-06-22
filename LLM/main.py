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
import time

import numpy as np
import requests

from Logging import logger_init
from utils import LLM_MODEL, EMB_MODEL

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")

# ================================= CONSTANTS ================================ #
OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MAX_RETRIES      = 5
RETRY_WAIT       = 60    # seconds to wait after a timeout before retrying
MAX_EMBED_CHARS  = 4000  # nomic-embed-text context is 2048 tokens; ~2 chars/token for dense content → ~4k chars safe limit

# ================================== CLASSES ================================= #
class OllamaChat:
	def __init__(self, model: str):
		self.model = model
		self.history = None
		LOGGER.info(f"Initialized OllamaChat with model '{model}'")

	def init_history(self, history: list):
		self.history = history
		LOGGER.debug(f"Initialized history with {len(history)} message(s)")

	def unload(self):
		"""Unload model from Ollama memory to free resources between phases."""
		try:
			requests.post(
				f"{OLLAMA_BASE_URL}/api/chat",
				json={"model": self.model, "messages": [], "keep_alive": 0},
				timeout=30,
			)
			LOGGER.info(f"Unloaded model '{self.model}' from Ollama memory.")
		except Exception as e:
			LOGGER.warning(f"Could not unload model '{self.model}': {e}")

	def generate_response(self) -> str:
		if self.history is None:
			LOGGER.critical("History not initialized!")
			return None

		for attempt in range(1, MAX_RETRIES + 1):
			try:
				resp = requests.post(
					f"{OLLAMA_BASE_URL}/api/chat",
					json={
						"model": self.model,
						"messages": self.history,
						"stream": False,
					},
					timeout=900,
				)
				resp.raise_for_status()
				content = resp.json()["message"]["content"]
				LOGGER.debug("Response generated")
				return content
			except requests.exceptions.Timeout:
				if attempt < MAX_RETRIES:
					LOGGER.warning(f"Ollama timed out (attempt {attempt}/{MAX_RETRIES}), waiting {RETRY_WAIT}s before retry...")
					time.sleep(RETRY_WAIT)
				else:
					LOGGER.error(f"Ollama timed out after {MAX_RETRIES} attempts, giving up.")
					return None
			except Exception as e:
				LOGGER.error(f"Could not generate a response! {e}")
				return None


class OllamaEmbed:
	def __init__(self, model: str):
		self.model = model
		LOGGER.info(f"Initialized OllamaEmbed with model '{model}'")

	def unload(self):
		"""Unload embedding model from Ollama memory."""
		try:
			requests.post(
				f"{OLLAMA_BASE_URL}/api/embed",
				json={"model": self.model, "input": "unload", "keep_alive": 0},
				timeout=30,
			)
			LOGGER.info(f"Unloaded embed model '{self.model}' from Ollama memory.")
		except Exception as e:
			LOGGER.warning(f"Could not unload embed model '{self.model}': {e}")

	def embed(self, text: str, is_query: bool = False) -> np.ndarray:
		prefix = "search_query: " if is_query else "search_document: "
		if len(text) > MAX_EMBED_CHARS:
			LOGGER.warning(f"Truncating embed input from {len(text)} to {MAX_EMBED_CHARS} chars")
			text = text[:MAX_EMBED_CHARS]
		prefixed = prefix + text

		for attempt in range(1, MAX_RETRIES + 1):
			try:
				resp = requests.post(
					f"{OLLAMA_BASE_URL}/api/embed",
					json={
						"model": self.model,
						"input": prefixed,
					},
					timeout=900,
				)
				resp.raise_for_status()
				embedding = resp.json()["embeddings"][0]
				return np.array(embedding)
			except requests.exceptions.Timeout:
				if attempt < MAX_RETRIES:
					LOGGER.warning(f"Ollama embed timed out (attempt {attempt}/{MAX_RETRIES}), waiting {RETRY_WAIT}s before retry...")
					time.sleep(RETRY_WAIT)
				else:
					LOGGER.error(f"Ollama embed timed out after {MAX_RETRIES} attempts, giving up.")
					return None
			except requests.exceptions.HTTPError as e:
				body = e.response.text if e.response is not None else "(no response body)"
				LOGGER.error(f"Could not generate embedding! {e} — Ollama said: {body}")
				return None
			except Exception as e:
				LOGGER.error(f"Could not generate embedding! {e}")
				return None

# ================================= FUNCTIONS ================================ #

# =================================== MAIN =================================== #
if __name__ == "__main__":
	llm = OllamaChat(LLM_MODEL)
