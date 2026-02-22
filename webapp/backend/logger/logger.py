import sys
from loguru import logger

def init_logger():
    loger = logger.add(
        sink=sys.stdout,
        level="DEBUG"
    )
    return logger
