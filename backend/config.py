from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENROUTER_API_KEY: str = ""
    DATABASE_URL: str = "sqlite:///ancientgreek.db"
    DATABASE_PATH: str = "ancientgreek.db"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,testserver"
    REQUIRE_ORIGIN_ON_PROTECTED_API: bool = True
    PROTECTED_API_PATHS: str = "/api/dictionary/translate"
    TRANSLATE_MODEL: str = "google/gemini-2.5-flash"
    INTERNAL_API_KEY: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()


def get_settings() -> Settings:
    return settings


def get_allowed_origins() -> list[str]:
    return [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]


def get_allowed_hosts() -> list[str]:
    return [host.strip().lower() for host in settings.ALLOWED_HOSTS.split(",") if host.strip()]


def get_protected_api_paths() -> list[str]:
    return [path.strip() for path in settings.PROTECTED_API_PATHS.split(",") if path.strip()]
