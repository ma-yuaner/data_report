"""Database-backed private/public templates for smart-analysis views."""
from __future__ import annotations

import json
from typing import Any

import pymysql

from .data_source import DataSource


SCOPES = {"dimension-analysis", "detail-fields"}


class SmartViewTemplateService:
    def __init__(self, config: dict[str, Any], source: DataSource | None = None):
        live = dict(config)
        live["DATA_MODE"] = "mysql"
        self.source = source or DataSource(live)
        self.database = self.source.database
        self.table = f"{self.database}.smart_view_template"

    @staticmethod
    def _scope(value: Any) -> str:
        scope = str(value or "").strip()
        if scope not in SCOPES:
            raise ValueError("模板类型不合法")
        return scope

    @staticmethod
    def _payload(values: dict[str, Any]) -> tuple[str, Any, bool]:
        name = str(values.get("name") or "").strip()
        if not name or len(name) > 30:
            raise ValueError("模板名称不能为空且不能超过30个字符")
        config = values.get("value")
        if not isinstance(config, dict):
            raise ValueError("模板配置不合法")
        encoded = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > 100_000:
            raise ValueError("模板配置过大")
        return name, encoded, bool(values.get("isPublic"))

    @staticmethod
    def _public(row: dict[str, Any], user_id: int) -> dict[str, Any]:
        value = row.get("config_json")
        if isinstance(value, str):
            value = json.loads(value)
        return {
            "id": int(row["id"]), "scope": str(row["scope_code"]),
            "name": str(row["template_name"]), "value": value,
            "ownerUserId": int(row["owner_user_id"]),
            "ownerName": str(row.get("owner_name_snapshot") or ""),
            "isOwner": int(row["owner_user_id"]) == user_id,
            "isPublic": bool(row["is_public"]),
            "updatedAt": row["updated_at"].isoformat() if row.get("updated_at") else "",
        }

    def list(self, user: dict[str, Any], scope_value: Any) -> dict[str, Any]:
        scope = self._scope(scope_value)
        user_id = int(user["id"])
        connection = self.source.connect()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    f"""SELECT id,scope_code,template_name,config_json,owner_user_id,
                               owner_name_snapshot,is_public,updated_at
                        FROM {self.table}
                        WHERE scope_code=%s AND (owner_user_id=%s OR is_public=1)
                        ORDER BY (owner_user_id=%s) DESC, is_public ASC, updated_at DESC, id DESC""",
                    (scope, user_id, user_id),
                )
                rows = [self._public(dict(row), user_id) for row in cursor.fetchall()]
            return {"scope": scope, "rows": rows}
        finally:
            connection.close()

    def save(self, user: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        scope = self._scope(values.get("scope"))
        name, config_json, is_public = self._payload(values)
        user_id = int(user["id"])
        owner_name = str(user.get("display_name") or user.get("username") or "")[:100]
        template_id = values.get("id")
        connection = self.source.connect()
        try:
            connection.begin()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                if template_id is not None:
                    cursor.execute(f"SELECT owner_user_id FROM {self.table} WHERE id=%s FOR UPDATE", (int(template_id),))
                    existing = cursor.fetchone()
                    if not existing:
                        raise ValueError("模板不存在")
                    if int(existing["owner_user_id"]) != user_id:
                        raise PermissionError("只能修改自己的模板")
                    cursor.execute(
                        f"""UPDATE {self.table} SET template_name=%s,config_json=%s,is_public=%s,
                                   owner_name_snapshot=%s WHERE id=%s""",
                        (name, config_json, int(is_public), owner_name, int(template_id)),
                    )
                    saved_id = int(template_id)
                else:
                    cursor.execute(
                        f"SELECT id FROM {self.table} WHERE scope_code=%s AND owner_user_id=%s AND template_name=%s FOR UPDATE",
                        (scope, user_id, name),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        saved_id = int(existing["id"])
                        cursor.execute(
                            f"UPDATE {self.table} SET config_json=%s,is_public=%s,owner_name_snapshot=%s WHERE id=%s",
                            (config_json, int(is_public), owner_name, saved_id),
                        )
                    else:
                        cursor.execute(
                            f"""INSERT INTO {self.table}
                                (scope_code,template_name,config_json,owner_user_id,owner_name_snapshot,is_public)
                                VALUES (%s,%s,%s,%s,%s,%s)""",
                            (scope, name, config_json, user_id, owner_name, int(is_public)),
                        )
                        saved_id = int(cursor.lastrowid)
                cursor.execute(
                    f"""SELECT id,scope_code,template_name,config_json,owner_user_id,
                               owner_name_snapshot,is_public,updated_at FROM {self.table} WHERE id=%s""",
                    (saved_id,),
                )
                result = self._public(dict(cursor.fetchone()), user_id)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def delete(self, user: dict[str, Any], template_id: int) -> dict[str, Any]:
        connection = self.source.connect()
        try:
            connection.begin()
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(f"SELECT owner_user_id FROM {self.table} WHERE id=%s FOR UPDATE", (template_id,))
                row = cursor.fetchone()
                if not row:
                    raise ValueError("模板不存在")
                if int(row["owner_user_id"]) != int(user["id"]):
                    raise PermissionError("只能删除自己的模板")
                cursor.execute(f"DELETE FROM {self.table} WHERE id=%s", (template_id,))
            connection.commit()
            return {"id": template_id}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
