import os
import logging
from core.config import LOG_DIR

# Ensure log directory exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

class LimitedFileHandler(logging.FileHandler):
    def __init__(self, filename, mode='a', encoding='utf-8', delay=False, max_lines=500):
        super().__init__(filename, mode, encoding, delay)
        self.max_lines = max_lines

    def emit(self, record):
        super().emit(record)
        self.flush()
        try:
            with open(self.baseFilename, 'r', encoding=self.encoding) as f:
                lines = f.readlines()
            if len(lines) > self.max_lines:
                with open(self.baseFilename, 'w', encoding=self.encoding) as f:
                    f.writelines(lines[-self.max_lines:])
        except: pass

# Root Logger
root_handler = LimitedFileHandler(os.path.join(LOG_DIR, "success.log"))
root_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[root_handler])

def setup_logger(name, log_file, level=logging.INFO):
    handler = LimitedFileHandler(os.path.join(LOG_DIR, log_file))
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
