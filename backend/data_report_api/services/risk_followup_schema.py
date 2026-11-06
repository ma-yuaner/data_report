"""Explicit deployment check/apply; never invoked by an HTTP request."""
import argparse
import re
import sys

from .risk_auto_store import RiskAutoStore

TABLES = {
    'bi_risk_followup_cases': ('id,version,conclusion,disposition,state,assignee,next_at,first_seen,special,body,updated_at', ('id',)),
    'bi_risk_order_reviews': ('order_id,issue_date,version,case_id,body', ('order_id', 'issue_date')),
    'bi_risk_followup_events': ('seq,id,case_id,order_id,issue_date,body,created_at', ('seq',)),
    'bi_risk_review_policies': ('id,body,created_at', ('id',)),
    'bi_risk_followup_requests': ('id,actor,digest,response,created_at', ('id',)),
}


def statements(sql):
    parts = [part.strip() for part in re.sub(r'(?m)^--.*$', '', sql).split(';') if part.strip()]
    if len(parts) != 6 or parts[0] != 'USE sibebid' or any(not part.startswith('CREATE TABLE IF NOT EXISTS ' + name + ' (') for part, name in zip(parts[1:], TABLES)):
        raise ValueError('Unexpected follow-up schema; nothing executed')
    return parts[1:]


def check(db, tables=None):
    for table, (columns, primary) in (tables or TABLES).items():
        db.execute('SELECT ' + columns + ' FROM ' + table + ' LIMIT 0').fetchall()
        row = db.execute('SELECT ENGINE AS engine FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=?', (table,)).fetchone()
        if not row or str(row['engine']).upper() != 'INNODB':
            raise ValueError('Follow-up tables must use InnoDB')
        keys = db.execute("SELECT COLUMN_NAME AS name FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION", (table,)).fetchall()
        if tuple(row['name'] for row in keys) != primary:
            raise ValueError('Follow-up table primary key mismatch')


def main():
    parser = argparse.ArgumentParser(description='Check dedicated follow-up tables; --apply explicitly reads DDL from stdin')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    from ..config import Config
    values = {key: getattr(Config, key) for key in dir(Config) if key.isupper()}
    ddl = statements(sys.stdin.read()) if args.apply else []
    try:
        with RiskAutoStore(values).db() as db:
            for sql in ddl:
                db.execute(sql)
            check(db)
    except Exception:
        raise SystemExit('FOLLOWUP_SCHEMA_NOT_READY: check approved sibebid tables, columns, InnoDB and keys; preserve data. DDL may have partially created NEW tables; no services switched.') from None
    print('FOLLOWUP_SCHEMA_READY: five dedicated tables checked; no ERP/ETL writes or business acceptance implied.')


if __name__ == '__main__':
    main()
