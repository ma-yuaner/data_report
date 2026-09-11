from __future__ import annotations

import os


class Config:
    APP_ENV = os.getenv("APP_ENV", "development")
    DEBUG = APP_ENV == "development"
    SECRET_KEY = os.getenv("SECRET_KEY", "development-only")
    DATA_MODE = os.getenv("DATA_MODE", "mock")
    HIVE_HOST = os.getenv("HIVE_HOST", "")
    HIVE_PORT = int(os.getenv("HIVE_PORT", "10000"))
    HIVE_DATABASE = os.getenv("HIVE_DATABASE", "lywz")
    HIVE_USER = os.getenv("HIVE_USER", "")
    HIVE_PASSWORD = os.getenv("HIVE_PASSWORD", "")
    HIVE_AUTH = os.getenv("HIVE_AUTH", "NONE")
    PROFIT_CACHE_TTL = int(os.getenv("PROFIT_CACHE_TTL", "300"))
    JSON_AS_ASCII = False


class TestConfig(Config):
    TESTING = True
    DEBUG = False
    DATA_MODE = "mock"
