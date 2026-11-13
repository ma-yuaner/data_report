from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import re
import sqlite3
import unittest
from unittest.mock import patch
from data_report_api.services.admwf.operations import AdmOperations, DEFAULT_CONFIG, DEFAULT_SLA, DATASET, decorate, due_expression
from data_report_api.services.admwf.policy import AdmError
from data_report_api.services.admwf.service import _json_value

class OperationsTest(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;self.addCleanup(self.db.close)
  self.db.create_function('JSON_UNQUOTE',1,lambda value:value)
  self.db.create_function('TIMESTAMPDIFF',3,lambda unit,a,b:(datetime.fromisoformat(b)-datetime.fromisoformat(a)).total_seconds()/60)
  self.db.executescript("""
  CREATE TABLE admwf_case(id INTEGER,adm_no TEXT,issued_date TEXT,created_at TEXT,case_status TEXT,currency TEXT,original_amount DECIMAL,cny_amount DECIMAL,airline_name TEXT,line_defaults_json TEXT,issuer_type TEXT,coordinator_name TEXT,coordinator_id INTEGER,master_recovery_status TEXT,pending_leader_transfer_json TEXT,master_recovery_due_at TEXT,reply_deadline TEXT);
  CREATE TABLE admwf_case_line(id INTEGER,case_id INTEGER,line_status TEXT,original_amount DECIMAL,cny_amount DECIMAL,supplier_name TEXT,ota_name TEXT,leader_name TEXT,operator_name TEXT,problem_attribution TEXT,appeal_status TEXT,diff_match_status TEXT,leader_id INTEGER,operator_id INTEGER,version_no INTEGER DEFAULT 1);
  CREATE TABLE admwf_line_context(line_id INTEGER PRIMARY KEY,case_id INTEGER,cause_category TEXT,cause_detail TEXT,evidence_note TEXT,blocking_reason TEXT,responsible_link TEXT,updated_by_id INTEGER,updated_at TEXT);
  CREATE TABLE admwf_transfer(id INTEGER,line_id INTEGER,status TEXT,to_operator_id INTEGER,to_operator_name TEXT,requested_at TEXT);
  CREATE TABLE admwf_operation_log(id INTEGER,case_id INTEGER,line_id INTEGER,to_status TEXT,from_status TEXT,occurred_at TEXT);
  CREATE TABLE admwf_operations_config(id INTEGER PRIMARY KEY,settings_json TEXT,updated_by_id INTEGER,updated_at TEXT);
  CREATE TABLE admwf_reminder_delivery(id INTEGER PRIMARY KEY,delivery_key TEXT UNIQUE,slot_key TEXT,endpoint_id TEXT,status TEXT,task_count INTEGER,message_summary TEXT,created_at TEXT,finished_at TEXT);
  """)
  now=datetime(2026,11,13,9,30)
  intake=json.dumps({'masterIntake':{'supplierName':'供应商甲','businessCategory':'票务','penaltyReasonType':'重复预定'},'leaderName':'组长甲'})
  self.db.execute("INSERT INTO admwf_case VALUES(1,'6007100530','2026-11-12','2026-11-10 00:00:00','ACTIVE','CNY',100,100,'CI',?,'AIRLINE','负责人',9,'NOT_REQUIRED',NULL,NULL,'2026-11-20 00:00:00')",(intake,))
  for id,amount,platform in [(11,40,'平台甲'),(12,60,'平台乙')]: self.db.execute("INSERT INTO admwf_case_line(id,case_id,line_status,original_amount,cny_amount,supplier_name,ota_name,leader_name,operator_name,problem_attribution,appeal_status,diff_match_status,leader_id,operator_id) VALUES(?,1,'PROCESSING',?,?,'供应商甲',?,'组长甲','操作员甲','HUMAN','NO_APPEAL','PENDING',3,4)",(id,amount,amount,platform))
  self.db.execute("INSERT INTO admwf_operation_log VALUES(1,1,11,'PROCESSING','PENDING_ACCEPT','2026-11-11 09:00:00')")
  self.db.commit()
  db=self.db
  class Cursor:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def execute(self,sql,params=()):
    due,_=due_expression(DEFAULT_CONFIG)
    replacement="min(datetime(entered_at,'+' || (CASE stage "+" ".join("WHEN %s THEN %s" for _ in DEFAULT_SLA)+" ELSE 24 END) || ' hours'),COALESCE(deadline,'9999-12-31 00:00:00'))"
    sql=sql.replace(due,replacement).replace('TIMESTAMPDIFF(MINUTE,',"TIMESTAMPDIFF('MINUTE',")
    sql=sql.replace('INSERT IGNORE','INSERT OR IGNORE').replace(' FOR UPDATE','')
    if 'ON DUPLICATE KEY UPDATE' in sql:
     first,last=sql.split('ON DUPLICATE KEY UPDATE');key='line_id' if 'admwf_line_context' in first else 'id'
     sql=first+'ON CONFLICT('+key+') DO UPDATE SET '+re.sub(r'VALUES\((\w+)\)',r'excluded.\1',last)
    self.result=db.execute(sql.replace('%s','?'),tuple(value.isoformat(sep=' ') if isinstance(value,datetime) else value.isoformat() if isinstance(value,date) else str(value) if isinstance(value,Decimal) else value for value in params));self.rowcount=self.result.rowcount
   def fetchone(self):
    row=self.result.fetchone();return dict(row) if row else None
   def fetchall(self):return [dict(row) for row in self.result.fetchall()]
  class Connection:
   def cursor(self):return Cursor()
  class Repository:
   @contextmanager
   def transaction(self):
    with db:yield Connection()
   def _lock_case_and_line(self,connection,case_id,line_id):
    return dict(db.execute('SELECT * FROM admwf_case WHERE id=?',(case_id,)).fetchone()),dict(db.execute('SELECT * FROM admwf_case_line WHERE id=?',(line_id,)).fetchone())
   def _next_event_no(self,*args):return 1
   def append_operation_log(self,*args,**kwargs):pass
  self.repo=Repository();self.sent=[]
  self.ops=AdmOperations({'ADM_EXTERNAL_DELIVERY_ENABLED':True},repository=self.repo,notifier=lambda url,payload:self.sent.append(payload) or {'errcode':0})
  self.ops._endpoint=lambda id:{'url':'https://example.invalid/not-used'}
  self.user={'id':9,'permissions':['adm.analysis','adm.notify.manage','adm.review','adm.view']}
  self.query={'startDate':'2026-11-01','endDate':'2026-11-30','dimension':'supplier'}

 def test_master_amount_not_multiplied_by_split_and_drill_filters(self):
  result=self.ops.analysis(self.user,self.query)
  self.assertEqual(result['totals']['case_count'],1)
  self.assertEqual(result['totals']['master_amount'],100)
  self.assertEqual(result['groups'][0]['amount'],100)
  self.assertEqual(result['groups'][0]['line_count'],2)
  detail=self.ops.rows(self.user,{**self.query,'platform':'平台甲'})
  self.assertEqual(detail['total'],1)
  self.assertEqual(detail['items'][0]['line_id'],11)
  result=self.ops.analysis(self.user,{**self.query,'dimension':'platform'})
  self.assertEqual(sum(row['amount'] for row in result['groups']),100)

 def test_missing_root_cause_and_saved_classification(self):
  self.ops.save_context(self.user,1,11,{'causeCategory':'FORCE_MAJEURE','causeDetail':'天气','evidenceNote':'附件A','blockingReason':'等待航司确认'})
  row=self.ops.context(self.user,1,11)
  self.assertEqual(row['cause_category'],'FORCE_MAJEURE')
  result=self.ops.analysis(self.user,{**self.query,'dimension':'cause','cause':'FORCE_MAJEURE'})
  self.assertEqual(result['groups'][0]['line_count'],1)
  with self.assertRaises(AdmError):self.ops.save_context({'id':99,'permissions':['adm.handle']},1,11,{'causeCategory':'HUMAN'})

 def test_permissions_and_sql_injection_dimensions(self):
  with self.assertRaises(AdmError):self.ops.analysis({'id':4,'permissions':['adm.view']},self.query)
  with self.assertRaises(AdmError):self.ops.analysis(self.user,{**self.query,'dimension':'stage;DROP TABLE x'})
  with self.assertRaises(AdmError):self.ops.rows(self.user,{'startDate':'2026-12-01','endDate':'2026-11-01'})

 def test_stage_timer_uses_transition_not_edits_and_boundaries(self):
  rows=self.ops.rows(self.user,self.query)['items']
  line=next(row for row in rows if row['line_id']==11)
  self.assertEqual(line['entered_at'],'2026-11-11 09:00:00')
  now=datetime(2026,11,13,9,30)
  row=decorate({'stage':'PENDING_ACCEPT','cause':'UNKNOWN','entered_at':now-timedelta(hours=72),'deadline':None,'active':1},DEFAULT_CONFIG,now)
  self.assertFalse(row['overdue']);self.assertTrue(row['soon'])
  row=decorate({'stage':'PROCESSING','cause':'UNKNOWN','entered_at':now-timedelta(hours=25),'deadline':None,'active':0},DEFAULT_CONFIG,now)
  self.assertFalse(row['overdue'])

 def test_notification_two_slots_idempotent_and_failure_not_retried(self):
  settings={**DEFAULT_CONFIG,'enabled':True,'endpointId':'1'}
  self.ops.save_settings(self.user,settings)
  with patch('data_report_api.services.admwf.operations.business_now',return_value=datetime(2026,11,13,9,30)):
   self.assertEqual(self.ops.send_due(datetime(2026,11,13,9,30)),1)
   self.assertEqual(self.ops.send_due(datetime(2026,11,13,9,31)),0)
   self.assertEqual(len(self.sent),1)
   self.assertIn('操作员甲',self.sent[0]['text']['content'])
   self.assertEqual(self.ops.send_due(datetime(2026,11,13,16,30)),1)
   self.assertEqual(self.ops.send_due(datetime(2026,11,13,17,30)),0)
  self.assertEqual(len(self.sent),2)

 def test_disabled_gate_and_preview_do_not_send(self):
  self.ops.preview(self.user)
  self.assertFalse(self.sent)
  self.ops.config['ADM_EXTERNAL_DELIVERY_ENABLED']=False
  self.assertEqual(self.ops.send_due(datetime(2026,11,13,9,30)),0)
  self.assertFalse(self.sent)
  with self.assertRaises(AdmError):self.ops.save_settings(self.user,{**DEFAULT_CONFIG,'enabled':True})

 def test_transport_unknown_is_not_reported_as_sent_or_retried(self):
  self.ops.save_settings(self.user,{**DEFAULT_CONFIG,'enabled':True,'endpointId':'1'})
  def fail(*args):raise TimeoutError()
  self.ops.notifier=fail
  self.assertEqual(self.ops.send_due(datetime(2026,11,13,9,30)),0)
  self.assertEqual(self.db.execute('SELECT status FROM admwf_reminder_delivery').fetchone()[0],'UNKNOWN')
  self.ops.notifier=lambda *args:{'errcode':0}
  self.assertEqual(self.ops.send_due(datetime(2026,11,13,9,31)),0)

 def test_report_has_summary_groups_and_exact_detail_scope(self):
  from openpyxl import load_workbook
  book=load_workbook(self.ops.report(self.user,{**self.query,'platform':'平台甲'}),read_only=True)
  self.addCleanup(book.close)
  self.assertEqual(book.sheetnames,['统计说明','维度分析','阶段时效','跟进明细'])
  rows=list(book['跟进明细'].values)
  self.assertEqual(len(rows),2)
  self.assertEqual(rows[1][0],'6007100530')
  self.assertEqual(rows[1][4],'平台甲')

 def test_http_report_returns_file_and_settings_preserve_stage_keys(self):
  from flask import Flask, Blueprint, g
  from data_report_api.api.admwf import register_routes
  app=Flask(__name__);api=Blueprint('test_operations',__name__);register_routes(api);app.register_blueprint(api)
  @app.before_request
  def actor():g.current_user=self.user
  original=self.ops.report
  with patch.object(AdmOperations,'report',lambda *args:original(self.user,self.query)):
   response=app.test_client().get('/v1/adm/analysis/report')
   self.assertEqual(response.status_code,200)
   self.assertTrue(response.data.startswith(b'PK'))
  with patch.object(AdmOperations,'public_settings',return_value={**DEFAULT_CONFIG,'history':[]}):
   response=app.test_client().get('/v1/adm/operations/settings')
   self.assertIn('PENDING_REVIEW',response.json['data']['slaHours'])

 def test_group_and_reminder_capacity_limits_reject_without_partial_delivery(self):
  for id in range(100,301):
   self.db.execute("INSERT INTO admwf_case_line(id,case_id,line_status,original_amount,cny_amount,supplier_name,ota_name,leader_name,operator_name,problem_attribution,appeal_status,diff_match_status,leader_id,operator_id) VALUES(?,1,'PROCESSING',0,0,'供应商甲',?,'组长甲','操作员甲','HUMAN','NO_APPEAL','PENDING',3,4)",(id,'平台'+str(id)))
  with self.assertRaisesRegex(AdmError,'200'):
   self.ops.analysis(self.user,{**self.query,'dimension':'platform'})
  self.db.executemany("INSERT INTO admwf_case_line(id,case_id,line_status,original_amount,cny_amount,supplier_name,ota_name,leader_name,operator_name,problem_attribution,appeal_status,diff_match_status,leader_id,operator_id) VALUES(?,1,'PROCESSING',0,0,'供应商甲','平台甲','组长甲','操作员甲','HUMAN','NO_APPEAL','PENDING',3,4)",[(id,) for id in range(1000,11000)])
  with self.assertRaisesRegex(AdmError,'10000'):self.ops.active_rows()
  self.assertFalse(self.sent)

 def test_schema_dictionary_covers_all_new_columns(self):
  from pathlib import Path
  from data_report_api.admwf_schema import columns,SCHEMA
  required=columns()
  self.assertEqual(sum(len(value) for value in required.values()),22)
  self.assertEqual(SCHEMA.read_text(encoding='utf-8'),(Path(__file__).resolve().parents[2]/'docs/sql/admwf-operations-20261113.sql').read_text(encoding='utf-8'))

 def test_platform_rejection_is_logged_as_failed(self):
  self.ops.save_settings(self.user,{**DEFAULT_CONFIG,'enabled':True,'endpointId':'1'})
  self.ops.notifier=lambda *args:{'errcode':40001}
  self.assertEqual(self.ops.send_due(datetime(2026,11,13,9,30)),0)
  self.assertEqual(self.db.execute('SELECT status FROM admwf_reminder_delivery').fetchone()[0],'FAILED')

 def test_cause_edit_preserves_canonical_value_and_changes_version(self):
  before=self.db.execute('SELECT version_no FROM admwf_case_line WHERE id=11').fetchone()[0]
  self.ops.save_context(self.user,1,11,{'causeCategory':'FORCE_MAJEURE','causeDetail':'天气'})
  row=self.db.execute('SELECT version_no,problem_attribution FROM admwf_case_line WHERE id=11').fetchone()
  self.assertEqual(tuple(row),(before+1,'FORCE_MAJEURE'))
  self.assertEqual(self.ops.context(self.user,1,11)['cause_category'],'FORCE_MAJEURE')

 def test_unassigned_person_group_drills_to_unassigned_only(self):
  self.db.execute("UPDATE admwf_case_line SET operator_id=NULL,operator_name=NULL WHERE id=12")
  data=self.ops.analysis(self.user,{**self.query,'dimension':'person'})
  bucket=next(row['bucket'] for row in data['groups'] if row['label']=='未分配')
  self.assertEqual(bucket,'__UNASSIGNED__')
  rows=self.ops.rows(self.user,{**self.query,'person':bucket})
  self.assertEqual(rows['total'],1)
  self.assertEqual(rows['items'][0]['line_id'],12)
