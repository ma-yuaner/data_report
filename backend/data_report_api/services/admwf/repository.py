"""Normalized MySQL persistence for ADM workflow.

No legacy ADM tables or aggregate JSON documents are read or written here.
"""

from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import re

from .domain import allocate_cny_amounts
from .policy import PRE_ACCEPT_STATUSES, AdmError, business_now
from .workflow import DIFF_MATCHED, closure_blockers, status_after_approval, validate_submit

# Older rows can carry the pre-assignment status even when a leader is already assigned.
LEADER_ALREADY_ASSIGNED = "(l.line_status='PENDING_LEADER' AND l.leader_id>0 AND COALESCE(l.operator_id,0)=0)"
EFFECTIVE_LINE_STATUS = f"(CASE WHEN {LEADER_ALREADY_ASSIGNED} THEN 'PENDING_OPERATOR' ELSE l.line_status END)"


def _leader_locked(line):
    return line.get("accepted_at") is not None or line["line_status"] not in PRE_ACCEPT_STATUSES


class AdmWorkflowRepository:
    REQUIRED_TABLES = (
        "admwf_case", "admwf_case_line", "admwf_number_sequence",
        "admwf_fx_snapshot", "admwf_operation_log",
    )

    def __init__(self, config, connector=None):
        self.config = config
        self.connector = connector

    def _option(self, name, default=None):
        return self.config.get("ADM_MYSQL_" + name) or self.config.get("MYSQL_" + name, default)

    def _connect(self):
        if self.connector:
            return self.connector()
        import pymysql
        if not self._option("HOST") or not self._option("USER") or not self._option("DATABASE"):
            raise AdmError("ADM数据库尚未配置", 503, "ADM_DATABASE_CONFIG")
        return pymysql.connect(
            host=self._option("HOST"), port=int(self._option("PORT", 3306)),
            user=self._option("USER"), password=self._option("PASSWORD", ""),
            database=self._option("DATABASE"), charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor, autocommit=False,
            connect_timeout=int(self._option("CONNECT_TIMEOUT", 10)),
            read_timeout=int(self._option("READ_TIMEOUT", 60)),
            write_timeout=int(self._option("WRITE_TIMEOUT", 60)),
        )

    @contextmanager
    def transaction(self):
        connection = None
        try:
            connection = self._connect()
            yield connection
            connection.commit()
        except AdmError:
            if connection:
                connection.rollback()
            raise
        except Exception as exc:
            if connection:
                connection.rollback()
            number = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
            mapping = {
                1044: (503, "ADM_DATABASE_PERMISSION", "ADM数据库权限不足"),
                1045: (503, "ADM_DATABASE_AUTH_FAILED", "ADM数据库认证失败"),
                1049: (503, "ADM_DATABASE_NOT_FOUND", "ADM目标数据库不存在"),
                1142: (503, "ADM_DATABASE_PERMISSION", "ADM数据库表权限不足"),
                1146: (503, "ADM_TABLE_MISSING", "ADM正式表尚未建立"),
                2003: (503, "ADM_DATABASE_UNREACHABLE", "ADM数据库无法连接"),
                2013: (503, "ADM_DATABASE_CONNECTION_LOST", "ADM数据库连接中断，请刷新核对结果"),
            }
            status, code, message = mapping.get(number, (500, "ADM_DATABASE_ERROR", "ADM数据库操作失败"))
            raise AdmError(message, status, code) from exc
        finally:
            if connection:
                connection.close()

    def check_schema(self):
        placeholders = ",".join(["%s"] * len(self.REQUIRED_TABLES))
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema=DATABASE() AND table_name IN (" + placeholders + ")",
                self.REQUIRED_TABLES,
            )
            found = {row["table_name"] for row in cursor.fetchall()}
        missing = sorted(set(self.REQUIRED_TABLES) - found)
        if missing:
            raise AdmError("ADM正式表不完整：" + "、".join(missing), 503, "ADM_TABLE_MISSING")

    def mark_due_recoveries(self, batch_size=200):
        now = business_now()
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT r.id,r.case_id,r.line_id,l.version_no FROM admwf_recovery r "
                    "JOIN admwf_case_line l ON l.id=r.line_id "
                    "JOIN admwf_case c ON c.id=r.case_id "
                    "WHERE r.status='WAITING' AND r.remind_at<=%s AND c.case_status='ACTIVE' "
                    "AND l.line_status='PROCESSING' AND l.recovery_status='WAITING' "
                    "ORDER BY r.remind_at,r.id LIMIT %s FOR UPDATE",
                    (now, min(1000, max(1, int(batch_size)))),
                )
                due = cursor.fetchall()
            for item in due:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE admwf_recovery SET status='REMINDER_DUE',updated_at=%s "
                        "WHERE id=%s AND status='WAITING'", (now, item["id"]),
                    )
                    cursor.execute(
                        "UPDATE admwf_case_line SET recovery_status='REMINDER_DUE',updated_at=%s "
                        "WHERE id=%s AND version_no=%s AND recovery_status='WAITING'",
                        (now, item["line_id"], item["version_no"]),
                    )
                self.append_operation_log(
                    connection, case_id=item["case_id"], line_id=item["line_id"],
                    event_no=self._next_event_no(connection, item["case_id"]),
                    event_type="RECOVERY_REMINDER_DUE", operator_id=0, operator_name="系统",
                    before_version=item["version_no"], after_version=item["version_no"],
                    before={"recoveryStatus": "WAITING"}, after={"recoveryStatus": "REMINDER_DUE"},
                    changed_fields=["recoveryStatus"],
                )
            return len(due)

    @staticmethod
    def _number_key(adm_no):
        original = str(adm_no or "").strip()
        if not original:
            raise AdmError("ADM单号不能为空")
        prefix = re.sub(r"[\\/\s:]+", "-", original)
        prefix = re.sub(r"-+", "-", prefix).strip("-")
        if not prefix:
            raise AdmError("ADM单号无法生成内部编号")
        return original, prefix[:100], hashlib.sha256(original.encode("utf-8")).hexdigest()

    def next_internal_no(self, connection, adm_no):
        original, prefix, digest = self._number_key(adm_no)
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    "INSERT INTO admwf_number_sequence"
                    "(adm_no_hash,original_adm_no,normalized_prefix,current_sequence) VALUES(%s,%s,%s,1)",
                    (digest, original, prefix),
                )
                sequence = 1
            except Exception as exc:
                if not exc.args or exc.args[0] != 1062:
                    raise
                cursor.execute(
                    "UPDATE admwf_number_sequence SET current_sequence=current_sequence+1 "
                    "WHERE adm_no_hash=%s", (digest,),
                )
                cursor.execute(
                    "SELECT normalized_prefix,current_sequence FROM admwf_number_sequence "
                    "WHERE adm_no_hash=%s FOR UPDATE", (digest,),
                )
                row = cursor.fetchone()
                prefix, sequence = row["normalized_prefix"], row["current_sequence"]
        return f"{prefix}-{sequence:02d}"

    def create_import_batch(self, batch_no, file_name, file_sha256, actor, *, total_rows,
                            failed_rows, errors):
        now = business_now()
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admwf_import_batch"
                "(batch_no,file_name,file_sha256,template_version,status,total_rows,success_rows,failed_rows,"
                "error_summary_json,imported_by_id,imported_by_name,previewed_at,created_at,updated_at) "
                "VALUES(%s,%s,%s,'DAILY19_V1','PREVIEWED',%s,0,%s,%s,%s,%s,%s,%s,%s)",
                (batch_no, file_name, file_sha256, total_rows, failed_rows,
                 json.dumps(errors, ensure_ascii=False, separators=(",", ":")) if errors else None,
                 actor["id"], actor["name"], now, now, now),
            )
            return cursor.lastrowid

    def get_import_batch(self, batch_no):
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM admwf_import_batch WHERE batch_no=%s", (batch_no,))
            return cursor.fetchone()

    def claim_import_batch(self, batch_id):
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE admwf_import_batch SET status='COMMITTING',updated_at=%s "
                "WHERE id=%s AND status IN ('PREVIEWED','FAILED')",
                (business_now(), batch_id),
            )
            if cursor.rowcount != 1:
                raise AdmError("导入批次已提交或正在处理", 409, "ADM_IMPORT_STATE")

    def finish_import_batch(self, batch_id, *, status, success_rows, failed_rows, errors=None):
        if status not in {"COMMITTED", "FAILED"}:
            raise AdmError("导入批次结果无效")
        now = business_now()
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE admwf_import_batch SET status=%s,success_rows=%s,failed_rows=%s,error_summary_json=%s,"
                "committed_at=%s,updated_at=%s WHERE id=%s AND status='COMMITTING'",
                (status, success_rows, failed_rows,
                 json.dumps(errors, ensure_ascii=False, separators=(",", ":")) if errors else None,
                 now if status == "COMMITTED" else None, now, batch_id),
            )
            if cursor.rowcount != 1:
                raise AdmError("导入批次状态已变更", 409, "ADM_IMPORT_STATE")

    def create_case(self, data, fx, actor, *, source_type="MANUAL", idempotency_key=None,
                    import_batch_id=None, case_status="ACTIVE"):
        """Create a balanced case, lines, FX snapshot, leader assignments and audit atomically."""
        with self.transaction() as connection:
            if idempotency_key:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT id FROM admwf_case WHERE idempotency_key=%s", (idempotency_key,))
                    existing = cursor.fetchone()
                if existing:
                    return self.get_case(existing["id"], connection=connection)
            internal_no = self.next_internal_no(connection, data["admNo"])
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO admwf_case"
                    "(internal_no,adm_no,issuer_type,issuer_code,issuer_name,currency,original_amount,cny_amount,"
                    "issued_date,reply_deadline,remark,coordinator_id,coordinator_name,case_status,source_type,"
                    "import_batch_id,idempotency_key,version_no,created_by_id,created_by_name,created_at,"
                    "updated_by_id,updated_by_name,updated_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s)",
                    (internal_no, data["admNo"], data["issuerType"], data["issuerCode"], data["issuerName"],
                     data["currency"], data["originalAmount"], data["cnyAmount"], data["issuedDate"],
                     data["replyDeadline"], data["remark"], actor["id"], actor["name"], case_status, source_type,
                     import_batch_id, idempotency_key, actor["id"], actor["name"], now,
                     actor["id"], actor["name"], now),
                )
                case_id = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO admwf_fx_snapshot"
                    "(case_id,source_record_id,source_code,actual_source,currency,exchange_currency,exchange_unit,"
                    "rate_field,rate_value,source_updated_at,formula,frozen_by_id,frozen_by_name,frozen_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (case_id, fx.get("sourceRecordId"), fx["sourceCode"], fx.get("actualSource"),
                     data["currency"], "CNY", fx["exchangeUnit"], fx["rateField"], fx["rateValue"],
                     fx.get("sourceUpdatedAt"), "人民币金额=原币金额×central_parity_rate",
                     actor["id"], actor["name"], now),
                )
                line_ids = []
                for number, line in enumerate(data["lines"], 1):
                    line_internal_no = f"{internal_no}-{number:03d}"
                    cursor.execute(
                        "INSERT INTO admwf_case_line"
                        "(case_id,line_internal_no,line_no,ota_code,ota_name,ota_order_no,supplier_code,supplier_name,"
                        "airline_code,airline_name,ticket_no,pnr,currency,original_amount,cny_amount,department_code,"
                        "department_name,diff_type_code,diff_type_name,difference_reason,investigation_note,leader_id,"
                        "leader_name,process_deadline,line_status,version_no,created_by_id,created_by_name,created_at,"
                        "updated_by_id,updated_by_name,updated_at) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                        "'PENDING_OPERATOR',1,%s,%s,%s,%s,%s,%s)",
                        (case_id, line_internal_no, number, line["otaCode"], line["otaName"], line["otaOrderNo"],
                         line["supplierCode"], line["supplierName"], line["airlineCode"], line["airlineName"],
                         line["ticketNo"], line["pnr"], data["currency"], line["originalAmount"], line["cnyAmount"],
                         line["departmentCode"], line["departmentName"], line["diffTypeCode"], line["diffTypeName"],
                         line["differenceReason"], line["investigationNote"], line["leaderId"], line["leaderName"],
                         data["replyDeadline"], actor["id"], actor["name"], now, actor["id"], actor["name"], now),
                    )
                    line_id = cursor.lastrowid
                    line_ids.append(line_id)
                    cursor.execute(
                        "INSERT INTO admwf_assignment"
                        "(case_id,line_id,assignment_type,to_user_id,to_user_name,assignment_reason,assigned_by_id,"
                        "assigned_by_name,assigned_at,effective_status,created_at) "
                        "VALUES(%s,%s,'LEADER',%s,%s,'建单指定负责组长',%s,%s,%s,'EFFECTIVE',%s)",
                        (case_id, line_id, line["leaderId"], line["leaderName"], actor["id"], actor["name"], now, now),
                    )
            self.append_operation_log(
                connection, case_id=case_id, line_id=None, event_no=1, event_type="CREATE_CASE",
                operator_id=actor["id"], operator_name=actor["name"],
                operation_source={"MANUAL": "WEB", "EXCEL": "EXCEL", "LEGACY": "MIGRATION"}[source_type],
                after_version=1, after={"internalNo": internal_no, "lineIds": line_ids, "caseStatus": case_status},
                changed_fields=["case", "lines", "fxSnapshot"],
            )
            return self.get_case(case_id, connection=connection)

    def publish_draft(self, case_id, actor):
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM admwf_case WHERE id=%s FOR UPDATE", (case_id,))
                case = cursor.fetchone()
                if not case:
                    raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
                if case["case_status"] != "DRAFT":
                    raise AdmError("只有草稿可以发布", 409, "ADM_ACTION_BLOCKED")
                now = business_now()
                cursor.execute(
                    "UPDATE admwf_case SET case_status='ACTIVE',version_no=version_no+1,updated_by_id=%s,"
                    "updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (actor["id"], actor["name"], now, case_id, case["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("草稿已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            self.append_operation_log(
                connection, case_id=case_id, line_id=None,
                event_no=self._next_event_no(connection, case_id), event_type="PUBLISH_DRAFT",
                operator_id=actor["id"], operator_name=actor["name"],
                before_version=case["version_no"], after_version=case["version_no"] + 1,
                before={"caseStatus": "DRAFT"}, after={"caseStatus": "ACTIVE"},
                changed_fields=["caseStatus"],
            )
            return self.get_case(case_id, connection=connection)

    def delete_draft(self, case_id, actor, reason):
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM admwf_case WHERE id=%s FOR UPDATE", (case_id,))
                case = cursor.fetchone()
                if not case:
                    raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
                if case["case_status"] != "DRAFT":
                    raise AdmError("只有草稿可以软删除", 409, "ADM_ACTION_BLOCKED")
                now = business_now()
                cursor.execute(
                    "UPDATE admwf_case SET case_status='DELETED',deleted_by_id=%s,deleted_by_name=%s,"
                    "deleted_at=%s,delete_reason=%s,version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,"
                    "updated_at=%s WHERE id=%s AND version_no=%s",
                    (actor["id"], actor["name"], now, reason, actor["id"], actor["name"], now,
                     case_id, case["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("草稿已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            self.append_operation_log(
                connection, case_id=case_id, line_id=None,
                event_no=self._next_event_no(connection, case_id), event_type="DELETE_DRAFT",
                operator_id=actor["id"], operator_name=actor["name"], note=reason,
                before_version=case["version_no"], after_version=case["version_no"] + 1,
                before={"caseStatus": "DRAFT"}, after={"caseStatus": "DELETED"},
                changed_fields=["caseStatus", "deleteReason"],
            )
            return self.get_case(case_id, connection=connection)

    def get_case(self, case_id, *, connection=None):
        if connection is None:
            with self.transaction() as managed:
                return self.get_case(case_id, connection=managed)
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM admwf_case WHERE id=%s", (case_id,))
            case = cursor.fetchone()
            if not case:
                return None
            legacy_source = self._load_legacy_source(cursor, case)
            cursor.execute("SELECT * FROM admwf_case_line WHERE case_id=%s ORDER BY line_no", (case_id,))
            lines = cursor.fetchall()
            cursor.execute("SELECT * FROM admwf_fx_snapshot WHERE case_id=%s", (case_id,))
            fx = cursor.fetchone()
            cursor.execute(
                "SELECT * FROM admwf_diff_match WHERE case_id=%s ORDER BY line_id,check_no", (case_id,),
            )
            diff_matches = cursor.fetchall()
            cursor.execute(
                "SELECT * FROM admwf_collection WHERE case_id=%s ORDER BY line_id,collection_no", (case_id,),
            )
            collections = cursor.fetchall()
            cursor.execute(
                "SELECT * FROM admwf_transfer WHERE case_id=%s ORDER BY requested_at,id", (case_id,),
            )
            transfers = cursor.fetchall()
            cursor.execute(
                "SELECT * FROM admwf_attachment WHERE case_id=%s ORDER BY uploaded_at,id", (case_id,),
            )
            attachments = cursor.fetchall()
            histories = {}
            for key, table, order_by in (
                ("assignments", "admwf_assignment", "line_id,assigned_at,id"),
                ("responsibilitySegments", "admwf_responsibility_segment", "line_id,started_at,id"),
                ("recoveries", "admwf_recovery", "line_id,recovery_no"),
                ("appeals", "admwf_appeal", "line_id,round_no"),
                ("reviews", "admwf_review", "line_id,review_no"),
                ("operationLogs", "admwf_operation_log", "event_no,id"),
            ):
                cursor.execute(f"SELECT * FROM {table} WHERE case_id=%s ORDER BY {order_by}", (case_id,))
                histories[key] = cursor.fetchall()
        return {
            "case": case, "lines": [self._effective_line(line) for line in lines], "fxSnapshot": fx,
            "legacySource": legacy_source,
            "diffMatches": diff_matches, "collections": collections, "transfers": transfers,
            "attachments": attachments, **histories,
        }

    @staticmethod
    def _effective_line(line):
        if line["line_status"] == "PENDING_LEADER" and line.get("leader_id") and not line.get("operator_id"):
            return {**line, "line_status": "PENDING_OPERATOR"}
        return line

    def get_case_summary(self, case_id):
        """Load only the records needed to paint the detail page shell."""
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM admwf_case WHERE id=%s", (case_id,))
            case = cursor.fetchone()
            if not case:
                return None
            legacy_source = self._load_legacy_source(cursor, case)
            cursor.execute("SELECT * FROM admwf_case_line WHERE case_id=%s ORDER BY line_no", (case_id,))
            lines = cursor.fetchall()
            cursor.execute("SELECT * FROM admwf_fx_snapshot WHERE case_id=%s", (case_id,))
            fx = cursor.fetchone()
        return {
            "case": case, "lines": [self._effective_line(line) for line in lines], "fxSnapshot": fx,
            "legacySource": legacy_source,
            "diffMatches": [], "collections": [], "transfers": [], "attachments": [],
            "assignments": [], "responsibilitySegments": [], "recoveries": [],
            "appeals": [], "reviews": [], "operationLogs": [],
        }

    @staticmethod
    def _load_legacy_source(cursor, case):
        """Load the original archived row only for one LEGACY detail request."""
        if str(case.get("source_type") or "").upper() != "LEGACY":
            return None
        cursor.execute(
            "SELECT m.source_system,m.source_table,m.source_record_id,b.batch_no AS migration_batch_no,"
            "m.source_adm_status,m.source_record_status,m.migration_mode,m.source_owner_text,"
            "m.source_handler_text,m.source_payload_json,m.source_row_hash,m.mapping_status,"
            "m.quality_note,m.migrated_at "
            "FROM admwf_legacy_mapping m "
            "LEFT JOIN admwf_migration_batch b ON b.id=m.migration_batch_id "
            "WHERE m.target_case_id=%s ORDER BY m.id LIMIT 1",
            (case["id"],),
        )
        source = cursor.fetchone()
        if not source:
            return None
        payload = source.get("source_payload_json")
        if isinstance(payload, (str, bytes, bytearray)):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError):
                payload = None
        source["source_payload"] = payload
        source.pop("source_payload_json", None)
        return source

    def update_case_basic(self, case_id, data, actor):
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM admwf_case WHERE id=%s FOR UPDATE", (case_id,))
                case = cursor.fetchone()
                if not case:
                    raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
                if case["case_status"] not in {"DRAFT", "ACTIVE"}:
                    raise AdmError("当前主单状态只允许查看基础信息", 409, "ADM_ACTION_BLOCKED")
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM admwf_case_line WHERE case_id=%s "
                    "AND (review_status='APPROVED' OR line_status='COMPLETED')",
                    (case_id,),
                )
                if int(cursor.fetchone()["total"]):
                    raise AdmError(
                        "主单已有订单审核通过或已完结，基础信息已锁定；特殊情况请先由ADM负责人撤回审核",
                        409, "ADM_REVIEWED_READ_ONLY",
                    )
                now = business_now()
                cursor.execute(
                    "UPDATE admwf_case SET adm_no=%s,issuer_type=%s,issuer_code=%s,issuer_name=%s,"
                    "issued_date=%s,reply_deadline=%s,remark=%s,version_no=version_no+1,updated_by_id=%s,"
                    "updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (data["admNo"], data["issuerType"], data["issuerCode"], data["issuerName"],
                     data["issuedDate"], data["replyDeadline"], data["remark"], actor["id"], actor["name"],
                     now, case_id, case["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("主单已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
                if case["reply_deadline"] != data["replyDeadline"]:
                    cursor.execute(
                        "UPDATE admwf_case_line SET process_deadline=%s,version_no=version_no+1,updated_by_id=%s,"
                        "updated_by_name=%s,updated_at=%s WHERE case_id=%s AND line_status NOT IN ('VOIDED','HISTORICAL')",
                        (data["replyDeadline"], actor["id"], actor["name"], now, case_id),
                    )
            before = {
                "admNo": case["adm_no"], "issuerType": case["issuer_type"],
                "issuerCode": case["issuer_code"], "issuerName": case["issuer_name"],
                "issuedDate": str(case["issued_date"]), "replyDeadline": str(case["reply_deadline"]),
                "remark": case["remark"],
            }
            after = {
                "admNo": data["admNo"], "issuerType": data["issuerType"],
                "issuerCode": data["issuerCode"], "issuerName": data["issuerName"],
                "issuedDate": str(data["issuedDate"]), "replyDeadline": str(data["replyDeadline"]),
                "remark": data["remark"],
            }
            changed = [key for key in after if before.get(key) != after.get(key)]
            self.append_operation_log(
                connection, case_id=case_id, line_id=None,
                event_no=self._next_event_no(connection, case_id), event_type="UPDATE_CASE_BASIC_INFO",
                operator_id=actor["id"], operator_name=actor["name"],
                before_version=case["version_no"], after_version=case["version_no"] + 1,
                before=before, after=after, changed_fields=changed,
            )
            return self.get_case(case_id, connection=connection)

    def update_line_basic(self, case_id, line_id, data, actor):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if line["line_status"] == "COMPLETED":
                raise AdmError("该订单已完结，不能直接修改；特殊情况请由ADM负责人发起受控更正", 409, "ADM_COMPLETED_READ_ONLY")
            if line.get("review_status") == "APPROVED":
                raise AdmError("该订单已审核通过，不能直接修改；如需更正，请由ADM负责人先撤回审核", 409, "ADM_REVIEWED_READ_ONLY")
            if case["case_status"] not in {"DRAFT", "ACTIVE"} or line["line_status"] in {"HISTORICAL", "VOIDED"}:
                raise AdmError("当前订单状态只允许查看基础信息", 409, "ADM_ACTION_BLOCKED")
            next_status = "PENDING_OPERATOR" if line["line_status"] == "PENDING_LEADER" else line["line_status"]
            now = business_now()
            with connection.cursor() as cursor:
                if line["leader_id"] != data["leaderId"]:
                    if _leader_locked(line):
                        raise AdmError("操作员已接单，不能更换组长", 409, "ADM_LEADER_LOCKED")
                    cursor.execute(
                        "UPDATE admwf_assignment SET effective_status='ENDED',ended_at=%s "
                        "WHERE line_id=%s AND assignment_type='LEADER' AND effective_status='EFFECTIVE'",
                        (now, line_id),
                    )
                    cursor.execute(
                        "INSERT INTO admwf_assignment"
                        "(case_id,line_id,assignment_type,from_user_id,from_user_name,to_user_id,to_user_name,"
                        "assignment_reason,assigned_by_id,assigned_by_name,assigned_at,effective_status,created_at) "
                        "VALUES(%s,%s,'LEADER',%s,%s,%s,%s,'编辑订单基础信息',%s,%s,%s,'EFFECTIVE',%s)",
                        (case_id, line_id, line["leader_id"], line["leader_name"], data["leaderId"],
                         data["leaderName"], actor["id"], actor["name"], now, now),
                    )
                cursor.execute(
                    "UPDATE admwf_case_line SET ota_code=%s,ota_name=%s,ota_order_no=%s,supplier_code=%s,"
                    "supplier_name=%s,airline_code=%s,airline_name=%s,ticket_no=%s,pnr=%s,department_code=%s,"
                    "department_name=%s,diff_type_code=%s,diff_type_name=%s,difference_reason=%s,"
                    "investigation_note=%s,leader_id=%s,leader_name=%s,line_status=%s,version_no=version_no+1,updated_by_id=%s,"
                    "updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (data["otaCode"], data["otaName"], data["otaOrderNo"], data["supplierCode"],
                     data["supplierName"], data["airlineCode"], data["airlineName"], data["ticketNo"],
                     data["pnr"], data["departmentCode"], data["departmentName"], data["diffTypeCode"],
                     data["diffTypeName"], data["differenceReason"], data["investigationNote"], data["leaderId"],
                     data["leaderName"], next_status, actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            fields = {
                "otaCode": "ota_code", "otaName": "ota_name", "otaOrderNo": "ota_order_no",
                "supplierCode": "supplier_code", "supplierName": "supplier_name",
                "airlineCode": "airline_code", "airlineName": "airline_name", "ticketNo": "ticket_no",
                "pnr": "pnr", "departmentCode": "department_code", "departmentName": "department_name",
                "diffTypeCode": "diff_type_code", "diffTypeName": "diff_type_name",
                "differenceReason": "difference_reason", "investigationNote": "investigation_note",
                "leaderId": "leader_id", "leaderName": "leader_name",
            }
            before = {key: line[column] for key, column in fields.items()}
            after = {key: data[key] for key in fields}
            changed = [key for key in fields if before.get(key) != after.get(key)]
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="UPDATE_LINE_BASIC_INFO",
                operator_id=actor["id"], operator_name=actor["name"],
                from_status=line["line_status"], to_status=next_status,
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                before=before, after=after, changed_fields=changed,
            )
            return self.get_case(case_id, connection=connection)

    @staticmethod
    def _ledger_scope(filters):
        where, values = ["1=1"], []
        if filters.get("status"):
            where.append("c.case_status=%s")
            values.append(filters["status"])
        else:
            where.append("c.case_status<>'DELETED'")
        if filters.get("activeOnly"):
            where.append("c.case_status='ACTIVE'")
        if filters.get("coordinatorId"):
            where.append("c.coordinator_id=%s")
            values.append(filters["coordinatorId"])
        if filters.get("search"):
            term = str(filters["search"]).strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("(c.internal_no LIKE %s ESCAPE '\\\\' OR c.adm_no LIKE %s ESCAPE '\\\\' OR c.issuer_name LIKE %s ESCAPE '\\\\')")
            values.extend([f"%{term}%"] * 3)
        if filters.get("sourceType"):
            where.append("c.source_type=%s")
            values.append(filters["sourceType"])
        return " AND ".join(where), values

    @staticmethod
    def _ledger_metrics(current):
        active = "c.case_status IN ('DRAFT','ACTIVE')"
        pending = "l.line_status IN ('PENDING_LEADER','PENDING_OPERATOR','PENDING_ACCEPT')"
        open_line = "l.line_status NOT IN ('COMPLETED','VOIDED','HISTORICAL')"
        soon = f"{active} AND c.reply_deadline>=%s AND c.reply_deadline<%s"
        late = f"{active} AND c.reply_deadline<%s"
        window = (current, current + timedelta(days=1))
        return {
            "pending": (
                ("c.case_status='DRAFT' OR EXISTS (SELECT 1 FROM admwf_case_line l WHERE l.case_id=c.id AND " + pending + ")", ()),
                (pending, ()),
            ),
            "open": ((active, ()), (open_line, ())),
            "soon": ((soon, window), (f"{soon} AND {open_line}", window)),
            "late": ((late, (current,)), (f"{late} AND {open_line}", (current,))),
        }

    def list_cases(self, filters, page, page_size):
        clause, values = self._ledger_scope(filters)
        metrics = self._ledger_metrics(business_now())
        metric = filters.get("metric")
        page_clause, page_values = clause, tuple(values)
        if metric in metrics:
            predicate, params = metrics[metric][0]
            page_clause += f" AND ({predicate})"
            page_values += params
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.*,COUNT(l.id) AS line_count,"
                "SUM(CASE WHEN l.line_status='COMPLETED' THEN 1 ELSE 0 END) AS completed_line_count,"
                "SUM(CASE WHEN l.line_status='VOIDED' THEN 1 ELSE 0 END) AS voided_line_count,"
                "SUM(CASE WHEN l.line_status='HISTORICAL' THEN 1 ELSE 0 END) AS historical_line_count,"
                f"SUM(CASE WHEN {EFFECTIVE_LINE_STATUS}='PENDING_LEADER' THEN 1 ELSE 0 END) AS pending_leader_count,"
                f"SUM(CASE WHEN {EFFECTIVE_LINE_STATUS}='PENDING_OPERATOR' THEN 1 ELSE 0 END) AS pending_operator_count,"
                "SUM(CASE WHEN l.line_status='PENDING_ACCEPT' THEN 1 ELSE 0 END) AS pending_accept_count,"
                "SUM(CASE WHEN l.line_status='PROCESSING' THEN 1 ELSE 0 END) AS processing_count,"
                "SUM(CASE WHEN l.line_status='PENDING_REVIEW' THEN 1 ELSE 0 END) AS pending_review_count,"
                "SUM(CASE WHEN l.line_status='WAITING_DIFF' THEN 1 ELSE 0 END) AS waiting_diff_count,"
                "SUM(CASE WHEN l.line_status='WAITING_COLLECTION' THEN 1 ELSE 0 END) AS waiting_collection_count "
                "FROM (SELECT c.id FROM admwf_case c WHERE " + page_clause + " "
                "ORDER BY c.updated_at DESC,c.id DESC LIMIT %s OFFSET %s) page_ids "
                "JOIN admwf_case c ON c.id=page_ids.id "
                "LEFT JOIN admwf_case_line l ON l.case_id=c.id "
                "GROUP BY c.id ORDER BY c.updated_at DESC,c.id DESC",
                (*page_values, page_size, (page - 1) * page_size),
            )
            items = cursor.fetchall()
            columns = ["COUNT(DISTINCT c.id) AS case_count", "COUNT(l.id) AS line_count"]
            params = []
            for key, ((case_predicate, case_params), (line_predicate, line_params)) in metrics.items():
                name = "overdue" if key == "late" else key
                if key == "pending":
                    case_predicate = f"c.case_status='DRAFT' OR {line_predicate}"
                columns.extend([
                    f"COUNT(DISTINCT CASE WHEN {case_predicate} THEN c.id END) AS {name}_case_count",
                    f"COUNT(CASE WHEN {line_predicate} THEN l.id END) AS {name}_line_count",
                ])
                params.extend((*case_params, *line_params))
            cursor.execute(
                "SELECT " + ",".join(columns) +
                " FROM admwf_case c LEFT JOIN admwf_case_line l ON l.case_id=c.id WHERE " + clause,
                (*params, *values),
            )
            summary = cursor.fetchone() or {}
        count_prefix = ("overdue" if metric == "late" else metric) if metric in metrics else None
        total_key = f"{count_prefix}_case_count" if count_prefix else "case_count"
        return {
            "items": items,
            "pagination": {"page": page, "pageSize": page_size, "total": int(summary.get(total_key, 0))},
            "summary": summary,
        }

    def list_ledger_lines(self, filters, page, page_size):
        clause, values = self._ledger_scope(filters)
        metrics = self._ledger_metrics(business_now())
        metric = filters.get("metric")
        if metric in metrics:
            predicate, params = metrics[metric][1]
            clause += f" AND ({predicate})"
            values.extend(params)
        source = " FROM admwf_case c JOIN admwf_case_line l ON l.case_id=c.id WHERE " + clause
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total" + source, values)
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT c.id AS case_id,c.adm_no,l.id,l.line_internal_no,l.ticket_no,l.ota_order_no,"
                f"l.pnr,l.department_name,l.leader_name,l.operator_name,{EFFECTIVE_LINE_STATUS} AS line_status" + source +
                " ORDER BY c.updated_at DESC,c.id DESC,l.line_no,l.id LIMIT %s OFFSET %s",
                (*values, page_size, (page - 1) * page_size),
            )
            items = cursor.fetchall()
        return {"items": items, "pagination": {"page": page, "pageSize": page_size, "total": total}}

    @staticmethod
    def _workbench_scope(actor_id, capabilities):
        conditions, values = [], []
        owner_statuses = []
        if capabilities.get("assignLeader"):
            owner_statuses.append("PENDING_LEADER")
        if capabilities.get("review"):
            owner_statuses.append("PENDING_REVIEW")
        if capabilities.get("diffMatch"):
            owner_statuses.append("WAITING_DIFF")
        if capabilities.get("collection"):
            owner_statuses.append("WAITING_COLLECTION")
        if owner_statuses:
            conditions.append(
                f"(c.coordinator_id=%s AND {EFFECTIVE_LINE_STATUS} IN (" + ",".join(["%s"] * len(owner_statuses)) + "))"
            )
            values.extend([actor_id, *owner_statuses])
        if capabilities.get("assignOperator"):
            conditions.append(f"(l.leader_id=%s AND {EFFECTIVE_LINE_STATUS}='PENDING_OPERATOR')")
            values.append(actor_id)
        if capabilities.get("handle"):
            conditions.append("(l.operator_id=%s AND l.line_status IN ('PENDING_ACCEPT','PROCESSING'))")
            values.append(actor_id)
        return conditions, values

    @staticmethod
    def _closable_case_source():
        return (
            " FROM admwf_case c WHERE c.case_status='ACTIVE' AND c.coordinator_id=%s "
            "AND EXISTS (SELECT 1 FROM admwf_case_line l WHERE l.case_id=c.id) "
            "AND NOT EXISTS (SELECT 1 FROM admwf_case_line l WHERE l.case_id=c.id "
            "AND l.line_status NOT IN ('COMPLETED','VOIDED','HISTORICAL'))"
        )

    @staticmethod
    def _transfer_queue_source(actor_id, capabilities, pending_only):
        scopes, values = [], []
        if capabilities.get("assignOperator"):
            scopes.append("t.requested_by_id=%s")
            values.append(actor_id)
        if capabilities.get("handle"):
            scopes.append("(t.from_operator_id=%s OR t.to_operator_id=%s)")
            values.extend((actor_id, actor_id))
        if not scopes:
            raise AdmError("没有查看转派记录的权限", 403, "ADM_FORBIDDEN")
        source = (
            " FROM admwf_transfer t JOIN admwf_case c ON c.id=t.case_id "
            "JOIN admwf_case_line l ON l.id=t.line_id AND l.case_id=c.id "
            "WHERE (" + " OR ".join(scopes) + ")"
        )
        if pending_only:
            source += " AND t.status='PENDING'"
        return source, values

    def list_workbench_queue(self, actor_id, capabilities, queue, page, page_size, *, pending_only=True):
        if queue == "close":
            if not capabilities.get("close"):
                raise AdmError("没有查看待结案主单的权限", 403, "ADM_FORBIDDEN")
            source, values = self._closable_case_source(), (actor_id,)
            fields = "c.id AS case_id,c.adm_no,c.internal_no,c.reply_deadline,c.updated_at"
            order = "c.updated_at DESC,c.id DESC"
        else:
            source, values = self._transfer_queue_source(actor_id, capabilities, pending_only)
            fields = (
                "t.id AS transfer_id,c.id AS case_id,c.adm_no,c.internal_no,l.id AS line_id,l.line_internal_no,"
                "t.status AS transfer_status,t.requested_at,t.requested_by_name,t.from_operator_name,"
                "t.to_operator_name,t.decided_at,t.decided_by_name,t.decision_reason,"
                "CASE WHEN t.status='PENDING' AND c.case_status='ACTIVE' AND l.line_status='PROCESSING' "
                "AND l.operator_id=t.from_operator_id THEN 1 ELSE 0 END AS actionable"
            )
            order = "t.requested_at DESC,t.id DESC"
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total" + source, values)
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT " + fields + source + " ORDER BY " + order + " LIMIT %s OFFSET %s",
                (*values, page_size, (page - 1) * page_size),
            )
            items = cursor.fetchall()
        return {"items": items, "pagination": {"page": page, "pageSize": page_size, "total": total}}

    def list_workbench(self, actor_id, capabilities, is_admin=False, limit=1000):
        # The workbench is always personal. System administrators may inspect the full
        # ledger, but must not inherit other coordinators' or assignees' task queues.
        conditions, values = self._workbench_scope(actor_id, capabilities)
        task_clause = "c.case_status='ACTIVE' AND (" + (" OR ".join(conditions) or "1=0") + ")"
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.id AS case_id,l.id AS line_id,l.operator_id,c.adm_no,c.internal_no,l.line_internal_no,"
                f"{EFFECTIVE_LINE_STATUS} AS line_status,l.recovery_status,l.appeal_status,l.review_status,l.department_name,l.leader_name,l.operator_name,"
                "c.reply_deadline,c.coordinator_id,NULL AS task_type,NULL AS transfer_id,"
                "(SELECT rv.result FROM admwf_review rv WHERE rv.line_id=l.id "
                " ORDER BY rv.review_no DESC LIMIT 1) AS latest_review_status,"
                "(SELECT rv.return_reason FROM admwf_review rv WHERE rv.line_id=l.id "
                " ORDER BY rv.review_no DESC LIMIT 1) AS latest_review_return_reason "
                "FROM admwf_case c JOIN admwf_case_line l ON l.case_id=c.id WHERE " + task_clause + " "
                "ORDER BY CASE WHEN c.reply_deadline IS NULL THEN 1 ELSE 0 END,c.reply_deadline,c.id,l.id LIMIT %s",
                (*values, max(1, min(int(limit), 1000))),
            )
            items = cursor.fetchall()
            if capabilities.get("handle"):
                cursor.execute(
                    "SELECT c.id AS case_id,l.id AS line_id,l.operator_id,c.adm_no,c.internal_no,l.line_internal_no,"
                    "l.line_status,l.recovery_status,l.appeal_status,l.department_name,l.leader_name,l.operator_name,"
                    "c.reply_deadline,c.coordinator_id,'TRANSFER_ACCEPT' AS task_type,t.id AS transfer_id,"
                    "t.from_operator_name,t.to_operator_name,t.handover_note "
                    "FROM admwf_transfer t JOIN admwf_case c ON c.id=t.case_id "
                    "JOIN admwf_case_line l ON l.id=t.line_id "
                    "WHERE t.status='PENDING' AND t.to_operator_id=%s AND c.case_status='ACTIVE' "
                    "AND l.line_status='PROCESSING' AND l.operator_id=t.from_operator_id "
                    "ORDER BY t.requested_at,t.id LIMIT %s",
                    (actor_id, max(1, min(int(limit), 1000))),
                )
                items.extend(cursor.fetchall())
            cursor.execute(
                "SELECT COUNT(*) AS total FROM admwf_case c JOIN admwf_case_line l ON l.case_id=c.id WHERE " + task_clause,
                values,
            )
            total = int(cursor.fetchone()["total"]) + sum(
                1 for item in items if item.get("task_type") == "TRANSFER_ACCEPT"
            )
            closable = 0
            if capabilities.get("close"):
                cursor.execute("SELECT COUNT(*) AS total" + self._closable_case_source(), (actor_id,))
                closable = int(cursor.fetchone()["total"])
            pending_transfers = 0
            if capabilities.get("assignOperator") or capabilities.get("handle"):
                source, params = self._transfer_queue_source(actor_id, capabilities, pending_only=True)
                cursor.execute("SELECT COUNT(*) AS total" + source, params)
                pending_transfers = int(cursor.fetchone()["total"])
        return {
            "items": items,
            "summary": {
                "total": total,
                "closableCaseCount": closable,
                "pendingTransferCount": pending_transfers,
                "truncated": total > len(items),
            },
        }

    @staticmethod
    def _lock_case_and_line(connection, case_id, line_id):
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM admwf_case WHERE id=%s FOR UPDATE", (case_id,))
            case = cursor.fetchone()
            cursor.execute("SELECT * FROM admwf_case_line WHERE id=%s AND case_id=%s FOR UPDATE", (line_id, case_id))
            line = cursor.fetchone()
        if not case or not line:
            raise AdmError("ADM主单或明细不存在", 404, "ADM_NOT_FOUND")
        return case, line

    @staticmethod
    def _next_event_no(connection, case_id):
        with connection.cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(event_no),0)+1 AS next_no FROM admwf_operation_log WHERE case_id=%s", (case_id,))
            return int(cursor.fetchone()["next_no"])

    @staticmethod
    def _finish_line_responsibility(connection, line_id, now):
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE admwf_responsibility_segment SET ended_at=%s,end_type='LINE_COMPLETED' "
                "WHERE line_id=%s AND ended_at IS NULL", (now, line_id),
            )
            cursor.execute(
                "UPDATE admwf_assignment SET effective_status='ENDED',ended_at=%s "
                "WHERE line_id=%s AND assignment_type='OPERATOR' AND effective_status='EFFECTIVE'",
                (now, line_id),
            )

    def assign_operator(self, case_id, line_id, operator, actor, reason=None):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or self._effective_line(line)["line_status"] != "PENDING_OPERATOR":
                raise AdmError("当前状态不能分配操作员", 409, "ADM_ACTION_BLOCKED")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE admwf_case_line SET operator_id=%s,operator_name=%s,line_status='PENDING_ACCEPT',"
                    "accepted_at=NULL,version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,updated_at=%s "
                    "WHERE id=%s AND version_no=%s",
                    (operator["id"], operator["name"], actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
                cursor.execute(
                    "INSERT INTO admwf_assignment"
                    "(case_id,line_id,assignment_type,to_user_id,to_user_name,assignment_reason,assigned_by_id,"
                    "assigned_by_name,assigned_at,effective_status,created_at) "
                    "VALUES(%s,%s,'OPERATOR',%s,%s,%s,%s,%s,%s,'PENDING',%s)",
                    (case_id, line_id, operator["id"], operator["name"], reason, actor["id"], actor["name"], now, now),
                )
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="ASSIGN_OPERATOR",
                operator_id=actor["id"], operator_name=actor["name"], from_status=line["line_status"],
                to_status="PENDING_ACCEPT", before_version=line["version_no"], after_version=line["version_no"] + 1,
                note=reason, before={"operatorId": line["operator_id"], "operatorName": line["operator_name"]},
                after={"operatorId": operator["id"], "operatorName": operator["name"]},
                changed_fields=["operatorId", "operatorName", "lineStatus"],
            )
            return self.get_case(case_id, connection=connection)

    def change_leader(self, case_id, line_id, leader, actor, reason):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if line["line_status"] == "COMPLETED":
                raise AdmError("该订单已完结，不能更换组长；特殊情况请走受控更正流程", 409, "ADM_COMPLETED_READ_ONLY")
            if line.get("review_status") == "APPROVED":
                raise AdmError("该订单已审核通过，不能更换组长；如需更正，请先撤回审核", 409, "ADM_REVIEWED_READ_ONLY")
            if case["case_status"] != "ACTIVE" or line["line_status"] in {"VOIDED", "HISTORICAL"}:
                raise AdmError("当前状态不能更换组长", 409, "ADM_ACTION_BLOCKED")
            if _leader_locked(line):
                raise AdmError("操作员已接单，不能更换组长", 409, "ADM_LEADER_LOCKED")
            next_status = "PENDING_OPERATOR" if line["line_status"] == "PENDING_LEADER" else line["line_status"]
            if line["leader_id"] == leader["id"]:
                raise AdmError("新组长不能与当前组长相同")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE admwf_assignment SET effective_status='ENDED',ended_at=%s "
                    "WHERE line_id=%s AND assignment_type='LEADER' AND effective_status='EFFECTIVE'",
                    (now, line_id),
                )
                cursor.execute(
                    "INSERT INTO admwf_assignment"
                    "(case_id,line_id,assignment_type,from_user_id,from_user_name,to_user_id,to_user_name,"
                    "assignment_reason,assigned_by_id,assigned_by_name,assigned_at,effective_status,created_at) "
                    "VALUES(%s,%s,'LEADER',%s,%s,%s,%s,%s,%s,%s,%s,'EFFECTIVE',%s)",
                    (case_id, line_id, line["leader_id"], line["leader_name"], leader["id"], leader["name"],
                     reason, actor["id"], actor["name"], now, now),
                )
                cursor.execute(
                    "UPDATE admwf_case_line SET leader_id=%s,leader_name=%s,line_status=%s,version_no=version_no+1,"
                    "updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (leader["id"], leader["name"], next_status, actor["id"], actor["name"], now,
                     line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="CHANGE_LEADER",
                operator_id=actor["id"], operator_name=actor["name"], note=reason,
                from_status=line["line_status"], to_status=next_status,
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                before={"leaderId": line["leader_id"], "leaderName": line["leader_name"]},
                after={"leaderId": leader["id"], "leaderName": leader["name"],
                       "operatorId": line["operator_id"], "operatorRetained": True},
                changed_fields=["leaderId", "leaderName"],
            )
            return self.get_case(case_id, connection=connection)

    def request_transfer(self, case_id, line_id, target, actor, reason, handover_note):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PROCESSING":
                raise AdmError("只能转派正在办理的明细", 409, "ADM_ACTION_BLOCKED")
            if line["leader_id"] != actor["id"]:
                raise AdmError("组长只能转派自己负责的明细", 403, "ADM_FORBIDDEN")
            if not line["operator_id"]:
                raise AdmError("该明细尚无当前操作员")
            if line["operator_id"] == target["id"]:
                raise AdmError("不能转派给当前操作员")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM admwf_transfer WHERE line_id=%s AND status='PENDING' LIMIT 1 FOR UPDATE",
                    (line_id,),
                )
                if cursor.fetchone():
                    raise AdmError("该明细已有待确认转派", 409, "ADM_ACTION_BLOCKED")
                cursor.execute(
                    "INSERT INTO admwf_transfer"
                    "(case_id,line_id,from_operator_id,from_operator_name,to_operator_id,to_operator_name,"
                    "requested_by_id,requested_by_name,transfer_reason,handover_note,status,requested_at,version_no) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s,1)",
                    (case_id, line_id, line["operator_id"], line["operator_name"], target["id"], target["name"],
                     actor["id"], actor["name"], reason, handover_note, now),
                )
                transfer_id = cursor.lastrowid
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="REQUEST_TRANSFER",
                operator_id=actor["id"], operator_name=actor["name"], note=reason,
                from_status="PROCESSING", to_status="PROCESSING",
                before_version=line["version_no"], after_version=line["version_no"],
                after={"transferId": transfer_id, "fromOperatorId": line["operator_id"],
                       "toOperatorId": target["id"], "status": "PENDING"},
                changed_fields=["pendingTransfer"],
            )
            return self.get_case(case_id, connection=connection)

    def decide_transfer(self, case_id, line_id, transfer_id, actor, decision, reason=None):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PROCESSING":
                raise AdmError("当前状态不能处理转派", 409, "ADM_ACTION_BLOCKED")
            if decision not in {"ACCEPTED", "REJECTED"}:
                raise AdmError("转派处理结果无效")
            if decision == "REJECTED" and not reason:
                raise AdmError("拒绝转派时必须填写原因")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM admwf_transfer WHERE id=%s AND case_id=%s AND line_id=%s FOR UPDATE",
                    (transfer_id, case_id, line_id),
                )
                transfer = cursor.fetchone()
                if not transfer:
                    raise AdmError("转派记录不存在", 404, "ADM_NOT_FOUND")
                if transfer["status"] != "PENDING":
                    raise AdmError("该转派已经处理", 409, "ADM_ACTION_BLOCKED")
                if transfer["to_operator_id"] != actor["id"]:
                    raise AdmError("只有目标操作员可以接受或拒绝转派", 403, "ADM_FORBIDDEN")
                if line["operator_id"] != transfer["from_operator_id"]:
                    raise AdmError("当前操作员已变更，该转派不再有效", 409, "ADM_VERSION_CONFLICT")
                cursor.execute(
                    "UPDATE admwf_transfer SET status=%s,decided_by_id=%s,decided_by_name=%s,"
                    "decision_reason=%s,decided_at=%s,version_no=version_no+1 "
                    "WHERE id=%s AND version_no=%s",
                    (decision, actor["id"], actor["name"], reason, now, transfer_id, transfer["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("转派已被其他人处理", 409, "ADM_VERSION_CONFLICT")
                if decision == "ACCEPTED":
                    cursor.execute(
                        "UPDATE admwf_responsibility_segment SET ended_at=%s,end_type='TRANSFERRED' "
                        "WHERE line_id=%s AND ended_at IS NULL", (now, line_id),
                    )
                    cursor.execute(
                        "UPDATE admwf_assignment SET effective_status='ENDED',ended_at=%s "
                        "WHERE line_id=%s AND assignment_type='OPERATOR' AND effective_status='EFFECTIVE'",
                        (now, line_id),
                    )
                    cursor.execute(
                        "INSERT INTO admwf_assignment"
                        "(case_id,line_id,assignment_type,from_user_id,from_user_name,to_user_id,to_user_name,"
                        "assignment_reason,assigned_by_id,assigned_by_name,assigned_at,effective_status,created_at) "
                        "VALUES(%s,%s,'OPERATOR',%s,%s,%s,%s,%s,%s,%s,%s,'EFFECTIVE',%s)",
                        (case_id, line_id, transfer["from_operator_id"], transfer["from_operator_name"],
                         transfer["to_operator_id"], transfer["to_operator_name"], transfer["transfer_reason"],
                         transfer["requested_by_id"], transfer["requested_by_name"], now, now),
                    )
                    cursor.execute(
                        "SELECT COALESCE(MAX(segment_no),0)+1 AS next_no FROM admwf_responsibility_segment "
                        "WHERE line_id=%s", (line_id,),
                    )
                    segment_no = int(cursor.fetchone()["next_no"])
                    cursor.execute(
                        "INSERT INTO admwf_responsibility_segment"
                        "(case_id,line_id,segment_no,operator_id,operator_name,start_type,started_at,source_transfer_id,"
                        "created_by_id,created_by_name,created_at) VALUES(%s,%s,%s,%s,%s,'TRANSFER_ACCEPT',%s,%s,%s,%s,%s)",
                        (case_id, line_id, segment_no, actor["id"], actor["name"], now, transfer_id,
                         actor["id"], actor["name"], now),
                    )
                    cursor.execute(
                        "UPDATE admwf_case_line SET operator_id=%s,operator_name=%s,accepted_at=%s,"
                        "version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,updated_at=%s "
                        "WHERE id=%s AND version_no=%s",
                        (actor["id"], actor["name"], now, actor["id"], actor["name"], now,
                         line_id, line["version_no"]),
                    )
                    if cursor.rowcount != 1:
                        raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            after_version = line["version_no"] + 1 if decision == "ACCEPTED" else line["version_no"]
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="TRANSFER_" + decision,
                operator_id=actor["id"], operator_name=actor["name"], note=reason,
                from_status="PROCESSING", to_status="PROCESSING",
                before_version=line["version_no"], after_version=after_version,
                before={"operatorId": line["operator_id"]},
                after={"operatorId": actor["id"] if decision == "ACCEPTED" else line["operator_id"],
                       "transferId": transfer_id, "transferStatus": decision},
                changed_fields=["operatorId", "responsibilitySegment"] if decision == "ACCEPTED" else ["pendingTransfer"],
            )
            return self.get_case(case_id, connection=connection)

    def accept_line(self, case_id, line_id, actor, *, source="WEB"):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PENDING_ACCEPT":
                raise AdmError("当前状态不能接单", 409, "ADM_ACTION_BLOCKED")
            if line["operator_id"] != actor["id"]:
                raise AdmError("只能接收分配给自己的明细", 403, "ADM_FORBIDDEN")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COALESCE(MAX(segment_no),0)+1 AS next_no FROM admwf_responsibility_segment "
                    "WHERE line_id=%s", (line_id,),
                )
                segment_no = int(cursor.fetchone()["next_no"])
                cursor.execute(
                    "UPDATE admwf_case_line SET line_status='PROCESSING',accepted_at=%s,version_no=version_no+1,"
                    "updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (now, actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
                cursor.execute(
                    "UPDATE admwf_assignment SET effective_status='EFFECTIVE' WHERE line_id=%s "
                    "AND assignment_type='OPERATOR' AND to_user_id=%s AND effective_status='PENDING'",
                    (line_id, actor["id"]),
                )
                cursor.execute(
                    "INSERT INTO admwf_responsibility_segment"
                    "(case_id,line_id,segment_no,operator_id,operator_name,start_type,started_at,"
                    "created_by_id,created_by_name,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (case_id, line_id, segment_no, actor["id"], actor["name"],
                     "ACCEPT", now, actor["id"], actor["name"], now),
                )
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="ACCEPT_LINE",
                operator_id=actor["id"], operator_name=actor["name"], operation_source=source,
                from_status="PENDING_ACCEPT", to_status="PROCESSING", before_version=line["version_no"],
                after_version=line["version_no"] + 1, after={"acceptedAt": now.isoformat(sep=" ")},
                changed_fields=["lineStatus", "acceptedAt", "responsibilitySegment"],
            )
            return self.get_case(case_id, connection=connection)

    def update_investigation_note(self, case_id, line_id, actor, note):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PROCESSING":
                raise AdmError("当前状态不能填写订单情况说明", 409, "ADM_ACTION_BLOCKED")
            if line["operator_id"] != actor["id"]:
                raise AdmError("只能填写自己负责明细的订单情况说明", 403, "ADM_FORBIDDEN")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE admwf_case_line SET investigation_note=%s,version_no=version_no+1,"
                    "updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (note, actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="UPDATE_INVESTIGATION_NOTE",
                operator_id=actor["id"], operator_name=actor["name"],
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                before={"investigationNote": line["investigation_note"]},
                after={"investigationNote": note}, changed_fields=["investigationNote"],
            )
            return self.get_case(case_id, connection=connection)

    def update_operator_supplement(self, case_id, line_id, actor, data):
        """Allow the current operator to supplement the six business identifiers and note."""
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PROCESSING":
                raise AdmError("当前状态不能补充订单资料", 409, "ADM_ACTION_BLOCKED")
            if int(line["operator_id"] or 0) != int(actor["id"]):
                raise AdmError("只能补充自己负责明细的订单资料", 403, "ADM_FORBIDDEN")
            fields = {
                "otaCode": "ota_code", "otaName": "ota_name", "otaOrderNo": "ota_order_no",
                "supplierCode": "supplier_code", "supplierName": "supplier_name",
                "airlineCode": "airline_code", "airlineName": "airline_name",
                "ticketNo": "ticket_no", "pnr": "pnr", "investigationNote": "investigation_note",
            }
            before = {key: line[column] for key, column in fields.items()}
            changed = [key for key in fields if before.get(key) != data.get(key)]
            if not changed:
                return self.get_case(case_id, connection=connection)
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE admwf_case_line SET ota_code=%s,ota_name=%s,ota_order_no=%s,supplier_code=%s,"
                    "supplier_name=%s,airline_code=%s,airline_name=%s,ticket_no=%s,pnr=%s,investigation_note=%s,"
                    "version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,updated_at=%s "
                    "WHERE id=%s AND version_no=%s",
                    (data["otaCode"], data["otaName"], data["otaOrderNo"], data["supplierCode"],
                     data["supplierName"], data["airlineCode"], data["airlineName"], data["ticketNo"],
                     data["pnr"], data["investigationNote"], actor["id"], actor["name"], now,
                     line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="UPDATE_OPERATOR_SUPPLEMENT",
                operator_id=actor["id"], operator_name=actor["name"],
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                before=before, after=data, changed_fields=changed,
            )
            return self.get_case(case_id, connection=connection)

    def claim_for_export(self, line_ids, actor, workbook_builder):
        requested = list(dict.fromkeys(int(value) for value in line_ids))
        with self.transaction() as connection:
            placeholders = ",".join(["%s"] * len(requested))
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT l.*,c.internal_no AS case_internal_no,c.adm_no,c.issuer_type,c.issuer_name,"
                    "c.original_amount AS case_original_amount,c.cny_amount AS case_cny_amount,c.case_status,"
                    "(SELECT r.started_at FROM admwf_recovery r WHERE r.line_id=l.id "
                    " ORDER BY r.recovery_no DESC LIMIT 1) AS recovery_started_at,"
                    "(SELECT rv.result FROM admwf_review rv WHERE rv.line_id=l.id "
                    " ORDER BY rv.review_no DESC LIMIT 1) AS latest_review_status,"
                    "(SELECT rv.return_reason FROM admwf_review rv WHERE rv.line_id=l.id "
                    " ORDER BY rv.review_no DESC LIMIT 1) AS latest_review_return_reason,"
                    "(SELECT ap.appeal_reason FROM admwf_appeal ap WHERE ap.line_id=l.id "
                    " ORDER BY ap.round_no DESC LIMIT 1) AS latest_appeal_reason,"
                    "(SELECT ap.appeal_target FROM admwf_appeal ap WHERE ap.line_id=l.id "
                    " ORDER BY ap.round_no DESC LIMIT 1) AS latest_appeal_target,"
                    "(SELECT ap.no_appeal_reason FROM admwf_appeal ap WHERE ap.line_id=l.id "
                    " ORDER BY ap.round_no DESC LIMIT 1) AS latest_no_appeal_reason,"
                    "(SELECT GROUP_CONCAT(CONCAT('/api/v1/adm/cases/',c.id,'/attachments/',a.id,'/preview') "
                    " ORDER BY a.id SEPARATOR '; ') FROM admwf_attachment a WHERE a.case_id=c.id "
                    " AND a.record_status='ACTIVE' AND (a.source_line_id IS NULL OR a.source_line_id=l.id)) "
                    "AS attachment_address "
                    "FROM admwf_case_line l JOIN admwf_case c ON c.id=l.case_id "
                    "WHERE l.id IN (" + placeholders + ") ORDER BY l.id FOR UPDATE",
                    requested,
                )
                rows = {int(row["id"]): row for row in cursor.fetchall()}
            included, excluded = [], []
            now = business_now()
            for line_id in requested:
                line = rows.get(line_id)
                if not line:
                    excluded.append({"lineId": line_id, "reason": "NOT_FOUND"})
                    continue
                if line["case_status"] != "ACTIVE":
                    excluded.append({"lineId": line_id, "reason": "CASE_NOT_ACTIVE"})
                    continue
                if line["operator_id"] != actor["id"]:
                    excluded.append({"lineId": line_id, "reason": "NOT_CURRENT_OPERATOR"})
                    continue
                if line["line_status"] == "PENDING_ACCEPT":
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT COALESCE(MAX(segment_no),0)+1 AS next_no FROM admwf_responsibility_segment "
                            "WHERE line_id=%s", (line_id,),
                        )
                        segment_no = int(cursor.fetchone()["next_no"])
                        cursor.execute(
                            "UPDATE admwf_case_line SET line_status='PROCESSING',accepted_at=%s,"
                            "version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,updated_at=%s "
                            "WHERE id=%s AND version_no=%s AND line_status='PENDING_ACCEPT'",
                            (now, actor["id"], actor["name"], now, line_id, line["version_no"]),
                        )
                        if cursor.rowcount != 1:
                            excluded.append({"lineId": line_id, "reason": "CLAIM_CONFLICT"})
                            continue
                        cursor.execute(
                            "UPDATE admwf_assignment SET effective_status='EFFECTIVE' WHERE line_id=%s "
                            "AND assignment_type='OPERATOR' AND to_user_id=%s AND effective_status='PENDING'",
                            (line_id, actor["id"]),
                        )
                        cursor.execute(
                            "INSERT INTO admwf_responsibility_segment"
                            "(case_id,line_id,segment_no,operator_id,operator_name,start_type,started_at,"
                            "created_by_id,created_by_name,created_at) VALUES(%s,%s,%s,%s,%s,'EXPORT_CLAIM',%s,%s,%s,%s)",
                            (line["case_id"], line_id, segment_no, actor["id"], actor["name"], now,
                             actor["id"], actor["name"], now),
                        )
                    self.append_operation_log(
                        connection, case_id=line["case_id"], line_id=line_id,
                        event_no=self._next_event_no(connection, line["case_id"]), event_type="ACCEPT_AND_EXPORT",
                        operator_id=actor["id"], operator_name=actor["name"], operation_source="EXCEL",
                        from_status="PENDING_ACCEPT", to_status="PROCESSING",
                        before_version=line["version_no"], after_version=line["version_no"] + 1,
                        after={"acceptedAt": now.isoformat(sep=" ")},
                        changed_fields=["lineStatus", "acceptedAt", "responsibilitySegment"],
                    )
                    line.update(line_status="PROCESSING", accepted_at=now, version_no=line["version_no"] + 1)
                elif line["line_status"] != "PROCESSING":
                    excluded.append({"lineId": line_id, "reason": "STATUS_NOT_EXPORTABLE"})
                    continue
                included.append(line)
            if not included:
                raise AdmError("选中明细均未能接单或导出", 409, "ADM_EXPORT_EMPTY")
            content = workbook_builder(included)
            return {"content": content, "includedCount": len(included), "excluded": excluded}

    def decide_recovery(self, case_id, line_id, decision, actor, reason=None, allow_override=False):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PROCESSING":
                raise AdmError("当前状态不能登记恢复决定", 409, "ADM_ACTION_BLOCKED")
            if line["operator_id"] != actor["id"] and not allow_override:
                raise AdmError("只能处理自己负责的明细", 403, "ADM_FORBIDDEN")
            if line["recovery_status"] != "UNDECIDED":
                raise AdmError("该明细已经登记恢复决定", 409, "ADM_ACTION_BLOCKED")
            if decision not in {"NEEDED", "NOT_NEEDED"}:
                raise AdmError("恢复决定无效")
            now = business_now()
            status = "WAITING" if decision == "NEEDED" else "NOT_REQUIRED"
            remind_at = now + timedelta(hours=48) if decision == "NEEDED" else None
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COALESCE(MAX(recovery_no),0)+1 AS next_no FROM admwf_recovery WHERE line_id=%s",
                    (line_id,),
                )
                recovery_no = int(cursor.fetchone()["next_no"])
                cursor.execute(
                    "INSERT INTO admwf_recovery"
                    "(case_id,line_id,recovery_no,decision,no_recovery_reason,started_at,remind_at,status,"
                    "created_by_id,created_by_name,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (case_id, line_id, recovery_no, decision, reason if decision == "NOT_NEEDED" else None,
                     now if decision == "NEEDED" else None, remind_at, status, actor["id"], actor["name"], now, now),
                )
                cursor.execute(
                    "UPDATE admwf_case_line SET recovery_status=%s,version_no=version_no+1,updated_by_id=%s,"
                    "updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (status, actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="DECIDE_RECOVERY",
                operator_id=actor["id"], operator_name=actor["name"], from_status=line["line_status"],
                to_status=line["line_status"], before_version=line["version_no"], after_version=line["version_no"] + 1,
                note=reason, before={"recoveryStatus": line["recovery_status"]},
                after={"recoveryStatus": status, "startedAt": now.isoformat(sep=" ") if decision == "NEEDED" else None,
                       "remindAt": remind_at.isoformat(sep=" ") if remind_at else None},
                changed_fields=["recoveryStatus"],
            )
            return self.get_case(case_id, connection=connection)

    def operator_import_context(self, line_internal_nos):
        if not line_internal_nos:
            return {}
        with self.transaction() as connection:
            placeholders = ",".join(["%s"] * len(line_internal_nos))
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT l.*,c.internal_no AS case_internal_no,c.adm_no,c.case_status,c.issuer_type,c.issuer_name,"
                    "c.currency,c.original_amount AS case_original_amount,c.cny_amount AS case_cny_amount,"
                    "(SELECT r.started_at FROM admwf_recovery r WHERE r.line_id=l.id "
                    " ORDER BY r.recovery_no DESC LIMIT 1) AS recovery_started_at,"
                    "(SELECT rv.result FROM admwf_review rv WHERE rv.line_id=l.id "
                    " ORDER BY rv.review_no DESC LIMIT 1) AS latest_review_status,"
                    "(SELECT rv.return_reason FROM admwf_review rv WHERE rv.line_id=l.id "
                    " ORDER BY rv.review_no DESC LIMIT 1) AS latest_review_return_reason,"
                    "(SELECT ap.appeal_reason FROM admwf_appeal ap WHERE ap.line_id=l.id "
                    " ORDER BY ap.round_no DESC LIMIT 1) AS latest_appeal_reason,"
                    "(SELECT ap.appeal_target FROM admwf_appeal ap WHERE ap.line_id=l.id "
                    " ORDER BY ap.round_no DESC LIMIT 1) AS latest_appeal_target,"
                    "(SELECT ap.no_appeal_reason FROM admwf_appeal ap WHERE ap.line_id=l.id "
                    " ORDER BY ap.round_no DESC LIMIT 1) AS latest_no_appeal_reason,"
                    "(SELECT GROUP_CONCAT(CONCAT('/api/v1/adm/cases/',c.id,'/attachments/',a.id,'/preview') "
                    " ORDER BY a.id SEPARATOR '; ') FROM admwf_attachment a WHERE a.case_id=c.id "
                    " AND a.record_status='ACTIVE' AND (a.source_line_id IS NULL OR a.source_line_id=l.id)) "
                    "AS attachment_address "
                    "FROM admwf_case_line l JOIN admwf_case c ON c.id=l.case_id "
                    "WHERE l.line_internal_no IN (" + placeholders + ")",
                    tuple(line_internal_nos),
                )
                return {row["line_internal_no"]: row for row in cursor.fetchall()}

    def confirm_recovery(self, case_id, line_id, actor, allow_override=False):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PROCESSING":
                raise AdmError("当前状态不能确认恢复处理", 409, "ADM_ACTION_BLOCKED")
            if line["operator_id"] != actor["id"] and not allow_override:
                raise AdmError("只能处理自己负责的明细", 403, "ADM_FORBIDDEN")
            if line["recovery_status"] not in {"WAITING", "REMINDER_DUE"}:
                raise AdmError("该明细无需确认恢复处理", 409, "ADM_ACTION_BLOCKED")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE admwf_recovery SET status='CONFIRMED',confirmed_by_id=%s,confirmed_by_name=%s,"
                    "confirmed_at=%s,updated_at=%s WHERE line_id=%s AND status IN ('WAITING','REMINDER_DUE')",
                    (actor["id"], actor["name"], now, now, line_id),
                )
                if cursor.rowcount != 1:
                    raise AdmError("恢复记录已变化，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
                cursor.execute(
                    "UPDATE admwf_case_line SET recovery_status='CONFIRMED',version_no=version_no+1,"
                    "updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="CONFIRM_RECOVERY",
                operator_id=actor["id"], operator_name=actor["name"], before_version=line["version_no"],
                after_version=line["version_no"] + 1, before={"recoveryStatus": line["recovery_status"]},
                after={"recoveryStatus": "CONFIRMED", "confirmedAt": now.isoformat(sep=" ")},
                changed_fields=["recoveryStatus"],
            )
            return self.get_case(case_id, connection=connection)

    def start_appeal(self, case_id, line_id, actor, reason, target, allow_override=False):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PROCESSING":
                raise AdmError("当前状态不能发起申诉记录", 409, "ADM_ACTION_BLOCKED")
            if line["operator_id"] != actor["id"] and not allow_override:
                raise AdmError("只能处理自己负责的明细", 403, "ADM_FORBIDDEN")
            if line["recovery_status"] not in {"NOT_REQUIRED", "CONFIRMED"}:
                raise AdmError("恢复编码事项尚未处理完成")
            if line["appeal_status"] not in {"UNDECIDED", "FAILED"}:
                raise AdmError("当前申诉状态不能开始新一轮申诉", 409, "ADM_ACTION_BLOCKED")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute("SELECT COALESCE(MAX(round_no),0)+1 AS next_no FROM admwf_appeal WHERE line_id=%s", (line_id,))
                round_no = int(cursor.fetchone()["next_no"])
                cursor.execute(
                    "INSERT INTO admwf_appeal"
                    "(case_id,line_id,round_no,decision,appeal_reason,appeal_target,status,started_at,"
                    "created_by_id,created_by_name,created_at,updated_by_id,updated_by_name,updated_at) "
                    "VALUES(%s,%s,%s,'APPEAL',%s,%s,'IN_PROGRESS',%s,%s,%s,%s,%s,%s,%s)",
                    (case_id, line_id, round_no, reason, target, now, actor["id"], actor["name"], now,
                     actor["id"], actor["name"], now),
                )
                cursor.execute(
                    "UPDATE admwf_case_line SET appeal_status='IN_PROGRESS',problem_attribution=NULL,"
                    "version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,updated_at=%s "
                    "WHERE id=%s AND version_no=%s",
                    (actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id, event_no=self._next_event_no(connection, case_id),
                event_type="START_APPEAL", operator_id=actor["id"], operator_name=actor["name"],
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                before={"appealStatus": line["appeal_status"]},
                after={"appealStatus": "IN_PROGRESS", "roundNo": round_no},
                changed_fields=["appealStatus"],
            )
            return self.get_case(case_id, connection=connection)

    def finish_appeal(self, case_id, line_id, actor, result, attribution=None, note=None, allow_override=False):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PROCESSING" or line["appeal_status"] != "IN_PROGRESS":
                raise AdmError("当前没有可登记结果的申诉", 409, "ADM_ACTION_BLOCKED")
            if line["operator_id"] != actor["id"] and not allow_override:
                raise AdmError("只能处理自己负责的明细", 403, "ADM_FORBIDDEN")
            if result not in {"SUCCEEDED", "FAILED"}:
                raise AdmError("申诉结果无效")
            if result == "FAILED" and attribution not in {"HUMAN", "PLATFORM", "SYSTEM"}:
                raise AdmError("申诉失败时必须选择问题归因")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM admwf_appeal WHERE line_id=%s AND status='IN_PROGRESS' "
                    "ORDER BY round_no DESC LIMIT 1 FOR UPDATE", (line_id,),
                )
                appeal = cursor.fetchone()
                if not appeal:
                    raise AdmError("申诉记录已变化，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
                cursor.execute(
                    "UPDATE admwf_appeal SET status=%s,problem_attribution=%s,result_at=%s,result_note=%s,"
                    "updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s",
                    (result, attribution if result == "FAILED" else None, now, note,
                     actor["id"], actor["name"], now, appeal["id"]),
                )
                cursor.execute(
                    "UPDATE admwf_case_line SET appeal_status=%s,problem_attribution=%s,version_no=version_no+1,"
                    "updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (result, attribution if result == "FAILED" else None, actor["id"], actor["name"],
                     now, line_id, line["version_no"]),
                )
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id, event_no=self._next_event_no(connection, case_id),
                event_type="FINISH_APPEAL", operator_id=actor["id"], operator_name=actor["name"], note=note,
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                before={"appealStatus": "IN_PROGRESS"},
                after={"appealStatus": result, "problemAttribution": attribution},
                changed_fields=["appealStatus", "problemAttribution"],
            )
            return self.get_case(case_id, connection=connection)

    def update_active_appeal(self, case_id, line_id, actor, reason, target):
        """Update the current in-progress appeal fields exported as editable Excel cells."""
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PROCESSING" or line["appeal_status"] != "IN_PROGRESS":
                raise AdmError("当前状态不能修改申诉信息", 409, "ADM_ACTION_BLOCKED")
            if int(line["operator_id"] or 0) != int(actor["id"]):
                raise AdmError("只能修改自己负责明细的申诉信息", 403, "ADM_FORBIDDEN")
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM admwf_appeal WHERE line_id=%s AND status='IN_PROGRESS' "
                    "ORDER BY round_no DESC LIMIT 1 FOR UPDATE",
                    (line_id,),
                )
                appeal = cursor.fetchone()
                if not appeal:
                    raise AdmError("进行中的申诉记录不存在", 409, "ADM_VERSION_CONFLICT")
                if appeal.get("appeal_reason") == reason and appeal.get("appeal_target") == target:
                    return self.get_case(case_id, connection=connection)
                now = business_now()
                cursor.execute(
                    "UPDATE admwf_appeal SET appeal_reason=%s,appeal_target=%s,updated_at=%s WHERE id=%s",
                    (reason, target, now, appeal["id"]),
                )
                cursor.execute(
                    "UPDATE admwf_case_line SET version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,"
                    "updated_at=%s WHERE id=%s AND version_no=%s",
                    (actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="UPDATE_APPEAL_DETAILS",
                operator_id=actor["id"], operator_name=actor["name"],
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                before={"appealReason": appeal.get("appeal_reason"), "appealTarget": appeal.get("appeal_target")},
                after={"appealReason": reason, "appealTarget": target},
                changed_fields=["appealReason", "appealTarget"],
            )
            return self.get_case(case_id, connection=connection)

    def record_no_appeal(self, case_id, line_id, actor, reason, attribution, allow_override=False):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PROCESSING":
                raise AdmError("当前状态不能登记不申诉", 409, "ADM_ACTION_BLOCKED")
            if line["operator_id"] != actor["id"] and not allow_override:
                raise AdmError("只能处理自己负责的明细", 403, "ADM_FORBIDDEN")
            if line["recovery_status"] not in {"NOT_REQUIRED", "CONFIRMED"}:
                raise AdmError("恢复编码事项尚未处理完成")
            if line["appeal_status"] != "UNDECIDED":
                raise AdmError("该明细已经登记申诉决定", 409, "ADM_ACTION_BLOCKED")
            if attribution not in {"HUMAN", "PLATFORM", "SYSTEM"}:
                raise AdmError("不申诉时必须选择问题归因")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO admwf_appeal"
                    "(case_id,line_id,round_no,decision,no_appeal_reason,status,problem_attribution,result_at,"
                    "created_by_id,created_by_name,created_at,updated_by_id,updated_by_name,updated_at) "
                    "VALUES(%s,%s,1,'NO_APPEAL',%s,'NO_APPEAL',%s,%s,%s,%s,%s,%s,%s,%s)",
                    (case_id, line_id, reason, attribution, now, actor["id"], actor["name"], now,
                     actor["id"], actor["name"], now),
                )
                cursor.execute(
                    "UPDATE admwf_case_line SET appeal_status='NO_APPEAL',problem_attribution=%s,"
                    "version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,updated_at=%s "
                    "WHERE id=%s AND version_no=%s",
                    (attribution, actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id, event_no=self._next_event_no(connection, case_id),
                event_type="RECORD_NO_APPEAL", operator_id=actor["id"], operator_name=actor["name"], note=reason,
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                before={"appealStatus": line["appeal_status"]},
                after={"appealStatus": "NO_APPEAL", "problemAttribution": attribution},
                changed_fields=["appealStatus", "problemAttribution"],
            )
            return self.get_case(case_id, connection=connection)

    def submit_review(self, case_id, line_id, actor, allow_override=False):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PROCESSING":
                raise AdmError("当前状态不能提交审核", 409, "ADM_ACTION_BLOCKED")
            if line["operator_id"] != actor["id"] and not allow_override:
                raise AdmError("只能提交自己负责的明细", 403, "ADM_FORBIDDEN")
            validate_submit(line["recovery_status"], line["appeal_status"], line["problem_attribution"])
            now = business_now()
            snapshot = json.dumps({
                "investigationNote": line["investigation_note"], "recoveryStatus": line["recovery_status"],
                "appealStatus": line["appeal_status"], "problemAttribution": line["problem_attribution"],
            }, ensure_ascii=False, separators=(",", ":"))
            with connection.cursor() as cursor:
                cursor.execute("SELECT COALESCE(MAX(review_no),0)+1 AS next_no FROM admwf_review WHERE line_id=%s", (line_id,))
                review_no = int(cursor.fetchone()["next_no"])
                cursor.execute(
                    "INSERT INTO admwf_review"
                    "(case_id,line_id,review_no,submitted_by_id,submitted_by_name,submitted_at,submission_snapshot_json,"
                    "result,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'PENDING',%s)",
                    (case_id, line_id, review_no, actor["id"], actor["name"], now, snapshot, now),
                )
                cursor.execute(
                    "UPDATE admwf_case_line SET line_status='PENDING_REVIEW',review_status='PENDING',"
                    "version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,updated_at=%s "
                    "WHERE id=%s AND version_no=%s",
                    (actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id, event_no=self._next_event_no(connection, case_id),
                event_type="SUBMIT_REVIEW", operator_id=actor["id"], operator_name=actor["name"],
                from_status="PROCESSING", to_status="PENDING_REVIEW", before_version=line["version_no"],
                after_version=line["version_no"] + 1, after={"reviewNo": review_no},
                changed_fields=["lineStatus", "reviewStatus"],
            )
            return self.get_case(case_id, connection=connection)

    def decide_review(self, case_id, line_id, actor, result, *, comment=None, return_reason=None,
                      return_type=None,
                      collection_required=None, expected_amount=None, collection_note=None):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "PENDING_REVIEW":
                raise AdmError("当前状态不能审核", 409, "ADM_ACTION_BLOCKED")
            if result not in {"APPROVED", "RETURNED"}:
                raise AdmError("审核结果无效")
            if result == "RETURNED" and not return_reason:
                raise AdmError("审核退回原因不能为空")
            if result == "RETURNED" and return_type not in {"SUPPLEMENT", "REAPPEAL"}:
                raise AdmError("请选择退回补充材料或退回重新申诉")
            if result == "APPROVED" and line["appeal_status"] == "SUCCEEDED" and collection_required is None:
                raise AdmError("申诉成功审核通过时必须确认是否需要回款")
            if result == "APPROVED" and line["appeal_status"] in {"FAILED", "NO_APPEAL"}:
                if collection_required:
                    raise AdmError("申诉失败或不申诉不进入回款流程")
                collection_required = False
                expected_amount = None
            now = business_now()
            if result == "RETURNED":
                next_status, review_status = "PROCESSING", "RETURNED"
                expected_amount = None
                prefix = "【驳回补充材料】" if return_type == "SUPPLEMENT" else "【驳回重新申诉】"
                stored_return_reason = prefix + return_reason
            else:
                approval_diff_status = "NOT_REQUIRED" if line["appeal_status"] == "SUCCEEDED" else "PENDING"
                next_status = status_after_approval(
                    appeal_status=line["appeal_status"], diff_match_status=approval_diff_status,
                    collection_required=collection_required, expected_collection_amount=expected_amount,
                    collected_amount=line["collected_amount"],
                )
                review_status = "APPROVED"
                stored_return_reason = None
            diff_match_status = line["diff_match_status"]
            if result == "APPROVED":
                diff_match_status = approval_diff_status
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM admwf_review WHERE line_id=%s AND result='PENDING' "
                    "ORDER BY review_no DESC LIMIT 1 FOR UPDATE", (line_id,),
                )
                review = cursor.fetchone()
                if not review:
                    raise AdmError("待审核记录不存在或已处理", 409, "ADM_VERSION_CONFLICT")
                cursor.execute(
                    "UPDATE admwf_review SET result=%s,reviewer_id=%s,reviewer_name=%s,reviewed_at=%s,"
                    "review_comment=%s,return_reason=%s,collection_required=%s,expected_collection_amount=%s,"
                    "collection_note=%s WHERE id=%s",
                    (result, actor["id"], actor["name"], now, comment, stored_return_reason,
                     collection_required if result == "APPROVED" else None, expected_amount, collection_note, review["id"]),
                )
                appeal_status = "UNDECIDED" if result == "RETURNED" and return_type == "REAPPEAL" else line["appeal_status"]
                problem_attribution = None if result == "RETURNED" and return_type == "REAPPEAL" else line["problem_attribution"]
                cursor.execute(
                    "UPDATE admwf_case_line SET line_status=%s,review_status=%s,appeal_status=%s,problem_attribution=%s,diff_match_status=%s,collection_required=%s,"
                    "expected_collection_amount=%s,version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,"
                    "updated_at=%s WHERE id=%s AND version_no=%s",
                    (next_status, review_status, appeal_status, problem_attribution, diff_match_status,
                     collection_required if result == "APPROVED" else None,
                     expected_amount, actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            if next_status == "COMPLETED":
                self._finish_line_responsibility(connection, line_id, now)
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id, event_no=self._next_event_no(connection, case_id),
                event_type="REVIEW_" + result, operator_id=actor["id"], operator_name=actor["name"],
                from_status="PENDING_REVIEW", to_status=next_status, before_version=line["version_no"],
                after_version=line["version_no"] + 1, note=stored_return_reason or comment,
                after={"reviewStatus": review_status, "collectionRequired": collection_required,
                       "expectedCollectionAmount": str(expected_amount) if expected_amount is not None else None,
                       "returnType": return_type, "appealStatus": appeal_status,
                       "diffMatchStatus": diff_match_status},
                changed_fields=["lineStatus", "reviewStatus", "appealStatus", "problemAttribution",
                                "diffMatchStatus", "collectionRequired", "expectedCollectionAmount"],
            )
            return self.get_case(case_id, connection=connection)

    def withdraw_review(self, case_id, line_id, actor, reason):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] not in {
                "WAITING_DIFF", "WAITING_COLLECTION", "COMPLETED",
            }:
                raise AdmError("当前状态没有可撤回的已通过审核", 409, "ADM_ACTION_BLOCKED")
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM admwf_collection "
                    "WHERE line_id=%s AND record_status='VALID'", (line_id,),
                )
                if int(cursor.fetchone()["total"]):
                    raise AdmError("已经发生有效回款，不能撤回审核；请按更正流程处理", 409, "ADM_ACTION_BLOCKED")
                cursor.execute(
                    "SELECT * FROM admwf_review WHERE line_id=%s AND result='APPROVED' AND withdrawn_flag=0 "
                    "ORDER BY review_no DESC LIMIT 1 FOR UPDATE", (line_id,),
                )
                review = cursor.fetchone()
                if not review:
                    raise AdmError("已通过审核记录不存在或已经撤回", 409, "ADM_VERSION_CONFLICT")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE admwf_review SET withdrawn_flag=1,withdrawn_by_id=%s,withdrawn_by_name=%s,"
                    "withdrawn_at=%s,withdraw_reason=%s WHERE id=%s AND withdrawn_flag=0",
                    (actor["id"], actor["name"], now, reason, review["id"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("审核记录已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
                cursor.execute(
                    "UPDATE admwf_case_line SET line_status='PROCESSING',review_status='WITHDRAWN',"
                    "collection_required=NULL,expected_collection_amount=NULL,version_no=version_no+1,"
                    "updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
                if line["line_status"] == "COMPLETED":
                    cursor.execute(
                        "UPDATE admwf_assignment SET effective_status='ENDED' WHERE line_id=%s "
                        "AND assignment_type='OPERATOR' AND effective_status='EFFECTIVE'", (line_id,),
                    )
                    cursor.execute(
                        "INSERT INTO admwf_assignment"
                        "(case_id,line_id,assignment_type,from_user_id,from_user_name,to_user_id,to_user_name,"
                        "assignment_reason,assigned_by_id,assigned_by_name,assigned_at,effective_status,created_at) "
                        "VALUES(%s,%s,'OPERATOR',%s,%s,%s,%s,%s,%s,%s,%s,'EFFECTIVE',%s)",
                        (case_id, line_id, line["operator_id"], line["operator_name"], line["operator_id"],
                         line["operator_name"], "审核撤回后恢复办理", actor["id"], actor["name"], now, now),
                    )
                    cursor.execute(
                        "SELECT COALESCE(MAX(segment_no),0)+1 AS next_no FROM admwf_responsibility_segment "
                        "WHERE line_id=%s", (line_id,),
                    )
                    segment_no = int(cursor.fetchone()["next_no"])
                    cursor.execute(
                        "INSERT INTO admwf_responsibility_segment"
                        "(case_id,line_id,segment_no,operator_id,operator_name,start_type,started_at,"
                        "created_by_id,created_by_name,created_at) VALUES(%s,%s,%s,%s,%s,'REVIEW_WITHDRAW',%s,%s,%s,%s)",
                        (case_id, line_id, segment_no, line["operator_id"], line["operator_name"], now,
                         actor["id"], actor["name"], now),
                    )
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="WITHDRAW_REVIEW",
                operator_id=actor["id"], operator_name=actor["name"], note=reason,
                from_status=line["line_status"], to_status="PROCESSING",
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                before={"reviewStatus": line["review_status"], "reviewId": review["id"]},
                after={"reviewStatus": "WITHDRAWN", "operatorId": line["operator_id"]},
                changed_fields=["lineStatus", "reviewStatus", "collectionRequired", "expectedCollectionAmount"],
            )
            return self.get_case(case_id, connection=connection)

    def record_difference_check(self, case_id, line_id, actor, match):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "WAITING_DIFF":
                raise AdmError("当前状态不需要核验差异单", 409, "ADM_ACTION_BLOCKED")
            if line["appeal_status"] not in {"FAILED", "NO_APPEAL"}:
                raise AdmError("只有申诉失败或不申诉的明细需要核验差异单")
            result_status = match["resultStatus"]
            allowed = DIFF_MATCHED | {"NOT_MATCHED", "QUERY_FAILED", "NOT_CONNECTED"}
            if result_status not in allowed:
                raise AdmError("差异单核验结果无效", 503, "ADM_REFERENCE_INVALID")
            now = business_now()
            next_status = "WAITING_DIFF"
            if result_status in DIFF_MATCHED:
                next_status = status_after_approval(
                    appeal_status=line["appeal_status"], diff_match_status=result_status,
                    collection_required=bool(line["collection_required"]),
                    expected_collection_amount=line["expected_collection_amount"],
                    collected_amount=line["collected_amount"],
                )
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COALESCE(MAX(check_no),0)+1 AS next_no FROM admwf_diff_match WHERE line_id=%s",
                    (line_id,),
                )
                check_no = int(cursor.fetchone()["next_no"])
                cursor.execute(
                    "INSERT INTO admwf_diff_match"
                    "(case_id,line_id,check_no,query_adm_no,query_ota_order_no,result_status,external_record_id,"
                    "matched_key_type,matched_key_value,response_summary_json,checked_by_id,checked_by_name,checked_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (case_id, line_id, check_no, case["adm_no"], match.get("matchedKeyValue"), result_status,
                     match.get("externalRecordId"), match.get("matchedKeyType"), match.get("matchedKeyValue"),
                     json.dumps(match.get("summary") or {}, ensure_ascii=False, separators=(",", ":")),
                     actor["id"], actor["name"], now),
                )
                cursor.execute(
                    "UPDATE admwf_case_line SET diff_match_status=%s,line_status=%s,version_no=version_no+1,"
                    "updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (result_status, next_status, actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            if next_status == "COMPLETED":
                self._finish_line_responsibility(connection, line_id, now)
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="CHECK_DIFFERENCE_ORDER",
                operator_id=actor["id"], operator_name=actor["name"],
                from_status=line["line_status"], to_status=next_status,
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                before={"diffMatchStatus": line["diff_match_status"]},
                after={"diffMatchStatus": result_status, "checkNo": check_no,
                       "matchedKeyType": match.get("matchedKeyType")},
                changed_fields=["diffMatchStatus", "lineStatus"],
            )
            return {"match": match, "caseDetail": self.get_case(case_id, connection=connection)}

    @staticmethod
    def _collection_total(connection, line_id):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(SUM(amount),0) AS total FROM admwf_collection "
                "WHERE line_id=%s AND record_status='VALID'", (line_id,),
            )
            return cursor.fetchone()["total"]

    def record_collection(self, case_id, line_id, actor, *, amount, received_date,
                          voucher_no, description, attachment_ids):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] != "WAITING_COLLECTION":
                raise AdmError("当前状态不能登记回款", 409, "ADM_ACTION_BLOCKED")
            if not line["collection_required"] or line["expected_collection_amount"] is None:
                raise AdmError("该明细没有已审核确认的应回款金额")
            now = business_now()
            with connection.cursor() as cursor:
                if attachment_ids:
                    placeholders = ",".join(["%s"] * len(attachment_ids))
                    cursor.execute(
                        "SELECT id FROM admwf_attachment WHERE case_id=%s AND record_status='ACTIVE' "
                        "AND id IN (" + placeholders + ") FOR UPDATE",
                        (case_id, *attachment_ids),
                    )
                    found = {int(row["id"]) for row in cursor.fetchall()}
                    if found != set(attachment_ids):
                        raise AdmError("回款凭证附件不存在或已作废")
                cursor.execute(
                    "SELECT COALESCE(MAX(collection_no),0)+1 AS next_no FROM admwf_collection WHERE line_id=%s",
                    (line_id,),
                )
                collection_no = int(cursor.fetchone()["next_no"])
                cursor.execute(
                    "INSERT INTO admwf_collection"
                    "(case_id,line_id,collection_no,currency,amount,received_date,voucher_no,description,"
                    "record_status,recorded_by_id,recorded_by_name,created_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'VALID',%s,%s,%s)",
                    (case_id, line_id, collection_no, case["currency"], amount, received_date,
                     voucher_no, description, actor["id"], actor["name"], now),
                )
                collection_id = cursor.lastrowid
                if attachment_ids:
                    placeholders = ",".join(["%s"] * len(attachment_ids))
                    cursor.execute(
                        "UPDATE admwf_attachment SET source_line_id=%s,business_type='COLLECTION',business_id=%s "
                        "WHERE case_id=%s AND id IN (" + placeholders + ")",
                        (line_id, collection_id, case_id, *attachment_ids),
                    )
            total = self._collection_total(connection, line_id)
            next_status = status_after_approval(
                appeal_status=line["appeal_status"], diff_match_status=line["diff_match_status"],
                collection_required=True, expected_collection_amount=line["expected_collection_amount"],
                collected_amount=total,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE admwf_case_line SET collected_amount=%s,line_status=%s,version_no=version_no+1,"
                    "updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (total, next_status, actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            if next_status == "COMPLETED":
                self._finish_line_responsibility(connection, line_id, now)
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="RECORD_COLLECTION",
                operator_id=actor["id"], operator_name=actor["name"],
                from_status=line["line_status"], to_status=next_status,
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                before={"collectedAmount": str(line["collected_amount"])},
                after={"collectedAmount": str(total), "collectionNo": collection_no},
                changed_fields=["collectedAmount", "lineStatus"],
            )
            return self.get_case(case_id, connection=connection)

    def void_collection(self, case_id, line_id, collection_id, actor, reason):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if case["case_status"] != "ACTIVE" or line["line_status"] not in {"WAITING_COLLECTION", "COMPLETED"}:
                raise AdmError("当前状态不能作废回款记录", 409, "ADM_ACTION_BLOCKED")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM admwf_collection WHERE id=%s AND case_id=%s AND line_id=%s FOR UPDATE",
                    (collection_id, case_id, line_id),
                )
                collection = cursor.fetchone()
                if not collection:
                    raise AdmError("回款记录不存在", 404, "ADM_NOT_FOUND")
                if collection["record_status"] != "VALID":
                    raise AdmError("该回款记录已作废", 409, "ADM_ACTION_BLOCKED")
                cursor.execute(
                    "UPDATE admwf_collection SET record_status='VOIDED',voided_by_id=%s,voided_by_name=%s,"
                    "voided_at=%s,void_reason=%s WHERE id=%s AND record_status='VALID'",
                    (actor["id"], actor["name"], now, reason, collection_id),
                )
                if cursor.rowcount != 1:
                    raise AdmError("回款记录已被其他人处理", 409, "ADM_VERSION_CONFLICT")
            total = self._collection_total(connection, line_id)
            next_status = status_after_approval(
                appeal_status=line["appeal_status"], diff_match_status=line["diff_match_status"],
                collection_required=True, expected_collection_amount=line["expected_collection_amount"],
                collected_amount=total,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE admwf_case_line SET collected_amount=%s,line_status=%s,version_no=version_no+1,"
                    "updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (total, next_status, actor["id"], actor["name"], now, line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            if next_status == "COMPLETED":
                self._finish_line_responsibility(connection, line_id, now)
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="VOID_COLLECTION",
                operator_id=actor["id"], operator_name=actor["name"], note=reason,
                from_status=line["line_status"], to_status=next_status,
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                before={"collectedAmount": str(line["collected_amount"]), "collectionId": collection_id},
                after={"collectedAmount": str(total), "recordStatus": "VOIDED"},
                changed_fields=["collectionRecordStatus", "collectedAmount", "lineStatus"],
            )
            return self.get_case(case_id, connection=connection)

    def void_line(self, case_id, line_id, actor, reason):
        with self.transaction() as connection:
            case, line = self._lock_case_and_line(connection, case_id, line_id)
            if line["line_status"] == "COMPLETED":
                raise AdmError("该订单已完结，不能直接作废；特殊情况请走受控更正流程", 409, "ADM_COMPLETED_READ_ONLY")
            if line.get("review_status") == "APPROVED":
                raise AdmError("该订单已审核通过，不能直接作废；如需更正，请先撤回审核", 409, "ADM_REVIEWED_READ_ONLY")
            if case["case_status"] != "ACTIVE" or line["line_status"] in {"VOIDED", "HISTORICAL"}:
                raise AdmError("当前状态不能作废明细", 409, "ADM_ACTION_BLOCKED")
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM admwf_collection "
                    "WHERE line_id=%s AND record_status='VALID'", (line_id,),
                )
                if int(cursor.fetchone()["total"]):
                    raise AdmError("该明细存在有效回款记录，请先作废错误回款记录")
                cursor.execute(
                    "SELECT COALESCE(SUM(original_amount),0) AS total,COUNT(*) AS line_count "
                    "FROM admwf_case_line WHERE case_id=%s AND id<>%s AND line_status<>'VOIDED'",
                    (case_id, line_id),
                )
                balance = cursor.fetchone()
            if int(balance["line_count"]) == 0:
                raise AdmError("主单至少必须保留一条有效明细")
            if balance["total"] != case["original_amount"]:
                raise AdmError("作废后有效明细金额合计将不等于主单金额，请先调整其他明细")
            now = business_now()
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE admwf_case_line SET line_status='VOIDED',voided_by_id=%s,voided_by_name=%s,"
                    "voided_at=%s,void_reason=%s,version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,"
                    "updated_at=%s WHERE id=%s AND version_no=%s",
                    (actor["id"], actor["name"], now, reason, actor["id"], actor["name"], now,
                     line_id, line["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
                cursor.execute(
                    "UPDATE admwf_responsibility_segment SET ended_at=%s,end_type='LINE_VOIDED' "
                    "WHERE line_id=%s AND ended_at IS NULL", (now, line_id),
                )
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="VOID_LINE",
                operator_id=actor["id"], operator_name=actor["name"], note=reason,
                from_status=line["line_status"], to_status="VOIDED",
                before_version=line["version_no"], after_version=line["version_no"] + 1,
                after={"voidedAt": now.isoformat(sep=" ")},
                changed_fields=["lineStatus", "voidReason"],
            )
            return self.get_case(case_id, connection=connection)

    def rebalance_lines(self, case_id, amounts, actor, reason):
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM admwf_case WHERE id=%s FOR UPDATE", (case_id,))
                case = cursor.fetchone()
                if not case:
                    raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
                if case["case_status"] != "ACTIVE":
                    raise AdmError("当前主单状态不能调整明细金额", 409, "ADM_ACTION_BLOCKED")
                cursor.execute(
                    "SELECT * FROM admwf_case_line WHERE case_id=%s AND line_status<>'VOIDED' ORDER BY line_no FOR UPDATE",
                    (case_id,),
                )
                lines = cursor.fetchall()
                cursor.execute("SELECT rate_value,exchange_unit FROM admwf_fx_snapshot WHERE case_id=%s", (case_id,))
                fx = cursor.fetchone()
            if set(amounts) != {line["id"] for line in lines}:
                raise AdmError("必须一次提交主单下全部有效明细金额")
            blocked = {"PENDING_REVIEW", "WAITING_DIFF", "WAITING_COLLECTION", "COMPLETED", "HISTORICAL"}
            if any(line["line_status"] in blocked for line in lines):
                raise AdmError("已有明细进入审核或完成阶段，不能再调整金额", 409, "ADM_ACTION_BLOCKED")
            if sum(amounts.values(), Decimal("0.00")) != case["original_amount"]:
                raise AdmError("调整后全部有效明细金额之和必须等于主单金额")
            if not fx or fx["exchange_unit"] <= 0:
                raise AdmError("主单冻结汇率无效", 500, "ADM_REFERENCE_INVALID")
            now = business_now()
            cny_total, allocated_cny = allocate_cny_amounts(
                [amounts[line["id"]] for line in lines], fx["rate_value"],
            )
            for line, cny_amount in zip(lines, allocated_cny):
                amount = amounts[line["id"]]
                if amount == line["original_amount"] and cny_amount == line["cny_amount"]:
                    continue
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE admwf_case_line SET original_amount=%s,cny_amount=%s,version_no=version_no+1,"
                        "updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                        (amount, cny_amount, actor["id"], actor["name"], now, line["id"], line["version_no"]),
                    )
                    if cursor.rowcount != 1:
                        raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
                self.append_operation_log(
                    connection, case_id=case_id, line_id=line["id"],
                    event_no=self._next_event_no(connection, case_id), event_type="REBALANCE_LINE_AMOUNT",
                    operator_id=actor["id"], operator_name=actor["name"], note=reason,
                    before_version=line["version_no"], after_version=line["version_no"] + 1,
                    before={"originalAmount": str(line["original_amount"]), "cnyAmount": str(line["cny_amount"])},
                    after={"originalAmount": str(amount), "cnyAmount": str(cny_amount)},
                    changed_fields=["originalAmount", "cnyAmount"],
                )
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE admwf_case SET cny_amount=%s,version_no=version_no+1,updated_by_id=%s,"
                    "updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (cny_total, actor["id"], actor["name"], now, case_id, case["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("主单已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            return self.get_case(case_id, connection=connection)

    def add_line(self, case_id, line, existing_amounts, actor, reason):
        """Add one order and rebalance all effective amounts in one transaction."""
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM admwf_case WHERE id=%s FOR UPDATE", (case_id,))
                case = cursor.fetchone()
                if not case:
                    raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
                if case["case_status"] not in {"DRAFT", "ACTIVE"}:
                    raise AdmError("当前主单状态不能新增订单", 409, "ADM_ACTION_BLOCKED")
                cursor.execute(
                    "SELECT * FROM admwf_case_line WHERE case_id=%s AND line_status<>'VOIDED' "
                    "ORDER BY line_no FOR UPDATE", (case_id,),
                )
                lines = cursor.fetchall()
                cursor.execute(
                    "SELECT rate_value,exchange_unit FROM admwf_fx_snapshot WHERE case_id=%s FOR UPDATE",
                    (case_id,),
                )
                fx = cursor.fetchone()
            if set(existing_amounts) != {item["id"] for item in lines}:
                raise AdmError("必须一次提交主单下全部现有有效明细金额")
            blocked = {"PENDING_REVIEW", "WAITING_DIFF", "WAITING_COLLECTION", "COMPLETED", "HISTORICAL"}
            if any(item["line_status"] in blocked for item in lines):
                raise AdmError("已有明细进入审核或完成阶段，不能再新增订单", 409, "ADM_ACTION_BLOCKED")
            if sum(existing_amounts.values(), line["originalAmount"]) != case["original_amount"]:
                raise AdmError("新增后全部有效明细金额之和必须等于主单金额")
            if not fx or fx["exchange_unit"] <= 0:
                raise AdmError("主单冻结汇率无效", 500, "ADM_REFERENCE_INVALID")
            now = business_now()
            all_amounts = [existing_amounts[current["id"]] for current in lines] + [line["originalAmount"]]
            cny_total, allocated_cny = allocate_cny_amounts(all_amounts, fx["rate_value"])
            for current, cny_amount in zip(lines, allocated_cny[:-1]):
                amount = existing_amounts[current["id"]]
                if amount == current["original_amount"] and cny_amount == current["cny_amount"]:
                    continue
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE admwf_case_line SET original_amount=%s,cny_amount=%s,version_no=version_no+1,"
                        "updated_by_id=%s,updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                        (amount, cny_amount, actor["id"], actor["name"], now,
                         current["id"], current["version_no"]),
                    )
                    if cursor.rowcount != 1:
                        raise AdmError("明细已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
                self.append_operation_log(
                    connection, case_id=case_id, line_id=current["id"],
                    event_no=self._next_event_no(connection, case_id), event_type="REBALANCE_LINE_AMOUNT",
                    operator_id=actor["id"], operator_name=actor["name"], note=reason,
                    before_version=current["version_no"], after_version=current["version_no"] + 1,
                    before={"originalAmount": str(current["original_amount"]), "cnyAmount": str(current["cny_amount"])},
                    after={"originalAmount": str(amount), "cnyAmount": str(cny_amount)},
                    changed_fields=["originalAmount", "cnyAmount"],
                )
            line["cnyAmount"] = allocated_cny[-1]
            with connection.cursor() as cursor:
                cursor.execute("SELECT COALESCE(MAX(line_no),0)+1 AS next_no FROM admwf_case_line WHERE case_id=%s", (case_id,))
                line_no = int(cursor.fetchone()["next_no"])
                line_internal_no = f"{case['internal_no']}-{line_no:03d}"
                cursor.execute(
                    "INSERT INTO admwf_case_line"
                    "(case_id,line_internal_no,line_no,ota_code,ota_name,ota_order_no,supplier_code,supplier_name,"
                    "airline_code,airline_name,ticket_no,pnr,currency,original_amount,cny_amount,department_code,"
                    "department_name,diff_type_code,diff_type_name,difference_reason,investigation_note,leader_id,"
                    "leader_name,process_deadline,line_status,version_no,created_by_id,created_by_name,created_at,"
                    "updated_by_id,updated_by_name,updated_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    "'PENDING_OPERATOR',1,%s,%s,%s,%s,%s,%s)",
                    (case_id, line_internal_no, line_no, line["otaCode"], line["otaName"], line["otaOrderNo"],
                     line["supplierCode"], line["supplierName"], line["airlineCode"], line["airlineName"],
                     line["ticketNo"], line["pnr"], case["currency"], line["originalAmount"], line["cnyAmount"],
                     line["departmentCode"], line["departmentName"], line["diffTypeCode"], line["diffTypeName"],
                     line["differenceReason"], line["investigationNote"], line["leaderId"], line["leaderName"],
                     case["reply_deadline"], actor["id"], actor["name"], now, actor["id"], actor["name"], now),
                )
                line_id = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO admwf_assignment"
                    "(case_id,line_id,assignment_type,to_user_id,to_user_name,assignment_reason,assigned_by_id,"
                    "assigned_by_name,assigned_at,effective_status,created_at) "
                    "VALUES(%s,%s,'LEADER',%s,%s,%s,%s,%s,%s,'EFFECTIVE',%s)",
                    (case_id, line_id, line["leaderId"], line["leaderName"], reason,
                     actor["id"], actor["name"], now, now),
                )
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="ADD_LINE",
                operator_id=actor["id"], operator_name=actor["name"], note=reason,
                after_version=1,
                after={"lineInternalNo": line_internal_no, "originalAmount": str(line["originalAmount"])},
                changed_fields=["lines"],
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE admwf_case SET cny_amount=%s,version_no=version_no+1,updated_by_id=%s,"
                    "updated_by_name=%s,updated_at=%s WHERE id=%s AND version_no=%s",
                    (cny_total, actor["id"], actor["name"], now, case_id, case["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("主单已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            return self.get_case(case_id, connection=connection)

    def close_case(self, case_id, actor):
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM admwf_case WHERE id=%s FOR UPDATE", (case_id,))
                case = cursor.fetchone()
                if not case:
                    raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
                if case["case_status"] != "ACTIVE":
                    raise AdmError("当前主单状态不能结案", 409, "ADM_ACTION_BLOCKED")
                cursor.execute("SELECT id,line_internal_no,line_status FROM admwf_case_line WHERE case_id=%s", (case_id,))
                lines = cursor.fetchall()
                if not lines:
                    raise AdmError("暂无订单明细，不能结案", 409, "ADM_CLOSE_BLOCKED")
                blockers = closure_blockers(lines)
                if blockers:
                    raise AdmError("还有未完成的有效明细，不能结案", 409, "ADM_CLOSE_BLOCKED")
                now = business_now()
                cursor.execute(
                    "UPDATE admwf_case SET case_status='CLOSED',closed_by_id=%s,closed_by_name=%s,closed_at=%s,"
                    "version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,updated_at=%s "
                    "WHERE id=%s AND version_no=%s",
                    (actor["id"], actor["name"], now, actor["id"], actor["name"], now,
                     case_id, case["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("主单已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
            self.append_operation_log(
                connection, case_id=case_id, line_id=None,
                event_no=self._next_event_no(connection, case_id), event_type="CLOSE_CASE",
                operator_id=actor["id"], operator_name=actor["name"],
                from_status="ACTIVE", to_status="CLOSED",
                before_version=case["version_no"], after_version=case["version_no"] + 1,
                after={"closedAt": now.isoformat(sep=" ")}, changed_fields=["caseStatus", "closedAt"],
            )
            return self.get_case(case_id, connection=connection)

    def void_case(self, case_id, actor, reason):
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM admwf_case WHERE id=%s FOR UPDATE", (case_id,))
                case = cursor.fetchone()
                if not case:
                    raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
                if case["case_status"] != "ACTIVE":
                    raise AdmError("只能作废正式办理中的主单", 409, "ADM_ACTION_BLOCKED")
                now = business_now()
                cursor.execute(
                    "UPDATE admwf_case SET case_status='VOIDED',voided_by_id=%s,voided_by_name=%s,voided_at=%s,"
                    "void_reason=%s,version_no=version_no+1,updated_by_id=%s,updated_by_name=%s,updated_at=%s "
                    "WHERE id=%s AND version_no=%s",
                    (actor["id"], actor["name"], now, reason, actor["id"], actor["name"], now,
                     case_id, case["version_no"]),
                )
                if cursor.rowcount != 1:
                    raise AdmError("主单已被其他人修改，请刷新后重试", 409, "ADM_VERSION_CONFLICT")
                cursor.execute(
                    "UPDATE admwf_responsibility_segment SET ended_at=%s,end_type='ADMIN_CORRECTION' "
                    "WHERE case_id=%s AND ended_at IS NULL", (now, case_id),
                )
            self.append_operation_log(
                connection, case_id=case_id, line_id=None,
                event_no=self._next_event_no(connection, case_id), event_type="VOID_CASE",
                operator_id=actor["id"], operator_name=actor["name"], note=reason,
                from_status="ACTIVE", to_status="VOIDED",
                before_version=case["version_no"], after_version=case["version_no"] + 1,
                after={"voidedAt": now.isoformat(sep=" ")}, changed_fields=["caseStatus", "voidReason"],
            )
            return self.get_case(case_id, connection=connection)

    def add_attachment(self, case_id, actor, category, metadata, line_id=None):
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM admwf_case WHERE id=%s FOR UPDATE", (case_id,))
                case = cursor.fetchone()
                if not case:
                    raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
                if case["case_status"] not in {"DRAFT", "ACTIVE"}:
                    raise AdmError("当前主单状态不能上传附件", 409, "ADM_ACTION_BLOCKED")
                if line_id is not None:
                    cursor.execute(
                        "SELECT id FROM admwf_case_line WHERE id=%s AND case_id=%s FOR UPDATE",
                        (line_id, case_id),
                    )
                    if not cursor.fetchone():
                        raise AdmError("附件所属明细不属于当前ADM主单", 400, "ADM_INVALID")
                now = business_now()
                cursor.execute(
                    "INSERT INTO admwf_attachment"
                    "(case_id,source_line_id,business_type,business_id,category,original_file_name,storage_key,"
                    "file_extension,mime_type,file_size,sha256,preview_status,record_status,uploaded_by_id,"
                    "uploaded_by_name,uploaded_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'ACTIVE',%s,%s,%s)",
                    (case_id, line_id, "LINE" if line_id is not None else "CASE",
                     line_id if line_id is not None else case_id, category,
                     metadata["originalFileName"], metadata["storageKey"],
                     metadata["fileExtension"], metadata["mimeType"], metadata["fileSize"], metadata["sha256"],
                     metadata["previewStatus"], actor["id"], actor["name"], now),
                )
                attachment_id = cursor.lastrowid
            self.append_operation_log(
                connection, case_id=case_id, line_id=line_id,
                event_no=self._next_event_no(connection, case_id), event_type="UPLOAD_ATTACHMENT",
                operator_id=actor["id"], operator_name=actor["name"],
                after={"attachmentId": attachment_id, "category": category,
                       "fileName": metadata["originalFileName"], "sha256": metadata["sha256"],
                       "scope": "LINE" if line_id is not None else "CASE"},
                changed_fields=["attachments"],
            )
            detail = self.get_case(case_id, connection=connection)
            detail["uploaded_attachment_id"] = attachment_id
            return detail

    def attachment(self, case_id, attachment_id):
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM admwf_attachment WHERE id=%s AND case_id=%s AND record_status='ACTIVE'",
                (attachment_id, case_id),
            )
            attachment = cursor.fetchone()
        if not attachment:
            raise AdmError("附件不存在或已作废", 404, "ADM_ATTACHMENT_NOT_FOUND")
        return attachment

    def audit_attachment_download(self, case_id, attachment_id, actor, reason=None):
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM admwf_case WHERE id=%s", (case_id,))
                if not cursor.fetchone():
                    raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
            self.append_operation_log(
                connection, case_id=case_id, line_id=None,
                event_no=self._next_event_no(connection, case_id), event_type="DOWNLOAD_ATTACHMENT",
                operator_id=actor["id"], operator_name=actor["name"], note=reason,
                detail={"attachmentId": attachment_id},
            )

    def void_attachment(self, case_id, attachment_id, actor, reason):
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM admwf_case WHERE id=%s FOR UPDATE", (case_id,))
                case = cursor.fetchone()
                if not case:
                    raise AdmError("ADM主单不存在", 404, "ADM_NOT_FOUND")
                if case["case_status"] not in {"DRAFT", "ACTIVE"}:
                    raise AdmError("当前主单状态不能作废附件", 409, "ADM_ACTION_BLOCKED")
                now = business_now()
                cursor.execute(
                    "UPDATE admwf_attachment SET record_status='VOIDED',voided_by_id=%s,voided_by_name=%s,"
                    "voided_at=%s,void_reason=%s WHERE id=%s AND case_id=%s AND record_status='ACTIVE'",
                    (actor["id"], actor["name"], now, reason, attachment_id, case_id),
                )
                if cursor.rowcount != 1:
                    raise AdmError("附件不存在或已作废", 404, "ADM_ATTACHMENT_NOT_FOUND")
            self.append_operation_log(
                connection, case_id=case_id, line_id=None,
                event_no=self._next_event_no(connection, case_id), event_type="VOID_ATTACHMENT",
                operator_id=actor["id"], operator_name=actor["name"], note=reason,
                after={"attachmentId": attachment_id, "recordStatus": "VOIDED"},
                changed_fields=["attachmentRecordStatus"],
            )
            return self.get_case(case_id, connection=connection)

    @staticmethod
    def append_operation_log(connection, *, case_id, line_id, event_no, event_type,
                             operator_id, operator_name, operation_source="WEB",
                             from_status=None, to_status=None, before_version=None,
                             after_version=None, note=None, request_id=None,
                             before=None, after=None, changed_fields=None, detail=None):
        values = [before, after, changed_fields, detail]
        encoded = [json.dumps(value, ensure_ascii=False, separators=(",", ":")) if value is not None else None for value in values]
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admwf_operation_log"
                "(case_id,line_id,event_no,event_type,from_status,to_status,before_version_no,after_version_no,"
                "operator_id,operator_name,operation_source,operation_note,request_id,before_data_json,"
                "after_data_json,changed_fields_json,detail_json,occurred_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (case_id, line_id, event_no, event_type, from_status, to_status,
                 before_version, after_version, operator_id, operator_name,
                 operation_source, note, request_id, *encoded, business_now()),
            )
