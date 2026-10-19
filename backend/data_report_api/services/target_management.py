"""业务目标配置与进度查询服务。

目标值只写入 biz_target_plan / biz_target_item；完成量只读取
ads_target_progress_day，该表无 ETL 快照时返回 null，不伪造 0 完成量。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .data_source import DataSource
from ..time_utils import business_now


LOGGER = logging.getLogger(__name__)
SCENES = frozenset({"PLATFORM", "GDS", "POLICY"})
EDIT_STATUSES = frozenset({"DRAFT", "ACTIVE", "PAUSED"})
VIEW_PERMISSION = "business_config.targets.view"
MANAGE_PERMISSION = "business_config.targets.manage"
PROGRESS_PERMISSION = "business_config.target_progress.view"


class TargetManagementUnavailable(RuntimeError):
    pass


def _permissions(user: dict[str, Any]) -> set[str]:
    return {str(value) for value in (user.get("permissions") or user.get("permission_codes") or [])}


def _require(user: dict[str, Any], permission: str, message: str) -> None:
    if bool(user.get("is_admin")) or permission in _permissions(user):
        return
    raise PermissionError(message)


def _require_any(user: dict[str, Any], permissions: set[str], message: str) -> None:
    if bool(user.get("is_admin")) or permissions.intersection(_permissions(user)):
        return
    raise PermissionError(message)


def _month(value: Any) -> tuple[str, date, date]:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", text):
        raise ValueError("目标月份必须为 YYYY-MM")
    year, month = (int(part) for part in text.split("-"))
    return text, date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _scene(value: Any) -> str:
    scene = str(value or "").strip().upper()
    if scene not in SCENES:
        raise ValueError("目标场景只支持 PLATFORM、GDS 或 POLICY")
    return scene


def _text(value: Any, label: str, *, required: bool = False, maximum: int = 150) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"请填写{label}")
    if len(text) > maximum:
        raise ValueError(f"{label}不能超过{maximum}个字符")
    return text


def _number(value: Any, label: str = "目标值") -> Decimal:
    try:
        number = Decimal(str(value))
    except Exception as error:
        raise ValueError(f"{label}必须为数字") from error
    if number < 0:
        raise ValueError(f"{label}不能小于0")
    return number.quantize(Decimal("0.0001"))


def _stable_code(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.strip().lower().encode("utf-8")).hexdigest()[:16].upper()
    return f"{prefix}_{digest}"


def _decimal(value: Any) -> float | None:
    return None if value is None else float(value)


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, (date, datetime)) else (str(value) if value else None)


def _row_status(plan_status: str, enabled: Any) -> str:
    if not bool(enabled):
        return "PAUSED"
    return "ACTIVE" if plan_status in {"ACTIVE", "PUBLISHED"} else plan_status


def _boolean_query(value: Any, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("includeUnconfigured 必须为 true 或 false")


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _change_action(before: dict[str, Any] | None, status: str) -> str:
    if not before:
        return "CREATE"
    previously_enabled = [bool(item.get("enabled")) for item in before.get("items", [])]
    if status == "PAUSED" and any(previously_enabled):
        return "PAUSE"
    if status != "PAUSED" and previously_enabled and not any(previously_enabled):
        return "RESUME"
    return "UPDATE"


class TargetManagementService:
    def __init__(self, config: dict[str, Any], source: DataSource | None = None):
        mysql_config = dict(config)
        mysql_config["DATA_MODE"] = "mysql"
        self.source = source or DataSource(mysql_config)
        self.database = self.source.database
        self.roster_database = str(config.get("ERP_ROSTER_DATABASE", "sibedb")).strip()
        self.roster_user_table = str(config.get("ERP_ROSTER_USER_TABLE", "system_user")).strip()
        self.roster_user_department_table = str(
            config.get("ERP_ROSTER_USER_DEPARTMENT_TABLE", "system_user_department")
        ).strip()
        self.roster_org_table = str(config.get("ERP_ROSTER_ORG_TABLE", "base_organization")).strip()
        self.platform_database = str(config.get("ERP_PLATFORM_DATABASE", "sibelog")).strip()
        self.platform_table = str(config.get("ERP_PLATFORM_TABLE", "sibe_ota")).strip()
        roster_mysql_config = dict(mysql_config)
        roster_mysql_config.update({
            "MYSQL_HOST": config.get("ERP_ROSTER_MYSQL_HOST") or config.get("MYSQL_HOST"),
            "MYSQL_PORT": config.get("ERP_ROSTER_MYSQL_PORT") or config.get("MYSQL_PORT", 3306),
            "MYSQL_DATABASE": self.roster_database,
            "MYSQL_USER": config.get("ERP_ROSTER_MYSQL_USER") or config.get("MYSQL_USER"),
            "MYSQL_PASSWORD": config.get("ERP_ROSTER_MYSQL_PASSWORD") or config.get("MYSQL_PASSWORD"),
            "MYSQL_CHARSET": config.get("ERP_ROSTER_MYSQL_CHARSET") or config.get("MYSQL_CHARSET", "utf8mb4"),
        })
        self.roster_source = DataSource(roster_mysql_config)
        for value in (
            self.roster_database, self.roster_user_table,
            self.roster_user_department_table, self.roster_org_table,
            self.platform_database, self.platform_table,
        ):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
                raise RuntimeError("目标管理ERP基础表配置不合法")

    def _table(self, name: str) -> str:
        return f"{self.database}.{name}"

    @staticmethod
    def _qualified(database: str, table: str) -> str:
        return f"{database}.{table}"

    @property
    def _roster_users(self) -> str:
        return self._qualified(self.roster_database, self.roster_user_table)

    @property
    def _roster_orgs(self) -> str:
        return self._qualified(self.roster_database, self.roster_org_table)

    @property
    def _roster_user_departments(self) -> str:
        return self._qualified(self.roster_database, self.roster_user_department_table)

    @property
    def _platforms(self) -> str:
        return self._qualified(self.platform_database, self.platform_table)

    def _roster_options(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        import pymysql

        connection = None
        try:
            connection = self.roster_source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    f"""SELECT ru.id, '' AS username,
                               ru.cname AS name, coalesce(ru.wechat_id, '') AS wechat_id,
                               coalesce(ro.org_code, '') AS department_code,
                               coalesce(ro.org_cname, '') AS department_name
                        FROM {self._roster_users} ru
                        LEFT JOIN (
                            SELECT user_id, max(id) AS latest_id
                            FROM {self._roster_user_departments}
                            GROUP BY user_id
                        ) latest ON latest.user_id=ru.id
                        LEFT JOIN {self._roster_user_departments} rud ON rud.id=latest.latest_id
                        LEFT JOIN {self._roster_orgs} ro ON ro.id=rud.department_id
                        WHERE ru.enabled=0 AND coalesce(ru.cname, '')<>''
                        ORDER BY ro.org_cname, ru.cname, ru.id"""
                )
                employees = [{
                    "id": int(row["id"]), "username": str(row["username"] or ""),
                    "name": str(row["name"]), "wechatId": str(row["wechat_id"] or ""),
                    "hasNotificationIdentity": bool(row["wechat_id"]),
                    "departmentCode": str(row["department_code"] or ""),
                    "departmentName": str(row["department_name"] or ""),
                    "source": f"{self.roster_database}.{self.roster_user_table}",
                } for row in cursor.fetchall()]
                cursor.execute(
                    f"""SELECT org_code AS code, org_cname AS name
                        FROM {self._roster_orgs}
                        WHERE coalesce(org_code, '')<>'' AND coalesce(org_cname, '')<>''
                        ORDER BY org_cname, org_code"""
                )
                departments = [
                    {"code": str(row["code"]), "name": str(row["name"])}
                    for row in cursor.fetchall()
                ]
            return employees, departments
        finally:
            if connection is not None:
                connection.close()

    def _roster_owner(self, owner_user_id: int) -> dict[str, Any] | None:
        import pymysql

        connection = None
        try:
            connection = self.roster_source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    f"""SELECT ru.id, ru.cname AS owner_name,
                               coalesce(ro.org_code, '') AS department_code,
                               coalesce(ro.org_cname, '') AS department_name
                        FROM {self._roster_users} ru
                        LEFT JOIN (
                            SELECT user_id, max(id) AS latest_id
                            FROM {self._roster_user_departments}
                            GROUP BY user_id
                        ) latest ON latest.user_id=ru.id
                        LEFT JOIN {self._roster_user_departments} rud ON rud.id=latest.latest_id
                        LEFT JOIN {self._roster_orgs} ro ON ro.id=rud.department_id
                        WHERE ru.id=%s AND ru.enabled=0 LIMIT 1""",
                    (owner_user_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        finally:
            if connection is not None:
                connection.close()

    def _roster_people(self, user_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not user_ids:
            return {}
        import pymysql

        connection = None
        try:
            connection = self.roster_source.connect()
            placeholders = ",".join(["%s"] * len(user_ids))
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    f"""SELECT id, cname AS name
                        FROM {self._roster_users}
                        WHERE enabled=0 AND coalesce(cname, '')<>''
                          AND id IN ({placeholders})""",
                    tuple(user_ids),
                )
                return {int(row["id"]): dict(row) for row in cursor.fetchall()}
        finally:
            if connection is not None:
                connection.close()

    def _roster_department(self, code: str) -> dict[str, Any] | None:
        import pymysql

        connection = None
        try:
            connection = self.roster_source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    f"""SELECT org_code AS code, org_cname AS name
                        FROM {self._roster_orgs}
                        WHERE org_code=%s AND coalesce(org_cname, '')<>'' LIMIT 1""",
                    (code,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        finally:
            if connection is not None:
                connection.close()

    def _configuration_snapshot(
        self,
        cursor: Any,
        plan_id: int,
        *,
        item_ids: list[int] | None = None,
        policy_group_code: str = "",
    ) -> dict[str, Any] | None:
        normalized_ids = list(dict.fromkeys(int(value) for value in (item_ids or []) if value))
        conditions = ["plan_id=%s"]
        params: list[Any] = [plan_id]
        selectors: list[str] = []
        if normalized_ids:
            selectors.append(f"id IN ({','.join(['%s'] * len(normalized_ids))})")
            params.extend(normalized_ids)
        if policy_group_code:
            selectors.append("policy_group_code=%s")
            params.append(policy_group_code)
        if not selectors:
            return None
        conditions.append(f"({' OR '.join(selectors)})")
        cursor.execute(
            f"""SELECT id,item_code,scope_key,metric_code,metric_version,
                       department_code,department_name_snapshot,
                       platform_code,platform_name_snapshot,gds_code,
                       policy_group_code,policy_group_name_snapshot,
                       policy_leader_user_id,policy_leader_name_snapshot,
                       owner_user_id,owner_name_snapshot,target_value,unit_code,
                       allocation_source,enabled,sort_order,remark,
                       created_by,created_at,updated_by,updated_at
                FROM {self._table('biz_target_item')}
                WHERE {' AND '.join(conditions)}
                ORDER BY gds_code,id""",
            tuple(params),
        )
        items = [dict(row) for row in cursor.fetchall()]
        if not items:
            return None
        member_group_code = policy_group_code or str(items[0].get("policy_group_code") or "")
        members: list[dict[str, Any]] = []
        if member_group_code:
            cursor.execute(
                f"""SELECT member_user_id,member_name_snapshot,sort_order
                    FROM {self._table('biz_target_policy_member')}
                    WHERE plan_id=%s AND policy_group_code=%s
                    ORDER BY sort_order,id""",
                (plan_id, member_group_code),
            )
            members = [dict(row) for row in cursor.fetchall()]
        return _json_ready({"items": items, "policyMembers": members})

    def _write_change_log(
        self,
        cursor: Any,
        *,
        plan_id: int,
        scene: str,
        status: str,
        item_ids: list[int],
        before: dict[str, Any] | None,
        after: dict[str, Any],
        change_reason: str,
        user: dict[str, Any],
    ) -> None:
        actor_id = int(user.get("id") or 0) or None
        actor_name = str(
            user.get("display_name") or user.get("displayName")
            or user.get("username") or user.get("user_name") or ""
        ).strip()[:100]
        cursor.execute(
            f"""INSERT INTO {self._table('biz_target_change_log')}
                (operation_id,plan_id,target_scene,action_type,target_item_ids,
                 before_json,after_json,change_reason,
                 changed_by_user_id,changed_by_name_snapshot)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                uuid.uuid4().hex, plan_id, scene, _change_action(before, status),
                json.dumps(item_ids, ensure_ascii=False),
                json.dumps(before, ensure_ascii=False) if before else None,
                json.dumps(after, ensure_ascii=False), change_reason,
                actor_id, actor_name,
            ),
        )

    def metrics(self, user: dict[str, Any]) -> dict[str, Any]:
        _require(user, VIEW_PERMISSION, "当前账号没有目标管理查看权限")
        import pymysql

        connection = None
        try:
            connection = self.source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    f"""SELECT metric_code, metric_name, metric_version, unit_code, date_basis,
                               source_system, measure_code, supported_scenes, definition,
                               filter_description, effective_start, effective_end
                        FROM {self._table('target_metric_definition')}
                        WHERE status='ACTIVE'
                          AND (effective_start IS NULL OR effective_start <= CURRENT_DATE)
                          AND (effective_end IS NULL OR effective_end >= CURRENT_DATE)
                        ORDER BY id"""
                )
                rows = cursor.fetchall()
            return {"available": True, "rows": [
                {
                    "code": row["metric_code"], "name": row["metric_name"],
                    "version": row["metric_version"], "unitCode": row["unit_code"],
                    "dateBasis": row["date_basis"], "sourceSystem": row["source_system"],
                    "measureCode": row["measure_code"],
                    "supportedScenes": [item for item in str(row["supported_scenes"] or "").split(",") if item],
                    "definition": row["definition"], "filterDescription": row["filter_description"],
                    "effectiveStart": _iso(row["effective_start"]), "effectiveEnd": _iso(row["effective_end"]),
                } for row in rows
            ]}
        except PermissionError:
            raise
        except Exception as error:
            LOGGER.exception("Target metric query failed")
            raise TargetManagementUnavailable("目标指标表不可用，请确认DDL已执行") from error
        finally:
            if connection is not None:
                connection.close()

    def options(self, user: dict[str, Any]) -> dict[str, Any]:
        _require(user, VIEW_PERMISSION, "当前账号没有目标管理查看权限")
        import pymysql

        connection = None
        try:
            connection = self.source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    f"""SELECT ota_code AS code, ota_cname AS name, ota_full_cname AS full_name
                        FROM {self._platforms}
                        WHERE status=1
                          AND (start_time IS NULL OR start_time<=NOW())
                          AND (end_time IS NULL OR end_time>=NOW())
                        ORDER BY sort_seq, ota_cname, ota_code"""
                )
                platforms = [{
                    "code": str(row["code"]), "name": str(row["name"] or row["code"]),
                    "fullName": str(row["full_name"] or row["name"] or row["code"]),
                    "source": f"{self.platform_database}.{self.platform_table}",
                } for row in cursor.fetchall()]
                cursor.execute(
                    f"""SELECT gds_code AS code
                        FROM {self._table('bi_gds_resource_metric_day')}
                        WHERE coalesce(gds_code, '') <> '' GROUP BY gds_code ORDER BY gds_code"""
                )
                gds = [{"code": str(row["code"]), "name": str(row["code"])} for row in cursor.fetchall()]
                cursor.execute(
                    f"""SELECT department_code AS code, max(department_name_snapshot) AS name
                        FROM (
                            SELECT department_code, department_name_snapshot FROM {self._table('biz_target_item')}
                            UNION ALL
                            SELECT department_code, department_name_snapshot FROM {self._table('biz_target_scope_assignment')}
                        ) d WHERE coalesce(department_code, '') <> ''
                        GROUP BY department_code ORDER BY name, code"""
                )
                configured_departments = [{"code": row["code"], "name": row["name"] or row["code"]} for row in cursor.fetchall()]
                cursor.execute(
                    f"""SELECT policy_group_code AS code, max(policy_group_name_snapshot) AS name
                        FROM {self._table('biz_target_item')}
                        WHERE coalesce(policy_group_code, '') <> ''
                        GROUP BY policy_group_code ORDER BY name, code"""
                )
                policies = [{"code": row["code"], "name": row["name"] or row["code"]} for row in cursor.fetchall()]
            roster_available = True
            roster_message = ""
            employees: list[dict[str, Any]] = []
            roster_departments: list[dict[str, Any]] = []
            try:
                employees, roster_departments = self._roster_options()
            except Exception as roster_error:
                roster_available = False
                roster_message = (
                    "ERP花名册暂不可读，请检查sibedb独立连接及system_user、"
                    "system_user_department、base_organization只读权限"
                )
                LOGGER.warning("ERP roster unavailable for target options: %s", roster_error)
            departments_by_code = {str(item["code"]): item for item in configured_departments}
            departments_by_code.update({str(item["code"]): item for item in roster_departments})
            departments = sorted(departments_by_code.values(), key=lambda item: (str(item["name"]), str(item["code"])))
            return {
                "available": True, "platforms": platforms, "gds": gds,
                "users": employees, "employees": employees, "departments": departments,
                "policyGroups": policies, "rosterAvailable": roster_available,
                "rosterMessage": roster_message,
                "sources": {
                    "platform": f"{self.platform_database}.{self.platform_table}",
                    "employee": f"{self.roster_database}.{self.roster_user_table}",
                    "department": f"{self.roster_database}.{self.roster_org_table}",
                },
            }
        except PermissionError:
            raise
        except Exception as error:
            LOGGER.exception("Target options query failed")
            raise TargetManagementUnavailable("目标管理基础选项查询失败") from error
        finally:
            if connection is not None:
                connection.close()

    def list_targets(self, user: dict[str, Any], *, scene_value: Any, period_value: Any,
                     status_value: Any = "ALL", keyword_value: Any = "") -> dict[str, Any]:
        _require(user, VIEW_PERMISSION, "当前账号没有目标管理查看权限")
        scene = _scene(scene_value)
        period, start, end = _month(period_value)
        status = str(status_value or "ALL").strip().upper()
        if status not in EDIT_STATUSES | {"ALL", "CLOSED", "VOID"}:
            raise ValueError("目标状态不合法")
        keyword = str(keyword_value or "").strip()
        import pymysql

        connection = None
        try:
            connection = self.source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                filters = ["p.target_scene=%s", "p.period_start=%s", "p.period_end=%s"]
                params: list[Any] = [scene, start, end]
                if status == "PAUSED":
                    filters.append("i.enabled=0")
                elif status != "ALL":
                    filters.append("p.status=%s")
                    params.append(status)
                    filters.append("i.enabled=1")
                if keyword:
                    like = f"%{keyword}%"
                    filters.append("concat_ws(' ',i.department_name_snapshot,i.platform_name_snapshot,i.gds_code,i.policy_group_name_snapshot,i.owner_name_snapshot,m.metric_name) LIKE %s")
                    params.append(like)
                cursor.execute(
                    f"""SELECT i.*, p.target_scene, p.status AS plan_status, p.period_start, p.period_end,
                               m.metric_name, m.unit_code AS metric_unit_code,
                               pr.stat_date, pr.actual_today, pr.actual_cumulative,
                               pr.planned_cumulative_rate, pr.completion_rate, pr.progress_gap_rate,
                               pr.remaining_value, pr.required_daily_value, pr.profit_cumulative,
                               pr.profit_per_segment, pr.data_status, pr.data_through_date
                        FROM {self._table('biz_target_plan')} p
                        JOIN {self._table('biz_target_item')} i ON i.plan_id=p.id
                        LEFT JOIN {self._table('target_metric_definition')} m
                          ON m.metric_code=i.metric_code AND m.metric_version=i.metric_version
                        LEFT JOIN {self._table('ads_target_progress_day')} pr
                          ON pr.id=(SELECT pr2.id FROM {self._table('ads_target_progress_day')} pr2
                                    WHERE pr2.target_item_id=i.id AND pr2.stat_date<=CURRENT_DATE
                                    ORDER BY pr2.stat_date DESC LIMIT 1)
                        WHERE {' AND '.join(filters)}
                        ORDER BY i.sort_order, i.department_name_snapshot, i.platform_name_snapshot,
                                 i.gds_code, i.policy_group_name_snapshot, i.id""",
                    tuple(params),
                )
                raw_rows = [dict(row) for row in cursor.fetchall()]
                if scene == "POLICY":
                    self._attach_policy_members(cursor, raw_rows)
            rows = self._public_rows(scene, period, raw_rows)
            target_total = sum(float(row["target"]) for row in rows)
            progress_rows = [row for row in rows if row["actual"] is not None]
            actual_total = sum(float(row["actual"]) for row in progress_rows) if progress_rows else None
            behind = sum(1 for row in progress_rows if row["completionRate"] is not None
                         and row["expectedRate"] is not None and row["completionRate"] < row["expectedRate"])
            through_dates = [row["dataThroughDate"] for row in rows if row["dataThroughDate"]]
            return {
                "available": True, "scene": scene, "period": period, "rows": rows,
                "summary": {
                    "target": target_total,
                    "actual": actual_total,
                    "completionRate": (actual_total / target_total) if actual_total is not None and target_total else None,
                    "behind": behind,
                    "configuredCount": len(rows), "progressReadyCount": len(progress_rows),
                },
                "dataThroughDate": max(through_dates) if through_dates else None,
            }
        except (PermissionError, ValueError):
            raise
        except Exception as error:
            LOGGER.exception("Target list query failed")
            raise TargetManagementUnavailable("目标配置查询失败，请确认DDL已执行") from error
        finally:
            if connection is not None:
                connection.close()

    def progress_dashboard(self, user: dict[str, Any], *, scene_value: Any, period_value: Any,
                           keyword_value: Any = "", include_unconfigured_value: Any = None) -> dict[str, Any]:
        """Return a read-only monthly dashboard without inventing missing ETL values.

        PLATFORM deliberately starts from the ERP platform master for completeness checks, but
        hides unconfigured OTAs by default. GDS and POLICY currently start from configured,
        active targets because neither scene has a complete master roster yet.
        """
        _require_any(
            user,
            {VIEW_PERMISSION, PROGRESS_PERMISSION},
            "当前账号没有目标进度查看权限",
        )
        scene = _scene(scene_value)
        period, start, end = _month(period_value)
        keyword = str(keyword_value or "").strip().lower()
        include_unconfigured = _boolean_query(include_unconfigured_value)
        import pymysql

        connection = None
        try:
            connection = self.source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                configured = self._dashboard_target_rows(cursor, scene, start, end)
                public_targets = self._public_rows(scene, period, configured)
                metric_rows = self._dashboard_metric_rows(cursor, scene, start, end)
                roster = self._dashboard_roster()

                if scene == "PLATFORM":
                    cursor.execute(
                        f"""SELECT ota_code AS code, ota_cname AS name, ota_full_cname AS full_name
                            FROM {self._platforms}
                            WHERE status=1
                              AND (start_time IS NULL OR start_time<=NOW())
                              AND (end_time IS NULL OR end_time>=NOW())
                            ORDER BY sort_seq, ota_cname, ota_code"""
                    )
                    masters = [dict(row) for row in cursor.fetchall()]
                    rows = self._platform_progress_rows(period, start, end, masters, public_targets, metric_rows, roster)
                    total_scope_count = len(masters)
                else:
                    rows = self._configured_progress_rows(scene, period, start, end, public_targets, metric_rows, roster)
                    total_scope_count = len(rows)

            configured_scope_count = sum(1 for row in rows if row["configured"])
            if scene == "PLATFORM" and not include_unconfigured:
                rows = [row for row in rows if row["configured"]]
            if keyword:
                rows = [row for row in rows if keyword in " ".join(str(row.get(key) or "").lower() for key in (
                    "platformCode", "platform", "gds", "policyCode", "policy", "policyLeaderName",
                    "policyMemberNames", "department", "owner",
                ))]
            progress_rows = [row for row in rows if row["actual"] is not None]
            configured_rows = [row for row in rows if row["configured"]]
            target_total = sum(float(row["target"] or 0) for row in configured_rows)
            actual_total = sum(float(row["actual"] or 0) for row in progress_rows) if progress_rows else None
            profits = [float(row["profit"]) for row in rows if row["profit"] is not None]
            losses = [float(row["lossAmount"]) for row in rows if row["lossAmount"] is not None]
            through_dates = [row["dataThroughDate"] for row in rows if row["dataThroughDate"]]
            etl_updated_times = [row["etl_updated_at"] for row in metric_rows if row.get("etl_updated_at")]
            return {
                "available": True,
                "scene": scene,
                "period": period,
                "rows": rows,
                "summary": {
                    "scopeCount": total_scope_count,
                    "visibleCount": len(rows),
                    "configuredCount": configured_scope_count,
                    "progressReadyCount": len(progress_rows),
                    "target": target_total,
                    "actual": actual_total,
                    "completionRate": actual_total / target_total if actual_total is not None and target_total else None,
                    "profit": sum(profits) if profits else None,
                    "lossAmount": sum(losses) if losses else None,
                },
                "dataThroughDate": max(through_dates) if through_dates else None,
                "dataUpdatedAt": _iso(max(etl_updated_times)) if etl_updated_times else None,
                "includeUnconfigured": include_unconfigured if scene == "PLATFORM" else False,
                "metricAvailability": {
                    "hasEtlData": bool(metric_rows or progress_rows),
                    "lossMetricsReady": any(row["lossAmount"] is not None for row in rows),
                    "message": "亏损指标尚未由ETL写入时保持为空，不按0展示。",
                },
            }
        except (PermissionError, ValueError):
            raise
        except Exception as error:
            LOGGER.exception("Target progress dashboard query failed")
            raise TargetManagementUnavailable("目标进度查询失败，请确认目标表和ERP基础表可用") from error
        finally:
            if connection is not None:
                connection.close()

    def _dashboard_target_rows(self, cursor: Any, scene: str, start: date, end: date) -> list[dict[str, Any]]:
        cursor.execute(
            f"""SELECT i.*, p.target_scene, p.status AS plan_status, p.period_start, p.period_end,
                       m.metric_name, m.unit_code AS metric_unit_code,
                       pr.stat_date, pr.actual_today, pr.actual_cumulative,
                       pr.planned_cumulative_rate, pr.completion_rate, pr.progress_gap_rate,
                       pr.remaining_value, pr.required_daily_value, pr.profit_cumulative,
                       pr.profit_per_segment, pr.data_status, pr.data_through_date
                FROM {self._table('biz_target_plan')} p
                JOIN {self._table('biz_target_item')} i ON i.plan_id=p.id
                LEFT JOIN {self._table('target_metric_definition')} m
                  ON m.metric_code=i.metric_code AND m.metric_version=i.metric_version
                LEFT JOIN {self._table('ads_target_progress_day')} pr
                  ON pr.id=(SELECT pr2.id FROM {self._table('ads_target_progress_day')} pr2
                            WHERE pr2.target_item_id=i.id AND pr2.stat_date<=CURRENT_DATE
                            ORDER BY pr2.stat_date DESC LIMIT 1)
                WHERE p.target_scene=%s AND p.period_start=%s AND p.period_end=%s
                  AND p.status IN ('ACTIVE','PUBLISHED') AND i.enabled=1 AND i.unit_code='SEGMENT'
                ORDER BY i.sort_order, i.id""",
            (scene, start, end),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        if scene == "POLICY":
            self._attach_policy_members(cursor, rows)
        return rows

    def _attach_policy_members(self, cursor: Any, rows: list[dict[str, Any]]) -> None:
        plan_ids = sorted({int(row["plan_id"]) for row in rows if row.get("plan_id") is not None})
        if not plan_ids:
            return
        placeholders = ",".join(["%s"] * len(plan_ids))
        cursor.execute(
            f"""SELECT plan_id, policy_group_code, member_user_id, member_name_snapshot
                FROM {self._table('biz_target_policy_member')}
                WHERE plan_id IN ({placeholders})
                ORDER BY plan_id, policy_group_code, sort_order, id""",
            tuple(plan_ids),
        )
        members: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for member in cursor.fetchall():
            key = (int(member["plan_id"]), str(member["policy_group_code"]))
            members.setdefault(key, []).append({
                "id": int(member["member_user_id"]),
                "name": str(member["member_name_snapshot"]),
            })
        for row in rows:
            key = (int(row["plan_id"]), str(row.get("policy_group_code") or ""))
            selected = members.get(key, [])
            row["policy_member_user_ids"] = [member["id"] for member in selected]
            row["policy_member_names"] = [member["name"] for member in selected]

    def _dashboard_metric_rows(self, cursor: Any, scene: str, start: date, end: date) -> list[dict[str, Any]]:
        dimension_column = {"PLATFORM": "platform_code", "GDS": "gds_code", "POLICY": "policy_group_code"}[scene]
        cursor.execute(
            f"""SELECT {dimension_column} AS scope_code, metric_code, business_date,
                       sum(actual_value) AS actual_value, sum(issue_profit) AS issue_profit,
                       sum(ticket_count) AS ticket_count,
                       CASE WHEN sum(data_status='MISSING')>0 THEN 'MISSING'
                            WHEN sum(data_status='PARTIAL')>0 THEN 'PARTIAL'
                            ELSE 'READY' END AS data_status,
                       max(source_max_time) AS source_max_time,
                       max(etl_updated_at) AS etl_updated_at
                FROM {self._table('dws_target_metric_day')}
                WHERE business_date BETWEEN %s AND %s
                  AND coalesce({dimension_column}, '')<>''
                  AND metric_code IN ('ISSUED_AIRLIFT_SEGMENT','REWARD_SEGMENT','GDS_1A_ELIGIBLE_SEGMENT',
                                      'ISSUE_PROFIT','LOSS_AMOUNT','LOSS_TICKET_COUNT','LOSS_SEGMENT_COUNT')
                GROUP BY {dimension_column}, metric_code, business_date""",
            (start, end),
        )
        return [dict(row) for row in cursor.fetchall()]

    def _dashboard_roster(self) -> dict[int, dict[str, Any]]:
        import pymysql

        connection = None
        try:
            connection = self.roster_source.connect()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    f"""SELECT ru.id, coalesce(ru.wechat_id, '') AS wechat_id,
                               coalesce(ro.org_code, '') AS department_code,
                               coalesce(ro.org_cname, '') AS department_name
                        FROM {self._roster_users} ru
                        LEFT JOIN (
                            SELECT user_id, max(id) AS latest_id
                            FROM {self._roster_user_departments}
                            GROUP BY user_id
                        ) latest ON latest.user_id=ru.id
                        LEFT JOIN {self._roster_user_departments} rud ON rud.id=latest.latest_id
                        LEFT JOIN {self._roster_orgs} ro ON ro.id=rud.department_id
                        WHERE ru.enabled=0"""
                )
                return {int(row["id"]): dict(row) for row in cursor.fetchall()}
        except Exception as error:
            LOGGER.warning("ERP roster unavailable for target dashboard: %s", error)
            return {}
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _metric_index(metric_rows: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
        index: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for row in metric_rows:
            index.setdefault(str(row["scope_code"]), {}).setdefault(str(row["metric_code"]), []).append(row)
        return index

    @staticmethod
    def _metric_value(metrics: dict[str, list[dict[str, Any]]], code: str, *, on_date: date | None = None) -> float | None:
        rows = metrics.get(code, [])
        if on_date is not None:
            rows = [row for row in rows if row["business_date"] == on_date]
        if not rows or any(str(row.get("data_status") or "READY") != "READY" for row in rows):
            return None
        values = [row["actual_value"] for row in rows]
        if any(value is None for value in values):
            return None
        return sum(float(value) for value in values)

    @staticmethod
    def _ticket_value(metrics: dict[str, list[dict[str, Any]]], code: str) -> float | None:
        rows = metrics.get(code, [])
        if any(str(row.get("data_status") or "READY") != "READY" for row in rows):
            return None
        values = [row["ticket_count"] for row in rows if row["ticket_count"] is not None]
        return sum(float(value) for value in values) if values else None

    @staticmethod
    def _report_dates(start: date, end: date) -> tuple[date | None, date | None]:
        anchor = min(end, business_now().date() - timedelta(days=1))
        if anchor < start:
            return None, None
        previous = anchor - timedelta(days=1)
        return anchor, previous if previous >= start else None

    def _progress_metrics(self, start: date, end: date, metrics: dict[str, list[dict[str, Any]]],
                          base: dict[str, Any]) -> dict[str, Any]:
        report_date, previous_date = self._report_dates(start, end)
        segment_code = str(base.get("metricCode") or "ISSUED_AIRLIFT_SEGMENT")
        segments = self._metric_value(metrics, segment_code)
        if segments is None and segment_code != "ISSUED_AIRLIFT_SEGMENT":
            segments = self._metric_value(metrics, "ISSUED_AIRLIFT_SEGMENT")
        actual = base.get("actual") if base.get("actual") is not None else segments
        profit = self._metric_value(metrics, "ISSUE_PROFIT")
        if profit is None:
            profit = base.get("profit")
        yesterday = self._metric_value(metrics, segment_code, on_date=report_date) if report_date else None
        if yesterday is None and report_date and segment_code != "ISSUED_AIRLIFT_SEGMENT":
            yesterday = self._metric_value(metrics, "ISSUED_AIRLIFT_SEGMENT", on_date=report_date)
        if yesterday is None:
            yesterday = base.get("yesterday")
        day_before = self._metric_value(metrics, segment_code, on_date=previous_date) if previous_date else None
        yesterday_profit = self._metric_value(metrics, "ISSUE_PROFIT", on_date=report_date) if report_date else None
        loss_amount = self._metric_value(metrics, "LOSS_AMOUNT")
        loss_tickets = self._metric_value(metrics, "LOSS_TICKET_COUNT")
        loss_segments = self._metric_value(metrics, "LOSS_SEGMENT_COUNT")
        total_tickets = self._ticket_value(metrics, segment_code)
        if total_tickets is None and segment_code != "ISSUED_AIRLIFT_SEGMENT":
            total_tickets = self._ticket_value(metrics, "ISSUED_AIRLIFT_SEGMENT")
        target = float(base.get("target") or 0)
        completion = base.get("completionRate")
        if completion is None and actual is not None and target:
            completion = float(actual) / target
        expected = base.get("expectedRate")
        remaining = base.get("remaining")
        if remaining is None and actual is not None and target:
            remaining = max(target - float(actual), 0.0)
        required_daily = base.get("requiredDaily")
        if required_daily is None and remaining is not None and report_date:
            days_left = max((end - report_date).days, 0)
            required_daily = remaining / days_left if days_left else (0.0 if remaining == 0 else None)
        metric_dates = [row["business_date"] for rows in metrics.values() for row in rows if row.get("business_date")]
        data_through_date = base.get("dataThroughDate") or (_iso(max(metric_dates)) if metric_dates else None)
        return {
            **base,
            "actual": actual,
            "completionRate": completion,
            "progressGapRate": (completion - expected) if completion is not None and expected is not None else base.get("progressGapRate"),
            "remaining": remaining,
            "requiredDaily": required_daily,
            "profit": profit,
            "profitPerSegment": (profit / actual) if profit is not None and actual else base.get("profitPerSegment"),
            "yesterday": yesterday,
            "dayBefore": day_before,
            "dayOverDayRate": ((yesterday - day_before) / day_before) if yesterday is not None and day_before else None,
            "yesterdayProfit": yesterday_profit,
            "yesterdayProfitPerSegment": (yesterday_profit / yesterday) if yesterday_profit is not None and yesterday else None,
            "lossAmount": loss_amount,
            "lossTicketCount": loss_tickets,
            "lossSegmentCount": loss_segments,
            "lossShare": (loss_tickets / total_tickets) if loss_tickets is not None and total_tickets else None,
            "totalTicketCount": total_tickets,
            "reportDate": _iso(report_date),
            "previousDate": _iso(previous_date),
            "dataThroughDate": data_through_date,
            "dataStatus": base.get("dataStatus") if actual is not None else ("READY" if metrics else "PENDING_ETL"),
        }

    def _platform_progress_rows(self, period: str, start: date, end: date,
                                masters: list[dict[str, Any]], targets: list[dict[str, Any]],
                                metric_rows: list[dict[str, Any]], roster: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        target_by_code = {str(row["platformCode"]): row for row in targets if row.get("platformCode")}
        metric_index = self._metric_index(metric_rows)
        result = []
        for master in masters:
            code = str(master["code"])
            target = target_by_code.get(code)
            base = dict(target) if target else {
                "id": f"PLATFORM:{code}", "itemId": None, "planId": None, "scene": "platform", "period": period,
                "departmentCode": "", "department": "", "platformCode": code,
                "platform": str(master["name"] or code), "gds": None, "policyCode": "", "policy": None,
                "ownerUserId": None, "owner": "", "metric": "有效出票承运航段",
                "metricCode": "ISSUED_AIRLIFT_SEGMENT", "metricVersion": "V1", "target": 0.0,
                "actual": None, "yesterday": None, "expectedRate": None, "completionRate": None,
                "progressGapRate": None, "remaining": None, "requiredDaily": None, "profit": None,
                "profitPerSegment": None, "status": "UNCONFIGURED", "dataStatus": "PENDING_ETL",
                "dataThroughDate": None, "remark": "", "itemIds": {},
            }
            owner_id = base.get("ownerUserId")
            employee = roster.get(int(owner_id)) if owner_id is not None else None
            base.update({
                "configured": target is not None,
                "platformFullName": str(master["full_name"] or master["name"] or code),
                "wechatConfigured": bool(employee and employee.get("wechat_id")),
            })
            result.append(self._progress_metrics(start, end, metric_index.get(code, {}), base))
        return result

    def _configured_progress_rows(self, scene: str, period: str, start: date, end: date,
                                  targets: list[dict[str, Any]], metric_rows: list[dict[str, Any]],
                                  roster: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        metric_index = self._metric_index(metric_rows)
        result = []
        for target in targets:
            scope_code = str(target.get("gds") if scene == "GDS" else target.get("policyCode") or "")
            owner_id = target.get("ownerUserId")
            employee = roster.get(int(owner_id)) if owner_id is not None else None
            base = {**target, "configured": True, "platformFullName": "", "wechatConfigured": bool(employee and employee.get("wechat_id"))}
            result.append(self._progress_metrics(start, end, metric_index.get(scope_code, {}), base))
        return result

    def _public_rows(self, scene: str, period: str, raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        simple = [self._public_row(scene, period, row) for row in raw_rows]
        if scene != "POLICY":
            return simple
        grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in simple:
            key = (row["planId"], row["departmentCode"], row["policyCode"], row["ownerUserId"], row["metricCode"])
            target = grouped.get(key)
            if target is None:
                target = {**row, "id": f"POLICY:{row['planId']}:{row['departmentCode']}:{row['policyCode']}:{row['ownerUserId'] or 0}",
                          "itemIds": {}, "gdsBreakdown": {}, "target": 0.0, "actual": None,
                          "yesterday": None, "profit": None, "completionRate": None,
                          "expectedRate": None, "progressGapRate": None}
                grouped[key] = target
            target["itemIds"][row["gds"]] = row["itemId"]
            target["gdsBreakdown"][row["gds"]] = {
                "itemId": row["itemId"], "target": row["target"], "actual": row["actual"],
                "yesterday": row["yesterday"], "dataStatus": row["dataStatus"],
            }
            target["target"] += row["target"]
            if row["actual"] is not None:
                target["actual"] = (target["actual"] or 0) + row["actual"]
                target["yesterday"] = (target["yesterday"] or 0) + (row["yesterday"] or 0)
            if row["profit"] is not None:
                target["profit"] = (target["profit"] or 0) + row["profit"]
            if row["dataThroughDate"] and (not target["dataThroughDate"] or row["dataThroughDate"] > target["dataThroughDate"]):
                target["dataThroughDate"] = row["dataThroughDate"]
        for row in grouped.values():
            ready = [item for item in row["gdsBreakdown"].values() if item["actual"] is not None]
            if not ready:
                row["actual"] = row["yesterday"] = row["profit"] = None
            if row["actual"] is not None and row["target"]:
                row["completionRate"] = row["actual"] / row["target"]
            expected_values = [raw["planned_cumulative_rate"] for raw in raw_rows
                               if raw["id"] in row["itemIds"].values() and raw["planned_cumulative_rate"] is not None]
            if expected_values:
                row["expectedRate"] = float(max(expected_values))
                row["progressGapRate"] = row["completionRate"] - row["expectedRate"] if row["completionRate"] is not None else None
        return list(grouped.values())

    @staticmethod
    def _public_row(scene: str, period: str, row: dict[str, Any]) -> dict[str, Any]:
        actual = _decimal(row["actual_cumulative"])
        return {
            "id": str(row["id"]), "itemId": int(row["id"]), "planId": int(row["plan_id"]),
            "scene": scene.lower(), "period": period,
            "departmentCode": row["department_code"], "department": row["department_name_snapshot"],
            "platformCode": row["platform_code"], "platform": row["platform_name_snapshot"] or None,
            "gds": row["gds_code"] or None,
            "policyCode": row["policy_group_code"],
            "policy": "/".join(str(value) for value in row.get("policy_member_names", []))
                      or row["policy_group_name_snapshot"] or None,
            "policyLeaderUserId": int(row["policy_leader_user_id"]) if row.get("policy_leader_user_id") is not None else None,
            "policyLeaderName": str(row.get("policy_leader_name_snapshot") or ""),
            "policyMemberUserIds": [int(value) for value in row.get("policy_member_user_ids", [])],
            "policyMemberNames": [str(value) for value in row.get("policy_member_names", [])],
            "ownerUserId": int(row["owner_user_id"]) if row["owner_user_id"] is not None else None,
            "owner": row["owner_name_snapshot"], "metric": row["metric_name"] or row["metric_code"],
            "metricCode": row["metric_code"], "metricVersion": row["metric_version"],
            "target": _decimal(row["target_value"]) or 0.0, "actual": actual,
            "yesterday": _decimal(row["actual_today"]) if row["stat_date"] is not None else None,
            "expectedRate": _decimal(row["planned_cumulative_rate"]),
            "completionRate": _decimal(row["completion_rate"]),
            "progressGapRate": _decimal(row["progress_gap_rate"]),
            "remaining": _decimal(row["remaining_value"]) if row["stat_date"] is not None else None,
            "requiredDaily": _decimal(row["required_daily_value"]),
            "profit": _decimal(row["profit_cumulative"]), "profitPerSegment": _decimal(row["profit_per_segment"]),
            "status": _row_status(str(row["plan_status"]), row["enabled"]),
            "dataStatus": row["data_status"] if row["stat_date"] is not None else "PENDING_ETL",
            "dataThroughDate": _iso(row["data_through_date"]), "remark": row["remark"] or "",
            "itemIds": {row["gds_code"]: int(row["id"])} if row["gds_code"] else {},
        }

    def save(self, user: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        _require(user, MANAGE_PERMISSION, "当前账号没有目标配置权限")
        scene = _scene(values.get("scene"))
        period, start, end = _month(values.get("period"))
        department_name = _text(values.get("departmentName"), "归属部门", required=True, maximum=100)
        department_code = _text(values.get("departmentCode"), "部门编码", required=True, maximum=64)
        owner_name = _text(values.get("ownerName"), "责任人", maximum=100)
        owner_user_id = values.get("policyLeaderUserId") if scene == "POLICY" else values.get("ownerUserId")
        if owner_user_id in (None, ""):
            raise ValueError("请选择组长" if scene == "POLICY" else "请从真实用户中选择责任人")
        try:
            owner_user_id = int(owner_user_id)
        except Exception as error:
            raise ValueError("责任人编号不合法") from error
        metric_code = _text(values.get("metricCode"), "指标口径", required=True, maximum=64)
        metric_version = _text(values.get("metricVersion") or "V1", "指标版本", maximum=20)
        status = str(values.get("status") or "ACTIVE").strip().upper()
        if status not in EDIT_STATUSES:
            raise ValueError("可编辑状态只支持草稿、执行中或暂停")
        change_reason = _text(values.get("changeReason"), "本次操作原因", maximum=1000)
        platform_code = platform_name = gds_code = policy_code = policy_name = ""
        policy_leader_user_id: int | None = None
        policy_leader_name = ""
        policy_member_user_ids: list[int] = []
        policy_member_names: list[str] = []
        if scene == "PLATFORM":
            platform_code = _text(values.get("platformCode"), "平台", required=True, maximum=64)
            platform_name = _text(values.get("platformName"), "平台名称", required=True, maximum=100)
        elif scene == "GDS":
            gds_code = _text(values.get("gdsCode"), "GDS", required=True, maximum=32).upper()
        else:
            raw_member_ids = values.get("policyMemberUserIds")
            if not isinstance(raw_member_ids, list) or not raw_member_ids:
                raise ValueError("请至少选择一名政策员")
            try:
                policy_member_user_ids = list(dict.fromkeys(int(value) for value in raw_member_ids))
            except Exception as error:
                raise ValueError("政策员编号不合法") from error
            policy_leader_user_id = owner_user_id
            if policy_leader_user_id not in policy_member_user_ids:
                raise ValueError("组长必须包含在政策员组合中")
            try:
                people = self._roster_people(policy_member_user_ids)
            except Exception as roster_error:
                raise TargetManagementUnavailable("ERP花名册不可读，无法校验政策员组合") from roster_error
            if len(people) != len(policy_member_user_ids):
                raise ValueError("政策员组合包含无效或已禁用人员")
            policy_member_names = [str(people[user_id]["name"]) for user_id in policy_member_user_ids]
            policy_leader_name = str(people[policy_leader_user_id]["name"])
            owner_name = policy_leader_name
            policy_name = ""
            policy_code = _text(values.get("policyGroupCode"), "政策组编码", maximum=100) or _stable_code(
                "POLICY", ",".join(str(value) for value in sorted(policy_member_user_ids))
            )

        try:
            roster_owner = self._roster_owner(owner_user_id)
            roster_department = self._roster_department(department_code)
        except Exception as roster_error:
            raise TargetManagementUnavailable(
                "ERP花名册不可读，无法校验责任人及归属部门"
            ) from roster_error
        if not roster_owner:
            raise ValueError("所选责任人不在有效ERP花名册中")
        owner_name = str(roster_owner["owner_name"] or "").strip()
        if not roster_department:
            raise ValueError("所选归属部门不在ERP组织资料中")
        department_code = str(roster_department["code"])
        department_name = str(roster_department["name"])

        import pymysql
        connection = cursor = None
        try:
            connection = self.source.connect()
            connection.begin()
            cursor = connection.cursor(pymysql.cursors.DictCursor)
            if scene == "PLATFORM":
                cursor.execute(
                    f"""SELECT ota_code, ota_cname FROM {self._platforms}
                        WHERE ota_code=%s AND status=1
                          AND (start_time IS NULL OR start_time<=NOW())
                          AND (end_time IS NULL OR end_time>=NOW()) LIMIT 1""",
                    (platform_code,),
                )
                platform = cursor.fetchone()
                if not platform:
                    raise ValueError("所选平台不在有效ERP平台资料中")
                platform_name = str(platform["ota_cname"] or platform["ota_code"])
            cursor.execute(
                f"SELECT metric_name, unit_code, supported_scenes FROM {self._table('target_metric_definition')} "
                "WHERE metric_code=%s AND metric_version=%s AND status='ACTIVE' LIMIT 1",
                (metric_code, metric_version),
            )
            metric = cursor.fetchone()
            if not metric:
                raise ValueError("所选指标口径不存在或未启用")
            if str(metric["unit_code"] or "").upper() != "SEGMENT":
                raise ValueError("目标配置当前只支持航段数量指标，金额指标仅用于进度看板")
            if scene not in {item.strip() for item in str(metric["supported_scenes"] or "").split(",")}:
                raise ValueError("所选指标口径不支持当前场景")
            if scene == "GDS" and metric_code == "GDS_1A_ELIGIBLE_SEGMENT" and gds_code != "1A":
                raise ValueError("1A考核有效航段只能用于1A目标")
            cursor.execute(
                f"""SELECT id, status FROM {self._table('biz_target_plan')}
                    WHERE target_scene=%s AND period_type='MONTH' AND period_start=%s AND period_end=%s
                    ORDER BY version_no DESC, id DESC LIMIT 1 FOR UPDATE""",
                (scene, start, end),
            )
            plan = cursor.fetchone()
            actor_id = int(user.get("id") or 0) or None
            plan_status = "DRAFT" if status == "DRAFT" else "ACTIVE"
            if plan:
                plan_id = int(plan["id"])
                cursor.execute(
                    f"UPDATE {self._table('biz_target_plan')} SET status=%s, updated_by=%s WHERE id=%s",
                    (plan_status, actor_id, plan_id),
                )
            else:
                plan_code = f"TARGET_{scene}_{period.replace('-', '')}_V1"
                cursor.execute(
                    f"""INSERT INTO {self._table('biz_target_plan')}
                        (plan_code,plan_name,target_scene,period_type,period_start,period_end,
                         progress_curve_code,status,version_no,created_by,updated_by)
                        VALUES (%s,%s,%s,'MONTH',%s,%s,'WEEKDAY_WEIGHT',%s,1,%s,%s)""",
                    (plan_code, f"{period} {scene} 目标", scene, start, end, plan_status, actor_id, actor_id),
                )
                plan_id = int(cursor.lastrowid)

            entries: list[tuple[str, Decimal, int | None]] = []
            if scene == "POLICY":
                targets = values.get("gdsTargets")
                if not isinstance(targets, list) or not targets:
                    raise ValueError("请至少配置一个GDS目标")
                item_ids = values.get("itemIds") if isinstance(values.get("itemIds"), dict) else {}
                for item in targets:
                    if not isinstance(item, dict):
                        raise ValueError("GDS目标格式不合法")
                    code = _text(item.get("gdsCode"), "GDS", required=True, maximum=32).upper()
                    entries.append((code, _number(item.get("targetValue")), int(item_ids[code]) if item_ids.get(code) else None))
            else:
                existing_id = values.get("itemId")
                entries.append((gds_code, _number(values.get("targetValue")), int(existing_id) if existing_id else None))
            if sum((entry[1] for entry in entries), Decimal("0")) <= 0:
                raise ValueError("目标航段数合计必须大于0")

            requested_item_ids = [entry[2] for entry in entries if entry[2]]
            before_snapshot = self._configuration_snapshot(
                cursor,
                plan_id,
                item_ids=requested_item_ids,
                policy_group_code=policy_code if scene == "POLICY" else "",
            )
            if before_snapshot and not change_reason:
                raise ValueError("修改目标配置时请填写本次操作原因")
            if not change_reason:
                change_reason = "新建目标配置"

            saved_ids: list[int] = []
            for entry_gds, target_value, existing_id in entries:
                scope_parts = [f"DEPT={department_code}"]
                if scene == "PLATFORM": scope_parts.append(f"PLATFORM={platform_code}")
                if scene in {"GDS", "POLICY"}: scope_parts.append(f"GDS={entry_gds}")
                if scene == "POLICY": scope_parts.append(f"POLICY={policy_code}")
                scope_parts.append(f"OWNER={owner_user_id}")
                scope_key = "|".join(scope_parts)
                enabled = 0 if status == "PAUSED" else 1
                remark = _text(values.get("remark"), "说明", maximum=1000)
                fields = (scope_key, metric_code, metric_version, department_code, department_name,
                          platform_code, platform_name, entry_gds, policy_code, policy_name,
                          policy_leader_user_id, policy_leader_name,
                          None, "",
                          owner_user_id, owner_name, target_value, metric["unit_code"], enabled,
                          remark or None, actor_id)
                if existing_id:
                    cursor.execute(
                        f"""UPDATE {self._table('biz_target_item')} SET
                            scope_key=%s,metric_code=%s,metric_version=%s,department_code=%s,
                            department_name_snapshot=%s,platform_code=%s,platform_name_snapshot=%s,
                            gds_code=%s,policy_group_code=%s,policy_group_name_snapshot=%s,
                            policy_leader_user_id=%s,policy_leader_name_snapshot=%s,
                            policy_member_user_id=%s,policy_member_name_snapshot=%s,
                            owner_user_id=%s,owner_name_snapshot=%s,target_value=%s,unit_code=%s,
                            enabled=%s,remark=%s,updated_by=%s WHERE id=%s AND plan_id=%s""",
                        (*fields, existing_id, plan_id),
                    )
                    if cursor.rowcount == 0:
                        cursor.execute(
                            f"SELECT id FROM {self._table('biz_target_item')} WHERE id=%s AND plan_id=%s",
                            (existing_id, plan_id),
                        )
                        if not cursor.fetchone():
                            raise ValueError("要编辑的目标不存在或不属于当前计划")
                    saved_ids.append(existing_id)
                else:
                    item_digest = hashlib.sha1(f"{plan_id}|{metric_code}|{scope_key}".encode()).hexdigest()[:20].upper()
                    item_code = f"TI_{item_digest}"
                    cursor.execute(
                        f"""INSERT INTO {self._table('biz_target_item')}
                            (plan_id,item_code,scope_key,metric_code,metric_version,department_code,
                             department_name_snapshot,platform_code,platform_name_snapshot,gds_code,
                             policy_group_code,policy_group_name_snapshot,
                             policy_leader_user_id,policy_leader_name_snapshot,
                             policy_member_user_id,policy_member_name_snapshot,
                             owner_user_id,owner_name_snapshot,
                             target_value,unit_code,allocation_source,enabled,remark,created_by,updated_by)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'MANUAL',%s,%s,%s,%s)
                            ON DUPLICATE KEY UPDATE target_value=VALUES(target_value),
                              department_name_snapshot=VALUES(department_name_snapshot),
                              platform_name_snapshot=VALUES(platform_name_snapshot),
                              policy_group_name_snapshot=VALUES(policy_group_name_snapshot),
                              policy_leader_user_id=VALUES(policy_leader_user_id),
                              policy_leader_name_snapshot=VALUES(policy_leader_name_snapshot),
                              policy_member_user_id=VALUES(policy_member_user_id),
                              policy_member_name_snapshot=VALUES(policy_member_name_snapshot),
                              owner_name_snapshot=VALUES(owner_name_snapshot),enabled=VALUES(enabled),
                              remark=VALUES(remark),updated_by=VALUES(updated_by),id=LAST_INSERT_ID(id)""",
                        (plan_id, item_code, *fields[:-1], actor_id, actor_id),
                    )
                    saved_ids.append(int(cursor.lastrowid))
            if scene == "POLICY":
                cursor.execute(
                    f"DELETE FROM {self._table('biz_target_policy_member')} "
                    "WHERE plan_id=%s AND policy_group_code=%s",
                    (plan_id, policy_code),
                )
                cursor.executemany(
                    f"""INSERT INTO {self._table('biz_target_policy_member')}
                        (plan_id,policy_group_code,member_user_id,member_name_snapshot,sort_order)
                        VALUES (%s,%s,%s,%s,%s)""",
                    [
                        (plan_id, policy_code, user_id, policy_member_names[index], index)
                        for index, user_id in enumerate(policy_member_user_ids)
                    ],
                )
            after_snapshot = self._configuration_snapshot(
                cursor,
                plan_id,
                item_ids=saved_ids,
                policy_group_code=policy_code if scene == "POLICY" else "",
            )
            if not after_snapshot:
                raise TargetManagementUnavailable("目标保存后无法生成审计快照")
            self._write_change_log(
                cursor,
                plan_id=plan_id,
                scene=scene,
                status=status,
                item_ids=saved_ids,
                before=before_snapshot,
                after=after_snapshot,
                change_reason=change_reason,
                user=user,
            )
            connection.commit()
            return {"planId": plan_id, "itemIds": saved_ids, "scene": scene, "period": period}
        except (PermissionError, ValueError, TargetManagementUnavailable):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Target save failed")
            raise TargetManagementUnavailable("目标保存失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()
