"""Execute regression paths against isolated SQL tables, never production data."""
from contextlib import contextmanager
from decimal import Decimal
import sqlite3
import unittest
from data_report_api.services.admwf.repository import AdmWorkflowRepository
from data_report_api.services.admwf.service import AdmWorkflowService
from data_report_api.services.admwf.policy import AdmError


class AssignmentRegressionTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""
          CREATE TABLE admwf_case_line(id INTEGER PRIMARY KEY,case_id INTEGER,line_status TEXT,
            operator_id INTEGER,operator_name TEXT,accepted_at TEXT,version_no INTEGER,
            updated_by_id INTEGER,updated_by_name TEXT,updated_at TEXT,leader_id INTEGER,
            original_amount DECIMAL,cny_amount DECIMAL,recovery_status TEXT,appeal_status TEXT,problem_attribution TEXT);
          INSERT INTO admwf_case_line VALUES(2,1,'PENDING_OPERATOR',NULL,NULL,NULL,1,NULL,NULL,NULL,3,0,0,'NOT_REQUIRED','UNDECIDED',NULL);
          CREATE TABLE admwf_assignment(case_id INTEGER,line_id INTEGER,assignment_type TEXT,
            to_user_id INTEGER,to_user_name TEXT,assignment_reason TEXT,assigned_by_id INTEGER,assigned_by_name TEXT,
            assigned_at TEXT,effective_status TEXT,created_at TEXT,ended_at TEXT);
          CREATE TABLE admwf_appeal(case_id INTEGER,line_id INTEGER,round_no INTEGER,decision TEXT,no_appeal_reason TEXT,
            status TEXT,problem_attribution TEXT,result_at TEXT,created_by_id INTEGER,created_by_name TEXT,
            created_at TEXT,updated_by_id INTEGER,updated_by_name TEXT,updated_at TEXT,UNIQUE(line_id,round_no));
        """)
        db = self.db
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql, params):
                self.result = db.execute(sql.replace("%s", "?").replace(" FOR UPDATE", ""),
                    tuple(value.isoformat(sep=" ") if hasattr(value, "hour") else str(value) if isinstance(value, Decimal) else value for value in params))
                self.rowcount = self.result.rowcount
            def fetchone(self):
                row = self.result.fetchone()
                return dict(row) if row else None
            def fetchall(self): return [dict(row) for row in self.result.fetchall()]
        class Connection:
            def cursor(self): return Cursor()
        @contextmanager
        def transaction():
            with db:
                yield Connection()
        self.repo = AdmWorkflowRepository({})
        self.repo.transaction = transaction
        self.case = {"id": 1, "case_status": "ACTIVE", "master_recovery_status": "NOT_REQUIRED",
            "original_amount": Decimal("100"), "cny_amount": Decimal("700")}
        self.repo._lock_case_and_line = lambda *args: (self.case, self.line())
        self.repo.get_case = lambda *args, **kwargs: {"case": self.case, "lines": [self.line()]}
        self.repo._next_event_no = lambda *args: 1
        self.logs = []
        self.repo.append_operation_log = lambda *args, **kwargs: self.logs.append(kwargs)

    def line(self): return dict(self.db.execute("SELECT * FROM admwf_case_line WHERE id=2").fetchone())

    def test_whole_inherits_amount_and_dispatches_without_supplement(self):
        self.repo.assign_operator(1,2,{"id":4,"name":"operator"},{"id":3,"name":"leader"},whole=True)
        line = self.line()
        self.assertEqual((line["original_amount"],line["cny_amount"],line["line_status"]),(100,700,"PENDING_ACCEPT"))
        self.assertTrue(any(log.get("note") == "资料已确认" for log in self.logs))

    def test_whole_cannot_bypass_split_validation(self):
        self.db.execute("INSERT INTO admwf_case_line(id,case_id,line_status) VALUES(5,1,'PENDING_OPERATOR')")
        with self.assertRaisesRegex(AdmError,"分单"):
            self.repo.assign_operator(1,2,{"id":4,"name":"operator"},{"id":3,"name":"leader"},whole=True)

    def test_reject_returns_to_leader_and_ends_pending_assignment(self):
        self.repo.assign_operator(1,2,{"id":4,"name":"operator"},{"id":3,"name":"leader"},whole=True)
        self.repo.reject_assignment(1,2,{"id":4,"name":"operator"})
        self.assertEqual(self.line()["line_status"],"PENDING_OPERATOR")
        self.assertIsNone(self.line()["operator_id"])
        self.assertEqual(self.line()["leader_id"],3)
        self.assertEqual(self.db.execute("SELECT effective_status FROM admwf_assignment").fetchone()[0],"ENDED")
        self.repo.assign_operator(1,2,{"id":6,"name":"other"},{"id":3,"name":"leader"},whole=True)
        self.assertEqual(self.line()["operator_id"],6)

    def test_reject_checks_assignee_and_state(self):
        self.repo.assign_operator(1,2,{"id":4,"name":"operator"},{"id":3,"name":"leader"},whole=True)
        with self.assertRaises(AdmError): self.repo.reject_assignment(1,2,{"id":8,"name":"other"})
        self.db.execute("UPDATE admwf_case_line SET line_status='PROCESSING'")
        with self.assertRaises(AdmError): self.repo.reject_assignment(1,2,{"id":4,"name":"operator"})

    def test_no_appeal_after_return_creates_next_round(self):
        self.db.execute("UPDATE admwf_case_line SET line_status='PROCESSING',operator_id=4")
        for _ in range(2):
            self.repo.record_no_appeal(1,2,{"id":4,"name":"operator"},"reason","SYSTEM")
            self.db.execute("UPDATE admwf_case_line SET appeal_status='UNDECIDED'")
        self.assertEqual([row[0] for row in self.db.execute("SELECT round_no FROM admwf_appeal ORDER BY round_no")],[1,2])

    def test_edit_master_requires_separate_permission(self):
        service = AdmWorkflowService.__new__(AdmWorkflowService)
        with self.assertRaisesRegex(AdmError,"权限"):
            service.update_case({"id":3,"permissions":["adm.create","adm.review"]},1,{})

    def test_edit_master_remains_available_after_case_closed(self):
        self.db.execute("CREATE TABLE admwf_case(id INTEGER PRIMARY KEY,case_status TEXT,adm_no TEXT,issuer_type TEXT,issuer_code TEXT,issuer_name TEXT,issued_date TEXT,reply_deadline TEXT,remark TEXT,version_no INTEGER,updated_by_id INTEGER,updated_by_name TEXT,updated_at TEXT)")
        self.db.execute("INSERT INTO admwf_case VALUES(1,'CLOSED','OLD','AIRLINE',NULL,'CI','2026-11-12','2026-12-01 00:00:00','',1,NULL,NULL,NULL)")
        self.db.execute("UPDATE admwf_case_line SET line_status='COMPLETED'")
        self.repo.update_case_basic(1,{"admNo":"NEW","issuerType":"AIRLINE","issuerCode":None,"issuerName":"CI",
            "issuedDate":"2026-11-12","replyDeadline":"2026-12-01 00:00:00","remark":"corrected"},{"id":9,"name":"owner"})
        row = self.db.execute("SELECT adm_no,case_status,remark FROM admwf_case WHERE id=1").fetchone()
        self.assertEqual(tuple(row),("NEW","CLOSED","corrected"))
        self.assertTrue(any(log["event_type"] == "UPDATE_CASE_BASIC_INFO" for log in self.logs))
