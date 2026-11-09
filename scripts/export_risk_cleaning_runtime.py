"""Export canonical rules offline into the standalone ETL; no application/Flask dependency."""
import argparse,ast,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SERVICES=ROOT/'backend/data_report_api/services'
MODULES=('risk_rule_priority','risk_commission_rule','risk_loss_threshold_config','risk_historical_threshold','risk_threshold_facts','risk_child_loss','risk_bet_loss','risk_ancillary_loss','risk_order_profit','risk_evidence_batch')


def selected(path,names):
    raw=path.read_text(encoding='utf-8');tree=ast.parse(raw)
    return '\n\n'.join(ast.get_source_segment(raw,node) for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-repo',required=True,type=Path)
    parser.add_argument('--check',action='store_true');args=parser.parse_args()
    target=args.target_repo/'etl_scripts/automation/risk_cleaning_runtime'
    files={'__init__.py':'"""Generated risk cleaning runtime; edit canonical application modules."""\n'}
    for name in MODULES:files[name+'.py']=(SERVICES/(name+'.py')).read_text(encoding='utf-8').replace('\r\n','\n')
    files['risk_order_evidence.py']='import re\nfrom datetime import date,datetime\nfrom decimal import Decimal\n\n'+selected(SERVICES/'risk_order_evidence.py',{'EvidenceError','order_id','_json_value','_rows'})
    files['risk_verification_flow.py']=selected(SERVICES/'risk_verification_flow.py',{'FlowError'})
    files['engine.py']='from .risk_commission_rule import RULE_ID,evaluate_commission_loss\nfrom .risk_child_loss import CHILD_REASON,ANCILLARY_REASON,BET_REASONS,NORMAL_REASONS,PROFIT_REASONS,SUPPORTED_REASONS,ORDER_FIELDS,read_child_evidence,evaluate_child\nfrom .risk_bet_loss import evaluate_bet,evaluate_normal\nfrom .risk_ancillary_loss import ANCILLARY_SQL,MAX_ANCILLARY_ROWS,evaluate_ancillary\nfrom .risk_order_profit import evaluate_order_profit\nfrom .risk_historical_threshold import HistoricalThresholds\nfrom .risk_order_evidence import _rows,order_id\nfrom .risk_verification_flow import FlowError\n\n'+selected(SERVICES/'risk_auto_verification.py',{'evaluate','read_evidence_cursor'})
    hashes={name:hashlib.sha256(content.encode()).hexdigest() for name,content in files.items()}
    digest=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    tree=ast.parse(files['risk_commission_rule.py']);version=next(n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='RULE_ID' for t in n.targets))
    manifest=json.dumps({'ruleVersion':version,'sha256':digest,'files':hashes},sort_keys=True,indent=2)+'\n'
    outputs={target/name:content for name,content in files.items()}
    outputs[target/'manifest.json']=manifest;outputs[SERVICES/'risk_engine_bundle.meta.json']=manifest
    for path,content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8')!=content:raise SystemExit('Risk runtime drift: '+str(path))
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
    print(json.dumps({'offline':True,'checked':args.check,'ruleVersion':version,'sha256':digest,'modules':len(files)}))


if __name__=='__main__':main()
