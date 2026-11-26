"""General data annotation workflow, isolated from operational ADM records."""
import json
import re
from io import BytesIO
from uuid import uuid4

from .adm_parsing.service import ParsingService
from .admwf.policy import AdmError, business_now, has
from .annotation_adm_compare import compare_candidate
from .annotation_evidence import (
    AnnotationFiles, MAX_FILE, MAX_FILES, MAX_MARKS, MAX_TOTAL,
    digest, filename, geometry, pdf_text, position, problem, short_text, validate_mark,
)
from .annotation_store import AnnotationStore, SAMPLE_COLUMNS, duplicate, encode

MENU = "annotation.center"
MENU_ADM = "adm.center"
STATUSES = ("draft", "submitted", "returned", "approved")
ID = re.compile(r"[a-f0-9]{32}")
ACCOUNT = re.compile(r"(?:0|[1-9][0-9]{0,18})")
ADM_FIELDS = [
    ("ADM 单号", "原件明确的 ADM 或 Document Number。"),
    ("航司编码", "原件的 Airline Code；保留出票三位码。"),
    ("开具日期", "罚单实际开具日期，与报表或航班日期区分。"),
    ("正式罚款金额", "罚单主记录的正式金额；附件费用另标。"),
    ("币种", "原件明确标注的正式罚款币种。"),
    ("下发原因", "原件说明的追扣原因或触发动作。"),
    ("事件角色", "原件中明示的参与者和动作；责任待业务确认。"),
    ("关联票号", "原件的相关票号；虚拟票号需要相应证据。"),
    ("PNR", "原件中的定位编码，按航司或 GDS 来源区分。"),
]
ADM_FIELD_KEYS = ("number", "airlineCode", "issuedDate", "amount", "currency", "reason", None, "ticketNumber", "pnrs")


def stamp():
    return business_now().isoformat(sep=" ", timespec="seconds")


def new_label(name, description, scope):
    return {"id": uuid4().hex, "name": name, "description": description, "scope": scope}


def eligible(user):
    return user and user.get("is_enabled", True) and (
        user.get("is_admin") or MENU in (user.get("menu_codes") or []))


