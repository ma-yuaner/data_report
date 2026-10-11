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

import bcrypt
from werkzeug.security import check_password_hash

from .data_source import DataSource
from ..time_utils import business_now_naive


USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ROLE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")

ROLE_PERMISSIONS = {
    "DATA_ENTRY": (
        "smart_placement.create",
        "smart_placement.edit",
        "smart_placement.delete",
        "smart_placement.withdraw",
    ),
    "DATA_MANAGER": (
        "smart_placement.review_data",
        "smart_placement.cancel",
    ),
    "POLICY_MANAGER": ("smart_placement.review_policy",),
    "POLICY_OPERATOR": (
        "smart_placement.claim",
        "smart_placement.execute",
        "smart_placement.orders.attention",
    ),
}
ROLE_MENUS = {
    "DATA_ENTRY": ("smart.placement.policies",),
    "DATA_MANAGER": ("smart.placement.policies",),
    "POLICY_MANAGER": ("smart.placement.policies",),
    "POLICY_OPERATOR": ("smart.placement.policies", "smart.placement.orders"),
}
BUSINESS_ROLE_CATALOG = (
    {"code": "DATA_ENTRY", "name": "数据录入员", "description": "录入、编辑并提交智能投放机会"},
    {"code": "DATA_MANAGER", "name": "数据运营经理", "description": "审核数据口径、样本和预估价值"},
    {"code": "POLICY_MANAGER", "name": "业务经理", "description": "任一业务经理可审核政策可执行性与风险"},
    {"code": "POLICY_OPERATOR", "name": "智能业务执行员", "description": "认领已审核任务并登记投放结果"},
)
PERMISSION_CATALOG = (
    {"code": "smart_placement.create", "name": "新建投放机会", "description": "创建投放机会并保存或提交", "menuCode": "smart.placement.policies"},
    {"code": "smart_placement.edit", "name": "编辑投放机会", "description": "编辑并重新提交本人创建的草稿或退回任务", "menuCode": "smart.placement.policies"},
    {"code": "smart_placement.delete", "name": "删除草稿或驳回任务", "description": "逻辑删除本人创建的草稿或已驳回任务并保留操作日志", "menuCode": "smart.placement.policies"},
    {"code": "smart_placement.withdraw", "name": "撤回待审核任务", "description": "在数据经理处理前撤回本人提交的任务并继续修改", "menuCode": "smart.placement.policies"},
    {"code": "smart_placement.cancel", "name": "作废投放任务", "description": "管理者作废尚未认领的已提交任务，必须填写原因", "menuCode": "smart.placement.policies"},
    {"code": "smart_placement.review_data", "name": "数据运营审核", "description": "审核数据口径、样本和预估价值", "menuCode": "smart.placement.policies"},
    {"code": "smart_placement.review_policy", "name": "业务经理审核", "description": "审核政策可执行性、风险与投放要求", "menuCode": "smart.placement.policies"},
    {"code": "smart_placement.claim", "name": "认领投放任务", "description": "认领已通过两级审核的投放任务", "menuCode": "smart.placement.policies"},
    {"code": "smart_placement.execute", "name": "登记投放结果", "description": "登记政策ID、投放时间并进入监控", "menuCode": "smart.placement.policies"},
    {"code": "smart_placement.orders.attention", "name": "处理收单关注", "description": "更新命中订单的关注状态和处理结果", "menuCode": "smart.placement.orders"},
    {"code": "monitor.center.view", "name": "查看监控中心", "description": "查看通用规则、命中事件和运行状态", "menuCode": "monitor.center"},
    {"code": "monitor.rule.manage", "name": "管理监控规则", "description": "新建、启用、暂停或停用监控规则", "menuCode": "monitor.center"},
    {"code": "monitor.event.view", "name": "查看监控事件", "description": "查看全部监控命中事件及业务关联", "menuCode": "monitor.center"},
    {"code": "monitor.event.manage", "name": "处理监控事件", "description": "确认、解决或忽略监控命中事件", "menuCode": "monitor.center"},
    {"code": "monitor.run.view", "name": "查看监控运行日志", "description": "查看采集、匹配和通知任务运行情况", "menuCode": "monitor.center"},
)
MENU_CATALOG = (
    {"code": "overview", "name": "经营总览", "description": "经营总览页面", "groupCode": "overview", "groupName": "经营总览"},
    {"code": "analysis.comprehensive", "name": "综合分析", "description": "出退改增综合经营分析", "groupCode": "analysis", "groupName": "业务分析"},
    {"code": "analysis.issue", "name": "出票分析", "description": "出票利润分析", "groupCode": "analysis", "groupName": "业务分析"},
    {"code": "analysis.refund", "name": "退票分析", "description": "退票利润分析", "groupCode": "analysis", "groupName": "业务分析"},
    {"code": "analysis.change", "name": "改签分析", "description": "改签利润分析", "groupCode": "analysis", "groupName": "业务分析"},
    {"code": "analysis.ancillary", "name": "增值分析", "description": "增值利润分析", "groupCode": "analysis", "groupName": "业务分析"},
    {"code": "risk.overview", "name": "风控总览", "description": "风控月度与趋势分析", "groupCode": "risk", "groupName": "风控分析"},
    {"code": "risk.issue", "name": "出票利润分析", "description": "风控出票利润分析", "groupCode": "risk", "groupName": "风控分析"},
    {"code": "risk.refund", "name": "退票利润分析", "description": "风控退票利润分析", "groupCode": "risk", "groupName": "风控分析"},
    {"code": "risk.change", "name": "改签利润分析", "description": "风控改签利润分析", "groupCode": "risk", "groupName": "风控分析"},
    {"code": "risk.errors", "name": "差错分析", "description": "差错原因与责任分析", "groupCode": "risk", "groupName": "风控分析"},
    {"code": "risk.orders", "name": "订单明细", "description": "风控订单明细", "groupCode": "risk", "groupName": "风控分析"},
    {"code": "risk.upload", "name": "数据上传", "description": "出退改风控数据上传", "groupCode": "risk", "groupName": "风控分析"},
    {"code": "customer_service.refund", "name": "退票分析", "description": "客服退票分析", "groupCode": "customer_service", "groupName": "客服分析"},
    {"code": "customer_service.change", "name": "改签分析", "description": "客服改签分析", "groupCode": "customer_service", "groupName": "客服分析"},
    {"code": "customer_service.flight_change", "name": "清Q/航变分析", "description": "客服清Q与航变分析", "groupCode": "customer_service", "groupName": "客服分析"},
    {"code": "smart.home", "name": "智能分析首页", "description": "智能分析工作台", "groupCode": "smart", "groupName": "智能分析"},
    {"code": "smart.placement.policies", "name": "投放政策", "description": "投放机会、审核、认领与登记", "groupCode": "smart", "groupName": "智能分析"},
    {"code": "smart.placement.orders", "name": "收单情况", "description": "政策命中订单与关注处理", "groupCode": "smart", "groupName": "智能分析"},
    {"code": "monitor.center", "name": "监控中心", "description": "通用规则、告警事件与任务运行监控", "groupCode": "monitor", "groupName": "监控中心"},
    {"code": "problems", "name": "问题中心", "description": "经营问题跟踪", "groupCode": "problems", "groupName": "问题中心"},
    {"code": "data_assets", "name": "数据资产", "description": "数据资产目录", "groupCode": "data_assets", "groupName": "数据资产"},
)

