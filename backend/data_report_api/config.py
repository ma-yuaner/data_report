from __future__ import annotations

import os


class Config:
    APP_ENV = os.getenv("APP_ENV", "development")
    DEBUG = APP_ENV == "development"
    SECRET_KEY = os.getenv("SECRET_KEY", "development-only")
    DATA_MODE = os.getenv("DATA_MODE", "mock")
    JSON_AS_ASCII = False


class TestConfig(Config):
    TESTING = True
    DEBUG = False
    DATA_MODE = "mock"

