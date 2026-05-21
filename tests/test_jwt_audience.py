"""Tests for JWT audience enforcement (#1360)."""
import pytest
from src.auth.jwt import JWTValidator, JWTValidationError


class TestJWTValidator:
    def setup_method(self):
        import jwt
        self.secret = "test-secret"
        self.validator = JWTValidator(secret=self.secret, audiences=["agent-orchestrator"])
    
    def _make_token(self, aud="agent-orchestrator", exp_offset=3600):
        import jwt, time
        return jwt.encode(
            {"sub": "service-a", "aud": aud, "exp": int(time.time()) + exp_offset},
            self.secret, algorithm="HS256"
        )
    
    def test_valid_token_passes(self):
        token = self._make_token()
        payload = self.validator.validate_token(token)
        assert payload["aud"] == "agent-orchestrator"
    
    def test_missing_audience_rejected(self):
        import jwt, time
        token = jwt.encode({"sub": "service-a", "exp": int(time.time()) + 3600}, self.secret)
        with pytest.raises(JWTValidationError):
            self.validator.validate_token(token)
    
    def test_wrong_audience_rejected(self):
        token = self._make_token(aud="wrong-audience")
        with pytest.raises(JWTValidationError, match="audience"):
            self.validator.validate_token(token)
    
    def test_expired_token_rejected(self):
        token = self._make_token(exp_offset=-3600)
        with pytest.raises(JWTValidationError):
            self.validator.validate_token(token)
