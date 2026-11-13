"""Explicit ADM operations schema check/apply entry point. Never runs on import."""
import argparse
from pathlib import Path
import re
from .config import Config
from .services.admwf.repository import AdmWorkflowRepository

SCHEMA=Path(__file__).parent / "services" / "admwf" / "operations_schema.sql"

def columns():
    text=SCHEMA.read_text(encoding="utf-8")
    return {name: re.findall(r"^ ([a-z_]+) (?:BIGINT|INT|CHAR|VARCHAR|TEXT|JSON|DATETIME)\b",body,re.M)
        for name,body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\) ENGINE=",text,re.S)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--apply",action="store_true");args=parser.parse_args()
    repo=AdmWorkflowRepository(vars(Config))
    with repo.transaction() as connection,connection.cursor() as cursor:
        if args.apply:
            for statement in SCHEMA.read_text(encoding="utf-8").split(';'):
                if statement.strip(): cursor.execute(statement)
        required=columns()
        required.update(admwf_case_line=["problem_attribution"],admwf_appeal=["problem_attribution"])
        cursor.execute("SELECT TABLE_NAME AS table_name,COLUMN_NAME AS column_name,COLUMN_COMMENT AS column_comment,DATA_TYPE AS data_type,CHARACTER_MAXIMUM_LENGTH AS max_length FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name IN ("+','.join(['%s']*len(required))+")",tuple(required))
        rows=cursor.fetchall()
        actual={(row["table_name"],row["column_name"]):row["column_comment"] for row in rows}
        if any(row["table_name"] in {"admwf_case_line","admwf_appeal"} and (row["data_type"]!="varchar" or int(row.get("max_length") or 0)<32) for row in rows):
            raise SystemExit("ADM attribution columns require reviewed --apply migration")
        missing=[table+'.'+column for table,fields in required.items() for column in fields if (table,column) not in actual]
        uncommented=[table+'.'+column for table,fields in required.items() for column in fields if (table,column) in actual and not actual[(table,column)]]
        if missing or uncommented: raise SystemExit("ADM operations schema not ready; missing="+','.join(missing)+" uncommented="+','.join(uncommented)+". Run with --apply after review.")
    print("ADM operations schema verified: "+str(sum(len(value) for value in required.values()))+" documented columns")

if __name__=="__main__":main()
