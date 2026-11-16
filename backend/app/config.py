from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://localhost:5432/resumaxxing"
    upload_dir: str = "uploads"
    default_user_email: str = "local@resumaxxing.dev"
    # Key material for encrypting stored API keys (see services/crypto.py).
    secret_key: str = "dev-insecure-secret-change-me"
    # When non-empty, every /api route except /api/health and /api/auth
    # requires a matching X-App-Password header.
    app_password: str = ""
    # JD URL scraping guards.
    scrape_max_bytes: int = 2_000_000
    scrape_timeout: float = 15.0

    class Config:
        env_file = ".env"


settings = Settings()
