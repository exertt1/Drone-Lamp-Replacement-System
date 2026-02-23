import sys
from loguru import logger

def init_logger():
    log = logger.add(
        sink=sys.stdout,
        level="DEBUG"
    )
    log = logger.add(
        sink=sys.stdout
    )
    return log
