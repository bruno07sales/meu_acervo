from pathlib import Path
from urllib.parse import urlparse

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    API_V1_STR: str = "/api/v1"
    APP_NAME: str = "artme-backend"
    ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000"
    SECRET_KEY: str = "change-me-in-production"
    MONGO_URI: str = "mongodb://127.0.0.1:27017"
    MONGO_DB_NAME: str = "artme"
    IMAGEM_STORAGE_BACKEND: str = "local"
    ENABLE_BOOTSTRAP_ADMIN: bool = False
    BOOTSTRAP_ADMIN_EMAIL: str | None = None
    BOOTSTRAP_ADMIN_PASSWORD: str | None = None
    BOOTSTRAP_ADMIN_NAME: str = "Administrador inicial"
    # Centraliza o nome do cookie para evitar valores hardcoded nas rotas e servicos
    COOKIE_NAME: str = "access_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    # Mantem a expiracao do cookie configuravel fora da rota de login
    COOKIE_MAX_AGE: int = 3600
    # Mantem a expiracao do JWT alinhada com a sessao sem hardcode nas rotas.
    JWT_EXP_SECONDS: int = 3600
    # Garante que criacao e remocao do cookie usem o mesmo escopo de path
    COOKIE_PATH: str = "/"

    @field_validator("ENV")
    @classmethod
    # Restringe o ambiente a valores conhecidos para evitar configurações ambiguas
    def validar_env(cls, value: str) -> str:
        normalizado = value.strip().lower()
        if normalizado not in {"development", "production"}:
            raise ValueError("ENV deve ser development ou production")
        return normalizado

    @field_validator("COOKIE_SAMESITE")
    @classmethod
    # Valida os valores aceitos para SameSite antes de subir a aplicação
    def validar_cookie_samesite(cls, value: str) -> str:
        normalizado = value.strip().lower()
        if normalizado not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE deve ser lax, strict ou none")
        return normalizado

    @computed_field
    def all_cors_origins(self) -> list[str]:
        origins = self.CORS_ORIGINS.split(",") if self.CORS_ORIGINS else []
        valid_origins: list[str] = []

        for origin in origins:
            normalized = str(origin).strip().rstrip("/")
            if not normalized:
                continue

            parsed = urlparse(normalized)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue

            valid_origins.append(normalized)

        return valid_origins

    @computed_field
    def local_cors_regex(self) -> str:
        return r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


settings = Settings()
