# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 07-MAR-2025  Initial Draft
# 13-JUL-2025  Implement custom daily log rotation for cron jobs.
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import json
import logging
import logging.handlers
from datetime import datetime

# ================================= CONSTANTS ================================ #
LOGDIR = os.environ["LOG_DIR"]
CFGDIR = os.environ["BCFG"]
LEVELS = {
    "DEBUG"    : logging.DEBUG,
    "INFO"     : logging.INFO,
    "WARNING"  : logging.WARNING,
    "ERROR"    : logging.ERROR,
    "CRITICAL" : logging.CRITICAL
}

# ================================== CLASSES ================================= #
class LogFormatter(logging.Formatter):
    def format(self, record):
        filename = os.path.basename(record.pathname)
        asctime = self.formatTime(record, datefmt='%d-%b-%Y %H:%M:%S')
        log_fmt = (
            f"{asctime} | {record.levelname:<8} | {record.name:<12} | "
            f"{filename}:{record.lineno:<4} | {record.funcName:<16}() | {record.msg}"
        )
        return log_fmt

# ================================= FUNCTIONS ================================ #
def load_config():
    with open(os.path.join(CFGDIR, "process.json"), "r") as fp:
        try:
            data = json.load(fp)
        except Exception as e:
            print(e)
    return data

def setup_manual_rotation(log_file_path):
    """
    Checks if the log file is from a previous day and renames it if so.
    This is designed to work with scripts run from cron.
    """
    if os.path.exists(log_file_path):
        try:
            mod_time = datetime.fromtimestamp(os.path.getmtime(log_file_path))
            if mod_time.date() < datetime.now().date():
                # Format the date from the modification time of the log file
                archive_date = mod_time.strftime('%Y-%m-%d')
                archive_log_path = f"{log_file_path}.{archive_date}"
                
                # To avoid overwriting, check if archive file exists
                if os.path.exists(archive_log_path):
                    # Simple append a number if it does, could be more robust
                    counter = 1
                    while os.path.exists(f"{archive_log_path}.{counter}"):
                        counter += 1
                    archive_log_path = f"{archive_log_path}.{counter}"

                os.rename(log_file_path, archive_log_path)
        except Exception as e:
            # If rotation fails, we can't log yet, so print to stderr
            print(f"Error: Could not rotate log file {log_file_path}: {e}")


def logger_init(PROCESS):
    level_name = load_config().get(PROCESS, {"LogLevel": "DEBUG"})["LogLevel"]
    level = LEVELS.get(level_name, logging.DEBUG)
    log_file_path = os.path.join(LOGDIR, PROCESS + ".log")

    # Perform rotation check before setting up the logger
    setup_manual_rotation(log_file_path)

    logger = logging.getLogger(PROCESS)
    logger.setLevel(level)
    
    # Avoid adding handlers if they already exist from a previous import
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.propagate = False

    formatter = LogFormatter()
    
    # Use a simple FileHandler since rotation is now manual
    handler = logging.FileHandler(log_file_path)
    handler.setLevel(level)
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger

# =================================== MAIN =================================== #
# if __name__ == "__main__":
#     pass
