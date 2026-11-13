"""Exercise deployment schema checks with full information_schema-shaped metadata."""
from contextlib import contextmanager
import unittest
from unittest.mock import patch
from data_report_api import admwf_schema


class AdmSchemaCheckTest(unittest.TestCase):
    def metadata(self):
        rows=[{"table_name":table,"column_name":column,"column_comment":"中文说明",
               "data_type":"bigint" if column.endswith("id") else "datetime", "max_length":None}
              for table,columns in admwf_schema.columns().items() for column in columns]
        for table in ("admwf_case_line","admwf_appeal"):
            rows.extend([
                {"table_name":table,"column_name":"id","column_comment":"主键","data_type":"bigint","max_length":None},
                {"table_name":table,"column_name":"created_at","column_comment":"创建时间","data_type":"datetime","max_length":None},
                {"table_name":table,"column_name":"original_amount","column_comment":"金额","data_type":"decimal","max_length":None},
                {"table_name":table,"column_name":"problem_attribution","column_comment":"问题归因","data_type":"varchar","max_length":32},
            ])
        return rows

    def run_check(self, rows, apply=False):
        statements=[]
        class Cursor:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def execute(self,sql,params=()): statements.append(sql)
            def fetchall(self): return rows
        class Connection:
            def cursor(self): return Cursor()
        class Repository:
            @contextmanager
            def transaction(self): yield Connection()
        args=["admwf_schema"]+(["--apply"] if apply else [])
        with patch.object(admwf_schema,"AdmWorkflowRepository",return_value=Repository()),patch("sys.argv",args):
            admwf_schema.main()
        return statements

    def test_non_attribution_business_columns_do_not_require_varchar(self):
        statements=self.run_check(self.metadata())
        self.assertEqual(len(statements),1)
        self.assertIn("information_schema.columns",statements[0])

    def test_apply_then_check_accepts_other_column_types(self):
        statements=self.run_check(self.metadata(),apply=True)
        self.assertEqual(sum("CREATE TABLE IF NOT EXISTS" in sql for sql in statements),3)
        self.assertEqual(sum("ALTER TABLE" in sql for sql in statements),2)

    def test_only_actual_attribution_type_or_length_is_rejected(self):
        for table,kind,length in [("admwf_case_line","enum",None),("admwf_appeal","varchar",16)]:
            rows=self.metadata()
            next(row for row in rows if row["table_name"]==table and row["column_name"]=="problem_attribution").update(data_type=kind,max_length=length)
            with self.subTest(table=table),self.assertRaisesRegex(SystemExit,table+r"\.problem_attribution"):
                self.run_check(rows)

    def test_missing_attribution_column_is_still_rejected(self):
        rows=[row for row in self.metadata() if not (row["table_name"]=="admwf_case_line" and row["column_name"]=="problem_attribution")]
        with self.assertRaisesRegex(SystemExit,"missing=admwf_case_line.problem_attribution"):
            self.run_check(rows)

    def test_missing_comment_is_still_rejected(self):
        rows=self.metadata();rows[0]["column_comment"]=""
        with self.assertRaisesRegex(SystemExit,"uncommented=admwf_line_context.line_id"):
            self.run_check(rows)
