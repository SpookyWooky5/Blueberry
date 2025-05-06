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
import csv
import sqlite3

from Common.Logging import logger_init

# ============================= GLOBAL VARIABLES ============================= #
LOGGER = logger_init("Database")

# ================================= CONSTANTS ================================ #
DBPATH = os.environ["Db"]
DATAPATH = os.environ["Data"]

# ================================== CLASSES ================================= #
# ================================= FUNCTIONS ================================ #
def connect_to_db():
	LOGGER.debug("Connecting to the database...")
	try:
		conn = sqlite3.connect(os.path.join(DBPATH, "db.sqlite3"))
		curr = conn.cursor()
		LOGGER.info("Successfully Connected")
	except Exception as e:
		LOGGER.error(f"Error while connecting to the database: {e}")
		sys.exit(1)
	return conn, curr

def dump_table(table_name):
	# connect_to_db, select table, and save dump to csv
	conn, curr = connect_to_db()
	try:
		data = curr.execute(f"SELECT * from {table_name}").fetchall()
		with open(os.path.join(DATAPATH, table_name + ".csv"), "w", newline='') as f:
			writer = csv.writer(f)
			writer.writerow(i[0] for i in curr.description)
			writer.writerows(data)
		LOGGER.info(f"Table {table_name} dumped to file")
	except Exception as e:
		LOGGER.error(f"Error while dumping table {table_name}: {e}")