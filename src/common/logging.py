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

# 2020-01-21T19:13:41 update

# 2020-02-26T12:41:16 update

# 2020-04-15T10:31:15 update

# 2020-06-04T08:55:59 update

# 2020-10-20T14:20:45 update

# 2020-11-04T12:47:37 update

# 2021-01-03T20:18:44 update

# 2021-08-16T09:55:15 update

# 2021-08-17T15:31:20 update

# 2021-09-03T19:42:47 update

# 2021-09-14T20:55:49 update

# 2021-11-05T14:29:30 update

# 2021-12-10T20:38:38 update

# 2021-12-15T09:54:55 update

# 2022-01-21T11:34:19 update

# 2022-02-22T14:21:14 update

# 2022-03-10T16:21:41 update

# 2022-05-07T09:03:51 update

# 2022-05-25T12:20:13 update

# 2022-07-14T14:40:31 update

# 2022-08-19T18:48:52 update

# 2022-09-13T11:52:44 update

# 2022-12-27T14:07:35 update

# 2023-01-18T15:30:02 update

# 2023-03-13T19:28:57 update

# 2023-03-17T11:11:13 update

# 2023-06-29T18:28:49 update

# 2023-07-05T13:48:03 update

# 2023-07-13T15:11:45 update

# 2023-08-28T19:47:24 update

# 2023-09-27T14:54:40 update

# 2024-03-22T16:35:48 update

# 2024-03-29T13:12:53 update
