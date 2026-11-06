"""Explicit two-table deployment; does not migrate or rewrite original evidence."""
import argparse
import re
import sys
from .risk_auto_store import RiskAutoStore
from .risk_followup_schema import check

TABLES={
    'bi_risk_config_evidence':('id,order_id,issue_date,original_result_id,body,created_at',('id',)),
    'bi_risk_config_observations':('seq,id,evidence_id,request_id,request_hash,body,created_at',('seq',)),
}


def statements(sql):
    parts=[part.strip() for part in re.sub(r'(?m)^--.*$','',sql).split(';') if part.strip()]
    if len(parts)!=3 or parts[0]!='USE sibebid' or any(not part.startswith('CREATE TABLE IF NOT EXISTS '+name+' (') for part,name in zip(parts[1:],TABLES)):
        raise ValueError('Unexpected config evidence DDL; nothing executed')
    return parts[1:]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    from ..config import Config
    config={k:getattr(Config,k) for k in dir(Config) if k.isupper()}
    ddl=statements(sys.stdin.read()) if args.apply else []
    try:
        with RiskAutoStore(config).db() as db:
            for sql in ddl:db.execute(sql)
            check(db,TABLES)
            for table in TABLES:
                indexes=db.execute('SELECT INDEX_NAME AS name,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columns_list,MIN(NON_UNIQUE) AS non_unique FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? GROUP BY INDEX_NAME',(table,)).fetchall()
                unique={r['columns_list'] for r in indexes if not int(r['non_unique'])}
                required={'order_id,issue_date'} if table=='bi_risk_config_evidence' else {'id','request_id'}
                if not required<=unique:raise ValueError('evidence uniqueness contract not ready')
    except Exception:
        raise SystemExit('CONFIG_EVIDENCE_SCHEMA_NOT_READY: preserve existing data, check new tables/keys/InnoDB; no service switch. DDL may have partially created NEW tables.') from None
    print('CONFIG_EVIDENCE_SCHEMA_READY')


if __name__=='__main__':main()
