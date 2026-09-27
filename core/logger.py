import os
import logging
from logging.handlers import RotatingFileHandler
from core.config import LOG_DIR

os.makedirs(LOG_DIR, exist_ok=True)

def _file_handler(filename):
    # ~100 KB per file plus one backup
    return RotatingFileHandler(filename, maxBytes=100_000, backupCount=1, encoding='utf-8')

# Root Logger
root_handler = _file_handler(os.path.join(LOG_DIR, "success.log"))
root_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[root_handler])

def setup_logger(name, log_file, level=logging.INFO):
    handler = _file_handler(os.path.join(LOG_DIR, log_file))
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    logger.addHandler(handler)
    return logger

log_error = setup_logger('error_logger', 'error.log', level=logging.ERROR)
log_sync = setup_logger('sync_logger', 'sync.log')
log_live = setup_logger('live_logger', 'live.log')

def smart_log(msg, level="INFO", component=None):
    if level == "ERROR":
        log_error.error(msg)
        return
    
    # INFO level logging
    logging.info(msg) # Goes to success.log (root logger)
    
    if component == "sync": 
        log_sync.info(msg)
    elif component == "live": 
        log_live.info(msg)
