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
    RISK_UPLOAD_WEBHDFS_URL = os.getenv("RISK_UPLOAD_WEBHDFS_URL", "")
    RISK_UPLOAD_WEBHDFS_USER = os.getenv("RISK_UPLOAD_WEBHDFS_USER", HIVE_USER)
    RISK_UPLOAD_WEBHDFS_HOST_MAP = os.getenv(
        "RISK_UPLOAD_WEBHDFS_HOST_MAP", ""
    )
    RISK_UPLOAD_WEBHDFS_CONNECT_TIMEOUT = int(
        os.getenv("RISK_UPLOAD_WEBHDFS_CONNECT_TIMEOUT", "10")
    )
    RISK_UPLOAD_WEBHDFS_READ_TIMEOUT = int(
        os.getenv("RISK_UPLOAD_WEBHDFS_READ_TIMEOUT", "300")
    )
    RISK_UPLOAD_HDFS_URI = os.getenv("RISK_UPLOAD_HDFS_URI", "hdfs://mycluster")
    RISK_UPLOAD_HDFS_ROOT = os.getenv(
        "RISK_UPLOAD_HDFS_ROOT", "/tmp/data-report/risk-uploads"
    )
    RISK_UPLOAD_ORC_TIMEZONE = os.getenv(
        "RISK_UPLOAD_ORC_TIMEZONE", "Asia/Shanghai"
    )
    RISK_UPLOAD_POLL_SECONDS = int(os.getenv("RISK_UPLOAD_POLL_SECONDS", "2"))
    MAX_CONTENT_LENGTH = RISK_UPLOAD_MAX_BYTES
    JSON_AS_ASCII = False
    AUTH_ENABLED = env_bool("AUTH_ENABLED", True)
    AUTH_AUTO_CREATE_TABLES = env_bool("AUTH_AUTO_CREATE_TABLES", True)
    AUTH_IDLE_TIMEOUT_SECONDS = int(os.getenv("AUTH_IDLE_TIMEOUT_SECONDS", "14400"))
    AUTH_ABSOLUTE_TIMEOUT_SECONDS = int(os.getenv("AUTH_ABSOLUTE_TIMEOUT_SECONDS", "86400"))
    AUTH_SESSION_TOUCH_SECONDS = int(os.getenv("AUTH_SESSION_TOUCH_SECONDS", "60"))
    AUTH_MAX_FAILED_ATTEMPTS = int(os.getenv("AUTH_MAX_FAILED_ATTEMPTS", "5"))
    AUTH_LOCK_SECONDS = int(os.getenv("AUTH_LOCK_SECONDS", "900"))
    AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "data_report_session")
    AUTH_CSRF_COOKIE_NAME = os.getenv("AUTH_CSRF_COOKIE_NAME", "data_report_csrf")
    AUTH_COOKIE_SECURE = env_bool("AUTH_COOKIE_SECURE", False)
    AUTH_BOOTSTRAP_ADMIN_USERNAME = os.getenv("AUTH_BOOTSTRAP_ADMIN_USERNAME", "")
    AUTH_BOOTSTRAP_ADMIN_PASSWORD = os.getenv("AUTH_BOOTSTRAP_ADMIN_PASSWORD", "")
    AUTH_BOOTSTRAP_ADMIN_DISPLAY_NAME = os.getenv(
        "AUTH_BOOTSTRAP_ADMIN_DISPLAY_NAME", "系统管理员"
    )


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
    AUTH_ENABLED = False
    AUTH_COOKIE_SECURE = False
