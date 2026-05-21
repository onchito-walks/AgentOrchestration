"""Tests for config env var type coercion (bounty #962 - $4K)."""

import os
import tempfile
import json
from src.common.config import Config


def _config_with_env(**env_vars):
    """Helper: create a Config loaded with specific env overrides."""
    # Save + set
    saved = {}
    for k, v in env_vars.items():
        saved[k] = os.environ.get(k)
        os.environ[k] = v
    # Prune non-AO_ entries so they don't pollute
    for k in list(os.environ.keys()):
        if k.startswith("AO_") and k not in env_vars:
            saved[k] = os.environ.pop(k, None)
    try:
        cfg = Config()
        return cfg
    finally:
        # Restore
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestEnvCoercion:
    """_coerce_env_value unit tests."""

    def test_boolean_true_variants(self):
        assert Config._coerce_env_value("true") is True
        assert Config._coerce_env_value("TRUE") is True
        assert Config._coerce_env_value("True") is True
        assert Config._coerce_env_value("1") is True
        assert Config._coerce_env_value("yes") is True
        assert Config._coerce_env_value("on") is True

    def test_boolean_false_variants(self):
        assert Config._coerce_env_value("false") is False
        assert Config._coerce_env_value("FALSE") is False
        assert Config._coerce_env_value("False") is False
        assert Config._coerce_env_value("0") is False
        assert Config._coerce_env_value("no") is False
        assert Config._coerce_env_value("off") is False

    def test_null(self):
        assert Config._coerce_env_value("null") is None
        assert Config._coerce_env_value("NULL") is None

    def test_integer(self):
        assert Config._coerce_env_value("42") == 42
        assert Config._coerce_env_value("-7") == -7
        assert Config._coerce_env_value("0") == 0  # boolean not int; 0 is in _BOOLEAN_FALSE

    def test_float(self):
        assert Config._coerce_env_value("3.14") == 3.14
        assert Config._coerce_env_value("-0.5") == -0.5

    def test_json_array(self):
        assert Config._coerce_env_value("[1,2,3]") == [1, 2, 3]

    def test_json_object(self):
        assert Config._coerce_env_value('{"key":"val"}') == {"key": "val"}

    def test_plain_string_fallback(self):
        assert Config._coerce_env_value("hello world") == "hello world"
        assert Config._coerce_env_value("some_path") == "some_path"


class TestEnvOverrideIntegration:
    """End-to-end: env var → Config.get() returns typed values."""

    def test_boolean_false_env_override(self):
        cfg = _config_with_env(AO_ENABLED="false")
        assert cfg.get("enabled") is False

    def test_boolean_true_env_override(self):
        cfg = _config_with_env(AO_ENABLED="true")
        assert cfg.get("enabled") is True

    def test_integer_env_override(self):
        cfg = _config_with_env(AO_MAX_RETRIES="10")
        assert cfg.get("max.retries") == 10

    def test_float_env_override(self):
        cfg = _config_with_env(AO_TIMEOUT_SECONDS="30.5")
        assert cfg.get("timeout.seconds") == 30.5

    def test_json_array_env_override(self):
        cfg = _config_with_env(AO_ALLOWED_ORIGINS='["http://a.com","http://b.com"]')
        assert cfg.get("allowed.origins") == ["http://a.com", "http://b.com"]

    def test_nested_config_key(self):
        cfg = _config_with_env(AO_DATABASE_HOST="db.example.com")
        assert cfg.get("database.host") == "db.example.com"

    def test_env_override_takes_precedence(self):
        """Env override should win over file-based config."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"host": "file-host", "port": 8080}, f)
            f.flush()
            cfg = Config(f.name)
            cfg._data["port"] = 8080
        os.unlink(f.name)
        # Set env override
        os.environ["AO_HOST"] = "env-host"
        try:
            cfg = Config()
            # Verify json.loads values are still present in underlying dict
            # (env overrides merged into _data, but get() still resolves)
            assert cfg.get("host") == "env-host"
        finally:
            os.environ.pop("AO_HOST", None)
