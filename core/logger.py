import os
import logging
from core.config import LOG_DIR, CLEANED_LOG_DIR

# Ensure log directories exist
for d in [LOG_DIR, CLEANED_LOG_DIR]:
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

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

def log_cleaned_article(title, content):
    """Saves cleaned article text for verification/auditing."""
    try:
        # Sanitize title for filename
        safe_title = "".join([c if c.isalnum() else "_" for c in title])
        file_path = os.path.join(CLEANED_LOG_DIR, f"{safe_title}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        log_error.error(f"Failed to log cleaned article {title}: {str(e)}")
