from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "CompApp API"
    DEBUG: bool = False

    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Browser origins allowed to call the API (e.g. Expo web on localhost).
    # Native mobile apps don't send an Origin header and don't need this.
    # In .env: CORS_ORIGINS=["http://localhost:8081","https://app.example.com"]
    CORS_ORIGINS: list[str] = []

    # Failed logins allowed per email / per IP within the window before lockout
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_WINDOW_SECONDS: int = 15 * 60

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_strong(cls, v):
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. Generate one with: "
                "python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    class Config:
        env_file = ".env"


settings = Settings()
