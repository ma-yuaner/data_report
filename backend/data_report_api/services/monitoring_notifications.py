"""Notification endpoints, templates and routes under the existing monitor permissions."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from urllib import request as urlrequest
from typing import Any

from ..time_utils import business_now_naive
from ..shared.daily_segment import EVENT as DAILY_SEGMENT_EVENT
from .monitoring_support import (
    MonitoringSource,
    NOTIFY_ENDPOINT_TABLE,
    MESSAGE_TEMPLATE_TABLE,
    NOTIFY_ROUTE_TABLE,
    ENDPOINT_STATUSES,
    NOTIFY_EVENT_CODES,
    RECIPIENT_STRATEGIES,
    MonitoringUnavailable,
    is_missing_table as _is_missing_table,
    dict_row as _dict_row,
    dict_rows as _dict_rows,
    json_value as _json_value,
    public_row as _public_row,
    require as _require,
    clean_text as _clean_text,
    string_list as _string_list,
    mask_webhook as _mask_webhook,
    validate_wecom_webhook as _validate_wecom_webhook,
    wecom_test_message as _wecom_test_message,
    json_list as _json_list,
)


class MonitoringNotifications(MonitoringSource):
    @staticmethod
    def _public_endpoint(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "endpointCode": str(row.get("endpoint_code") or ""),
            "endpointName": str(row.get("endpoint_name") or ""),
            "channel": str(row.get("channel") or "WECOM"),
            "webhookMasked": _mask_webhook(row.get("webhook_url")),
            "webhookConfigured": bool(row.get("webhook_url")),
            "mentionedUserIds": _json_list(row.get("mentioned_user_ids")),
            "mentionedMobiles": _json_list(row.get("mentioned_mobiles")),
            "smartPlacementEnabled": bool(row.get("smart_placement_enabled")),
            "status": str(row.get("status") or "DISABLED"),
            "updatedByName": str(row.get("updated_by_name") or "SYSTEM"),
            "updatedAt": _json_value(row.get("updated_at")),
        }

    def list_notify_endpoints(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        _require(user, "monitor.rule.manage", "当前账号没有通知群配置权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"SELECT * FROM {self._table(NOTIFY_ENDPOINT_TABLE)} ORDER BY status='ACTIVE' DESC,smart_placement_enabled DESC,id"
            )
            return [self._public_endpoint(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
        except Exception as error:
            if _is_missing_table(error):
                raise MonitoringUnavailable("企业微信通知表尚未创建，请先执行monitoring-wecom-notification-v1.sql") from error
            raise self._unavailable(error, "通知群配置查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def resolve_notification_endpoint(self, user: dict[str, Any], endpoint_id: str) -> dict[str, Any]:
        """Server-only bridge for other modules; never expose its raw URL through HTTP."""
        _require(user, "monitor.rule.manage", "当前账号没有通知群配置权限")
        if not str(endpoint_id).isdigit():
            raise ValueError("通知端点ID无效")
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self._table(NOTIFY_ENDPOINT_TABLE)} WHERE id=%s", (int(endpoint_id),))
            row = _dict_row(cursor, cursor.fetchone())
            if not row or row.get("status") != "ACTIVE" or row.get("channel") != "WECOM":
                raise ValueError("通知端点不存在、停用或不是企业微信群")
            url = _validate_wecom_webhook(row.get("webhook_url"), required=True)
            fingerprint = hashlib.sha256((url + str(row.get("updated_at"))).encode()).hexdigest()
            return {"id": str(row["id"]), "name": str(row.get("endpoint_name") or ""), "url": url, "fingerprint": fingerprint}
        except (ValueError, PermissionError):
            raise
        except Exception as error:
            raise MonitoringUnavailable("ADM通知端点读取失败") from error
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    def save_notify_endpoint(
        self,
        user: dict[str, Any],
        values: dict[str, Any],
        endpoint_id: int | None = None,
    ) -> dict[str, Any]:
        _require(user, "monitor.rule.manage", "当前账号没有通知群配置权限")
        endpoint_name = _clean_text(values.get("endpointName"))[:100]
        if not endpoint_name:
            raise ValueError("通知群名称不能为空")
        status = _clean_text(values.get("status") or "ACTIVE").upper()
        if status not in ENDPOINT_STATUSES:
            raise ValueError("通知群状态不支持")
        mentioned_user_ids = _string_list(values.get("mentionedUserIds"))
        mentioned_mobiles = _string_list(values.get("mentionedMobiles"))
        invalid_mobiles = [item for item in mentioned_mobiles if not re.fullmatch(r"\+?\d{6,20}", item)]
        if invalid_mobiles:
            raise ValueError(f"@手机号格式不正确：{invalid_mobiles[0]}")
        actor_id = int(user.get("id") or 0)
        actor_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        current = business_now_naive()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            existing = None
            if endpoint_id is not None:
                cursor.execute(
                    f"SELECT * FROM {self._table(NOTIFY_ENDPOINT_TABLE)} WHERE id=%s FOR UPDATE",
                    (endpoint_id,),
                )
                existing = _dict_row(cursor, cursor.fetchone())
                if not existing:
                    raise ValueError("通知群配置不存在")
            webhook = _validate_wecom_webhook(values.get("webhookUrl"), required=existing is None)
            if not webhook and existing:
                webhook = str(existing.get("webhook_url") or "")
            if existing:
                cursor.execute(
                    f"""UPDATE {self._table(NOTIFY_ENDPOINT_TABLE)}
                        SET endpoint_name=%s,webhook_url=%s,mentioned_user_ids=%s,mentioned_mobiles=%s,
                            smart_placement_enabled=%s,status=%s,updated_by_id=%s,updated_by_name=%s,updated_at=%s
                        WHERE id=%s""",
                    (
                        endpoint_name, webhook, json.dumps(mentioned_user_ids, ensure_ascii=False),
                        json.dumps(mentioned_mobiles, ensure_ascii=False),
                        1 if values.get("smartPlacementEnabled") else 0, status,
                        actor_id, actor_name, current, endpoint_id,
                    ),
                )
                saved_id = int(endpoint_id)
                endpoint_code = str(existing.get("endpoint_code") or "")
            else:
                endpoint_code = f"WECOM-{uuid.uuid4().hex[:16].upper()}"
                cursor.execute(
                    f"""INSERT INTO {self._table(NOTIFY_ENDPOINT_TABLE)} (
                        endpoint_code,endpoint_name,channel,webhook_url,mentioned_user_ids,mentioned_mobiles,
                        smart_placement_enabled,status,created_by_id,created_by_name,created_at,
                        updated_by_id,updated_by_name,updated_at
                    ) VALUES ({','.join(['%s'] * 14)})""",
                    (
                        endpoint_code, endpoint_name, "WECOM", webhook,
                        json.dumps(mentioned_user_ids, ensure_ascii=False),
                        json.dumps(mentioned_mobiles, ensure_ascii=False),
                        1 if values.get("smartPlacementEnabled") else 0, status,
                        actor_id, actor_name, current, actor_id, actor_name, current,
                    ),
                )
                saved_id = int(cursor.lastrowid)
            connection.commit()
            return {
                "id": saved_id,
                "endpointCode": endpoint_code,
                "endpointName": endpoint_name,
                "status": status,
                "smartPlacementEnabled": bool(values.get("smartPlacementEnabled")),
            }
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            if _is_missing_table(error):
                raise MonitoringUnavailable("企业微信通知表尚未创建，请先执行monitoring-wecom-notification-v1.sql") from error
            raise self._unavailable(error, "通知群配置保存失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def test_notify_endpoint(self, user: dict[str, Any], endpoint_id: int) -> dict[str, Any]:
        _require(user, "monitor.rule.manage", "当前账号没有通知群测试权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self._table(NOTIFY_ENDPOINT_TABLE)} WHERE id=%s", (endpoint_id,))
            endpoint = _dict_row(cursor, cursor.fetchone())
            if not endpoint:
                raise ValueError("通知群配置不存在")
            if str(endpoint.get("status")) != "ACTIVE":
                raise ValueError("通知群已停用，请先启用后再测试")
            body = json.dumps(
                _wecom_test_message(
                    str(endpoint.get("endpoint_name") or "企业微信群"),
                    _json_list(endpoint.get("mentioned_user_ids")),
                    _json_list(endpoint.get("mentioned_mobiles")),
                ),
                ensure_ascii=False,
            ).encode("utf-8")
            response = urlrequest.urlopen(
                urlrequest.Request(
                    str(endpoint["webhook_url"]),
                    data=body,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    method="POST",
                ),
                timeout=10,
            )
            result = json.loads(response.read().decode("utf-8"))
            if int(result.get("errcode", -1)) != 0:
                raise ValueError(f"企业微信返回失败：{result.get('errmsg') or result}")
            return {"id": endpoint_id, "success": True, "message": "测试消息发送成功"}
        except (ValueError, PermissionError):
            raise
        except Exception as error:
            if _is_missing_table(error):
                raise MonitoringUnavailable("企业微信通知表尚未创建，请先执行monitoring-wecom-notification-v1.sql") from error
            raise MonitoringUnavailable(f"企业微信测试发送失败：{error}") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def list_message_templates(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        _require(user, "monitor.rule.manage", "当前账号没有通知模板配置权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"SELECT * FROM {self._table(MESSAGE_TEMPLATE_TABLE)} ORDER BY event_code,channel,id"
            )
            rows = []
            for row in _dict_rows(cursor, list(cursor.fetchall())):
                item = _public_row(row)
                item["fieldSchema"] = json.loads(row.get("field_schema_json") or "{}")
                item.pop("fieldSchemaJson", None)
                rows.append(item)
            return rows
        except PermissionError:
            raise
        except Exception as error:
            if _is_missing_table(error):
                raise MonitoringUnavailable("通知模型表尚未创建，请先执行smart-placement-lifecycle-notification-v2.sql") from error
            raise self._unavailable(error, "通知模板查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def update_message_template(
        self, user: dict[str, Any], template_id: int, values: dict[str, Any],
    ) -> dict[str, Any]:
        _require(user, "monitor.rule.manage", "当前账号没有通知模板配置权限")
        title = _clean_text(values.get("titleTemplate"))[:300]
        body = _clean_text(values.get("bodyTemplate"))
        status = _clean_text(values.get("status") or "ACTIVE").upper()
        if not title or not body:
            raise ValueError("消息标题和正文模板不能为空")
        if len(body) > 4000:
            raise ValueError("消息正文模板不能超过4000个字符")
        if status not in ENDPOINT_STATUSES:
            raise ValueError("消息模板状态不支持")
        actor_id = int(user.get("id") or 0)
        actor_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            cursor.execute(
                f"SELECT * FROM {self._table(MESSAGE_TEMPLATE_TABLE)} WHERE id=%s FOR UPDATE",
                (template_id,),
            )
            row = _dict_row(cursor, cursor.fetchone())
            if not row:
                raise ValueError("消息模板不存在")
            schema = json.loads(row.get("field_schema_json") or "{}")
            allowed = {str(item) for item in schema.get("allowedFields") or []}
            placeholders = set(re.findall(r"\{([A-Za-z][A-Za-z0-9_]*)\}", f"{title}\n{body}"))
            invalid = sorted(placeholders - allowed)
            if invalid:
                raise ValueError(f"消息模板包含未授权变量：{','.join(invalid)}")
            cursor.execute(
                f"""UPDATE {self._table(MESSAGE_TEMPLATE_TABLE)}
                    SET title_template=%s,body_template=%s,status=%s,
                        version_no=version_no+1,updated_by_id=%s,
                        updated_by_name=%s,updated_at=%s WHERE id=%s""",
                (title, body, status, actor_id, actor_name, business_now_naive(), template_id),
            )
            connection.commit()
            return {"id": template_id, "versionNo": int(row.get("version_no") or 1) + 1, "status": status}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            raise self._unavailable(error, "通知模板保存失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def create_message_template(
        self, user: dict[str, Any], values: dict[str, Any],
    ) -> dict[str, Any]:
        """Copy a registered event template without widening its event or field contract."""
        _require(user, "monitor.rule.manage", "当前账号没有通知模板配置权限")
        try:
            source_template_id = int(values.get("sourceTemplateId") or 0)
        except Exception as error:
            raise ValueError("请选择基础消息模板") from error
        if source_template_id <= 0:
            raise ValueError("请选择基础消息模板")
        template_name = _clean_text(values.get("templateName"))[:100]
        title = _clean_text(values.get("titleTemplate"))[:300]
        body = _clean_text(values.get("bodyTemplate"))
        status = _clean_text(values.get("status") or "ACTIVE").upper()
        if not template_name:
            raise ValueError("消息模板名称不能为空")
        if not title or not body:
            raise ValueError("消息标题和正文模板不能为空")
        if len(body) > 4000:
            raise ValueError("消息正文模板不能超过4000个字符")
        if status not in ENDPOINT_STATUSES:
            raise ValueError("消息模板状态不支持")
        actor_id = int(user.get("id") or 0)
        actor_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            cursor.execute(
                f"SELECT * FROM {self._table(MESSAGE_TEMPLATE_TABLE)} WHERE id=%s AND status IN ('ACTIVE','DISABLED') FOR UPDATE",
                (source_template_id,),
            )
            source = _dict_row(cursor, cursor.fetchone())
            if not source:
                raise ValueError("基础消息模板不存在")
            schema_text = str(source.get("field_schema_json") or "{}")
            schema = json.loads(schema_text)
            allowed = {str(item) for item in schema.get("allowedFields") or []}
            placeholders = set(re.findall(r"\{([A-Za-z][A-Za-z0-9_]*)\}", f"{title}\n{body}"))
            invalid = sorted(placeholders - allowed)
            if invalid:
                raise ValueError(f"消息模板包含未授权变量：{','.join(invalid)}")
            event_code = str(source.get("event_code") or "").upper()
            channel = str(source.get("channel") or "WECOM").upper()
            template_code = f"CUSTOM_{event_code[:32]}_{uuid.uuid4().hex[:12].upper()}"
            cursor.execute(
                f"""INSERT INTO {self._table(MESSAGE_TEMPLATE_TABLE)} (
                    template_code,template_name,event_code,channel,title_template,body_template,
                    field_schema_json,version_no,status,created_by_id,created_by_name,
                    updated_by_id,updated_by_name,created_at,updated_at
                ) VALUES ({','.join(['%s'] * 15)})""",
                (
                    template_code, template_name, event_code, channel, title, body,
                    schema_text, 1, status, actor_id, actor_name, actor_id, actor_name,
                    business_now_naive(), business_now_naive(),
                ),
            )
            saved_id = int(cursor.lastrowid)
            connection.commit()
            return {
                "id": saved_id, "templateCode": template_code,
                "eventCode": event_code, "status": status,
            }
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            raise self._unavailable(error, "消息模板创建失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def list_notify_routes(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        _require(user, "monitor.rule.manage", "当前账号没有通知路由配置权限")
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            cursor.execute(
                f"""SELECT r.*,t.template_code,t.template_name,e.endpoint_name
                    FROM {self._table(NOTIFY_ROUTE_TABLE)} r
                    JOIN {self._table(MESSAGE_TEMPLATE_TABLE)} t ON t.id=r.template_id
                    LEFT JOIN {self._table(NOTIFY_ENDPOINT_TABLE)} e ON e.id=r.endpoint_id
                    ORDER BY r.event_code,r.priority_no,r.id"""
            )
            return [_public_row(row) for row in _dict_rows(cursor, list(cursor.fetchall()))]
        except PermissionError:
            raise
        except Exception as error:
            if _is_missing_table(error):
                raise MonitoringUnavailable("通知模型表尚未创建，请先执行smart-placement-lifecycle-notification-v2.sql") from error
            raise self._unavailable(error, "通知路由查询失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def save_notify_route(
        self, user: dict[str, Any], values: dict[str, Any], route_id: int | None = None,
    ) -> dict[str, Any]:
        _require(user, "monitor.rule.manage", "当前账号没有通知路由配置权限")
        route_name = _clean_text(values.get("routeName"))[:100]
        event_code = _clean_text(values.get("eventCode")).upper()
        strategy = _clean_text(values.get("recipientStrategy") or "TASK_ASSIGNEE").upper()
        status = _clean_text(values.get("status") or "ACTIVE").upper()
        use_defaults = bool(values.get("useSmartDefaultEndpoints"))
        if event_code == DAILY_SEGMENT_EVENT and (use_defaults or strategy != "NONE"):
            raise ValueError("日累计航段通知必须指定通知群，并选择不动态@人员")
        if not route_name:
            raise ValueError("通知路由名称不能为空")
        if event_code not in NOTIFY_EVENT_CODES:
            raise ValueError("通知事件类型不支持")
        if strategy not in RECIPIENT_STRATEGIES:
            raise ValueError("动态收件人策略不支持")
        if status not in ENDPOINT_STATUSES:
            raise ValueError("通知路由状态不支持")
        try:
            template_id = int(values.get("templateId"))
            endpoint_id = int(values["endpointId"]) if values.get("endpointId") not in (None, "") else None
            priority_no = max(1, min(int(values.get("priorityNo") or 100), 9999))
        except (TypeError, ValueError) as error:
            raise ValueError("通知模板、通知群或优先级格式不正确") from error
        if not endpoint_id and not use_defaults:
            raise ValueError("请选择通知群，或启用全部默认通知群")
        actor_id = int(user.get("id") or 0)
        actor_name = str(user.get("display_name") or user.get("username") or "SYSTEM")[:100]
        current = business_now_naive()
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            cursor.execute(
                f"SELECT id,event_code,channel FROM {self._table(MESSAGE_TEMPLATE_TABLE)} WHERE id=%s AND status='ACTIVE'",
                (template_id,),
            )
            template = _dict_row(cursor, cursor.fetchone())
            if not template or str(template["event_code"]) != event_code or str(template["channel"]) != "WECOM":
                raise ValueError("所选消息模板与事件类型不匹配或已停用")
            if endpoint_id:
                cursor.execute(
                    f"SELECT id FROM {self._table(NOTIFY_ENDPOINT_TABLE)} WHERE id=%s AND channel='WECOM'",
                    (endpoint_id,),
                )
                if not cursor.fetchone():
                    raise ValueError("通知群不存在")
            if route_id:
                cursor.execute(f"SELECT route_code FROM {self._table(NOTIFY_ROUTE_TABLE)} WHERE id=%s FOR UPDATE", (route_id,))
                existing = _dict_row(cursor, cursor.fetchone())
                if not existing:
                    raise ValueError("通知路由不存在")
                cursor.execute(
                    f"""UPDATE {self._table(NOTIFY_ROUTE_TABLE)}
                        SET route_name=%s,event_code=%s,endpoint_id=%s,template_id=%s,
                            recipient_strategy=%s,use_smart_default_endpoints=%s,
                            priority_no=%s,status=%s,updated_by_id=%s,updated_by_name=%s,updated_at=%s
                        WHERE id=%s""",
                    (route_name,event_code,endpoint_id,template_id,strategy,int(use_defaults),priority_no,status,actor_id,actor_name,current,route_id),
                )
                saved_id = route_id
            else:
                route_code = f"NRT-{uuid.uuid4().hex[:16].upper()}"
                cursor.execute(
                    f"""INSERT INTO {self._table(NOTIFY_ROUTE_TABLE)} (
                        route_code,route_name,event_code,channel,endpoint_id,template_id,
                        recipient_strategy,use_smart_default_endpoints,priority_no,status,
                        created_by_id,created_by_name,created_at,updated_by_id,updated_by_name,updated_at
                    ) VALUES ({','.join(['%s'] * 16)})""",
                    (route_code,route_name,event_code,"WECOM",endpoint_id,template_id,strategy,int(use_defaults),priority_no,status,actor_id,actor_name,current,actor_id,actor_name,current),
                )
                saved_id = int(cursor.lastrowid)
            connection.commit()
            return {"id": saved_id, "eventCode": event_code, "status": status}
        except (ValueError, PermissionError):
            if connection is not None: connection.rollback()
            raise
        except Exception as error:
            if connection is not None: connection.rollback()
            raise self._unavailable(error, "通知路由保存失败") from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()
