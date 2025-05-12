from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from dotenv import load_dotenv


load_dotenv()


class Settings(BaseSettings):
    PG_URL: SecretStr
    REDIS_HOST: str
    REDIS_PORT: int
    STMT_KEY: str
    SMTP_EMAIL: str
    AUTH_SECRET_KEY: SecretStr
    model_config = SettingsConfigDict(env_file=".env", extra="allow")


settings = Settings()
