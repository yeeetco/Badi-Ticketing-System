from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    # Resolve .env from this file, so commands work from any directory.
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env", extra="ignore"
    )

    database_url: str
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000"
    cookie_secure: bool = False
    environment: Literal['development', 'production'] = 'development'
    allowed_hosts: str = 'localhost,127.0.0.1,testserver'

    @model_validator(mode='after')
    def production_boundaries(self):
        if self.environment == 'production':
            origins = [value.strip() for value in self.allowed_origins.split(',')]
            if not self.cookie_secure or not origins or any(not value.startswith('https://') or '*' in value for value in origins):
                raise ValueError('Production requires secure cookies and explicit HTTPS origins.')
            if '*' in self.allowed_hosts or 'testserver' in self.allowed_hosts:
                raise ValueError('Production requires explicit deployed hosts.')
        return self


settings = Settings()
