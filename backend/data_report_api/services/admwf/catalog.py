"""Server-side validation bridges for ADM reference data."""

from decimal import Decimal

from .policy import AdmError, has


class AdmCatalog:
    def __init__(self, config):
        self.config = config

    def _call(self, key, message, *args):
        resolver = self.config.get(key)
        if not callable(resolver):
            raise AdmError(message, 503, "ADM_REFERENCE_UNAVAILABLE")
        result = resolver(*args)
        if not result:
            raise AdmError(message)
        return result

    def _query_one(self, sql, params):
        import pymysql
        try:
            connection = pymysql.connect(
                host=self.config.get("ERP_ROSTER_MYSQL_HOST") or self.config.get("ERP_MYSQL_HOST") or self.config.get("MYSQL_HOST"),
                port=int(self.config.get("ERP_ROSTER_MYSQL_PORT") or self.config.get("ERP_MYSQL_PORT") or self.config.get("MYSQL_PORT", 3306)),
                user=self.config.get("ERP_ROSTER_MYSQL_USER") or self.config.get("ERP_MYSQL_USER") or self.config.get("MYSQL_USER"),
                password=self.config.get("ERP_ROSTER_MYSQL_PASSWORD") or self.config.get("ERP_MYSQL_PASSWORD") or self.config.get("MYSQL_PASSWORD", ""),
                database=self.config.get("ERP_ROSTER_DATABASE") or self.config.get("ERP_MYSQL_DATABASE") or "sibedb",
                charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10, read_timeout=30, write_timeout=30,
            )
            try:
                with connection.cursor() as cursor:
                    cursor.execute(sql, params)
                    return cursor.fetchone()
            finally:
                connection.close()
        except Exception as exc:
            raise AdmError("ADM基础资料暂不可用", 503, "ADM_REFERENCE_UNAVAILABLE") from exc

    def _query_all(self, sql, params):
        import pymysql
        try:
            connection = pymysql.connect(
                host=self.config.get("ERP_ROSTER_MYSQL_HOST") or self.config.get("ERP_MYSQL_HOST") or self.config.get("MYSQL_HOST"),
                port=int(self.config.get("ERP_ROSTER_MYSQL_PORT") or self.config.get("ERP_MYSQL_PORT") or self.config.get("MYSQL_PORT", 3306)),
                user=self.config.get("ERP_ROSTER_MYSQL_USER") or self.config.get("ERP_MYSQL_USER") or self.config.get("MYSQL_USER"),
                password=self.config.get("ERP_ROSTER_MYSQL_PASSWORD") or self.config.get("ERP_MYSQL_PASSWORD") or self.config.get("MYSQL_PASSWORD", ""),
                database=self.config.get("ERP_ROSTER_DATABASE") or self.config.get("ERP_MYSQL_DATABASE") or "sibedb",
                charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10, read_timeout=30, write_timeout=30,
            )
            try:
                with connection.cursor() as cursor:
                    cursor.execute(sql, params)
                    return cursor.fetchall()
            finally:
                connection.close()
        except Exception as exc:
            raise AdmError("ADM基础资料暂不可用", 503, "ADM_REFERENCE_UNAVAILABLE") from exc

    def _hotel_query_all(self, sql, params=()):
        """Read HOTEL-owned reference dictionaries with its dedicated account."""
        import pymysql
        required = ("HOTEL_MYSQL_HOST", "HOTEL_MYSQL_USER", "HOTEL_MYSQL_DATABASE")
        if any(not self.config.get(name) for name in required):
            raise AdmError("ADM差异类型数据源尚未配置", 503, "ADM_REFERENCE_UNAVAILABLE")
        connection = None
        try:
            connection = pymysql.connect(
                host=self.config["HOTEL_MYSQL_HOST"],
                port=int(self.config.get("HOTEL_MYSQL_PORT", 3306)),
                user=self.config["HOTEL_MYSQL_USER"],
                password=self.config.get("HOTEL_MYSQL_PASSWORD", ""),
                database=self.config.get("HOTEL_MYSQL_DATABASE") or "common_prod_db",
                charset=self.config.get("HOTEL_MYSQL_CHARSET") or "utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=int(self.config.get("HOTEL_MYSQL_CONNECT_TIMEOUT", 10)),
                read_timeout=int(self.config.get("HOTEL_MYSQL_READ_TIMEOUT", 60)),
                write_timeout=int(self.config.get("HOTEL_MYSQL_WRITE_TIMEOUT", 60)),
            )
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                return cursor.fetchall()
        except Exception as exc:
            raise AdmError("ADM差异类型参考数据暂不可用", 503, "ADM_REFERENCE_UNAVAILABLE") from exc
        finally:
            if connection is not None:
                connection.close()

    def _difference_type_rows(self):
        rows = self._hotel_query_all(
            "SELECT det_cname FROM common_prod_db.base_com_type_det "
            "WHERE type_code='FI_AMT_DIFF_TYPE' AND det_cname LIKE 'ADM-%' AND status=1"
        )
        return [
            {"code": str(row["det_cname"]).strip(), "name": str(row["det_cname"]).strip()}
            for row in rows if str(row.get("det_cname") or "").strip()
        ]

    @staticmethod
    def _unique(rows, label):
        if len(rows) != 1:
            raise AdmError(f"{label}必须填写唯一有效的编码或名称")
        return {"code": str(rows[0]["code"]), "name": str(rows[0]["name"])}

    def difference_match(self, query):
        """Check one active FI ADM difference order without copying FI business data."""
        resolver = self.config.get("ADMWF_DIFF_MATCH_RESOLVER")
        if callable(resolver):
            return resolver(query)
        required = ("FI_MYSQL_HOST", "FI_MYSQL_USER", "FI_MYSQL_DATABASE")
        if any(not self.config.get(name) for name in required):
            return {
                "resultStatus": "NOT_CONNECTED",
                "matchedKeyType": query["keyType"],
                "matchedKeyValue": query["keyValue"],
                "summary": {"reason": "FI_NOT_CONFIGURED"},
            }
        connection = None
        try:
            import pymysql

            connection = pymysql.connect(
                host=self.config["FI_MYSQL_HOST"],
                port=int(self.config.get("FI_MYSQL_PORT", 3306)),
                user=self.config["FI_MYSQL_USER"],
                password=self.config.get("FI_MYSQL_PASSWORD", ""),
                database=self.config.get("FI_MYSQL_DATABASE") or "ibf_prod_db",
                charset=self.config.get("FI_MYSQL_CHARSET") or "utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=int(self.config.get("FI_MYSQL_CONNECT_TIMEOUT", 10)),
                read_timeout=int(self.config.get("FI_MYSQL_READ_TIMEOUT", 60)),
                write_timeout=int(self.config.get("FI_MYSQL_WRITE_TIMEOUT", 60)),
            )
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
                cursor.execute(
                    "SELECT id,diff_no,diff_date,update_time FROM order_info_diff_reason "
                    "WHERE diff_reason='R01' AND sys_product_type='P1' AND diff_type='D1' "
                    "AND status=1 AND ota_order_no=%s ORDER BY update_time DESC,id DESC LIMIT 1",
                    (query["keyValue"],),
                )
                row = cursor.fetchone()
            if not row:
                return {
                    "resultStatus": "NOT_MATCHED",
                    "matchedKeyType": query["keyType"],
                    "matchedKeyValue": query["keyValue"],
                    "summary": {"source": "ibf_prod_db.order_info_diff_reason"},
                }
            return {
                "resultStatus": query["matchedStatus"],
                "externalRecordId": str(row["id"]),
                "matchedKeyType": query["keyType"],
                "matchedKeyValue": query["keyValue"],
                "summary": {
                    "source": "ibf_prod_db.order_info_diff_reason",
                    "diffNo": row.get("diff_no"),
                    "diffDate": str(row["diff_date"]) if row.get("diff_date") else None,
                    "sourceUpdatedAt": str(row["update_time"]) if row.get("update_time") else None,
                },
            }
        except Exception as exc:
            return {
                "resultStatus": "QUERY_FAILED",
                "matchedKeyType": query["keyType"],
                "matchedKeyValue": query["keyValue"],
                "summary": {"reason": type(exc).__name__},
            }
        finally:
            if connection is not None:
                connection.close()

    def fx(self, currency):
        if str(currency or "").upper() == "CNY":
            return {
                "sourceRecordId": None, "sourceCode": 6, "actualSource": "CNY_IDENTITY",
                "exchangeUnit": 1, "rateValue": Decimal("1"), "sourceUpdatedAt": None,
                "rateField": "central_parity_rate",
            }
        resolver = self.config.get("ADMWF_FX_RESOLVER")
        result = resolver(currency) if callable(resolver) else self._query_one(
            "SELECT id AS sourceRecordId,source AS sourceCode,actual_source AS actualSource,"
            "exchange_unit AS exchangeUnit,central_parity_rate AS rateValue,update_time AS sourceUpdatedAt "
            "FROM sibe_exchange_rate WHERE source=6 AND data_flag=0 AND currency='CNY' "
            "AND exchange_currency=%s ORDER BY update_time DESC,id DESC LIMIT 1", (currency,),
        )
        if not result:
            raise AdmError("找不到该币种的有效历史汇率")
        result["rateField"] = "central_parity_rate"
        required = ("sourceCode", "exchangeUnit", "rateField", "rateValue")
        if any(result.get(key) in (None, "") for key in required):
            raise AdmError("汇率来源返回内容不完整", 503, "ADM_REFERENCE_INVALID")
        if result["rateField"] != "central_parity_rate" or Decimal(str(result["rateValue"])) <= 0:
            raise AdmError("汇率字段或汇率值不符合ADM换算规则", 503, "ADM_REFERENCE_INVALID")
        return result

    def user(self, user_id, *, leader=False):
        result = self._call("ADM_USER_RESOLVER", "所选人员不存在或人员目录不可用", user_id)
        if not result.get("is_enabled", True):
            raise AdmError("所选人员已停用")
        if not has(result, "adm.view") or (leader and not (has(result, "adm.assign_operator") or has(result, "adm.assign"))) or (not leader and not has(result, "adm.handle")):
            raise AdmError("所选人员没有对应的ADM查看和办理权限")
        return {"id": int(result["id"]), "name": str(result.get("display_name") or result.get("username") or result["id"])}

    def user_value(self, value, *, leader=False):
        raw = str(value or "").strip()
        provider = self.config.get("ADM_WORKFLOW_USER_OPTIONS")
        if not raw or not callable(provider):
            raise AdmError("负责组长不存在或人员目录不可用")
        options = provider() or {}
        candidates = options.get("leader" if leader else "handle") or []
        matches = [item for item in candidates if raw in {str(item.get("id") or ""), str(item.get("name") or "")}]
        if len(matches) != 1:
            raise AdmError("负责组长必须填写唯一有效的账号ID或姓名")
        return self.user(matches[0]["id"], leader=leader)

    def department(self, code):
        resolver = self.config.get("ADMWF_DEPARTMENT_RESOLVER")
        result = resolver(code) if callable(resolver) else self._query_one(
            "SELECT org_code AS code,org_cname AS name FROM base_organization "
            "WHERE org_code=%s AND status=1 LIMIT 1", (code,),
        )
        if not result:
            raise AdmError("业务部门不存在或已停用")
        return {"code": str(result["code"]), "name": str(result["name"])}

    def department_value(self, value):
        raw = str(value or "").strip()
        rows = self._query_all(
            "SELECT org_code AS code,org_cname AS name FROM base_organization "
            "WHERE status=1 AND (org_code=%s OR org_cname=%s) LIMIT 2", (raw, raw),
        )
        return self._unique(rows, "业务归属部门")

    def diff_type(self, code):
        resolver = self.config.get("ADMWF_DIFF_TYPE_RESOLVER")
        result = resolver(code) if callable(resolver) else next(
            (row for row in self._difference_type_rows() if row["code"] == str(code or "").strip()),
            None,
        )
        if not result:
            raise AdmError("差异类型不存在或已停用")
        return {"code": str(result["code"]), "name": str(result["name"])}

    def diff_type_value(self, value):
        raw = str(value or "").strip()
        rows = [row for row in self._difference_type_rows() if raw in {row["code"], row["name"]}][:2]
        return self._unique(rows, "差异类型")

    def optional_master(self, kind, code):
        if not code:
            return None
        mapping = {
            "ota": ("ADMWF_OTA_RESOLVER", "OTA不存在或OTA资料不可用"),
            "supplier": ("ADMWF_SUPPLIER_RESOLVER", "供应商不存在或供应商资料不可用"),
        }
        key, message = mapping[kind]
        resolver = self.config.get(key)
        if callable(resolver):
            result = resolver(code)
        elif kind == "ota":
            result = self._query_one(
                "SELECT ota_code AS code,ota_cname AS name FROM sibe_ota "
                "WHERE ota_code=%s AND status=1 LIMIT 1", (code,),
            )
        else:
            result = self._query_one(
                "SELECT supplier_code AS code,supplier_cname AS name FROM sibe_supplier "
                "WHERE supplier_code=%s AND status=1 LIMIT 1", (code,),
            )
        if not result:
            raise AdmError(message)
        return {"code": str(result["code"]), "name": str(result["name"])}

    def optional_master_value(self, kind, value):
        raw = str(value or "").strip()
        if not raw:
            return None
        if kind == "ota":
            rows = self._query_all(
                "SELECT ota_code AS code,ota_cname AS name FROM sibe_ota "
                "WHERE status=1 AND (ota_code=%s OR ota_cname=%s) LIMIT 2", (raw, raw),
            )
            return self._unique(rows, "OTA平台")
        rows = self._query_all(
            "SELECT supplier_code AS code,supplier_cname AS name FROM sibe_supplier "
            "WHERE status=1 AND (supplier_code=%s OR supplier_cname=%s) LIMIT 2", (raw, raw),
        )
        return self._unique(rows, "供应商")

    def options(self, kind, search="", limit=100):
        """Return selectable ADM reference values without trusting client labels."""
        raw = str(search or "").strip()
        size = min(200, max(1, int(limit)))
        escaped = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        if kind == "department":
            return self._query_all(
                "SELECT org_code AS code,org_cname AS name FROM base_organization "
                "WHERE status=1 AND (org_code LIKE %s ESCAPE '\\\\' OR org_cname LIKE %s ESCAPE '\\\\') "
                "ORDER BY org_cname,org_code LIMIT %s", (like, like, size),
            )
        if kind == "diffType":
            needle = raw.casefold()
            rows = self._difference_type_rows()
            return [row for row in rows if not needle or needle in row["name"].casefold()][:size]
        table = {
            "ota": ("sibe_ota", "ota_code", "ota_cname"),
            "supplier": ("sibe_supplier", "supplier_code", "supplier_cname"),
        }.get(kind)
        if table:
            table_name, code_name, display_name = table
            return self._query_all(
                f"SELECT {code_name} AS code,{display_name} AS name FROM {table_name} "
                f"WHERE status=1 AND ({code_name} LIKE %s ESCAPE '\\\\' OR {display_name} LIKE %s ESCAPE '\\\\') "
                f"ORDER BY {display_name},{code_name} LIMIT %s", (like, like, size),
            )
        raise AdmError("不支持的ADM基础资料类型")