LEGACY_MENU_EXPANSIONS = {
    group_code: tuple(item["code"] for item in MENU_CATALOG if item["groupCode"] == group_code)
    for group_code in {item["groupCode"] for item in MENU_CATALOG}
}
MENU_CODES = {item["code"] for item in MENU_CATALOG}
MENU_GROUP_BY_CODE = {item["code"]: item["groupCode"] for item in MENU_CATALOG}


def configurable_menu_codes(menu_codes: Any) -> list[str]:
    """Return leaf page codes, expanding legacy first-level module codes."""
    normalized: set[str] = set()
    for raw_code in menu_codes or ():
        code = str(raw_code).strip()
        if not code:
            continue
        if code in LEGACY_MENU_EXPANSIONS:
            normalized.update(LEGACY_MENU_EXPANSIONS[code])
        elif code in MENU_CODES:
            normalized.add(code)
    return sorted(normalized)


def effective_menu_codes(menu_codes: Any) -> list[str]:
    """Return page codes plus their first-level group codes for navigation."""
    leaves = configurable_menu_codes(menu_codes)
    return sorted(set(leaves) | {MENU_GROUP_BY_CODE[code] for code in leaves})


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def password_hash(value: str) -> str:
    return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def password_matches(stored_hash: str, candidate: str) -> bool:
    try:
        if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
            return bcrypt.checkpw(candidate.encode("utf-8"), stored_hash.encode("utf-8"))
        return check_password_hash(stored_hash, candidate)
    except (TypeError, ValueError):
        return False


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "AUTH_ERROR"):
        super().__init__(message)
        self.status = status
        self.code = code


