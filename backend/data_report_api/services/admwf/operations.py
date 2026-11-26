"""ADM operational analytics, process context and scheduled group reminders."""
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
import re
from urllib import request as urlrequest

from .policy import AdmError, business_now, require, identity, display_name
from .repository import AdmWorkflowRepository
from .service import require_any

CAUSES = {"HUMAN":"人为", "SYSTEM":"系统", "EXTERNAL":"外部规则/平台", "BUSINESS":"业务原因", "FORCE_MAJEURE":"不可抗力", "UNKNOWN":"待查明"}
STAGES = {"LEADER_DECISION":"恢复判断", "OWNER_RECOVERY":"待操作恢复", "RECOVERING":"正在恢复", "RECOVERED":"待录入订单",
          "PENDING_LEADER":"待分配组长", "PENDING_OPERATOR":"待派单", "PENDING_ACCEPT":"待接单", "PROCESSING":"办理中",
          "PENDING_REVIEW":"待审核", "WAITING_DIFF":"待匹配差异单", "WAITING_COLLECTION":"待回款", "COMPLETED":"已完成",
          "TRANSFER_ACCEPT":"待确认转派", "NOT_REQUIRED":"待录入订单"}
DEFAULT_SLA = {key: 72 if key in {"LEADER_DECISION","PENDING_LEADER","PENDING_OPERATOR","PENDING_ACCEPT"} else 48 if key == "RECOVERING" else 24 for key in STAGES if key != "COMPLETED"}
DEFAULT_CONFIG = {"enabled":False,"endpointId":None,"times":["09:30","16:30"],"slaHours":DEFAULT_SLA,"baseUrl":""}
DIMENSIONS = {"airline":"airline", "supplier":"supplier", "platform":"platform", "category":"category", "penalty":"penalty",
              "cause":"cause", "leader":"leader", "operator":"operator", "person":"person_id", "stage":"stage", "source":"source"}
MASTER_DIMENSIONS = {"airline","supplier","category","penalty","source"}

