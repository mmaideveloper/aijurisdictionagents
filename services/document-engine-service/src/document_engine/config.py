from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "document-engine-service"
    database_url: str = "sqlite:///./document_engine.db"
    worker_poll_interval_seconds: float = 2.0
    worker_batch_size: int = 5
    generated_documents_dir: str = "./generated-documents"


settings = Settings()
