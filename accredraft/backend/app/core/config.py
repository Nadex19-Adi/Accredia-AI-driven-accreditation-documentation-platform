import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "AccreditDraft"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    
    # Database — defaults to SQLite so the stack runs with zero setup.
    # Point this at PostgreSQL for production (see .env.example).
    DATABASE_URL: str = "sqlite:///./accredraft.db"
    
    # Redis (only needed when running the optional RQ worker)
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # S3 Storage — if unreachable, storage falls back to LOCAL_STORAGE_DIR
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "accredraft"
    S3_REGION: str = "us-east-1"
    LOCAL_STORAGE_DIR: str = "storage"
    
    # LLM
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    
    # JWT
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # File Upload
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: set = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".xlsx", ".xls"}
    
    # Paths
    LAYOUT_TEMPLATES_DIR: str = "templates"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()