# Each row is exactly one effective order, or a master without any effective orders.
DATASET = """
SELECT c.id AS case_id,l.id AS line_id,c.adm_no,c.issued_date,c.created_at,c.case_status,c.currency,
 c.original_amount AS master_original,c.cny_amount AS master_cny,l.original_amount AS line_original,l.cny_amount AS line_cny,
 COALESCE(NULLIF(c.airline_name,''),'未填写') AS airline,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(c.line_defaults_json,'$.masterIntake.supplierName')),''),NULLIF(l.supplier_name,''),'未填写') AS supplier,
 COALESCE(NULLIF(l.ota_name,''),'未填写') AS platform,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(c.line_defaults_json,'$.masterIntake.businessCategory')),''),'未填写') AS category,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(c.line_defaults_json,'$.masterIntake.penaltyReasonType')),''),'未填写') AS penalty,
 c.issuer_type AS source,COALESCE(NULLIF(l.leader_name,''),JSON_UNQUOTE(JSON_EXTRACT(c.line_defaults_json,'$.leaderName')),'未分配') AS leader,
 COALESCE(NULLIF(l.operator_name,''),'未分配') AS operator,
 CASE WHEN l.problem_attribution='PLATFORM' THEN 'EXTERNAL'
 WHEN l.problem_attribution IN ('HUMAN','SYSTEM','EXTERNAL','BUSINESS','FORCE_MAJEURE','UNKNOWN') THEN l.problem_attribution
 ELSE COALESCE(x.cause_category,'UNKNOWN') END AS cause,
 x.cause_detail,x.evidence_note,x.blocking_reason,x.responsible_link,
 l.appeal_status,l.diff_match_status,
 CASE WHEN tr.id IS NOT NULL OR c.pending_leader_transfer_json IS NOT NULL THEN 'TRANSFER_ACCEPT'
 ELSE CASE WHEN l.line_status='PENDING_LEADER' AND l.leader_id>0 AND COALESCE(l.operator_id,0)=0 THEN 'PENDING_OPERATOR' ELSE COALESCE(l.line_status,c.master_recovery_status,'PENDING_LEADER') END END AS stage,
 CASE WHEN tr.id IS NOT NULL THEN tr.to_operator_name
 WHEN c.pending_leader_transfer_json IS NOT NULL THEN JSON_UNQUOTE(JSON_EXTRACT(c.pending_leader_transfer_json,'$.toName'))
 WHEN l.line_status='PENDING_LEADER' AND l.leader_id>0 THEN l.leader_name
 WHEN l.line_status IN ('PENDING_LEADER','PENDING_REVIEW','WAITING_DIFF','WAITING_COLLECTION') THEN c.coordinator_name
 WHEN l.line_status='PENDING_OPERATOR' THEN l.leader_name
 WHEN l.id IS NOT NULL THEN l.operator_name
 WHEN c.master_recovery_status IN ('OWNER_RECOVERY','RECOVERING') THEN c.coordinator_name
 ELSE JSON_UNQUOTE(JSON_EXTRACT(c.line_defaults_json,'$.leaderName')) END AS person,
 CASE WHEN tr.id IS NOT NULL THEN tr.to_operator_id
 WHEN c.pending_leader_transfer_json IS NOT NULL THEN JSON_UNQUOTE(JSON_EXTRACT(c.pending_leader_transfer_json,'$.toId'))
 WHEN l.line_status='PENDING_LEADER' AND l.leader_id>0 THEN l.leader_id
 WHEN l.line_status IN ('PENDING_LEADER','PENDING_REVIEW','WAITING_DIFF','WAITING_COLLECTION') THEN c.coordinator_id
 WHEN l.line_status='PENDING_OPERATOR' THEN l.leader_id
 WHEN l.id IS NOT NULL THEN l.operator_id
 WHEN c.master_recovery_status IN ('OWNER_RECOVERY','RECOVERING') THEN c.coordinator_id
 ELSE JSON_UNQUOTE(JSON_EXTRACT(c.line_defaults_json,'$.leaderId')) END AS person_id,
 COALESCE(tr.requested_at,(SELECT MAX(o.occurred_at) FROM admwf_operation_log o WHERE o.case_id=c.id
 AND ((l.id IS NOT NULL AND o.line_id=l.id AND o.to_status=l.line_status) OR
 (l.id IS NULL AND o.line_id IS NULL AND o.to_status=c.master_recovery_status))
 AND COALESCE(o.from_status,'')<>COALESCE(o.to_status,'')),c.created_at) AS entered_at,
 CASE WHEN l.id IS NULL AND c.master_recovery_status='RECOVERING' THEN c.master_recovery_due_at ELSE c.reply_deadline END AS deadline,
 CASE WHEN l.line_status='COMPLETED' THEN 0 WHEN c.case_status<>'ACTIVE' THEN 0 ELSE 1 END AS active
FROM admwf_case c
LEFT JOIN admwf_case_line l ON l.case_id=c.id AND l.line_status NOT IN ('VOIDED','HISTORICAL')
LEFT JOIN admwf_line_context x ON x.line_id=l.id
LEFT JOIN admwf_transfer tr ON tr.id=(SELECT MAX(t.id) FROM admwf_transfer t WHERE t.line_id=l.id AND t.status='PENDING')
WHERE c.case_status NOT IN ('DELETED','VOIDED','HISTORICAL')
"""


def parsed_time(value):
    if not value: return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def decorate(row, settings, now=None):
    row = dict(row)
    now = now or business_now()
    entered = parsed_time(row.get("entered_at")) or now
    hours = settings["slaHours"].get(row["stage"])
    due = entered + timedelta(hours=hours) if hours else None
    deadline = parsed_time(row.get("deadline"))
    if deadline is not None and (due is None or deadline < due): due = deadline
    active = bool(row.get("active"))
    row.update(stage_name=STAGES.get(row["stage"],row["stage"]),cause_name=CAUSES.get(row["cause"],"待查明"),
               person=row.get("person") or "未分配",elapsed_hours=round(max(0,(now-entered).total_seconds()/3600),1),due_at=due,
               overdue=active and due is not None and now>due,
               soon=active and due is not None and now<=due<=now+timedelta(hours=4))
    return row


