from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    APP_NAME: str = "Fixtr API"
    DEBUG: bool = False

    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    # Access tokens are short-lived; the app renews them with its refresh token
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    # A device stays signed in while it's used at least this often
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # "Forgot password" codes
    PASSWORD_RESET_CODE_MINUTES: int = 15
    PASSWORD_RESET_MAX_ATTEMPTS: int = 5

    # Email: "console" logs messages (development); "smtp" sends them
    EMAIL_BACKEND: Literal["console", "smtp"] = "console"
    EMAIL_FROM: str = "Fixtr <no-reply@localhost>"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_STARTTLS: bool = True  # port 587; set False and use port 465 for implicit TLS

    # Browser origins allowed to call the API (e.g. Expo web on localhost).
    # Native mobile apps don't send an Origin header and don't need this.
    # In .env: CORS_ORIGINS=["http://localhost:8081","https://app.example.com"]
    CORS_ORIGINS: list[str] = []

    # Public address of this server, used to build share links (e.g.
    # https://fixtr.example.com). Unset = the address the request came in on,
    # which on a phone in development is the dev machine's LAN IP.
    PUBLIC_BASE_URL: str | None = None

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

    @model_validator(mode="after")
    def smtp_configured(self):
        if self.EMAIL_BACKEND == "smtp" and not self.SMTP_HOST:
            raise ValueError("EMAIL_BACKEND=smtp needs SMTP_HOST")
        return self


settings = Settings()