class MySqlAuthStore:
    TABLE_STATEMENTS = (
        """
        CREATE TABLE IF NOT EXISTS auth_user_security (
            user_id INT NOT NULL,
            must_change_password TINYINT(1) NOT NULL DEFAULT 0,
            failed_attempts INT NOT NULL DEFAULT 0,
            locked_until DATETIME NULL,
            password_changed_at DATETIME NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (user_id),
            KEY idx_auth_user_security_lock (locked_until)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='sys_user登录安全扩展'
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
        """
        CREATE TABLE IF NOT EXISTS sys_role_menu (
            role_id BIGINT UNSIGNED NOT NULL,
            menu_code VARCHAR(64) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (role_id, menu_code),
            KEY idx_sys_role_menu_code (menu_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色菜单权限'
        """,
        """
        CREATE TABLE IF NOT EXISTS sys_user_permission (
            user_id BIGINT UNSIGNED NOT NULL COMMENT 'sys_user.id',
            permission_code VARCHAR(100) NOT NULL COMMENT '权限编码',
            effect VARCHAR(8) NOT NULL COMMENT 'ALLOW额外开启；DENY单独关闭',
            assigned_by BIGINT UNSIGNED NULL COMMENT '配置人sys_user.id',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, permission_code),
            KEY idx_sup_permission (permission_code, effect)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户功能权限例外配置'
        """,
    )
    USER_SELECT = """
        SELECT u.id, u.username, u.email,
               coalesce(nullif(u.full_name, ''), u.username) AS display_name,
               u.hashed_password AS password_hash,
               (u.role = 'admin') AS is_admin,
               u.is_active AS is_enabled,
               coalesce(sec.must_change_password, 0) AS must_change_password,
               coalesce(sec.failed_attempts, 0) AS failed_attempts,
               sec.locked_until, sec.password_changed_at,
               u.created_at, u.updated_at
        FROM sys_user u
        LEFT JOIN auth_user_security sec ON sec.user_id = u.id
    """

    def __init__(self, config: dict[str, Any]):
        mysql_config = dict(config)
        mysql_config["DATA_MODE"] = "mysql"
        self.source = DataSource(mysql_config)

    @staticmethod
    def _missing_rbac(error: Exception) -> bool:
        return bool(getattr(error, "args", ())) and error.args[0] == 1146

    def _with_access(self, user: dict[str, Any] | None) -> dict[str, Any] | None:
        if not user:
            return None
        connection = None
        try:
            import pymysql

            connection = self.source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT r.role_code, r.role_name, r.description, rp.permission_code
                    FROM sys_user_role ur
                    JOIN sys_role r ON r.id = ur.role_id AND r.is_active = 1
                    LEFT JOIN sys_role_permission rp ON rp.role_id = r.id
                    WHERE ur.user_id = %s ORDER BY r.id, rp.permission_code
                    """,
                    (int(user["id"]),),
                )
                access_rows = [dict(row) for row in cursor.fetchall()]
                role_menu_configured = True
                try:
                    cursor.execute(
                        """
                        SELECT DISTINCT rm.menu_code
                        FROM sys_user_role ur
                        JOIN sys_role r ON r.id = ur.role_id AND r.is_active = 1
                        JOIN sys_role_menu rm ON rm.role_id = r.id
                        WHERE ur.user_id = %s ORDER BY rm.menu_code
                        """,
                        (int(user["id"]),),
                    )
                    role_menus = {str(row["menu_code"]) for row in cursor.fetchall()}
                except Exception as error:
                    if not self._missing_rbac(error):
                        raise
                    role_menu_configured = False
                    role_menus = set()
                try:
                    cursor.execute(
                        "SELECT menu_code FROM sys_user_menu WHERE user_id=%s ORDER BY id",
                        (int(user["id"]),),
                    )
                    direct_menus = {str(row["menu_code"]) for row in cursor.fetchall()}
                except Exception as error:
                    if not self._missing_rbac(error):
                        raise
                    direct_menus = set()
                try:
                    cursor.execute(
                        "SELECT permission_code, effect FROM sys_user_permission WHERE user_id=%s ORDER BY permission_code",
                        (int(user["id"]),),
                    )
                    permission_overrides = {
                        str(row["permission_code"]): str(row["effect"]).upper()
                        for row in cursor.fetchall()
                    }
                except Exception as error:
                    if not self._missing_rbac(error):
                        raise
                    permission_overrides = {}
            roles_by_code: dict[str, dict[str, str]] = {}
            role_permissions: set[str] = set()
            for row in access_rows:
                roles_by_code.setdefault(
                    row["role_code"],
                    {"code": row["role_code"], "name": row["role_name"], "description": row.get("description") or ""},
                )
                if row.get("permission_code"):
                    role_permissions.add(row["permission_code"])
            allowed_permissions = {
                code for code, effect in permission_overrides.items() if effect == "ALLOW"
            }
            denied_permissions = {
                code for code, effect in permission_overrides.items() if effect == "DENY"
            }
            permissions = (role_permissions | allowed_permissions) - denied_permissions
            permission_menus = {
                row["menuCode"] for row in PERMISSION_CATALOG
                if row["code"] in permissions
            }
            return {
                **user,
                "business_roles": list(roles_by_code.values()),
                "permissions": sorted(permissions),
                "role_permissions": sorted(role_permissions),
                "permission_overrides": permission_overrides,
                "menu_codes": effective_menu_codes(
                    role_menus | direct_menus | permission_menus
                ),
                "direct_menu_codes": sorted(direct_menus),
                "rbac_configured": role_menu_configured,
            }
        except Exception as error:
            if not self._missing_rbac(error):
                raise
            return {
                **user, "business_roles": [], "permissions": [],
                "role_permissions": [], "permission_overrides": {},
                "menu_codes": [], "direct_menu_codes": [], "rbac_configured": False,
            }
        finally:
            if connection is not None:
                connection.close()

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
        row = self._fetchone("SELECT count(1) AS total FROM sys_user")
        return int(row["total"] if row else 0)

    def enabled_admin_count(self) -> int:
        row = self._fetchone(
            "SELECT count(1) AS total FROM sys_user WHERE role = 'admin' AND is_active = 1"
        )
        return int(row["total"] if row else 0)

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        return self._with_access(self._fetchone(f"{self.USER_SELECT} WHERE u.username = %s", (username,)))

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        return self._with_access(self._fetchone(f"{self.USER_SELECT} WHERE u.id = %s", (user_id,)))

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        return self._with_access(self._fetchone(f"{self.USER_SELECT} WHERE u.email = %s", (email,)))

    def create_user(self, values: dict[str, Any]) -> dict[str, Any]:
        connection = self.source.connect()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sys_user (
                        username, email, hashed_password, full_name, role,
                        is_active, last_login_at, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s)
                    """,
                    (
                        values["username"], values["email"],
                        values["password_hash"], values["display_name"],
                        "admin" if values["is_admin"] else "analyst",
                        int(values["is_enabled"]), values["created_at"], values["updated_at"],
                    ),
                )
                user_id = int(cursor.lastrowid)
                for code in values.get("role_codes") or []:
                    cursor.execute(
                        """
                        INSERT INTO sys_user_role (user_id, role_id, assigned_by, assigned_at)
                        SELECT %s, id, %s, %s FROM sys_role
                        WHERE role_code=%s AND is_active=1
                        """,
                        (user_id, values.get("assigned_by"), values["created_at"], code),
                    )
                    if cursor.rowcount != 1:
                        raise AuthError(f"角色不存在或未启用：{code}")
                cursor.execute(
                    """
                    INSERT INTO auth_user_security (
                        user_id, must_change_password, failed_attempts, locked_until,
                        password_changed_at, created_at, updated_at
                    ) VALUES (%s, %s, 0, NULL, %s, %s, %s)
                    """,
                    (
                        user_id, int(values["must_change_password"]),
                        values.get("password_changed_at"), values["created_at"], values["updated_at"],
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.get_user_by_id(user_id) or {}

    def update_login_failure(
        self, user_id: int, failed_attempts: int, locked_until: datetime | None, now: datetime
    ) -> None:
        self._execute(
            """
            INSERT INTO auth_user_security (
                user_id, must_change_password, failed_attempts, locked_until,
                password_changed_at, created_at, updated_at
            ) VALUES (%s, 0, %s, %s, NULL, %s, %s)
            ON DUPLICATE KEY UPDATE failed_attempts = VALUES(failed_attempts),
                locked_until = VALUES(locked_until), updated_at = VALUES(updated_at)
            """,
            (user_id, failed_attempts, locked_until, now, now),
        )

    def reset_login_state(self, user_id: int, now: datetime) -> None:
        self._execute(
            """
            INSERT INTO auth_user_security (
                user_id, must_change_password, failed_attempts, locked_until,
                password_changed_at, created_at, updated_at
            ) VALUES (%s, 0, 0, NULL, NULL, %s, %s)
            ON DUPLICATE KEY UPDATE failed_attempts = 0, locked_until = NULL,
                updated_at = VALUES(updated_at)
            """,
            (user_id, now, now),
        )

    def set_password(
        self, user_id: int, password_hash: str, must_change: bool, now: datetime
    ) -> None:
        connection = self.source.connect()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE sys_user SET hashed_password = %s, updated_at = %s WHERE id = %s",
                    (password_hash, now, user_id),
                )
                cursor.execute(
                    """
                    INSERT INTO auth_user_security (
                        user_id, must_change_password, failed_attempts, locked_until,
                        password_changed_at, created_at, updated_at
                    ) VALUES (%s, %s, 0, NULL, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE must_change_password = VALUES(must_change_password),
                        failed_attempts = 0, locked_until = NULL,
                        password_changed_at = VALUES(password_changed_at), updated_at = VALUES(updated_at)
                    """,
                    (user_id, int(must_change), now, now, now),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def update_user(self, user_id: int, values: dict[str, Any], now: datetime) -> None:
        assignments: list[str] = []
        params: list[Any] = []
        if "display_name" in values:
            assignments.append("full_name = %s")
            params.append(values["display_name"])
        if "email" in values:
            assignments.append("email = %s")
            params.append(values["email"])
        if "is_admin" in values:
            assignments.append("role = %s")
            params.append("admin" if values["is_admin"] else "analyst")
        if "is_enabled" in values:
            assignments.append("is_active = %s")
            params.append(int(values["is_enabled"]))
        if not assignments:
            return
        assignments.append("updated_at = %s")
        params.extend((now, user_id))
        self._execute(
            f"UPDATE sys_user SET {', '.join(assignments)} WHERE id = %s", tuple(params)
        )

    def list_users(self) -> list[dict[str, Any]]:
        return [self._with_access(row) or row for row in self._fetchall(f"{self.USER_SELECT} ORDER BY u.id")]

    def list_business_roles(self) -> list[dict[str, Any]]:
        try:
            return [
                {"code": row["role_code"], "name": row["role_name"], "description": row.get("description") or ""}
                for row in self._fetchall(
                    "SELECT role_code, role_name, description FROM sys_role WHERE is_active=1 ORDER BY id"
                )
            ]
        except Exception as error:
            if self._missing_rbac(error):
                raise AuthError("智能投放角色表尚未创建，请先执行smart-placement-rbac.sql", 503, "RBAC_NOT_CONFIGURED") from error
            raise

    def list_roles(self) -> list[dict[str, Any]]:
        connection = self.source.connect()
        try:
            import pymysql

            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT r.role_code, r.role_name, r.description, r.is_active,
                           count(distinct ur.user_id) AS user_count
                    FROM sys_role r
                    LEFT JOIN sys_user_role ur ON ur.role_id = r.id
                    GROUP BY r.id, r.role_code, r.role_name, r.description, r.is_active
                    ORDER BY r.id
                    """
                )
                roles = [dict(row) for row in cursor.fetchall()]
                cursor.execute(
                    """
                    SELECT r.role_code, rm.menu_code
                    FROM sys_role r JOIN sys_role_menu rm ON rm.role_id = r.id
                    ORDER BY r.id, rm.menu_code
                    """
                )
                menu_rows = [dict(row) for row in cursor.fetchall()]
                cursor.execute(
                    """
                    SELECT r.role_code, rp.permission_code
                    FROM sys_role r JOIN sys_role_permission rp ON rp.role_id = r.id
                    ORDER BY r.id, rp.permission_code
                    """
                )
                permission_rows = [dict(row) for row in cursor.fetchall()]
        except Exception as error:
            if self._missing_rbac(error):
                raise AuthError("角色菜单权限表尚未创建，请先执行role-based-access-control.sql", 503, "RBAC_NOT_CONFIGURED") from error
            raise
        finally:
            connection.close()
        menus_by_role: dict[str, list[str]] = {}
        permissions_by_role: dict[str, list[str]] = {}
        for row in menu_rows:
            menus_by_role.setdefault(str(row["role_code"]), []).append(str(row["menu_code"]))
        for row in permission_rows:
            permissions_by_role.setdefault(str(row["role_code"]), []).append(str(row["permission_code"]))
        return [
            {
                "code": str(row["role_code"]),
                "name": str(row["role_name"]),
                "description": str(row.get("description") or ""),
                "isActive": bool(row["is_active"]),
                "userCount": int(row.get("user_count") or 0),
                "menuCodes": configurable_menu_codes(
                    menus_by_role.get(str(row["role_code"]), [])
                ),
                "permissions": permissions_by_role.get(str(row["role_code"]), []),
            }
            for row in roles
        ]

    def create_role(self, values: dict[str, Any]) -> None:
        connection = self.source.connect()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO sys_role (role_code, role_name, description, is_active) VALUES (%s,%s,%s,%s)",
                    (values["code"], values["name"], values.get("description") or None, int(values["is_active"])),
                )
                role_id = int(cursor.lastrowid)
                for menu_code in values["menu_codes"]:
                    cursor.execute(
                        "INSERT INTO sys_role_menu (role_id, menu_code, created_at) VALUES (%s,%s,%s)",
                        (role_id, menu_code, values["updated_at"]),
                    )
                for permission_code in values["permissions"]:
                    cursor.execute(
                        "INSERT INTO sys_role_permission (role_id, permission_code, created_at) VALUES (%s,%s,%s)",
                        (role_id, permission_code, values["updated_at"]),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def update_role(self, role_code: str, values: dict[str, Any]) -> None:
        connection = self.source.connect()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM sys_role WHERE role_code=%s FOR UPDATE", (role_code,))
                role_row = cursor.fetchone()
                if not role_row:
                    raise AuthError("角色不存在", 404, "ROLE_NOT_FOUND")
                role_id = int(role_row[0])
                cursor.execute(
                    "UPDATE sys_role SET role_name=%s, description=%s, is_active=%s, updated_at=%s WHERE role_code=%s",
                    (values["name"], values.get("description") or None, int(values["is_active"]), values["updated_at"], role_code),
                )
                cursor.execute("DELETE FROM sys_role_menu WHERE role_id=%s", (role_id,))
                cursor.execute("DELETE FROM sys_role_permission WHERE role_id=%s", (role_id,))
                for menu_code in values["menu_codes"]:
                    cursor.execute(
                        "INSERT INTO sys_role_menu (role_id, menu_code, created_at) VALUES (%s,%s,%s)",
                        (role_id, menu_code, values["updated_at"]),
                    )
                for permission_code in values["permissions"]:
                    cursor.execute(
                        "INSERT INTO sys_role_permission (role_id, permission_code, created_at) VALUES (%s,%s,%s)",
                        (role_id, permission_code, values["updated_at"]),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def set_user_roles(self, user_id: int, role_codes: list[str], actor_id: int) -> None:
        connection = self.source.connect()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM sys_user_role WHERE user_id=%s", (user_id,))
                for code in role_codes:
                    cursor.execute(
                        """
                        INSERT INTO sys_user_role (user_id, role_id, assigned_by, assigned_at)
                        SELECT %s, id, %s, %s FROM sys_role
                        WHERE role_code=%s AND is_active=1
                        """,
                        (user_id, actor_id, business_now_naive(), code),
                    )
                    if cursor.rowcount != 1:
                        raise AuthError(f"业务角色不存在或未启用：{code}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def set_user_permissions(
        self, user_id: int, overrides: dict[str, str], actor_id: int
    ) -> None:
        connection = self.source.connect()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM sys_user_permission WHERE user_id=%s", (user_id,))
                now = business_now_naive()
                for permission_code, effect in overrides.items():
                    cursor.execute(
                        """
                        INSERT INTO sys_user_permission (
                            user_id, permission_code, effect, assigned_by, created_at, updated_at
                        ) VALUES (%s,%s,%s,%s,%s,%s)
                        """,
                        (user_id, permission_code, effect, actor_id, now, now),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_menu_catalog(self) -> list[dict[str, Any]]:
        return [dict(row) for row in MENU_CATALOG]

    def set_user_menus(self, user_id: int, menu_codes: list[str]) -> None:
        connection = self.source.connect()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM sys_user_menu WHERE user_id=%s", (user_id,))
                now = business_now_naive()
                for code in menu_codes:
                    cursor.execute(
                        "INSERT INTO sys_user_menu (user_id, menu_code, created_at, updated_at) VALUES (%s,%s,%s,%s)",
                        (user_id, code, now, now),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

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
        return self._with_access(self._fetchone(
            """
            SELECT s.id AS session_id, s.user_id, s.token_hash, s.csrf_token_hash,
                   s.created_at AS session_created_at, s.last_seen_at,
                   s.absolute_expires_at, s.revoked_at,
                   u.id, u.username, u.email,
                   coalesce(nullif(u.full_name, ''), u.username) AS display_name,
                   u.hashed_password AS password_hash,
                   (u.role = 'admin') AS is_admin,
                   u.is_active AS is_enabled,
                   coalesce(sec.must_change_password, 0) AS must_change_password,
                   coalesce(sec.failed_attempts, 0) AS failed_attempts,
                   sec.locked_until, sec.password_changed_at,
                   u.created_at, u.updated_at
            FROM auth_session s
            JOIN sys_user u ON u.id = s.user_id
            LEFT JOIN auth_user_security sec ON sec.user_id = u.id
            WHERE s.token_hash = %s
            """,
            (hashed_token,),
        ))

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
        self.roles: dict[str, dict[str, Any]] = {
            row["code"]: {
                **dict(row), "isActive": True, "userCount": 0,
                "menuCodes": list(ROLE_MENUS.get(row["code"], ())),
                "permissions": list(ROLE_PERMISSIONS.get(row["code"], ())),
            }
            for row in BUSINESS_ROLE_CATALOG
        }

    def _refresh_user_access(self, user_id: int) -> None:
        row = self.users[user_id]
        active_roles = [
            self.roles[code] for code in row.get("role_codes", [])
            if code in self.roles and self.roles[code]["isActive"]
        ]
        row["business_roles"] = [
            {"code": role["code"], "name": role["name"], "description": role["description"]}
            for role in active_roles
        ]
        role_permissions = {
            permission for role in active_roles for permission in role["permissions"]
        }
        overrides = row.get("permission_overrides", {})
        allowed_permissions = {
            code for code, effect in overrides.items() if effect == "ALLOW"
        }
        denied_permissions = {
            code for code, effect in overrides.items() if effect == "DENY"
        }
        row["role_permissions"] = sorted(role_permissions)
        row["permissions"] = sorted(
            (role_permissions | allowed_permissions) - denied_permissions
        )
        permission_menus = {
            item["menuCode"] for item in PERMISSION_CATALOG
            if item["code"] in row["permissions"]
        }
        row["menu_codes"] = effective_menu_codes(
            {menu for role in active_roles for menu in role["menuCodes"]}
            | set(row.get("direct_menu_codes", []))
            | permission_menus
        )

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

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._lock:
            return deepcopy(next((row for row in self.users.values() if row.get("email") == email), None))

    def create_user(self, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._user_id += 1
            row = {
                "id": self._user_id, "failed_attempts": 0, "locked_until": None,
                "business_roles": [], "permissions": [], "menu_codes": [], "rbac_configured": True,
                "role_codes": list(values.get("role_codes") or []), "direct_menu_codes": [],
                "role_permissions": [], "permission_overrides": {},
                **deepcopy(values),
            }
            self.users[self._user_id] = row
            self._refresh_user_access(self._user_id)
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

    def list_business_roles(self) -> list[dict[str, Any]]:
        return [
            {"code": role["code"], "name": role["name"], "description": role["description"]}
            for role in self.roles.values() if role["isActive"]
        ]

    def list_roles(self) -> list[dict[str, Any]]:
        with self._lock:
            counts = {
                code: sum(code in row.get("role_codes", []) for row in self.users.values())
                for code in self.roles
            }
            return [
                {**deepcopy(role), "userCount": counts[code]}
                for code, role in self.roles.items()
            ]

    def create_role(self, values: dict[str, Any]) -> None:
        with self._lock:
            if values["code"] in self.roles:
                raise AuthError("角色编码已存在", 409, "ROLE_EXISTS")
            self.roles[values["code"]] = {
                "code": values["code"], "name": values["name"],
                "description": values.get("description") or "",
                "isActive": bool(values["is_active"]), "userCount": 0,
                "menuCodes": list(values["menu_codes"]),
                "permissions": list(values["permissions"]),
            }

    def update_role(self, role_code: str, values: dict[str, Any]) -> None:
        with self._lock:
            if role_code not in self.roles:
                raise AuthError("角色不存在", 404, "ROLE_NOT_FOUND")
            self.roles[role_code].update(
                name=values["name"], description=values.get("description") or "",
                isActive=bool(values["is_active"]),
                menuCodes=list(values["menu_codes"]),
                permissions=list(values["permissions"]),
            )
            for user_id in self.users:
                self._refresh_user_access(user_id)

    def set_user_roles(self, user_id: int, role_codes: list[str], actor_id: int) -> None:
        del actor_id
        with self._lock:
            self.users[user_id]["role_codes"] = list(role_codes)
            self._refresh_user_access(user_id)

    def set_user_permissions(
        self, user_id: int, overrides: dict[str, str], actor_id: int
    ) -> None:
        del actor_id
        with self._lock:
            self.users[user_id]["permission_overrides"] = deepcopy(overrides)
            self._refresh_user_access(user_id)

    def list_menu_catalog(self) -> list[dict[str, Any]]:
        return [dict(row) for row in MENU_CATALOG]

    def set_user_menus(self, user_id: int, menu_codes: list[str]) -> None:
        with self._lock:
            self.users[user_id]["direct_menu_codes"] = list(menu_codes)
            self._refresh_user_access(user_id)

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
                    email=None,
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
        if len(password.encode("utf-8")) > 72:
            raise AuthError("密码UTF-8长度不能超过72字节")

    @staticmethod
    def public_user(user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(user["id"]),
            "username": str(user["username"]),
            "email": str(user.get("email") or ""),
            "displayName": str(user["display_name"]),
            "isAdmin": bool(user["is_admin"]),
            "isEnabled": bool(user["is_enabled"]),
            "mustChangePassword": bool(user["must_change_password"]),
            "failedAttempts": int(user.get("failed_attempts") or 0),
            "lockedUntil": AuthManager.iso(user.get("locked_until")),
            "passwordChangedAt": AuthManager.iso(user.get("password_changed_at")),
            "createdAt": AuthManager.iso(user.get("created_at")),
            "businessRoles": list(user.get("business_roles") or []),
            "permissions": list(user.get("permissions") or []),
            "rolePermissions": list(user.get("role_permissions") or []),
            "permissionOverrides": dict(user.get("permission_overrides") or {}),
            "rbacConfigured": bool(user.get("rbac_configured", True)),
            "menuCodes": list(user.get("menu_codes") or []),
            "legacyMenuCodes": list(user.get("direct_menu_codes") or []),
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
            "detail": detail or {}, "created_at": business_now_naive(),
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
        if invalid or not password_matches(str(user.get("password_hash", "")), password):
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
        if not fresh or not password_matches(str(fresh["password_hash"]), current_password):
            self.audit("change_password", False, user=user, ip_address=ip_address, user_agent=user_agent, detail={"reason": "invalid_current_password"})
            raise AuthError("当前密码错误", 400, "INVALID_CURRENT_PASSWORD")
        self.validate_password(new_password)
        if password_matches(str(fresh["password_hash"]), new_password):
            raise AuthError("新密码不能与当前密码相同")
        now = self.now_fn()
        self.store.set_password(int(user["id"]), password_hash(new_password), False, now)
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
        is_admin: bool, must_change_password: bool, email: str | None,
        role_codes: list[str] | None = None, assigned_by: int | None = None,
    ) -> dict[str, Any]:
        username = self.normalize_username(username)
        name = display_name.strip()
        if not name or len(name) > 100:
            raise AuthError("姓名不能为空且不能超过100个字符")
        self.validate_password(password)
        normalized_email = (email or f"{username}@data-report.local").strip().lower()
        if len(normalized_email) > 100 or not EMAIL_RE.fullmatch(normalized_email):
            raise AuthError("邮箱格式不合法")
        if self.store.get_user_by_username(username):
            raise AuthError("用户名已存在", 409, "USERNAME_EXISTS")
        if self.store.get_user_by_email(normalized_email):
            raise AuthError("邮箱已存在", 409, "EMAIL_EXISTS")
        now = business_now_naive()
        return self.store.create_user({
            "username": username, "email": normalized_email, "display_name": name,
            "password_hash": password_hash(password),
            "is_admin": is_admin, "is_enabled": True,
            "must_change_password": must_change_password,
            "password_changed_at": None, "created_at": now, "updated_at": now,
            "role_codes": role_codes or [], "assigned_by": assigned_by,
        })

    def create_user(
        self, actor: dict[str, Any], *, username: str, display_name: str,
        password: str, is_admin: bool, email: str | None,
        role_codes: Any,
        ip_address: str, user_agent: str,
    ) -> dict[str, Any]:
        self.require_admin(actor)
        normalized_roles = self._validate_assignable_roles(role_codes)
        user = self._create_user(
            username=username, display_name=display_name, password=password,
            is_admin=is_admin, must_change_password=True, email=email,
            role_codes=normalized_roles, assigned_by=int(actor["id"]),
        )
        self.audit("create_user", True, user=actor, ip_address=ip_address, user_agent=user_agent, detail={"targetUserId": user["id"], "targetUsername": user["username"], "isAdmin": is_admin, "roleCodes": normalized_roles})
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
        if "email" in values:
            email = str(values["email"]).strip().lower()
            if len(email) > 100 or not EMAIL_RE.fullmatch(email):
                raise AuthError("邮箱格式不合法")
            email_owner = self.store.get_user_by_email(email)
            if email_owner and int(email_owner["id"]) != target_id:
                raise AuthError("邮箱已存在", 409, "EMAIL_EXISTS")
            cleaned["email"] = email
        for key in ("is_admin", "is_enabled"):
            if key in values:
                if not isinstance(values[key], bool):
                    raise AuthError("账号状态参数不合法")
                cleaned[key] = values[key]
        self.store.update_user(target_id, cleaned, business_now_naive())
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
        self.store.set_password(target_id, password_hash(new_password), True, now)
        self.store.revoke_user_sessions(target_id, now)
        self.audit("reset_password", True, user=actor, ip_address=ip_address, user_agent=user_agent, detail={"targetUserId": target_id, "targetUsername": target["username"]})

    def users(self, actor: dict[str, Any]) -> list[dict[str, Any]]:
        self.require_admin(actor)
        return [self.public_user(row) for row in self.store.list_users()]

    def business_roles(self, actor: dict[str, Any]) -> list[dict[str, Any]]:
        self.require_admin(actor)
        return self.store.list_business_roles()

    def roles(self, actor: dict[str, Any]) -> list[dict[str, Any]]:
        self.require_admin(actor)
        return [
            {**row, "dataScope": "ALL"}
            for row in self.store.list_roles()
        ]

    def permission_catalog(self, actor: dict[str, Any]) -> list[dict[str, Any]]:
        self.require_admin(actor)
        return [dict(row) for row in PERMISSION_CATALOG]

    @staticmethod
    def _normalize_role_codes(role_codes: Any) -> list[str]:
        if not isinstance(role_codes, list):
            raise AuthError("角色必须为数组")
        return list(dict.fromkeys(
            str(code).strip().upper() for code in role_codes if str(code).strip()
        ))

    def _validate_assignable_roles(self, role_codes: Any) -> list[str]:
        normalized = self._normalize_role_codes(role_codes)
        supported = {row["code"] for row in self.store.list_business_roles()}
        invalid = [code for code in normalized if code not in supported]
        if invalid:
            raise AuthError(f"角色不存在或未启用：{','.join(invalid)}")
        return normalized

    @staticmethod
    def _role_values(values: dict[str, Any], *, require_code: bool) -> dict[str, Any]:
        code = str(values.get("roleCode", "")).strip().upper()
        if require_code and not ROLE_CODE_RE.fullmatch(code):
            raise AuthError("角色编码须为3至64位大写字母、数字或下划线，且以字母开头")
        name = str(values.get("name", "")).strip()
        description = str(values.get("description", "")).strip()
        if not name or len(name) > 100:
            raise AuthError("角色名称不能为空且不能超过100个字符")
        if len(description) > 500:
            raise AuthError("角色说明不能超过500个字符")
        menu_codes = values.get("menuCodes")
        permissions = values.get("permissions")
        if not isinstance(menu_codes, list) or not isinstance(permissions, list):
            raise AuthError("菜单权限和功能权限必须为数组")
        raw_menus = list(dict.fromkeys(str(item).strip() for item in menu_codes if str(item).strip()))
        normalized_menus = configurable_menu_codes(raw_menus)
        normalized_permissions = list(dict.fromkeys(str(item).strip() for item in permissions if str(item).strip()))
        supported_menus = MENU_CODES | set(LEGACY_MENU_EXPANSIONS)
        supported_permissions = {row["code"] for row in PERMISSION_CATALOG}
        invalid_menus = [item for item in raw_menus if item not in supported_menus]
        invalid_permissions = [item for item in normalized_permissions if item not in supported_permissions]
        if invalid_menus:
            raise AuthError(f"不支持的菜单权限：{','.join(invalid_menus)}")
        if invalid_permissions:
            raise AuthError(f"不支持的功能权限：{','.join(invalid_permissions)}")
        required_menus = {
            row["menuCode"] for row in PERMISSION_CATALOG
            if row["code"] in normalized_permissions
        }
        missing_menus = sorted(required_menus - set(normalized_menus))
        if missing_menus:
            raise AuthError(f"所选功能权限必须同时授权菜单：{','.join(missing_menus)}")
        is_active = values.get("isActive", True)
        if not isinstance(is_active, bool):
            raise AuthError("角色启用状态不合法")
        return {
            "code": code, "name": name, "description": description,
            "menu_codes": normalized_menus,
            "permissions": normalized_permissions,
            "is_active": is_active,
            "updated_at": business_now_naive(),
        }

    def create_role(
        self, actor: dict[str, Any], values: dict[str, Any],
        ip_address: str, user_agent: str,
    ) -> dict[str, Any]:
        self.require_admin(actor)
        cleaned = self._role_values(values, require_code=True)
        if any(row["code"] == cleaned["code"] for row in self.store.list_roles()):
            raise AuthError("角色编码已存在", 409, "ROLE_EXISTS")
        self.store.create_role(cleaned)
        self.audit(
            "create_role", True, user=actor, ip_address=ip_address,
            user_agent=user_agent, detail={
                "roleCode": cleaned["code"],
                "menuCodes": cleaned["menu_codes"],
                "permissions": cleaned["permissions"],
                "isActive": cleaned["is_active"],
            },
        )
        return next(row for row in self.roles(actor) if row["code"] == cleaned["code"])

    def update_role(
        self, actor: dict[str, Any], role_code: str, values: dict[str, Any],
        ip_address: str, user_agent: str,
    ) -> dict[str, Any]:
        self.require_admin(actor)
        normalized_code = role_code.strip().upper()
        cleaned = self._role_values(values, require_code=False)
        existing = next(
            (row for row in self.store.list_roles() if row["code"] == normalized_code),
            None,
        )
        if not existing:
            raise AuthError("角色不存在", 404, "ROLE_NOT_FOUND")
        self.store.update_role(normalized_code, cleaned)
        self.audit(
            "update_role", True, user=actor, ip_address=ip_address,
            user_agent=user_agent,
            detail={
                "roleCode": normalized_code,
                "affectedUserCount": int(existing.get("userCount") or 0),
                "before": {
                    "name": existing["name"],
                    "menuCodes": existing.get("menuCodes") or [],
                    "permissions": existing.get("permissions") or [],
                    "isActive": bool(existing.get("isActive")),
                },
                "after": {
                    "name": cleaned["name"],
                    "menuCodes": cleaned["menu_codes"],
                    "permissions": cleaned["permissions"],
                    "isActive": cleaned["is_active"],
                },
            },
        )
        return next(row for row in self.roles(actor) if row["code"] == normalized_code)

    def update_business_roles(
        self, actor: dict[str, Any], target_id: int, role_codes: list[Any],
        ip_address: str, user_agent: str,
    ) -> dict[str, Any]:
        self.require_admin(actor)
        target = self.store.get_user_by_id(target_id)
        if not target:
            raise AuthError("账号不存在", 404, "USER_NOT_FOUND")
        normalized = self._validate_assignable_roles(role_codes)
        self.store.set_user_roles(target_id, normalized, int(actor["id"]))
        updated = self.store.get_user_by_id(target_id) or target
        self.audit(
            "update_business_roles", True, user=actor, ip_address=ip_address,
            user_agent=user_agent,
            detail={"targetUserId": target_id, "roleCodes": normalized},
        )
        return self.public_user(updated)

    def update_user_permissions(
        self, actor: dict[str, Any], target_id: int, overrides: Any,
        ip_address: str, user_agent: str,
    ) -> dict[str, Any]:
        self.require_admin(actor)
        target = self.store.get_user_by_id(target_id)
        if not target:
            raise AuthError("账号不存在", 404, "USER_NOT_FOUND")
        if not isinstance(overrides, dict):
            raise AuthError("个人权限配置必须为对象")
        supported = {row["code"] for row in PERMISSION_CATALOG}
        normalized: dict[str, str] = {}
        for raw_code, raw_effect in overrides.items():
            code = str(raw_code).strip()
            effect = str(raw_effect).strip().upper()
            if code not in supported:
                raise AuthError(f"不支持的功能权限：{code}")
            if effect == "INHERIT" or not effect:
                continue
            if effect not in {"ALLOW", "DENY"}:
                raise AuthError(f"个人权限状态不支持：{effect}")
            normalized[code] = effect
        self.store.set_user_permissions(target_id, normalized, int(actor["id"]))
        updated = self.store.get_user_by_id(target_id) or target
        self.audit(
            "update_user_permissions", True, user=actor,
            ip_address=ip_address, user_agent=user_agent,
            detail={"targetUserId": target_id, "permissionOverrides": normalized},
        )
        return self.public_user(updated)

    def menu_catalog(self, actor: dict[str, Any]) -> list[dict[str, Any]]:
        self.require_admin(actor)
        return self.store.list_menu_catalog()

    def update_user_menus(
        self, actor: dict[str, Any], target_id: int, menu_codes: list[Any],
        ip_address: str, user_agent: str,
    ) -> dict[str, Any]:
        self.require_admin(actor)
        target = self.store.get_user_by_id(target_id)
        if not target:
            raise AuthError("账号不存在", 404, "USER_NOT_FOUND")
        if not isinstance(menu_codes, list):
            raise AuthError("菜单权限必须为数组")
        raw_codes = list(dict.fromkeys(str(code).strip() for code in menu_codes if str(code).strip()))
        supported = MENU_CODES | set(LEGACY_MENU_EXPANSIONS)
        invalid = [code for code in raw_codes if code not in supported]
        if invalid:
            raise AuthError(f"不支持的菜单编码：{','.join(invalid)}")
        normalized = configurable_menu_codes(raw_codes)
        self.store.set_user_menus(target_id, normalized)
        updated = self.store.get_user_by_id(target_id) or target
        self.audit(
            "update_user_menus", True, user=actor, ip_address=ip_address,
            user_agent=user_agent,
            detail={"targetUserId": target_id, "menuCodes": normalized},
        )
        return self.public_user(updated)

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
