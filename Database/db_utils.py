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
import sqlite3

import dataset

from Logging import logger_init

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

def connect_to_dataset():
	LOGGER.debug("Connecting to the database via dataset...")
	try:
		db = dataset.connect(f"sqlite:///{os.path.join(DBPATH, 'db.sqlite3')}")
		LOGGER.info("Successfully Connected via dataset")
	except Exception as e:
		LOGGER.error(f"Error while connecting to the database via dataset: {e}")
		sys.exit(1)
	return db

def get_or_create_client(client, client_name):
	db = connect_to_dataset()
	try:
		client_id = db['clients'].find_one(email=client)
	except Exception as e:
		LOGGER.error(f"Could not get Client ID for {client}, {e}")
		return -1
	if client_id is None:
		db['clients'].insert(dict(
			name=client_name,
			email=client
		))
		client_id = db['clients'].find_one(email=client)
	client_id = client_id['id']
	return client_id