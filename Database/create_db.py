# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 08-MAR-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import sys

from Logging import logger_init
from Database import connect_to_db

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("Database")

# ================================= CONSTANTS ================================ #
DBPATH = os.environ["Db"]
CREATE_SCHEMA_PATH = os.path.join(DBPATH, "schema.sql")
DROP_SCHEMA_PATH = os.path.join(DBPATH, "drop_db.sql")

# ================================== CLASSES ================================= #
# ================================= FUNCTIONS ================================ #
def drop_tables(conn, curr):
	try:
		LOGGER.debug("Dropping previous tables, if any")
		with open(DROP_SCHEMA_PATH, "r") as fp:
			curr.executescript(fp.read())
		conn.commit()
		LOGGER.info("Dropped previous tables successfully")
	except Exception as e:
		LOGGER.error(f"Error while dropping old tables: {e}")
		conn.rollback()
		sys.exit(1)

def create_tables(conn, curr):
	try:
		LOGGER.debug("Creating new tables from schema.sql")
		with open(CREATE_SCHEMA_PATH, "r") as fp:
			curr.executescript(fp.read())
		conn.commit()
		LOGGER.info("Tables created successfully")
	except Exception as e:
		LOGGER.error(f"Error while creating tables: {e}")
		conn.rollback()
		sys.exit(1)
# =================================== MAIN =================================== #
if __name__ == "__main__":
	conn, curr = connect_to_db()

	drop_tables(conn, curr)
	create_tables(conn, curr)
