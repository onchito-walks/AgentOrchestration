import pytest
from src.common.config import Config


class TestConfig:
    def test_load_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"app": {"name": "test", "port": 8080}}')
        config = Config(str(config_file))
        assert config.get("app.name") == "test"
        assert config.get("app.port") == 8080

    def test_default_value(self):
        config = Config()
        assert config.get("nonexistent.key", "default") == "default"

    def test_set_value(self):
        config = Config()
        config.set("database.host", "localhost")
        assert config.get("database.host") == "localhost"

    def test_nested_set(self):
        config = Config()
        config.set("a.b.c.d", "value")
        assert config.get("a.b.c.d") == "value"

    def test_to_dict(self):
        config = Config()
        config.set("key1", "value1")
        config.set("key2", "value2")
        data = config.to_dict()
        assert data["key1"] == "value1"
        assert data["key2"] == "value2"

# 2019-02-01T18:58:35 update

# 2019-07-31T13:45:15 update

# 2019-08-09T17:54:41 update

# 2019-08-14T16:29:54 update

# 2019-10-11T10:28:34 update

# 2019-10-25T09:23:55 update

# 2019-12-13T09:04:47 update

# 2020-04-09T10:21:21 update

# 2020-05-08T17:44:24 update

# 2020-07-20T13:54:19 update

# 2020-09-24T15:42:29 update

# 2020-12-09T20:16:24 update

# 2021-04-21T13:19:36 update

# 2021-05-25T09:15:06 update

# 2021-10-13T20:37:29 update

# 2021-11-18T18:37:15 update