def due_expression(settings):
    pairs=list(settings["slaHours"].items())
    case="CASE stage "+" ".join("WHEN %s THEN %s" for _ in pairs)+" ELSE 24 END"
    return "LEAST(DATE_ADD(entered_at, INTERVAL ("+case+") HOUR),COALESCE(deadline,'9999-12-31 00:00:00'))", [value for pair in pairs for value in pair]


class AdmOperations:
    def __init__(self, config, repository=None, notifier=None):
        self.config = config
        self.repo = repository or AdmWorkflowRepository(config)
        self.notifier = notifier

    def settings(self):
        with self.repo.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT settings_json FROM admwf_operations_config WHERE id=1")
            row = cursor.fetchone()
        saved = json.loads(row["settings_json"]) if row else {}
        return {**DEFAULT_CONFIG,**saved,"slaHours":{**DEFAULT_SLA,**saved.get("slaHours",{})}}

    def public_settings(self, user):
        require(user,"adm.notify.manage")
        settings = self.settings()
        settings["deliveryEnabled"] = bool(self.config.get("ADM_EXTERNAL_DELIVERY_ENABLED"))
        with self.repo.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT id,slot_key,status,task_count,message_summary,created_at,finished_at FROM admwf_reminder_delivery ORDER BY id DESC LIMIT 30")
            settings["history"] = cursor.fetchall()
        return settings

    def endpoints(self,user):
        require(user,"adm.notify.manage")
        from ..monitoring_notifications import MonitoringNotifications
        rows = MonitoringNotifications(self.config).list_notify_endpoints({"id":identity(user),"is_admin":True})
        return [{"id":row["id"],"name":row["endpointName"]} for row in rows if row["status"]=="ACTIVE" and row["channel"]=="WECOM"]

    def save_settings(self,user,body):
        require(user,"adm.notify.manage")
        if not isinstance(body.get("enabled"),bool): raise AdmError("请选择是否启用提醒")
        times = body.get("times")
        if not isinstance(times,list) or not 1<=len(times)<=2 or len(set(times))!=len(times) or any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",str(t)) for t in times):
            raise AdmError("每天设置一到两个不同的HH:mm提醒时间")
        sla = body.get("slaHours",{})
        if not isinstance(sla,dict) or any(key not in DEFAULT_SLA or isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=720 for key,value in sla.items()):
            raise AdmError("阶段时限请填写1至720小时的整数")
        endpoint = body.get("endpointId")
        if endpoint is not None:
            if not str(endpoint).isdigit(): raise AdmError("通知群无效")
            self._endpoint(str(endpoint))
        if body["enabled"] and endpoint is None: raise AdmError("请先选择通知群")
        base_url=str(body.get("baseUrl") or "").rstrip('/')
        if base_url and not re.fullmatch(r"https?://[^\s?#]+",base_url): raise AdmError("页面地址须为HTTP或HTTPS地址")
        saved={"enabled":body["enabled"],"endpointId":str(endpoint) if endpoint is not None else None,"times":sorted(times),"slaHours":{**DEFAULT_SLA,**sla},"baseUrl":base_url}
        with self.repo.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO admwf_operations_config(id,settings_json,updated_by_id,updated_at) VALUES(1,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE settings_json=VALUES(settings_json),updated_by_id=VALUES(updated_by_id),updated_at=VALUES(updated_at)",
                (json.dumps(saved,ensure_ascii=False),identity(user),business_now()))
        return self.public_settings(user)

    def save_context(self,user,case_id,line_id,body):
        require_any(user,"adm.handle","adm.assign_operator","adm.assign","adm.review","adm.edit_master")
        cause=body.get("causeCategory")
        if cause not in CAUSES: raise AdmError("请选择人为、系统、外部规则、业务原因、不可抗力或待查明")
        fields={key:str(body.get(key) or "").strip() for key in ("causeDetail","evidenceNote","blockingReason","responsibleLink")}
        if any(len(value)>2000 for value in fields.values()): raise AdmError("原因与证据说明每项最多2000字")
        actor=identity(user)
        with self.repo.transaction() as connection:
            case,line=self.repo._lock_case_and_line(connection,int(case_id),int(line_id))
            if not user.get("is_admin") and actor not in {case["coordinator_id"],line.get("leader_id"),line.get("operator_id")}:
                raise AdmError("只能补充本人负责订单的原因信息",403,"ADM_FORBIDDEN")
            with connection.cursor() as cursor:
                cursor.execute("UPDATE admwf_case_line SET problem_attribution=%s,version_no=version_no+1 WHERE id=%s AND case_id=%s", (cause,int(line_id),int(case_id)))
                cursor.execute("INSERT INTO admwf_line_context(line_id,case_id,cause_category,cause_detail,evidence_note,blocking_reason,responsible_link,updated_by_id,updated_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE cause_category=VALUES(cause_category),cause_detail=VALUES(cause_detail),"
                    "evidence_note=VALUES(evidence_note),blocking_reason=VALUES(blocking_reason),responsible_link=VALUES(responsible_link),updated_by_id=VALUES(updated_by_id),updated_at=VALUES(updated_at)",
                    (int(line_id),int(case_id),cause,fields["causeDetail"],fields["evidenceNote"],fields["blockingReason"],fields["responsibleLink"],actor,business_now()))
            self.repo.append_operation_log(connection,case_id=int(case_id),line_id=int(line_id),event_no=self.repo._next_event_no(connection,int(case_id)),
                event_type="UPDATE_CAUSE_CONTEXT",operator_id=actor,operator_name=display_name(user),before_version=line.get("version_no"),after_version=(line.get("version_no") or 0)+1,
                before={"problemAttribution":line.get("problem_attribution")},after={"causeCategory":cause,**fields})
        return {"saved":True}

    def context(self,user,case_id,line_id):
        require(user,"adm.view")
        with self.repo.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT x.cause_detail,x.evidence_note,x.blocking_reason,x.responsible_link,"
                "CASE WHEN l.problem_attribution='PLATFORM' THEN 'EXTERNAL' WHEN l.problem_attribution IN "
                "('HUMAN','SYSTEM','EXTERNAL','BUSINESS','FORCE_MAJEURE','UNKNOWN') THEN l.problem_attribution ELSE COALESCE(x.cause_category,'UNKNOWN') END AS cause_category "
                "FROM admwf_case_line l LEFT JOIN admwf_line_context x ON x.line_id=l.id WHERE l.case_id=%s AND l.id=%s",(int(case_id),int(line_id)))
            return cursor.fetchone() or {"cause_category":"UNKNOWN"}

    def scope(self,query):
        clauses,params=[],[]
        if query.get("startDate") or query.get("endDate"):
            try:
                first=datetime.strptime(query["startDate"],"%Y-%m-%d").date(); last=datetime.strptime(query["endDate"],"%Y-%m-%d").date()
            except (ValueError,KeyError,TypeError): raise AdmError("请完整选择统计起止日期") from None
            if first>last or (last-first).days>366: raise AdmError("日期范围最多367天且开始日期不晚于结束日期")
            clauses.append("issued_date BETWEEN %s AND %s");params.extend((first,last))
        else:
            clauses.append("issued_date BETWEEN %s AND %s");today=business_now().date();params.extend((today-timedelta(days=29),today))
        for key,column in DIMENSIONS.items():
            if query.get(key):
                if key=="person" and query[key]=="__UNASSIGNED__":
                    clauses.append("(person_id IS NULL OR person_id=0)")
                else:
                    clauses.append(column+"=%s");params.append(str(query[key])[:200])
        return " AND ".join(clauses),params

    def analysis(self,user,query):
        require(user,"adm.analysis")
        dimension=str(query.get("dimension") or "stage")
        if dimension not in DIMENSIONS: raise AdmError("分析维度无效")
        where,params=self.scope(query)
        column=DIMENSIONS[dimension]
        # Aggregate in the database. Master dimensions deduplicate case amounts before summing.
        with self.repo.transaction() as connection, connection.cursor() as cursor:
            source=" FROM ("+DATASET+") w WHERE "+where
            cursor.execute("SELECT COUNT(DISTINCT case_id) AS case_count,COUNT(line_id) AS line_count,SUM(active) AS pending_count,"
                "SUM(CASE WHEN cause='UNKNOWN' THEN 1 ELSE 0 END) AS unknown_count"+source,params)
            totals=cursor.fetchone()
            cursor.execute("SELECT SUM(master_cny) AS amount FROM (SELECT case_id,MAX(master_cny) AS master_cny"+source+" GROUP BY case_id) m",params)
            totals["master_amount"]=cursor.fetchone()["amount"] or Decimal("0")
            cursor.execute("SELECT SUM(line_cny) AS allocated_amount,SUM(CASE WHEN appeal_status='SUCCEEDED' THEN 1 ELSE 0 END) AS succeeded,"
                "SUM(CASE WHEN appeal_status='FAILED' THEN 1 ELSE 0 END) AS failed,SUM(CASE WHEN appeal_status='NO_APPEAL' THEN 1 ELSE 0 END) AS no_appeal"+source,params)
            totals.update(cursor.fetchone())
            if dimension in MASTER_DIMENSIONS:
                cursor.execute("SELECT bucket,COUNT(*) AS case_count,SUM(line_count) AS line_count,SUM(amount) AS amount,SUM(pending_count) AS pending_count "
                    "FROM (SELECT "+column+" AS bucket,case_id,MAX(master_cny) AS amount,COUNT(line_id) AS line_count,SUM(active) AS pending_count"+source+" GROUP BY "+column+",case_id) g GROUP BY bucket ORDER BY amount DESC,bucket LIMIT 201",params)
            else:
                cursor.execute("SELECT "+column+" AS bucket,MAX(person) AS person_label,COUNT(DISTINCT case_id) AS case_count,COUNT(line_id) AS line_count,"
                    "SUM(COALESCE(line_cny,0)) AS amount,SUM(active) AS pending_count"+source+" GROUP BY "+column+" ORDER BY pending_count DESC,amount DESC,bucket LIMIT 201",params)
            groups=cursor.fetchall()
            if len(groups)>200: raise AdmError("维度分组超过200项，请缩小日期或追加筛选",422,"ADM_ANALYSIS_TOO_LARGE")
            due,due_params=due_expression(self.settings())
            cursor.execute("SELECT stage,COUNT(*) AS task_count,SUM(active) AS pending_count,"
                "SUM(CASE WHEN active=1 AND %s>"+due+" THEN 1 ELSE 0 END) AS overdue_count,"
                "ROUND(AVG(CASE WHEN active=1 THEN TIMESTAMPDIFF(MINUTE,entered_at,%s)/60 END),1) AS avg_hours"
                +source+" GROUP BY stage ORDER BY pending_count DESC",(business_now(),*due_params,business_now(),*params))
            stages=cursor.fetchall()
            totals["overdue_count"]=sum(int(row["overdue_count"] or 0) for row in stages)
            cursor.execute("SELECT issued_date AS day,COUNT(DISTINCT case_id) AS case_count FROM ("+DATASET+") w WHERE "+where+" GROUP BY issued_date ORDER BY issued_date",params)
            trend=cursor.fetchall()
        for row in groups:
            if dimension=="cause": row["label"]=CAUSES.get(row["bucket"],row["bucket"])
            elif dimension=="stage": row["label"]=STAGES.get(row["bucket"],row["bucket"])
            elif dimension=="person":
                row["label"]=row.get("person_label") or "未分配"
                if not row["bucket"]: row["bucket"]="__UNASSIGNED__"
            else: row["label"]=row["bucket"] or "未分配"
        return {"totals":totals,"groups":groups,"stages":stages,"trend":trend,"dimension":dimension,
                "amountBasis":"主单冻结人民币（主单去重）" if dimension in MASTER_DIMENSIONS else "明细冻结人民币（未分单主单暂不分配到明细维度）",
                "generatedAt":business_now(),"scope":"已授权的全部ADM；按下发日期，默认近30天；当前状态快照"}

    def rows(self,user,query):
        require(user,"adm.analysis")
        where,params=self.scope(query)
        try: page=max(1,int(query.get("page",1)))
        except (ValueError,TypeError): raise AdmError("页码无效") from None
        with self.repo.transaction() as connection, connection.cursor() as cursor:
            source=" FROM ("+DATASET+") w WHERE "+where
            cursor.execute("SELECT COUNT(*) AS total"+source,params);total=int(cursor.fetchone()["total"])
            cursor.execute("SELECT *"+source+" ORDER BY active DESC,entered_at,case_id,line_id LIMIT 50 OFFSET %s",(*params,(page-1)*50))
            rows=cursor.fetchall()
        settings=self.settings()
        return {"items":[decorate(row,settings) for row in rows],"total":total,"page":page,"pageSize":50}

    def report(self,user,query):
        from io import BytesIO
        from openpyxl import Workbook
        result=self.analysis(user,query)
        where,params=self.scope(query)
        with self.repo.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ("+DATASET+") w WHERE "+where+" ORDER BY active DESC,entered_at,case_id,line_id LIMIT 10001",params)
            rows=cursor.fetchall()
        if len(rows)>10000: raise AdmError("分析明细导出最多10000行，请缩小日期或追加维度条件",422,"ADM_ANALYSIS_TOO_LARGE")
        settings=self.settings()
        book=Workbook(write_only=True)
        def add(name,headers,items):
            sheet=book.create_sheet(name);sheet.append(headers)
            for row in items:
                sheet.append([("'"+value if isinstance(value,str) and value.startswith(('=','+','-','@')) else value) for value in row])
        t=result["totals"]
        add("统计说明",["项目","内容"],[["生成时间",business_now().isoformat(sep=' ')],["范围",json.dumps(dict(query),ensure_ascii=False)],["时间口径","下发日期，默认近30天；状态为当前快照"],["金额口径",result["amountBasis"]],["主单数",t["case_count"]],["主单冻结人民币",str(t["master_amount"])],["当前待办项",t["pending_count"]],["超时项",t["overdue_count"]]])
        add("维度分析",["分组","主单数","明细数","金额CNY","待办项"],[[r["label"],r["case_count"],r["line_count"],str(r["amount"] or 0),r["pending_count"]] for r in result["groups"]])
        add("阶段时效",["阶段","当前待办项","超时项","平均停留小时"],[[STAGES.get(r["stage"],r["stage"]),r["pending_count"],r["overdue_count"],r["avg_hours"]] for r in result["stages"]])
        rows=[decorate(row,settings) for row in rows]
        add("跟进明细",["ADM主单号","内部明细ID","航司","供应商","平台","根因","原因说明","当前阶段","跟进人","阶段进入时间","应完成时间","停留小时","超时","阻塞原因"],
            [[r["adm_no"],r["line_id"],r["airline"],r["supplier"],r["platform"],r["cause_name"],r["cause_detail"],r["stage_name"],r["person"],str(r["entered_at"]),str(r["due_at"] or ''),r["elapsed_hours"],"是" if r["overdue"] else "否",r["blocking_reason"]] for r in rows])
        output=BytesIO();book.save(output);output.seek(0);return output

    def active_rows(self):
        with self.repo.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ("+DATASET+") w WHERE active=1 ORDER BY entered_at,case_id,line_id LIMIT 10001")
            rows=cursor.fetchall()
        if len(rows)>10000: raise AdmError("活动ADM超过10000项，提醒未发送，请缩小通知范围或优化汇总",422,"ADM_REMINDER_TOO_LARGE")
        settings=self.settings()
        return [decorate(row,settings) for row in rows]

    def preview(self,user):
        require(user,"adm.notify.manage")
        return self.digest(self.active_rows(),self.settings())

    @staticmethod
    def digest(rows,settings):
        people={};stages={}
        for row in rows:
            person=row["person"] or "未分配"
            group=people.setdefault(str(row.get("person_id") or "unassigned"),{"name":person,"personId":row.get("person_id"),"total":0,"overdue":0,"soon":0,"items":[]})
            group["total"]+=1;group["overdue"]+=int(row["overdue"]);group["soon"]+=int(row["soon"])
            stages[row["stage_name"]]=stages.get(row["stage_name"],0)+1
            if len(group["items"])<5: group["items"].append(f"{row['adm_no']} · {row['stage_name']} · 已停留{row['elapsed_hours']}小时"+(' · 超时' if row["overdue"] else ''))
        lines=[f"ADM跟进提醒 · {business_now():%Y-%m-%d %H:%M}",f"当前待办{len(rows)}项 · 超时{sum(int(r['overdue']) for r in rows)}项 · 4小时内到期{sum(int(r['soon']) for r in rows)}项"]
        lines.append("阶段："+"；".join(f"{key}{value}" for key,value in stages.items()))
        for group in sorted(people.values(),key=lambda item:(-item['overdue'],-item['total'],item['name'])):
            lines.append(f"\n{group['name']}：{group['total']}项（超时{group['overdue']}，临期{group['soon']}）")
            lines.extend(group["items"])
        if settings.get("baseUrl"): lines.append(settings["baseUrl"]+"/adm/analysis")
        text="\n".join(lines)
        # WECOM text limit is bounded conservatively by UTF-8 bytes; do not silently omit people.
        if len(text.encode('utf-8'))>1800:
            lines=lines[:3]+[f"{g['name']}：待办{g['total']}，超时{g['overdue']}，临期{g['soon']}" for g in people.values()]
            if settings.get("baseUrl"): lines.append(settings["baseUrl"]+"/adm/analysis")
            text="\n".join(lines)
        if len(text.encode('utf-8'))>1800: raise AdmError("提醒人员过多，需配置分群后发送，未截断人员清单",422,"ADM_REMINDER_TOO_LARGE")
        return {"text":text,"taskCount":len(rows),"people":list(people.values()),"stages":stages}

    def _endpoint(self,endpoint_id):
        from ..monitoring_notifications import MonitoringNotifications
        return MonitoringNotifications(self.config).resolve_notification_endpoint({"id":1,"is_admin":True},str(endpoint_id))

    def send_due(self,now=None):
        now=now or business_now()
        if not self.config.get("ADM_EXTERNAL_DELIVERY_ENABLED"): return 0
        settings=self.settings()
        if not settings["enabled"] or not settings["endpointId"]: return 0
        slots=[time for time in settings["times"] if 0<=(now-datetime.strptime(f"{now:%Y-%m-%d} {time}","%Y-%m-%d %H:%M")).total_seconds()<300]
        sent=0
        for time in slots:
            slot=f"{now:%Y-%m-%d} {time}"
            endpoint=self._endpoint(settings["endpointId"])
            rows=self.active_rows()
            if len(settings["times"])>1 and time==settings["times"][-1]:
                rows=[row for row in rows if row["overdue"] or row["soon"]]
            digest=self.digest(rows,settings)
            key=hashlib.sha256((slot+str(settings["endpointId"])).encode()).hexdigest()
            with self.repo.transaction() as connection, connection.cursor() as cursor:
                cursor.execute("INSERT IGNORE INTO admwf_reminder_delivery(delivery_key,slot_key,endpoint_id,status,task_count,message_summary,created_at) VALUES(%s,%s,%s,'CLAIMED',%s,%s,%s)",
                    (key,slot,str(settings["endpointId"]),digest["taskCount"],digest["text"],now))
                if cursor.rowcount!=1: continue
            status="SKIPPED" if digest["taskCount"]==0 else "SENT"
            if digest["taskCount"]:
                try:
                    payload={"msgtype":"text","text":{"content":digest["text"]}}
                    if self.notifier: response=self.notifier(endpoint["url"],payload)
                    else:
                        req=urlrequest.Request(endpoint["url"],data=json.dumps(payload,ensure_ascii=False).encode(),headers={"Content-Type":"application/json"},method="POST")
                        with urlrequest.urlopen(req,timeout=10) as result: response=json.loads(result.read(65536))
                    if response.get("errcode")!=0: status="FAILED"
                except Exception: status="UNKNOWN"
            with self.repo.transaction() as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE admwf_reminder_delivery SET status=%s,finished_at=%s WHERE delivery_key=%s AND status='CLAIMED'",(status,business_now(),key))
            sent+=int(status=="SENT")
        return sent
