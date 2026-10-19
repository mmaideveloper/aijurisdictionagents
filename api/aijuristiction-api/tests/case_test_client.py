"""Authenticated synthetic owner fixture for existing case behavior tests.

Security tests use the ordinary TestClient and explicit credentials instead.
This helper performs real token issuance and validation; it does not bypass auth.
"""
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient as BaseTestClient


class TestClient(BaseTestClient):
    __test__ = False

    def request(self, method, url, **kwargs):
        from app.cases_api import get_store
        from app.case_security import auth_store

        if "/v1/cases" in str(url):
            payload = kwargs.get("json") or {}
            query = parse_qs(urlsplit(str(url)).query)
            params = kwargs.get("params") or {}
            subject = str(payload.get("user_id") or params.get("user_id") or query.get("user_id", [""])[0])
            provider = self.app.dependency_overrides.get(get_store, get_store)
            store = provider()
            self.app.dependency_overrides[auth_store] = provider
            if not any(part in str(url) for part in ("/it-assessments", "/software-assessments")) and subject and type(store).__name__ != "_FakeStore" and store.find_user_by_id(user_id=subject):
                token = store.issue_device_auth_token(user_id=subject, device_id="synthetic-case-test")
                kwargs["headers"] = {**dict(kwargs.get("headers") or {}), "x-jurisdigta-device-id": "synthetic-case-test", "x-jurisdigta-device-token": token}
        return super().request(method, url, **kwargs)
