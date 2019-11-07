"""Structured logging configuration."""

import json
import logging
import sys
from datetime import datetime
from typing import Dict, Optional


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), handlers=[handler])

# 2019-01-14T10:37:21 update

# 2019-01-15T13:20:32 update

# 2019-01-22T12:39:53 update

# 2019-04-24T12:23:11 update

# 2019-05-30T17:23:20 update

# 2019-07-23T19:29:50 update

# 2019-07-29T17:21:51 update

# 2019-11-07T14:37:43 update
