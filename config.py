import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    TARGET_USERS: int = 1000
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'leetcode_data.db'}"
    REQUEST_DELAY: float = 1.0
    MAX_RETRIES: int = 3
    MAX_CONCURRENCY: int = 3
    REQUEST_TIMEOUT: float = 15.0
    LEETCODE_URL: str = "https://leetcode.com/graphql/"
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Admin Authentication
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "change_this_password"
    ADMIN_SECRET_KEY: str = "super_secret_admin_session_key_replace_in_production"
    SESSION_EXPIRE_HOURS: int = 24

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
