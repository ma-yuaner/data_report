"""Material limits and source verification for manual annotation."""
import hashlib
import math
import os
import re
import tempfile
from pathlib import Path
from unicodedata import normalize as unicode_normalize
from uuid import uuid4

from .adm_parsing.documents import EXTENSIONS, extract
from .admwf.policy import AdmError

MAX_FILE = 20 * 1024 * 1024
MAX_TOTAL = 50 * 1024 * 1024
MAX_FILES = 10
MAX_MARKS = 300
HASH = re.compile(r"[0-9a-f]{64}")


def problem(message, status=422, code="ANNOTATION_INVALID"):
    raise AdmError(message, status, code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def short_text(value, limit, *, required=False):
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        problem(f"请填写 {limit} 字以内的文本")
    value = value.strip()
    if required and not value:
        problem("请填写必填内容")
    return value


def filename(value):
    name = short_text(Path(str(value or "").replace("\\", "/")).name, 240, required=True)
    if Path(name).suffix.lower() not in EXTENSIONS:
        problem("仅支持 PDF、XLSX、TXT、CSV 和 DOCX")
    if any(ord(char) < 32 for char in name):
        problem("文件名包含无效字符")
    return name


class AnnotationFiles:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, key):
        # Digest-only filenames keep user filenames and ADM paths out of disk addressing.
        if not isinstance(key, str) or not HASH.fullmatch(key):
            problem("原件地址无效", 404)
        path = (self.root / key).resolve()
        if path.parent != self.root or not path.is_file():
            problem("原件未找到，请联系管理员核查备份", 404)
        return path

    def material(self, named_bytes):
        self.root.mkdir(parents=True, exist_ok=True)
        files = []
        # Parse in staging. Failed inputs do not accumulate in persistent storage.
        with tempfile.TemporaryDirectory(prefix="import-", dir=self.root) as directory:
            staging = Path(directory)
            for name, data in named_bytes:
                key = digest(data)
                if not data or len(data) > MAX_FILE:
                    problem("单份文件需大于 0 且不超过 20 MB", 413)
                storage_key = key + Path(name).suffix.lower()
                (staging / storage_key).write_bytes(data)
                files.append({"id": uuid4().hex, "name": name, "sha256": key,
                              "size": len(data), "storageKey": storage_key, "pages": None})
            segments = extract(files, staging)
            file_index = {f["id"]: f for f in files}
            for segment in segments:
                file = file_index[segment["fileId"]]
                if Path(file["name"]).suffix.lower() == ".pdf":
                    page = int(segment["locator"][1:-1])
                    segment["page"] = page
                    file["pages"] = max(file["pages"] or 0, page)
            for file in files:
                src = staging / file["storageKey"]
                if src.exists():
                    os.replace(src, self.root / file["sha256"])
        return [{key: value for key, value in f.items() if key != "storageKey"} for f in files], segments


def pdf_text(value):
    # PDF.js and pypdf can disagree about spaces between glyph runs and ligatures.
    return re.sub(r"[^\S\x1c-\x1f]+", "", unicode_normalize("NFKC", value))


def validate_mark(mark, fields, segments, *, title=False, pdf_pages=None):
    if not isinstance(mark, dict):
        problem("原文标注格式无效")
    file_id = mark.get("fileId")
    if not isinstance(file_id, str):
        problem("请选择标注所属文件")
    label = mark.get("labelId")
    if not title and (not isinstance(label, str) or label not in fields):
        problem("请选择当前项目的字段标签")
    page = mark.get("page")
    if page is not None and (type(page) is not int or not 1 <= page <= 200):
        problem("原文页码无效")
    segment_id = mark.get("segmentId")
    if segment_id is not None and not isinstance(segment_id, str):
        problem("原文段落无效")
    segment = next((item for item in segments if item["fileId"] == file_id and (
        item["id"] == segment_id if segment_id else page is not None and item.get("page") == page)), None)
    if not segment or (page is not None and page != segment.get("page")):
        problem("原文定位与文件不匹配")
    quote = short_text(mark.get("quote"), 200 if title else 2000, required=True)
    start, end = mark.get("start"), mark.get("end")
    rects = mark.get("rects") or []
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= 100_000:
        problem("原文字符位置无效")
    result = {"fileId": file_id, "segmentId": segment["id"], "quote": quote, "start": start, "end": end}
    if segment.get("page") is not None:
        result["page"] = segment["page"]
        page_text = pdf_pages[segment["id"]] if pdf_pages is not None else pdf_text(segment["text"])
        needle = pdf_text(quote)
        occurrence = page_text.find(needle) if needle else -1
        if occurrence >= 0 and page_text.find(needle, occurrence+1) < 0:
            # The same unique text can be selected in either PDF or extracted-text view.
            result["canonicalRange"] = [occurrence, occurrence+len(needle)]
    if rects:
        # Browser PDF glyph offsets differ from pypdf; also prove the quote exists in the page.
        if not page or not isinstance(rects, list) or len(rects) > 100:
            problem("PDF 高亮位置无效")
        verified = []
        for rect in rects:
            if not isinstance(rect, dict):
                problem("PDF 高亮位置无效")
            values = [rect.get(key) for key in ("x", "y", "w", "h")]
            if any(type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value) for value in values):
                problem("PDF 高亮坐标超出范围")
            x, y, width, height = values
            if width == 0 or height == 0 or x+width > 1.00001 or y+height > 1.00001:
                problem("PDF 高亮范围无效")
            verified.append(dict(zip(("x", "y", "w", "h"), values)))
        if occurrence < 0:
            problem(f"第 {page} 页的选区无法在提取原文中定位，请切到「提取正文」重新标记")
        result["rects"] = verified
    else:
        # Browser range offsets count UTF-16 code units, including surrogate pairs.
        source = segment["text"].encode("utf-16-le")
        try:
            selected = source[start*2:end*2].decode("utf-16-le").strip()
        except UnicodeDecodeError:
            selected = None
        if end*2 > len(source) or selected != quote:
            problem("文字选区与提取原文不一致，请重新选择")
    if not title:
        result.update(id=uuid4().hex, labelId=label)
    return result


def position(mark):
    base = (mark["fileId"], mark["segmentId"])
    if mark.get("canonicalRange"):
        return (*base, "text", *mark["canonicalRange"])
    if mark.get("rects"):
        return (*base, "pdf", geometry(mark))
    return (*base, "raw", mark["start"], mark["end"])


def geometry(mark):
    return tuple(sorted(tuple(round(rect[key], 3) for key in ("x", "y", "w", "h"))
                        for rect in mark.get("rects", [])))
