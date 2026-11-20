"""Export only platform SLA thresholds for the separate ETL server."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile

FIELDS = ("platform", "auditVoluntary", "auditInvoluntary", "operationVoluntary", "operationInvoluntary")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with closing(sqlite3.connect(args.store.resolve().as_uri()+"?mode=ro", uri=True)) as db:
        current = db.execute("SELECT revision, records FROM change_sla_limits WHERE id=1").fetchone()
    if not current:
        parser.error("时限配置尚未导入")
    rows = [{key: row.get(key, "") for key in FIELDS} for row in json.loads(current[1])]
    if not rows:
        parser.error("时限配置为空")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent, delete=False) as temp:
        path = Path(temp.name)
        try:
            json.dump(rows, temp, ensure_ascii=False)
            temp.close()
            os.replace(path, args.output)
        finally:
            path.unlink(missing_ok=True)
    print(f"revision={current[0]} rules={len(rows)}")


if __name__ == "__main__":
    main()