class AnnotationService:
    def __init__(self, config, user, accounts=None):
        if not eligible(user) or user.get("id") is None or (user["id"] == 0 and not config.get("TESTING")):
            problem("无数据标注访问权", 403, "ANNOTATION_FORBIDDEN")
        self.config = config
        self.user = user
        self.actor = str(user["id"])
        self.admin = bool(user.get("is_admin"))
        self.store = AnnotationStore(config)
        self.files = AnnotationFiles(config["ANNOTATION_ROOT"])
        self.accounts_source = accounts or (lambda: [user])

    def can_create(self):
        return has(self.user, "annotation.manage")

    def accounts(self):
        return {str(u["id"]): str(u.get("display_name") or u.get("username") or u["id"])[:120]
                for u in self.accounts_source() if eligible(u) and u.get("id") is not None}

    def account_options(self, project_id=None):
        if project_id:
            with self.store.transaction() as conn:
                self.project_access(conn, project_id, {"manager"})
        elif not self.can_create():
            problem("仅项目管理员可查询候选账号", 403, "ANNOTATION_FORBIDDEN")
        return {"items": [{"id": key, "name": name} for key, name in self.accounts().items()]}

    def project_access(self, conn, project_id, roles=None, *, lock=False):
        project = self.store.project(conn, project_id, lock=lock)
        if not project:
            problem("项目不存在或无权访问", 404, "ANNOTATION_NOT_FOUND")
        if self.admin or project["owner_id"] == self.actor:
            role = "manager"
        else:
            member = self.store.one(conn, "SELECT role FROM annotation_member WHERE project_id=? AND account_id=?",
                                    (project_id, self.actor))
            role = member["role"] if member else None
        if not role or roles is not None and role not in roles:
            problem("没有该项目的操作权限", 403, "ANNOTATION_FORBIDDEN")
        return project, role

    def public_project(self, conn, project, role):
        return {"id": project["id"], "name": project["name"], "kind": project["kind"], "ownerId": project["owner_id"],
                "version": project["version_no"], "labels": json.loads(project["labels"]), "role": role,
                "members": self.store.members(conn, project["id"]) if role == "manager" else []}

    def projects(self):
        with self.store.transaction() as conn:
            if self.admin:
                rows = self.store.all(conn, "SELECT p.*,NULL AS member_role FROM annotation_project p ORDER BY p.name,p.id")
            else:
                rows = self.store.all(conn, "SELECT p.*,m.role AS member_role FROM annotation_project p "
                                      "LEFT JOIN annotation_member m ON p.id=m.project_id AND m.account_id=? "
                                      "WHERE p.owner_id=? OR m.account_id IS NOT NULL ORDER BY p.name,p.id",
                                      (self.actor, self.actor))
            return {"canCreate": self.can_create(), "items": [
                self.public_project(conn, p, "manager" if self.admin or p["owner_id"] == self.actor else p["member_role"])
                for p in rows]}

    def create_project(self, data):
        if not self.can_create():
            problem("无新建项目权限", 403, "ANNOTATION_FORBIDDEN")
        name, kind = short_text(data.get("name"), 100, required=True), data.get("kind")
        if kind not in ("adm", "general"):
            problem("请选择 ADM 或通用项目")
        labels = [new_label(*field, "field") for field in ADM_FIELDS] if kind == "adm" else []
        if kind == "adm":
            for label, field in zip(labels, ADM_FIELD_KEYS):
                if field:
                    label["admField"] = field
        project_id = uuid4().hex
        try:
            with self.store.transaction(write=True) as conn:
                self.store.write(conn, "INSERT INTO annotation_project(id,name,owner_id,kind,version_no,labels) "
                                 "VALUES(?,?,?,?,1,?)", (project_id, name, self.actor, kind, encode(labels)))
                return self.public_project(conn, self.store.project(conn, project_id), "manager")
        except Exception as exc:
            if duplicate(exc):
                problem("已存在同名标注项目", 409, "ANNOTATION_DUPLICATE")
            raise

    def configure(self, ident, data):
        with self.store.transaction(write=True) as conn:
            project, role = self.project_access(conn, ident, {"manager"}, lock=True)
            self.expect_version(project, data.get("version"))
            old = {item["id"]: item for item in json.loads(project["labels"])}
            permitted = self.accounts()
            labels, seen = [], set()
            incoming, memberships = data.get("labels"), data.get("members")
            if not isinstance(incoming, list) or not isinstance(memberships, list) or len(incoming) > 100 or len(memberships) > 200:
                problem("项目标签或成员超出限制")
            label_ids = set()
            for item in incoming:
                if not isinstance(item, dict):
                    problem("标签格式无效")
                scope = item.get("scope")
                if scope not in ("field", "document"):
                    problem("标签层级无效")
                label_name = short_text(item.get("name"), 50, required=True)
                description = short_text(item.get("description"), 300, required=True)
                key = (scope, label_name.casefold())
                ident_label = item.get("id")
                if ident_label and (not isinstance(ident_label, str) or ident_label not in old or
                                    old[ident_label]["scope"] != scope or ident_label in label_ids):
                    problem("已有标签层级不能修改或重复提交")
                if key in seen:
                    problem("同一层级的标签名称必须唯一")
                label = new_label(label_name, description, scope)
                if ident_label:
                    label["id"] = ident_label
                    if old[ident_label].get("admField"):
                        label["admField"] = old[ident_label]["admField"]
                label_ids.add(label["id"])
                seen.add(key)
                labels.append(label)
            if set(old) - label_ids:
                problem("已有标签请保留，以便历史标注仍可定位")
            result = {}
            previous = {row["id"]: row for row in self.store.members(conn, ident)}
            for member in memberships:
                if not isinstance(member, dict) or not isinstance(member.get("id"), str):
                    problem("项目成员格式无效")
                account, assigned_role = member["id"], member.get("role")
                if account == project["owner_id"] or account in result or not ACCOUNT.fullmatch(account):
                    problem("成员重复或已是项目负责人")
                if assigned_role not in ("annotator", "reviewer"):
                    problem("项目角色必须是标注员或复核人")
                if account not in permitted and (account not in previous or assigned_role != previous[account]["role"]):
                    problem("只能添加具有数据标注菜单权限的启用账号")
                result[account] = (assigned_role, permitted.get(account) or previous[account]["name"])
            self.store.write(conn, "UPDATE annotation_project SET labels=?,version_no=version_no+1 WHERE id=?",
                             (encode(labels), ident))
            self.store.write(conn, "DELETE FROM annotation_member WHERE project_id=?", (ident,))
            for account, (member_role, member_name) in result.items():
                self.store.write(conn, "INSERT INTO annotation_member(project_id,account_id,role,display_name) VALUES(?,?,?,?)",
                                 (ident, account, member_role, member_name))
            return self.public_project(conn, self.store.project(conn, ident), role)

    @staticmethod
    def expect_version(row, expected):
        if type(expected) is not int or expected != row["version_no"]:
            problem("记录已更新，请刷新后再操作", 409, "ANNOTATION_CONFLICT")

    def permissions(self, row, role, payload):
        assigned = row["assignee_id"] == self.actor
        pending = row["status"] in ("draft", "returned")
        return {"canEdit": assigned and role in ("annotator", "manager") and pending,
                "canDelete": role == "manager" and pending,
                "canReview": role in ("reviewer", "manager") and row["status"] == "submitted" and
                             payload.get("submittedBy") != self.actor,
                "canAssign": role == "manager" and pending}

    def public_sample(self, row, role):
        payload = json.loads(row["payload"])
        sample = {"id": row["id"], "projectId": row["project_id"], "name": row["name"], "title": row["title"],
                  "platform": row["platform"], "status": row["status"], "version": row["version_no"],
                  "expected": row["expected"], "positionCount": row["position_count"],
                  "assigneeId": row["assignee_id"], "creatorId": row["creator_id"], "sourceTaskId": row["source_task_id"],
                  "updatedAt": str(row["updated_at"]), "files": payload["files"],
                  "reviewNote": payload.get("reviewNote", ""), **self.permissions(row, role, payload)}
        if "segments" in row:
            sample.update(marks=payload["marks"], fileLabels=payload["fileLabels"],
                          titleEvidence=payload.get("titleEvidence"), segments=json.loads(row["segments"]))
        return sample

    def sample_access(self, conn, ident, *, lock=False):
        row = self.store.one(conn, "SELECT project_id FROM annotation_sample WHERE id=?", (ident,))
        if not row:
            problem("样本不存在或无权访问", 404, "ANNOTATION_NOT_FOUND")
        project, role = self.project_access(conn, row["project_id"], lock=lock)
        if lock and not self.store.path:
            row = self.store.one(conn, "SELECT " + SAMPLE_COLUMNS + ",segments FROM annotation_sample WHERE id=? FOR UPDATE", (ident,))
        else:
            row = self.store.sample(conn, ident)
        if not row or row["status"] == "deleted":
            problem("样本不存在或无权访问", 404, "ANNOTATION_NOT_FOUND")
        if role == "annotator" and row["assignee_id"] != self.actor:
            problem("只可查看分配给自己的样本", 403, "ANNOTATION_FORBIDDEN")
        return row, project, role

    def list_samples(self, project_id, page, status, search):
        if not 1 <= page <= 10000 or status not in ("", *STATUSES):
            problem("分页或样本状态无效")
        search = short_text(search, 100).lower()
        with self.store.transaction() as conn:
            _, role = self.project_access(conn, project_id)
            conditions, params = ["project_id=?", "status<>'deleted'"], [project_id]
            if role == "annotator":
                conditions.append("assignee_id=?")
                params.append(self.actor)
            if search:
                conditions.append("(INSTR(LOWER(name),?)>0 OR INSTR(LOWER(title),?)>0 OR INSTR(LOWER(platform),?)>0)")
                params.extend([search]*3)
            where = " AND ".join(conditions)
            counts = dict.fromkeys(STATUSES, 0)
            for row in self.store.all(conn, "SELECT status,COUNT(*) AS total FROM annotation_sample WHERE "+where+
                                      " GROUP BY status", tuple(params)):
                counts[row["status"]] = row["total"]
            if status:
                where += " AND status=?"
                params.append(status)
            rows = self.store.all(conn, "SELECT "+SAMPLE_COLUMNS+" FROM annotation_sample WHERE "+where+
                                  " ORDER BY updated_at DESC,id DESC LIMIT 20 OFFSET ?", (*params, (page-1)*20))
            return {"items": [self.public_sample(row, role) for row in rows], "counts": counts,
                    "total": counts[status] if status else sum(counts.values())}

    def check_import(self, project_id, *, adm=False):
        with self.store.transaction() as conn:
            project, _ = self.project_access(conn, project_id, {"manager"} if adm else {"manager", "annotator"})
            if adm and project["kind"] != "adm":
                problem("仅 ADM 项目支持导入 ADM 解析来件")

    def create_sample(self, project_id, named_bytes, source_task_id=None):
        hashes = sorted(digest(data) for _, data in named_bytes)
        if len(set(hashes)) != len(hashes):
            problem("同一材料组包含内容完全相同的附件，请去重后导入")
        key = digest(encode(hashes).encode("utf-8"))
        query = "SELECT "+SAMPLE_COLUMNS+" FROM annotation_sample WHERE project_id=? AND fingerprint=?"
        with self.store.transaction() as conn:
            _, role = self.project_access(conn, project_id, {"manager", "annotator"})
            existing = self.store.one(conn, query, (project_id, key))
            if existing:
                return self.existing_sample(existing, role)
        files, segments = self.files.material(named_bytes)
        name = files[0]["name"] if len(files) == 1 else f'{files[0]["name"]} 等 {len(files)} 份'
        with self.store.transaction(write=True) as conn:
            _, role = self.project_access(conn, project_id, {"manager"} if source_task_id else {"manager", "annotator"}, lock=True)
            existing = self.store.one(conn, query, (project_id, key))
            if existing:
                return self.existing_sample(existing, role)
            ident = uuid4().hex
            payload = {"files": files, "marks": [], "fileLabels": [], "titleEvidence": None}
            self.store.write(conn, "INSERT INTO annotation_sample "
                             "(id,project_id,fingerprint,creator_id,assignee_id,status,version_no,updated_at,name,title,"
                             "platform,source_task_id,expected,position_count,payload,segments) "
                             "VALUES(?,?,?,?,?,'draft',1,?,?, '', '', ?,NULL,0,?,?)",
                             (ident, project_id, key, self.actor, self.actor, stamp(), name, source_task_id,
                              encode(payload), encode(segments)))
            self.record(conn, ident, 1, "import", "", {"files": files, "sourceTaskId": source_task_id})
            row = self.store.sample(conn, ident)
            row.pop("segments")
            return self.public_sample(row, role)

    def existing_sample(self, row, role):
        if role == "annotator" and row["assignee_id"] != self.actor:
            problem("项目中已存在相同原件，请联系项目管理员", 409, "ANNOTATION_DUPLICATE")
        result = self.public_sample(row, role)
        result["duplicate"] = True
        return result

    def upload(self, project_id, files, grouped):
        self.check_import(project_id)
        if not 1 <= len(files) <= MAX_FILES:
            problem("每次请选择 1 至 10 份文件")
        results, errors, materials, total = [], [], [], 0
        for file in files:
            try:
                name = filename(file.filename)
                content = file.stream.read(MAX_FILE+1)
                total += len(content)
                if total > MAX_TOTAL:
                    problem("单批文件合计不超过 50 MB", 413)
                if not content or len(content) > MAX_FILE:
                    problem("单份文件需大于 0 且不超过 20 MB", 413)
                materials.append((name, content))
            except AdmError as error:
                errors.append({"name": str(file.filename or "")[:240], "message": error.message})
        if grouped and errors:
            return {"items": [], "errors": errors}
        for group in ([materials] if grouped else [[m] for m in materials]):
            try:
                results.append(self.create_sample(project_id, group))
            except AdmError as error:
                errors.append({"name": group[0][0], "message": error.message})
        return {"items": results, "errors": errors}

    def import_adm(self, project_id, task_id):
        self.check_import(project_id, adm=True)
        if not isinstance(task_id, str) or not ID.fullmatch(task_id):
            problem("请输入有效的 ADM 解析来件 ID")
        if not self.admin and MENU_ADM not in (self.user.get("menu_codes") or []):
            problem("导入前需具有 ADM 解析原件查看权限", 403)
        service = ParsingService(self.config)
        source = service._get(self.user, task_id)  # Same ownership check as ADM original-file download.
        materials, total = [], 0
        if not 1 <= len(source["files"]) <= MAX_FILES:
            problem("该 ADM 来件文件数超出限制")
        for file in source["files"]:
            path, name = service.file(self.user, task_id, file["id"])
            with path.open("rb") as stream:
                content = stream.read(MAX_FILE+1)
            total += len(content)
            if not content or len(content) > MAX_FILE or total > MAX_TOTAL:
                problem("该 ADM 来件文件大小超出标注限额", 413)
            if digest(content) != file["sha256"]:
                problem("ADM 原件指纹不一致，请先核对原档")
            materials.append((filename(name), content))
        return self.create_sample(project_id, materials, task_id)

    def record(self, conn, ident, version, action, note, snapshot):
        self.store.write(conn, "INSERT INTO annotation_revision "
                         "(sample_id,version_no,action,actor_id,occurred_at,note,snapshot) VALUES(?,?,?,?,?,?,?)",
                         (ident, version, action, self.actor, stamp(), note, encode(snapshot)))

    def detail(self, ident):
        with self.store.transaction() as conn:
            row, _, role = self.sample_access(conn, ident)
            return self.detail_record(conn, row, role)

    def detail_record(self, conn, row, role):
        sample = self.public_sample(row, role)
        project = self.store.project(conn, row["project_id"])
        sample["canReopen"] = self.can_reopen(row, project, role)
        sample["labelReviewNeeded"] = self.label_review_needed(json.loads(row["payload"]), json.loads(project["labels"]))
        events = self.store.all(conn, "SELECT action,actor_id,occurred_at,note FROM annotation_revision WHERE sample_id=? "
                               "ORDER BY version_no DESC LIMIT 100", (row["id"],))
        sample["history"] = [{"action": event["action"], "actor": event["actor_id"],
                              "at": str(event["occurred_at"]), "note": event["note"]} for event in events]
        return sample

    @staticmethod
    def label_review_needed(payload, labels):
        saved = payload.get("draftLabels")
        if saved is None:
            return False
        used = {mark["labelId"] for mark in payload["marks"]} | set(payload["fileLabels"])
        return {label["id"]: label for label in saved if label["id"] in used} != {
            label["id"]: label for label in labels if label["id"] in used}

    @staticmethod
    def expect_project_version(project, expected):
        if type(expected) is not int or expected != project["version_no"]:
            problem("项目标签或成员配置已更新，请刷新项目后核对", 409, "ANNOTATION_PROJECT_CONFLICT")

    def update_sample(self, ident, data):
        with self.store.transaction(write=True) as conn:
            row, project, role = self.sample_access(conn, ident, lock=True)
            self.expect_version(row, data.get("version"))
            self.expect_project_version(project, data.get("projectVersion"))
            payload = json.loads(row["payload"])
            if not self.permissions(row, role, payload)["canEdit"]:
                problem("当前状态或账号不可编辑", 403)
            labels = json.loads(project["labels"])
            field_ids = {item["id"] for item in labels if item["scope"] == "field"}
            doc_ids = {item["id"] for item in labels if item["scope"] == "document"}
            marks, file_labels = data.get("marks"), data.get("fileLabels")
            if (not isinstance(marks, list) or len(marks) > MAX_MARKS or not isinstance(file_labels, list) or
                    len(file_labels) > 100 or any(not isinstance(key, str) or key not in doc_ids for key in file_labels)):
                problem("标注数量超过限制，或标签不属于当前项目")
            segments = json.loads(row["segments"])
            result, unique_marks, pdf_selections = [], set(), {}
            by_segment = {part["id"]: pdf_text(part["text"]) for part in segments if part.get("page")}
            quote_positions = {}
            old_ids = {mark["id"] for mark in payload["marks"]}
            used_ids = set()
            for mark in marks:
                clean = validate_mark(mark, field_ids, segments, pdf_pages=by_segment)
                if clean.get("rects"):
                    selection = (clean["fileId"], clean["page"], geometry(clean))
                    text = pdf_text(clean["quote"])
                    if pdf_selections.setdefault(selection, text) != text:
                        problem("同一 PDF 选区不能对应不同原文")
                key = (clean["labelId"], position(clean))
                if key in unique_marks:
                    continue
                if clean.get("page"):
                    text = pdf_text(clean["quote"])
                    group = (clean["segmentId"], text)
                    positions = quote_positions.setdefault(group, set())
                    positions.add(key[1])
                    if text and len(positions) > by_segment[clean["segmentId"]].count(text):
                        problem("该引文标记的位置多于它在同一页的出现次数，请核对重复标注")
                unique_marks.add(key)
                candidate_id = mark.get("id")
                if isinstance(candidate_id, str) and candidate_id in old_ids and candidate_id not in used_ids:
                    clean["id"] = candidate_id
                used_ids.add(clean["id"])
                result.append(clean)
            title = short_text(data.get("title"), 200)
            platform = short_text(data.get("platform"), 100)
            evidence = data.get("titleEvidence")
            title_evidence = validate_mark(evidence, field_ids, segments, title=True, pdf_pages=by_segment) if evidence is not None else None
            if title_evidence and title_evidence["quote"] != title:
                problem("标题和所选原文不一致，请重新标标题或取消原文关联")
            payload.update(marks=result, fileLabels=list(dict.fromkeys(file_labels)), titleEvidence=title_evidence,
                           draftLabels=labels)
            count = len({position(mark) for mark in result})
            self.store.write(conn, "UPDATE annotation_sample SET title=?,platform=?,expected=?,position_count=?,"
                             "payload=?,version_no=version_no+1,updated_at=? WHERE id=?",
                             (title, platform, count or None, count, encode(payload), stamp(), ident))
            return self.detail_record(conn, self.store.sample(conn, ident), role)

    def snapshot(self, row, payload, labels):
        return {"id": row["id"], "revision": row["version_no"], "title": row["title"], "platform": row["platform"],
                "sourceTaskId": row["source_task_id"], "files": payload["files"], "titleEvidence": payload.get("titleEvidence"),
                "expectedPositions": row["expected"], "annotatedPositions": row["position_count"], "labels": labels,
                "marks": payload["marks"], "fileLabels": payload["fileLabels"], "submittedBy": payload.get("submittedBy"),
                "reviewedBy": payload.get("reviewedBy"), "reviewedAt": payload.get("reviewedAt")}

    def delete_sample(self, ident, data):
        with self.store.transaction(write=True) as conn:
            row, _, role = self.sample_access(conn, ident, lock=True)
            if role != "manager":
                problem("仅项目管理员可删除样本", 403, "ANNOTATION_FORBIDDEN")
            self.expect_version(row, data.get("version"))
            if row["status"] not in ("draft", "returned"):
                problem("只能删除待标注或已退回的样本", 409, "ANNOTATION_CONFLICT")
            # Reserve the old row for audit and release its material fingerprint for reimport.
            deleted_key = digest(("deleted:" + ident).encode("ascii"))
            self.store.write(conn, "UPDATE annotation_sample SET status='deleted',fingerprint=?,"
                             "version_no=version_no+1,updated_at=? WHERE id=?",
                             (deleted_key, stamp(), ident))
            self.record(conn, ident, row["version_no"] + 1, "delete", "", {"previousStatus": row["status"]})
            return {"id": ident}

    def can_reopen(self, row, project, role):
        return (project["kind"] == "adm" and row["status"] == "approved"
                and row["assignee_id"] == self.actor and role in ("annotator", "manager"))

    def actions(self, ident, data):
        action = data.get("action")
        if action not in ("submit", "approve", "return", "assign", "reopen"):
            problem("不支持该样本操作")
        with self.store.transaction(write=True) as conn:
            row, project, role = self.sample_access(conn, ident, lock=True)
            self.expect_version(row, data.get("version"))
            payload = json.loads(row["payload"])
            permitted = self.permissions(row, role, payload)
            note = short_text(data.get("note", ""), 500, required=action == "return")
            assignee, status = row["assignee_id"], row["status"]
            expected = row["expected"]
            if action == "submit":
                if not permitted["canEdit"]:
                    problem("当前账号无权提交此样本", 403)
                if not row["title"] or not row["platform"] or not row["position_count"]:
                    problem("请补齐标题、来源平台，并至少标记一处字段证据")
                labels = json.loads(project["labels"])
                self.expect_project_version(project, data.get("projectVersion"))
                if self.label_review_needed(payload, labels):
                    problem("已有标注的标签定义已变更，请核对后重新保存草稿", 409, "ANNOTATION_PROJECT_CONFLICT")
                status = "submitted"
                expected = row["position_count"]
                payload.update(submittedBy=self.actor, reviewNote="", labelSnapshot=labels)
            elif action in ("approve", "return"):
                if not permitted["canReview"]:
                    problem("只能复核其他标注员已提交的样本", 403)
                status = "approved" if action == "approve" else "returned"
                payload.update(reviewNote=note, reviewedBy=self.actor, reviewedAt=stamp())
            elif action == "reopen":
                if not self.can_reopen(row, project, role):
                    problem("仅当前标注人可重新编辑已确认的 ADM 样本", 403, "ANNOTATION_FORBIDDEN")
                status = "draft"
                for key in ("submittedBy", "reviewedBy", "reviewedAt", "reviewNote", "labelSnapshot"):
                    payload.pop(key, None)
            else:
                if not permitted["canAssign"]:
                    problem("当前账号或状态不可分配样本", 403)
                assignee = data.get("assigneeId")
                owners = {project["owner_id"]} | {m["id"] for m in self.store.members(conn, project["id"]) if m["role"] == "annotator"}
                if not isinstance(assignee, str) or assignee not in owners or assignee not in self.accounts():
                    problem("请选择当前项目中有权限的标注员")
            self.store.write(conn, "UPDATE annotation_sample SET status=?,assignee_id=?,payload=?,"
                             "expected=?,version_no=version_no+1,updated_at=? WHERE id=?",
                             (status, assignee, encode(payload), expected, stamp(), ident))
            row = self.store.sample(conn, ident)
            snapshot = self.snapshot(row, payload, payload.get("labelSnapshot", [])) if action != "assign" else {"assigneeId": assignee}
            self.record(conn, ident, row["version_no"], action, note, snapshot)
            result = self.detail_record(conn, row, role)
            if action == "submit":
                successor = self.store.one(conn, "SELECT id FROM annotation_sample WHERE project_id=? AND assignee_id=? "
                                           "AND status IN ('draft','returned') ORDER BY updated_at DESC,id DESC LIMIT 1",
                                           (row["project_id"], self.actor))
                result["nextEditableId"] = successor["id"] if successor else None
            return result

    def file(self, ident, file_id):
        with self.store.transaction() as conn:
            row, _, _ = self.sample_access(conn, ident)
            file = next((item for item in json.loads(row["payload"])["files"] if item["id"] == file_id), None)
            if not file:
                problem("样本原件不存在", 404)
            return self.files.path(file["sha256"]), file["name"]

    def datasets(self, ident):
        with self.store.transaction() as conn:
            self.project_access(conn, ident, {"manager", "reviewer"})
            rows = self.store.all(conn, "SELECT id,name,created_at,sample_count FROM annotation_dataset "
                                  "WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT 100", (ident,))
            return {"items": [{"id": row["id"], "name": row["name"], "createdAt": str(row["created_at"]),
                               "count": row["sample_count"]} for row in rows]}

    def publish(self, ident, data):
        name = short_text(data.get("name"), 100, required=True)
        ids = data.get("sampleIds")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(
                not isinstance(key, str) or not ID.fullmatch(key) for key in ids) or len(set(ids)) != len(ids):
            problem("请选择 1 至 100 份不重复的已复核样本")
        release_id, now = uuid4().hex, stamp()
        try:
            with self.store.transaction(write=True) as conn:
                project, _ = self.project_access(conn, ident, {"manager"}, lock=True)
                slots = ",".join("?" for _ in ids)
                rows = self.store.all(conn, "SELECT "+SAMPLE_COLUMNS+" FROM annotation_sample "
                                      "WHERE project_id=? AND id IN ("+slots+") ORDER BY id", (ident, *ids))
                if len(rows) != len(ids) or any(row["status"] != "approved" for row in rows):
                    problem("只能发布当前项目已复核通过且完整的样本")
                snapshots = []
                for row in rows:
                    payload = json.loads(row["payload"])
                    snapshots.append(self.snapshot(row, payload, payload["labelSnapshot"]))
                envelope = {"schemaVersion": 1, "id": release_id, "name": name, "createdAt": now, "count": len(rows),
                            "project": {"id": ident, "name": project["name"], "kind": project["kind"],
                                        "version": project["version_no"]}, "samples": snapshots}
                serialized = encode(envelope)
                if len(serialized.encode("utf-8")) > 20 * 1024 * 1024:
                    problem("发布包超过 20 MB，请分批发布", 413)
                self.store.write(conn, "INSERT INTO annotation_dataset "
                                 "(id,project_id,name,created_at,creator_id,sample_count,payload) VALUES(?,?,?,?,?,?,?)",
                                 (release_id, ident, name, now, self.actor, len(rows), serialized))
                return {"id": release_id, "name": name, "createdAt": now, "count": len(rows)}
        except Exception as exc:
            if duplicate(exc):
                problem("同一项目已有同名发布版本", 409, "ANNOTATION_DUPLICATE")
            raise

    def dataset(self, ident, release_id):
        with self.store.transaction() as conn:
            self.project_access(conn, ident, {"manager", "reviewer"})
            return self.read_dataset(conn, ident, release_id)

    def read_dataset(self, conn, ident, release_id):
        row = self.store.one(conn, "SELECT payload FROM annotation_dataset WHERE id=? AND project_id=?",
                             (release_id, ident))
        if not row:
            problem("已发布数据集不存在", 404)
        return json.loads(row["payload"])

    def few_shot(self, ident, release_id):
        content = BytesIO()
        with self.store.transaction() as conn:
            self.project_access(conn, ident, {"manager", "reviewer"})
            release = self.read_dataset(conn, ident, release_id)
            for sample in release["samples"]:
                row = self.store.sample(conn, sample["id"])
                if not row or row["project_id"] != ident:
                    problem("发布样本缺少原文，无法导出完整 Few-shot", 409, "ANNOTATION_SOURCE_MISSING")
                # Segments are fixed on import. All annotations come from the published snapshot.
                files = {file["id"]: {"name": file["name"], "segments": []} for file in sample["files"]}
                for segment in json.loads(row["segments"]):
                    source = files.get(segment["fileId"])
                    if source is not None:
                        source["segments"].append({"location": segment["locator"], "text": segment["text"]})
                if not files or any(not file["segments"] for file in files.values()):
                    problem("发布样本缺少原文，无法导出完整 Few-shot", 409, "ANNOTATION_SOURCE_MISSING")

                labels = {label["id"]: label for label in sample["labels"]}
                fields = {}
                for mark in sample["marks"]:
                    fields.setdefault(mark["labelId"], []).append(mark["quote"])
                example = {
                    "input": {
                        "documents": list(files.values()),
                        "labels": [{key: label[key] for key in ("name", "description", "scope")}
                                   for label in labels.values()],
                    },
                    "output": {
                        "title": sample["title"],
                        "platform": sample["platform"],
                        "fields": {labels[key]["name"]: list(dict.fromkeys(values)) for key, values in fields.items()},
                        "documentLabels": [labels[key]["name"] for key in sample["fileLabels"]],
                    },
                }
                line = (encode(example) + "\n").encode("utf-8")
                if content.tell() + len(line) > 20 * 1024 * 1024:
                    problem("Few-shot 文件超过 20 MB，请将样本分成较小的发布版本", 413, "ANNOTATION_SIZE")
                content.write(line)
        content.seek(0)
        return content

    def compare_adm(self, ident, release_id):
        dataset = self.dataset(ident, release_id)
        if dataset["project"]["kind"] != "adm":
            problem("仅 ADM 项目支持与现有解析结果对照")
        source = ParsingService(self.config)
        results = []
        for sample in dataset["samples"]:
            result = {"sampleId": sample["id"], "title": sample["title"], "status": "unlinked", "fields": []}
            results.append(result)
            task_id = sample["sourceTaskId"]
            if not task_id:
                continue
            result["status"] = "unavailable"
            if not self.admin and MENU_ADM not in (self.user.get("menu_codes") or []):
                continue
            try:
                task = source._get(self.user, task_id)
            except AdmError as exc:
                if exc.status >= 500:
                    raise
                continue
            candidate = task.get("candidate")
            if isinstance(candidate, dict):
                result.update(status="compared", fields=compare_candidate(sample, candidate))
        return {"samples": results}
