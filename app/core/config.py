from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, EmailStr, validator
from typing import List, Union

class Settings(BaseSettings):
    PROJECT_NAME: str = "MySuf Backend"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    FACE_MATCH_THRESHOLD: float = 0.55
    MIN_IMAGE_WIDTH: int = 720
    MIN_IMAGE_HEIGHT: int = 480
    OCR_MODEL_LANGUAGE: str = "en"
    INSIGHTFACE_MODEL_NAME: str = "buffalo_l"
    
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_PORT: str
    DATABASE_URL: str

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

settings = Settings()
