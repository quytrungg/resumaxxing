from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://localhost:5432/resumaxxing"
    upload_dir: str = "uploads"
    default_user_email: str = "local@resumaxxing.dev"

    class Config:
        env_file = ".env"


settings = Settings()
