# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 07-MAR-2025  Initial Draft
# ============================================================================ #

# ================================== IMPORTS ================================= #
import os
import json
import logging
import logging.handlers

# ================================= CONSTANTS ================================ #
LOGDIR = os.environ["Log"]
CFGDIR = os.environ["Xml"]
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
            f"{asctime} | {record.levelname}\t| {record.name}\t| "
            f"{filename}-{record.lineno}\t| {record.funcName}()\t| {record.msg}"
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

def logger_init(PROCESS):
    # level = LEVELS[load_config()[PROCESS]["LogLevel"]]
    level = load_config().get(PROCESS, {"LogLevel": "DEBUG"})["LogLevel"]
    log_file_path = os.path.join(LOGDIR, PROCESS + ".log")

    logger = logging.getLogger(PROCESS)
    logger.setLevel(level)
    logger.handlers = []
    logger.propagate = False

    formatter = LogFormatter()
    
    rotating_handler = logging.handlers.TimedRotatingFileHandler(log_file_path, when='d')
    rotating_handler.setLevel(level)
    rotating_handler.setFormatter(formatter)

    logger.addHandler(rotating_handler)
    return logger

# =================================== MAIN =================================== #
# if __name__ == "__main__":
#     pass
# else:
#     CALLER  = inspect.stack()[-1].filename
#     PROCESS = CALLER.split(os.sep)[-2]
#     logger_init(PROCESS)