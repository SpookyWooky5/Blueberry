# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 00-XXX-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import numpy as np

from Logging import logger_init

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("LLM")

# ================================= CONSTANTS ================================ #

# ================================== CLASSES ================================= #

# ================================= FUNCTIONS ================================ #
def cosine(a, b):
	norm_a = np.linalg.norm(a)
	norm_b = np.linalg.norm(b)

	if norm_a == 0 or norm_b == 0:
		return 0	
	
	return np.dot(a, b) / (norm_a * norm_b)

# =================================== MAIN =================================== #
if __name__ == "__main__":
	pass