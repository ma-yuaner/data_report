from __future__ import annotations

import os


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    APP_ENV = os.getenv("APP_ENV", "development")
    DEBUG = APP_ENV == "development"
    SECRET_KEY = os.getenv("SECRET_KEY", "development-only")
    DATA_MODE = os.getenv("DATA_MODE", "mysql")
    MYSQL_HOST = os.getenv("MYSQL_HOST", "")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "sibebid")
    MYSQL_USER = os.getenv("MYSQL_USER", "")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_CHARSET = os.getenv("MYSQL_CHARSET", "utf8mb4")
    MYSQL_CONNECT_TIMEOUT = int(os.getenv("MYSQL_CONNECT_TIMEOUT", "10"))
    MYSQL_READ_TIMEOUT = int(os.getenv("MYSQL_READ_TIMEOUT", "60"))
    MYSQL_WRITE_TIMEOUT = int(os.getenv("MYSQL_WRITE_TIMEOUT", "60"))
    HIVE_HOST = os.getenv("HIVE_HOST", "")
    HIVE_PORT = int(os.getenv("HIVE_PORT", "10000"))
    HIVE_DATABASE = os.getenv("HIVE_DATABASE", "lywz")
    HIVE_USER = os.getenv("HIVE_USER", "")
    HIVE_PASSWORD = os.getenv("HIVE_PASSWORD", "")
    HIVE_AUTH = os.getenv("HIVE_AUTH", "NONE")
    PROFIT_CACHE_TTL = int(os.getenv("PROFIT_CACHE_TTL", "300"))
    RISK_UPLOAD_ENABLED = env_bool("RISK_UPLOAD_ENABLED", True)
    RISK_UPLOAD_TOKEN = os.getenv("RISK_UPLOAD_TOKEN", "")
    RISK_UPLOAD_ROOT = os.getenv("RISK_UPLOAD_ROOT", "/app/var/risk-uploads")
    RISK_UPLOAD_MAX_MB = int(os.getenv("RISK_UPLOAD_MAX_MB", "200"))
    RISK_UPLOAD_MAX_BYTES = RISK_UPLOAD_MAX_MB * 1024 * 1024
    RISK_UPLOAD_INSERT_BATCH_SIZE = int(os.getenv("RISK_UPLOAD_INSERT_BATCH_SIZE", "2000"))
    RISK_UPLOAD_POLL_SECONDS = int(os.getenv("RISK_UPLOAD_POLL_SECONDS", "2"))
    MAX_CONTENT_LENGTH = RISK_UPLOAD_MAX_BYTES
    JSON_AS_ASCII = False


class TestConfig(Config):
    TESTING = True
    DEBUG = False
    DATA_MODE = "mock"
    MYSQL_HOST = ""
    MYSQL_USER = ""
    HIVE_HOST = ""
    HIVE_USER = ""
    RISK_UPLOAD_ENABLED = False
    RISK_UPLOAD_ROOT = "/tmp/data-report-risk-upload-tests"
