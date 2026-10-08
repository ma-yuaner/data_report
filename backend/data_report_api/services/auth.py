from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from werkzeug.security import check_password_hash, generate_password_hash

from .data_source import DataSource


USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "AUTH_ERROR"):
        super().__init__(message)
        self.status = status
        self.code = code


class MySqlAuthStore:
    TABLE_STATEMENTS = (
        """
        CREATE TABLE IF NOT EXISTS auth_user (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            username VARCHAR(64) NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            is_admin TINYINT(1) NOT NULL DEFAULT 0,
            is_enabled TINYINT(1) NOT NULL DEFAULT 1,
            must_change_password TINYINT(1) NOT NULL DEFAULT 1,
            failed_attempts INT NOT NULL DEFAULT 0,
            locked_until DATETIME NULL,
            password_changed_at DATETIME NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_auth_user_username (username),
            KEY idx_auth_user_enabled_admin (is_enabled, is_admin)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据中心本地登录账号'
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_session (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            user_id BIGINT UNSIGNED NOT NULL,
            token_hash CHAR(64) NOT NULL,
            csrf_token_hash CHAR(64) NOT NULL,
            created_at DATETIME NOT NULL,
            last_seen_at DATETIME NOT NULL,
            absolute_expires_at DATETIME NOT NULL,
            revoked_at DATETIME NULL,
            ip_address VARCHAR(64) NULL,
            user_agent VARCHAR(500) NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_auth_session_token (token_hash),
            KEY idx_auth_session_user_active (user_id, revoked_at),
            KEY idx_auth_session_expiry (absolute_expires_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据中心服务端登录会话'
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_audit_log (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            user_id BIGINT UNSIGNED NULL,
            username VARCHAR(64) NULL,
            action VARCHAR(64) NOT NULL,
            success TINYINT(1) NOT NULL,
            ip_address VARCHAR(64) NULL,
            user_agent VARCHAR(500) NULL,
            detail_json TEXT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            KEY idx_auth_audit_created (created_at),
            KEY idx_auth_audit_user (user_id, created_at),
            KEY idx_auth_audit_action (action, success, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据中心认证审计日志'
        """,
    )

    def __init__(self, config: dict[str, Any]):
        mysql_config = dict(config)
        mysql_config["DATA_MODE"] = "mysql"
        self.source = DataSource(mysql_config)

    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        import pymysql

        connection = self.source.connect()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                return dict(row) if row else None
        finally:
            connection.close()

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        import pymysql

        connection = self.source.connect()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        connection = self.source.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return int(cursor.lastrowid or cursor.rowcount)
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        connection = self.source.connect()
        try:
            with connection.cursor() as cursor:
                for statement in self.TABLE_STATEMENTS:
                    cursor.execute(statement)
        finally:
            connection.close()

    def user_count(self) -> int:
        row = self._fetchone("SELECT count(1) AS total FROM auth_user")
        return int(row["total"] if row else 0)

    def enabled_admin_count(self) -> int:
        row = self._fetchone(
            "SELECT count(1) AS total FROM auth_user WHERE is_admin = 1 AND is_enabled = 1"
        )
        return int(row["total"] if row else 0)

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        return self._fetchone("SELECT * FROM auth_user WHERE username = %s", (username,))

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        return self._fetchone("SELECT * FROM auth_user WHERE id = %s", (user_id,))

    def create_user(self, values: dict[str, Any]) -> dict[str, Any]:
        user_id = self._execute(
            """
            INSERT INTO auth_user (
                username, display_name, password_hash, is_admin, is_enabled,
                must_change_password, failed_attempts, locked_until,
                password_changed_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 0, NULL, %s, %s, %s)
            """,
            (
                values["username"], values["display_name"], values["password_hash"],
                int(values["is_admin"]), int(values["is_enabled"]),
                int(values["must_change_password"]), values.get("password_changed_at"),
                values["created_at"], values["updated_at"],
            ),
        )
        return self.get_user_by_id(user_id) or {}

    def update_login_failure(
        self, user_id: int, failed_attempts: int, locked_until: datetime | None, now: datetime
    ) -> None:
        self._execute(
            "UPDATE auth_user SET failed_attempts = %s, locked_until = %s, updated_at = %s WHERE id = %s",
            (failed_attempts, locked_until, now, user_id),
        )

    def reset_login_state(self, user_id: int, now: datetime) -> None:
        self._execute(
            "UPDATE auth_user SET failed_attempts = 0, locked_until = NULL, updated_at = %s WHERE id = %s",
            (now, user_id),
        )

    def set_password(
        self, user_id: int, password_hash: str, must_change: bool, now: datetime
    ) -> None:
        self._execute(
            """
            UPDATE auth_user
            SET password_hash = %s, must_change_password = %s, failed_attempts = 0,
                locked_until = NULL, password_changed_at = %s, updated_at = %s
            WHERE id = %s
            """,
            (password_hash, int(must_change), now, now, user_id),
        )

    def update_user(self, user_id: int, values: dict[str, Any], now: datetime) -> None:
        assignments: list[str] = []
        params: list[Any] = []
        mapping = {
            "display_name": "display_name",
            "is_admin": "is_admin",
            "is_enabled": "is_enabled",
        }
        for key, column in mapping.items():
            if key in values:
                assignments.append(f"{column} = %s")
                params.append(int(values[key]) if key.startswith("is_") else values[key])
        if not assignments:
            return
        assignments.append("updated_at = %s")
        params.extend((now, user_id))
        self._execute(
            f"UPDATE auth_user SET {', '.join(assignments)} WHERE id = %s", tuple(params)
        )

    def list_users(self) -> list[dict[str, Any]]:
        return self._fetchall(
            """
            SELECT id, username, display_name, is_admin, is_enabled,
                   must_change_password, failed_attempts, locked_until,
                   password_changed_at, created_at, updated_at
            FROM auth_user ORDER BY id
            """
        )

    def create_session(self, values: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO auth_session (
                user_id, token_hash, csrf_token_hash, created_at, last_seen_at,
                absolute_expires_at, revoked_at, ip_address, user_agent
            ) VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s)
            """,
            (
                values["user_id"], values["token_hash"], values["csrf_token_hash"],
                values["created_at"], values["last_seen_at"],
                values["absolute_expires_at"], values.get("ip_address"),
                values.get("user_agent"),
            ),
        )

    def get_session(self, hashed_token: str) -> dict[str, Any] | None:
        return self._fetchone(
            """
            SELECT s.id AS session_id, s.user_id, s.token_hash, s.csrf_token_hash,
                   s.created_at AS session_created_at, s.last_seen_at,
                   s.absolute_expires_at, s.revoked_at,
                   u.id, u.username, u.display_name, u.password_hash,
                   u.is_admin, u.is_enabled, u.must_change_password,
                   u.failed_attempts, u.locked_until, u.password_changed_at,
                   u.created_at, u.updated_at
            FROM auth_session s
            JOIN auth_user u ON u.id = s.user_id
            WHERE s.token_hash = %s
            """,
            (hashed_token,),
        )

    def touch_session(self, session_id: int, now: datetime) -> None:
        self._execute(
            "UPDATE auth_session SET last_seen_at = %s WHERE id = %s AND revoked_at IS NULL",
            (now, session_id),
        )

    def revoke_session(self, session_id: int, now: datetime) -> None:
        self._execute(
            "UPDATE auth_session SET revoked_at = %s WHERE id = %s AND revoked_at IS NULL",
            (now, session_id),
        )

    def revoke_user_sessions(self, user_id: int, now: datetime) -> None:
        self._execute(
            "UPDATE auth_session SET revoked_at = %s WHERE user_id = %s AND revoked_at IS NULL",
            (now, user_id),
        )

    def write_audit(self, values: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO auth_audit_log (
                user_id, username, action, success, ip_address, user_agent,
                detail_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                values.get("user_id"), values.get("username"), values["action"],
                int(values["success"]), values.get("ip_address"), values.get("user_agent"),
                json.dumps(values.get("detail") or {}, ensure_ascii=False), values["created_at"],
            ),
        )

    def list_audits(self, limit: int = 200) -> list[dict[str, Any]]:
        return self._fetchall(
            """
            SELECT id, user_id, username, action, success, ip_address,
                   detail_json, created_at
            FROM auth_audit_log ORDER BY id DESC LIMIT %s
            """,
            (limit,),
        )


class MemoryAuthStore:
    """Tests and local unit checks only; production sessions use MySQL."""

    def __init__(self):
        self.users: dict[int, dict[str, Any]] = {}
        self.sessions: dict[int, dict[str, Any]] = {}
        self.audits: list[dict[str, Any]] = []
        self._user_id = 0
        self._session_id = 0
        self._audit_id = 0
        self._lock = threading.RLock()

    def ensure_schema(self) -> None:
        return None

    def user_count(self) -> int:
        return len(self.users)

    def enabled_admin_count(self) -> int:
        return sum(bool(row["is_admin"] and row["is_enabled"]) for row in self.users.values())

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self._lock:
            return deepcopy(next((row for row in self.users.values() if row["username"] == username), None))

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self._lock:
            return deepcopy(self.users.get(user_id))

    def create_user(self, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._user_id += 1
            row = {
                "id": self._user_id, "failed_attempts": 0, "locked_until": None,
                **deepcopy(values),
            }
            self.users[self._user_id] = row
            return deepcopy(row)

    def update_login_failure(self, user_id: int, failed_attempts: int, locked_until: datetime | None, now: datetime) -> None:
        with self._lock:
            self.users[user_id].update(failed_attempts=failed_attempts, locked_until=locked_until, updated_at=now)

    def reset_login_state(self, user_id: int, now: datetime) -> None:
        with self._lock:
            self.users[user_id].update(failed_attempts=0, locked_until=None, updated_at=now)

    def set_password(self, user_id: int, password_hash: str, must_change: bool, now: datetime) -> None:
        with self._lock:
            self.users[user_id].update(
                password_hash=password_hash, must_change_password=must_change,
                failed_attempts=0, locked_until=None, password_changed_at=now,
                updated_at=now,
            )

    def update_user(self, user_id: int, values: dict[str, Any], now: datetime) -> None:
        with self._lock:
            self.users[user_id].update(**deepcopy(values), updated_at=now)

    def list_users(self) -> list[dict[str, Any]]:
        with self._lock:
            return [deepcopy(self.users[key]) for key in sorted(self.users)]

    def create_session(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._session_id += 1
            self.sessions[self._session_id] = {"session_id": self._session_id, "revoked_at": None, **deepcopy(values)}

    def get_session(self, hashed_token: str) -> dict[str, Any] | None:
        with self._lock:
            session = next((row for row in self.sessions.values() if row["token_hash"] == hashed_token), None)
            if not session:
                return None
            user = self.users.get(int(session["user_id"]))
            return deepcopy({**session, **(user or {})}) if user else None

    def touch_session(self, session_id: int, now: datetime) -> None:
        with self._lock:
            self.sessions[session_id]["last_seen_at"] = now

    def revoke_session(self, session_id: int, now: datetime) -> None:
        with self._lock:
            self.sessions[session_id]["revoked_at"] = now

    def revoke_user_sessions(self, user_id: int, now: datetime) -> None:
        with self._lock:
            for row in self.sessions.values():
                if row["user_id"] == user_id and row.get("revoked_at") is None:
                    row["revoked_at"] = now

    def write_audit(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._audit_id += 1
            self.audits.append({"id": self._audit_id, **deepcopy(values)})

    def list_audits(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(deepcopy(self.audits)))[:limit]


class AuthManager:
    def __init__(
        self,
        store: MySqlAuthStore | MemoryAuthStore,
        config: dict[str, Any],
        now_fn: Callable[[], datetime] = utc_now,
    ):
        self.store = store
        self.config = config
        self.now_fn = now_fn

    def initialize(self) -> bool:
        if self.config.get("AUTH_AUTO_CREATE_TABLES", True):
            self.store.ensure_schema()
        username = str(self.config.get("AUTH_BOOTSTRAP_ADMIN_USERNAME", "")).strip()
        password = str(self.config.get("AUTH_BOOTSTRAP_ADMIN_PASSWORD", ""))
        if self.store.user_count() == 0 and username and password:
            try:
                self._create_user(
                    username=username,
                    display_name=str(self.config.get("AUTH_BOOTSTRAP_ADMIN_DISPLAY_NAME", "系统管理员")),
                    password=password,
                    is_admin=True,
                    must_change_password=True,
                )
            except Exception:
                # Gunicorn workers may initialize at the same time. If another
                # worker has already inserted the same bootstrap account, the
                # unique-key failure is harmless; unrelated database errors
                # must still stop startup.
                normalized = self.normalize_username(username)
                if not self.store.get_user_by_username(normalized):
                    raise
                return True
            self.audit("bootstrap_admin", True, username=username, detail={"source": "environment"})
            return True
        return self.store.user_count() > 0

    @staticmethod
    def normalize_username(value: str) -> str:
        username = value.strip().lower()
        if not USERNAME_RE.fullmatch(username):
            raise AuthError("用户名须为3至64位字母、数字、点、下划线或短横线")
        return username

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password) < 8 or not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
            raise AuthError("密码至少8位，且必须同时包含字母和数字")

    @staticmethod
    def public_user(user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(user["id"]),
            "username": str(user["username"]),
            "displayName": str(user["display_name"]),
            "isAdmin": bool(user["is_admin"]),
            "isEnabled": bool(user["is_enabled"]),
            "mustChangePassword": bool(user["must_change_password"]),
            "failedAttempts": int(user.get("failed_attempts") or 0),
            "lockedUntil": AuthManager.iso(user.get("locked_until")),
            "passwordChangedAt": AuthManager.iso(user.get("password_changed_at")),
            "createdAt": AuthManager.iso(user.get("created_at")),
        }

    @staticmethod
    def iso(value: Any) -> str | None:
        return value.isoformat(timespec="seconds") if isinstance(value, datetime) else None

    def audit(
        self, action: str, success: bool, *, user: dict[str, Any] | None = None,
        username: str | None = None, ip_address: str | None = None,
        user_agent: str | None = None, detail: dict[str, Any] | None = None,
    ) -> None:
        self.store.write_audit({
            "user_id": user.get("id") if user else None,
            "username": user.get("username") if user else username,
            "action": action, "success": success, "ip_address": ip_address,
            "user_agent": (user_agent or "")[:500] or None,
            "detail": detail or {}, "created_at": self.now_fn(),
        })

    def login(self, username_value: str, password: str, ip_address: str, user_agent: str) -> dict[str, Any]:
        try:
            username = self.normalize_username(username_value)
        except AuthError:
            username = username_value.strip().lower()[:64]
        user = self.store.get_user_by_username(username)
        now = self.now_fn()
        invalid = not user or not bool(user.get("is_enabled"))
        locked_until = user.get("locked_until") if user else None
        if locked_until and locked_until > now:
            invalid = True
        if invalid or not check_password_hash(str(user.get("password_hash", "")), password):
            if user and bool(user.get("is_enabled")) and not (locked_until and locked_until > now):
                attempts = int(user.get("failed_attempts") or 0) + 1
                max_attempts = int(self.config.get("AUTH_MAX_FAILED_ATTEMPTS", 5))
                new_lock = now + timedelta(seconds=int(self.config.get("AUTH_LOCK_SECONDS", 900))) if attempts >= max_attempts else None
                self.store.update_login_failure(int(user["id"]), attempts, new_lock, now)
            self.audit("login", False, user=user, username=username, ip_address=ip_address, user_agent=user_agent, detail={"reason": "invalid_credentials"})
            raise AuthError("用户名或密码错误", 401, "INVALID_CREDENTIALS")

        self.store.reset_login_state(int(user["id"]), now)
        session = self.create_session(user, ip_address, user_agent, now)
        self.audit("login", True, user=user, ip_address=ip_address, user_agent=user_agent)
        return {"user": self.public_user(user), **session}

    def create_session(
        self, user: dict[str, Any], ip_address: str, user_agent: str,
        now: datetime | None = None,
    ) -> dict[str, str]:
        now = now or self.now_fn()
        raw_token = secrets.token_urlsafe(48)
        raw_csrf = secrets.token_urlsafe(32)
        self.store.create_session({
            "user_id": int(user["id"]), "token_hash": token_hash(raw_token),
            "csrf_token_hash": token_hash(raw_csrf), "created_at": now,
            "last_seen_at": now,
            "absolute_expires_at": now + timedelta(seconds=int(self.config.get("AUTH_ABSOLUTE_TIMEOUT_SECONDS", 86400))),
            "ip_address": ip_address, "user_agent": user_agent[:500],
        })
        return {"sessionToken": raw_token, "csrfToken": raw_csrf}

    def authenticate(self, raw_token: str | None) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if not raw_token:
            return None
        session = self.store.get_session(token_hash(raw_token))
        if not session or session.get("revoked_at") is not None:
            return None
        now = self.now_fn()
        idle_timeout = timedelta(seconds=int(self.config.get("AUTH_IDLE_TIMEOUT_SECONDS", 14400)))
        if not bool(session.get("is_enabled")) or now >= session["absolute_expires_at"] or now - session["last_seen_at"] >= idle_timeout:
            self.store.revoke_session(int(session["session_id"]), now)
            return None
        if now - session["last_seen_at"] >= timedelta(seconds=int(self.config.get("AUTH_SESSION_TOUCH_SECONDS", 60))):
            self.store.touch_session(int(session["session_id"]), now)
            session["last_seen_at"] = now
        return session, session

    def verify_csrf(self, session: dict[str, Any], raw_csrf: str | None) -> bool:
        return bool(raw_csrf) and hmac.compare_digest(
            str(session["csrf_token_hash"]), token_hash(str(raw_csrf))
        )

    def logout(self, user: dict[str, Any], session: dict[str, Any], ip_address: str, user_agent: str) -> None:
        self.store.revoke_session(int(session["session_id"]), self.now_fn())
        self.audit("logout", True, user=user, ip_address=ip_address, user_agent=user_agent)

    def change_password(
        self, user: dict[str, Any], current_password: str, new_password: str,
        ip_address: str, user_agent: str,
    ) -> dict[str, str]:
        fresh = self.store.get_user_by_id(int(user["id"]))
        if not fresh or not check_password_hash(str(fresh["password_hash"]), current_password):
            self.audit("change_password", False, user=user, ip_address=ip_address, user_agent=user_agent, detail={"reason": "invalid_current_password"})
            raise AuthError("当前密码错误", 400, "INVALID_CURRENT_PASSWORD")
        self.validate_password(new_password)
        if check_password_hash(str(fresh["password_hash"]), new_password):
            raise AuthError("新密码不能与当前密码相同")
        now = self.now_fn()
        self.store.set_password(int(user["id"]), generate_password_hash(new_password, method="scrypt"), False, now)
        self.store.revoke_user_sessions(int(user["id"]), now)
        updated = self.store.get_user_by_id(int(user["id"])) or fresh
        session = self.create_session(updated, ip_address, user_agent, now)
        self.audit("change_password", True, user=updated, ip_address=ip_address, user_agent=user_agent)
        return session

    def require_admin(self, actor: dict[str, Any]) -> None:
        if not bool(actor.get("is_admin")):
            raise AuthError("没有账号管理权限", 403, "ADMIN_REQUIRED")

    def _create_user(
        self, *, username: str, display_name: str, password: str,
        is_admin: bool, must_change_password: bool,
    ) -> dict[str, Any]:
        username = self.normalize_username(username)
        name = display_name.strip()
        if not name or len(name) > 100:
            raise AuthError("姓名不能为空且不能超过100个字符")
        self.validate_password(password)
        if self.store.get_user_by_username(username):
            raise AuthError("用户名已存在", 409, "USERNAME_EXISTS")
        now = self.now_fn()
        return self.store.create_user({
            "username": username, "display_name": name,
            "password_hash": generate_password_hash(password, method="scrypt"),
            "is_admin": is_admin, "is_enabled": True,
            "must_change_password": must_change_password,
            "password_changed_at": None, "created_at": now, "updated_at": now,
        })

    def create_user(
        self, actor: dict[str, Any], *, username: str, display_name: str,
        password: str, is_admin: bool, ip_address: str, user_agent: str,
    ) -> dict[str, Any]:
        self.require_admin(actor)
        user = self._create_user(
            username=username, display_name=display_name, password=password,
            is_admin=is_admin, must_change_password=True,
        )
        self.audit("create_user", True, user=actor, ip_address=ip_address, user_agent=user_agent, detail={"targetUserId": user["id"], "targetUsername": user["username"], "isAdmin": is_admin})
        return self.public_user(user)

    def update_user(
        self, actor: dict[str, Any], target_id: int, values: dict[str, Any],
        ip_address: str, user_agent: str,
    ) -> dict[str, Any]:
        self.require_admin(actor)
        target = self.store.get_user_by_id(target_id)
        if not target:
            raise AuthError("账号不存在", 404, "USER_NOT_FOUND")
        if target_id == int(actor["id"]) and (values.get("is_enabled") is False or values.get("is_admin") is False):
            raise AuthError("不能禁用自己或取消自己的管理员身份")
        if bool(target["is_admin"]) and bool(target["is_enabled"]) and (
            values.get("is_enabled") is False or values.get("is_admin") is False
        ) and self.store.enabled_admin_count() <= 1:
            raise AuthError("系统必须保留至少一个启用的管理员")
        cleaned: dict[str, Any] = {}
        if "display_name" in values:
            display_name = str(values["display_name"]).strip()
            if not display_name or len(display_name) > 100:
                raise AuthError("姓名不能为空且不能超过100个字符")
            cleaned["display_name"] = display_name
        for key in ("is_admin", "is_enabled"):
            if key in values:
                if not isinstance(values[key], bool):
                    raise AuthError("账号状态参数不合法")
                cleaned[key] = values[key]
        self.store.update_user(target_id, cleaned, self.now_fn())
        if cleaned.get("is_enabled") is False:
            self.store.revoke_user_sessions(target_id, self.now_fn())
        updated = self.store.get_user_by_id(target_id) or target
        self.audit("update_user", True, user=actor, ip_address=ip_address, user_agent=user_agent, detail={"targetUserId": target_id, "changes": cleaned})
        return self.public_user(updated)

    def reset_password(
        self, actor: dict[str, Any], target_id: int, new_password: str,
        ip_address: str, user_agent: str,
    ) -> None:
        self.require_admin(actor)
        target = self.store.get_user_by_id(target_id)
        if not target:
            raise AuthError("账号不存在", 404, "USER_NOT_FOUND")
        self.validate_password(new_password)
        now = self.now_fn()
        self.store.set_password(target_id, generate_password_hash(new_password, method="scrypt"), True, now)
        self.store.revoke_user_sessions(target_id, now)
        self.audit("reset_password", True, user=actor, ip_address=ip_address, user_agent=user_agent, detail={"targetUserId": target_id, "targetUsername": target["username"]})

    def users(self, actor: dict[str, Any]) -> list[dict[str, Any]]:
        self.require_admin(actor)
        return [self.public_user(row) for row in self.store.list_users()]

    def audits(self, actor: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        self.require_admin(actor)
        output: list[dict[str, Any]] = []
        for row in self.store.list_audits(max(1, min(limit, 500))):
            detail = row.get("detail")
            if detail is None and row.get("detail_json"):
                try:
                    detail = json.loads(row["detail_json"])
                except (TypeError, json.JSONDecodeError):
                    detail = {}
            output.append({
                "id": int(row["id"]), "userId": row.get("user_id"),
                "username": row.get("username"), "action": row["action"],
                "success": bool(row["success"]), "ipAddress": row.get("ip_address"),
                "detail": detail or {}, "createdAt": self.iso(row.get("created_at")),
            })
        return output
