"""业务目标配置与进度查询服务。

目标值只写入 biz_target_plan / biz_target_item；完成量只读取
ads_target_progress_day，该表无 ETL 快照时返回 null，不伪造 0 完成量。
"""
from __future__ import annotations

import hashlib
import logging
import re
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .data_source import DataSource


LOGGER = logging.getLogger(__name__)
SCENES = frozenset({"PLATFORM", "GDS", "POLICY"})
EDIT_STATUSES = frozenset({"DRAFT", "ACTIVE", "PAUSED"})
VIEW_PERMISSION = "business_config.targets.view"
MANAGE_PERMISSION = "business_config.targets.manage"


class TargetManagementUnavailable(RuntimeError):
    pass


def _permissions(user: dict[str, Any]) -> set[str]:
    return {str(value) for value in (user.get("permissions") or user.get("permission_codes") or [])}


def _require(user: dict[str, Any], permission: str, message: str) -> None:
    if bool(user.get("is_admin")) or permission in _permissions(user):
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


class TargetManagementService:
    def __init__(self, config: dict[str, Any], source: DataSource | None = None):
        mysql_config = dict(config)
        mysql_config["DATA_MODE"] = "mysql"
        self.source = source or DataSource(mysql_config)
        self.database = self.source.database

    def _table(self, name: str) -> str:
        return f"{self.database}.{name}"

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
                    f"""SELECT ota_code AS code, max(ota_cname) AS name
                        FROM {self._table('bi_gds_resource_metric_day')}
                        WHERE coalesce(ota_code, '') <> ''
                        GROUP BY ota_code ORDER BY name, code"""
                )
                platforms = [{"code": str(row["code"]), "name": str(row["name"] or row["code"])} for row in cursor.fetchall()]
                cursor.execute(
                    f"""SELECT gds_code AS code
                        FROM {self._table('bi_gds_resource_metric_day')}
                        WHERE coalesce(gds_code, '') <> '' GROUP BY gds_code ORDER BY gds_code"""
                )
                gds = [{"code": str(row["code"]), "name": str(row["code"])} for row in cursor.fetchall()]
                cursor.execute(
                    f"""SELECT id, username, coalesce(nullif(full_name, ''), username) AS name
                        FROM {self._table('sys_user')} WHERE is_active=1 ORDER BY name, id"""
                )
                users = [{"id": int(row["id"]), "username": row["username"], "name": row["name"]} for row in cursor.fetchall()]
                cursor.execute(
                    f"""SELECT department_code AS code, max(department_name_snapshot) AS name
                        FROM (
                            SELECT department_code, department_name_snapshot FROM {self._table('biz_target_item')}
                            UNION ALL
                            SELECT department_code, department_name_snapshot FROM {self._table('biz_target_scope_assignment')}
                        ) d WHERE coalesce(department_code, '') <> ''
                        GROUP BY department_code ORDER BY name, code"""
                )
                departments = [{"code": row["code"], "name": row["name"] or row["code"]} for row in cursor.fetchall()]
                cursor.execute(
                    f"""SELECT policy_group_code AS code, max(policy_group_name_snapshot) AS name
                        FROM {self._table('biz_target_item')}
                        WHERE coalesce(policy_group_code, '') <> ''
                        GROUP BY policy_group_code ORDER BY name, code"""
                )
                policies = [{"code": row["code"], "name": row["name"] or row["code"]} for row in cursor.fetchall()]
            return {"available": True, "platforms": platforms, "gds": gds, "users": users,
                    "departments": departments, "policyGroups": policies}
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
            "policyCode": row["policy_group_code"], "policy": row["policy_group_name_snapshot"] or None,
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
        department_code = _text(values.get("departmentCode"), "部门编码", maximum=64) or _stable_code("DEPT", department_name)
        owner_name = _text(values.get("ownerName"), "责任人", required=True, maximum=100)
        owner_user_id = values.get("ownerUserId")
        if owner_user_id in (None, ""):
            raise ValueError("请从真实用户中选择责任人")
        try:
            owner_user_id = int(owner_user_id)
        except Exception as error:
            raise ValueError("责任人编号不合法") from error
        metric_code = _text(values.get("metricCode"), "指标口径", required=True, maximum=64)
        metric_version = _text(values.get("metricVersion") or "V1", "指标版本", maximum=20)
        status = str(values.get("status") or "ACTIVE").strip().upper()
        if status not in EDIT_STATUSES:
            raise ValueError("可编辑状态只支持草稿、执行中或暂停")
        platform_code = platform_name = gds_code = policy_code = policy_name = ""
        if scene == "PLATFORM":
            platform_code = _text(values.get("platformCode"), "平台", required=True, maximum=64)
            platform_name = _text(values.get("platformName"), "平台名称", required=True, maximum=100)
        elif scene == "GDS":
            gds_code = _text(values.get("gdsCode"), "GDS", required=True, maximum=32).upper()
        else:
            policy_name = _text(values.get("policyGroupName"), "政策员/政策组", required=True, maximum=150)
            policy_code = _text(values.get("policyGroupCode"), "政策组编码", maximum=100) or _stable_code("POLICY", policy_name)

        import pymysql
        connection = cursor = None
        try:
            connection = self.source.connect()
            connection.begin()
            cursor = connection.cursor(pymysql.cursors.DictCursor)
            cursor.execute(
                f"SELECT metric_name, unit_code, supported_scenes FROM {self._table('target_metric_definition')} "
                "WHERE metric_code=%s AND metric_version=%s AND status='ACTIVE' LIMIT 1",
                (metric_code, metric_version),
            )
            metric = cursor.fetchone()
            if not metric:
                raise ValueError("所选指标口径不存在或未启用")
            if scene not in {item.strip() for item in str(metric["supported_scenes"] or "").split(",")}:
                raise ValueError("所选指标口径不支持当前场景")
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
                          owner_user_id, owner_name, target_value, metric["unit_code"], enabled,
                          remark or None, actor_id)
                if existing_id:
                    cursor.execute(
                        f"""UPDATE {self._table('biz_target_item')} SET
                            scope_key=%s,metric_code=%s,metric_version=%s,department_code=%s,
                            department_name_snapshot=%s,platform_code=%s,platform_name_snapshot=%s,
                            gds_code=%s,policy_group_code=%s,policy_group_name_snapshot=%s,
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
                             policy_group_code,policy_group_name_snapshot,owner_user_id,owner_name_snapshot,
                             target_value,unit_code,allocation_source,enabled,remark,created_by,updated_by)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'MANUAL',%s,%s,%s,%s)
                            ON DUPLICATE KEY UPDATE target_value=VALUES(target_value),
                              department_name_snapshot=VALUES(department_name_snapshot),
                              platform_name_snapshot=VALUES(platform_name_snapshot),
                              policy_group_name_snapshot=VALUES(policy_group_name_snapshot),
                              owner_name_snapshot=VALUES(owner_name_snapshot),enabled=VALUES(enabled),
                              remark=VALUES(remark),updated_by=VALUES(updated_by),id=LAST_INSERT_ID(id)""",
                        (plan_id, item_code, *fields[:-1], actor_id, actor_id),
                    )
                    saved_ids.append(int(cursor.lastrowid))
            connection.commit()
            return {"planId": plan_id, "itemIds": saved_ids, "scene": scene, "period": period}
        except (PermissionError, ValueError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            LOGGER.exception("Target save failed")
            raise TargetManagementUnavailable("目标保存失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()
