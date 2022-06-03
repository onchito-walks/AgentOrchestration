"""Configuration management module."""

import os
import json
from typing import Any, Dict, Optional


class Config:
    def __init__(self, config_path: Optional[str] = None):
        self._data: Dict[str, Any] = {}
        if config_path:
            self.load(config_path)
        self._load_env_overrides()

    def load(self, path: str) -> None:
        with open(path) as f:
            self._data = json.load(f)

    def _load_env_overrides(self) -> None:
        prefix = "AO_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower().replace("_", ".")
                self._set_nested(config_key, value)

    def _set_nested(self, key: str, value: Any) -> None:
        parts = key.split(".")
        current = self._data
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    def get(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        current = self._data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
                if current is None:
                    return default
            else:
                return default
        return current

    def set(self, key: str, value: Any) -> None:
        self._set_nested(key, value)

    def to_dict(self) -> Dict:
        return self._data

# 2019-03-14T15:29:32 update

# 2019-05-06T15:01:41 update

# 2019-07-12T09:57:32 update

# 2019-08-30T16:15:51 update

# 2019-08-30T19:29:48 update

# 2019-11-29T18:40:08 update

# 2020-01-06T17:10:44 update

# 2020-01-23T10:35:15 update

# 2020-04-27T16:39:24 update

# 2020-05-26T16:41:05 update

# 2020-07-19T11:00:28 update

# 2021-02-26T14:06:47 update

# 2021-04-25T15:41:25 update

# 2021-05-03T10:13:52 update

# 2021-05-25T19:02:26 update

# 2021-07-20T13:34:30 update

# 2021-09-23T13:29:24 update

# 2021-11-12T13:25:31 update

# 2022-01-07T11:55:24 update

# 2022-03-08T17:13:29 update

# 2022-03-09T12:33:27 update

# 2022-03-24T14:25:02 update

# 2022-04-12T20:49:22 update

# 2022-04-13T15:58:33 update

# 2022-06-03T19:19:58 update
