"""Offline export of the analysis contract; no Flask or application deployment on 216."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / 'backend/data_report_api/services'


def select(path, names):
    source = path.read_text(encoding='utf-8')
    parts = []
    for node in ast.parse(source).body:
        identifiers = {node.name} if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else {target.id for target in node.targets if isinstance(target, ast.Name)} if isinstance(node, ast.Assign) else set()
        if identifiers & names:
            parts.append(ast.get_source_segment(source, node))
    return '\n\n'.join(parts) + '\n'


def outputs(target_repo):
    facts = ('import hashlib,json\nfrom pathlib import Path\n'
             'from risk_cleaning_runtime.engine import RULE_ID,SUPPORTED_REASONS\n'
             'from risk_cleaning_runtime.risk_order_evidence import EvidenceError\n')
    facts += select(SERVICES/'risk_prepared_facts.py', {'PROJECTION','JOINS','STATUS_PROJECTION','stamp','fact'})
    facts += '\ndef engine_hash():\n    return json.loads((Path(__file__).parent.parent/"risk_cleaning_runtime/manifest.json").read_text(encoding="utf-8"))["sha256"]\n'
    contract = 'from datetime import date\nfrom risk_cleaning_runtime.risk_order_evidence import EvidenceError\n'
    contract += select(SERVICES/'risk_verification_overview.py', {'_period','METRIC_JOIN','METRIC_PROFIT','METRIC_FIELDS'})
    snapshot = (SERVICES/'risk_analytics_snapshot.py').read_text(encoding='utf-8')
    for before, after in [('.risk_auto_store','.store'),('.risk_order_evidence','risk_cleaning_runtime.risk_order_evidence'),('.risk_prepared_facts','.facts'),('.risk_commission_rule','risk_cleaning_runtime.risk_commission_rule'),('.risk_verification_overview','.contract')]:
        snapshot = snapshot.replace('from '+before+' import', 'from '+after+' import')
    snapshot = snapshot.replace('        from ..config import Config\n        config={key:getattr(Config,key) for key in dir(Config) if key.isupper()}','        config={}')
    store = (SERVICES/'risk_auto_store.py').read_text(encoding='utf-8')
    store = store.replace('from .data_source import DataSource', 'from .connection import DataSource')
    files = {'__init__.py':'"""Generated analysis runtime. Edit application source and re-export."""\n', 'facts.py':facts,'contract.py':contract,'snapshot.py':snapshot,'store.py':store}
    # Connection adapter stays ETL-owned: shared config get_connect/raw_connection only.
    digest={name:hashlib.sha256(value.encode()).hexdigest() for name,value in files.items()}
    manifest={'version':'risk-analytics-v4','files':digest,'ruleVersion':json.loads((SERVICES/'risk_engine_bundle.meta.json').read_text(encoding='utf-8'))['ruleVersion'],'ruleHash':json.loads((SERVICES/'risk_engine_bundle.meta.json').read_text(encoding='utf-8'))['sha256']}
    files['manifest.json']=json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    return {target_repo/'etl_scripts/automation/risk_analytics_runtime'/name:value for name,value in files.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-repo',type=Path,required=True);parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    for path,content in outputs(args.target_repo).items():
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8')!=content:raise SystemExit('Analytics runtime drift: '+path.name)
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8',newline='\n')
    print(json.dumps({'offline':True,'checked':args.check,'databaseAccessed':False,'files':6}))

if __name__=='__main__':main()
