import json
import os
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Instead of patching the app object directly, import the module that defines base_redis_client.
import fastapi_app.main as main_module
from pipeline.config import PipelineSettings, AppSettings, load_pipeline_settings

# Define a dummy Redis class that mimics only the methods used by our endpoints.
class DummyRedis:
    def ping(self):
        return True

    def get(self, key):
        # For endpoints using get, return a dummy JSON-string when needed.
        return '{"status": "dummy", "version": "2.0.0", "components": {"redis": "connected"}}'

    def set(self, key, value):
        # Dummy set does nothing.
        pass

    def keys(self, pattern):
        return []

def test_health_endpoint(monkeypatch):
    # Monkey patch the base_redis_client in the main module
    monkeypatch.setattr(main_module, "base_redis_client", DummyRedis())

    client = TestClient(main_module.app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    # Check that the response includes expected keys.
    assert "status" in data
    assert "version" in data
    assert "components" in data
    # The dummy should simulate a healthy Redis
    redis_status = data.get("components", {}).get("redis", "")
    assert isinstance(redis_status, str)
