from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    database_url: str
    identity_database_url: str
    public_url: str
    auth_url: str
    environment: str
    endpoint: str
    deployment: str
    api_version: str
    api_key: str

    @classmethod
    def load(cls) -> "Settings":
        path = Path(os.environ.get("LAWS_TEST_ENV_FILE", ".env-laws-test"))
        values = dotenv_values(path)

        def required(key: str) -> str:
            value = str(values.get(key) or "").strip()
            if not value or value == "unknown-variable":
                raise ValueError(f"Missing setting: {key}")
            return value

        settings = cls(
            *(
                required(key)
                for key in (
                    "LAWS_TEST_DATABASE_URL",
                    "LAWS_TEST_IDENTITY_DATABASE_URL",
                    "LAWS_TEST_PUBLIC_URL",
                    "LAWS_TEST_AUTH_URL",
                    "LAWS_TEST_ENVIRONMENT",
                    "AZURE_OPENAI_ENDPOINT",
                    "AZURE_OPENAI_DEPLOYMENT",
                    "AZURE_OPENAI_API_VERSION",
                    "AZURE_OPENAI_API_KEY",
                )
            )
        )
        if settings.environment not in {"development", "test", "production"}:
            raise ValueError("Invalid LAWS_TEST_ENVIRONMENT")
        for connection in (settings.database_url, settings.identity_database_url):
            uri = urlparse(connection)
            if uri.scheme != "postgresql":
                raise ValueError("PostgreSQL is required")
            if settings.environment != "production" and uri.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("Development/test databases must be local")
        if urlparse(settings.database_url).path != "/laws-tests":
            raise ValueError("Expected database laws-tests")
        for url in (settings.public_url, settings.auth_url):
            uri = urlparse(url)
            if uri.username or uri.password or uri.query or uri.fragment:
                raise ValueError("Invalid public/auth URL")
            if uri.scheme != "https" and not (
                settings.environment != "production"
                and uri.scheme == "http"
                and uri.hostname in {"localhost", "127.0.0.1"}
            ):
                raise ValueError("HTTPS is required outside loopback development")
        return settings

    @property
    def auth_origin(self) -> str:
        uri = urlparse(self.auth_url)
        return f"{uri.scheme}://{uri.netloc}"
