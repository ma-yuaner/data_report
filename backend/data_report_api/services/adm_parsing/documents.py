"""Bounded text extraction with deterministic locators; never executes documents."""
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from ..admwf.policy import AdmError

EXTENSIONS = {".pdf", ".xlsx", ".txt", ".csv", ".docx"}


def extract(files, root, maximum=60000):
    segments, total = [], 0

    def add(file, locator, text):
        nonlocal total
        text = str(text or "").strip()
        if not text:
            return
        total += len(text)
        if total > maximum or len(segments) >= 4000:
            raise AdmError("材料正文超过单次解析上限，请拆分来件；未截断材料或调用模型", 413, "PARSE_INPUT_LIMIT")
        segments.append({"id": f"s{len(segments)+1}", "fileId": file["id"], "locator": locator, "text": text})

    for file in files:
        path = (Path(root) / file["storageKey"]).resolve()
        if Path(root).resolve() not in path.parents or not path.is_file():
            raise AdmError("原件不存在或存储路径无效", 422, "PARSE_FILE_MISSING")
        extension = Path(file["name"]).suffix.lower()
        start = len(segments)
        try:
            if extension in {".txt", ".csv"}:
                raw = path.read_bytes()
                try:
                    content = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    content = raw.decode("gb18030")
                if "\x00" in content:
                    raise ValueError("binary text")
                for i, line in enumerate(content.splitlines(), 1):
                    add(file, f"第{i}行", line)
            elif extension == ".pdf":
                from pypdf import PdfReader
                if not path.read_bytes()[:8].startswith(b"%PDF-"):
                    raise ValueError("PDF signature")
                reader = PdfReader(path)
                if reader.is_encrypted or not 0 < len(reader.pages) <= 200:
                    raise AdmError("PDF已加密或超过200页，请解密或拆分", 422, "PARSE_PDF_LIMIT")
                for i, page in enumerate(reader.pages, 1):
                    add(file, f"第{i}页", page.extract_text())
            elif extension in {".xlsx", ".docx"}:
                with zipfile.ZipFile(path) as archive:
                    entries = archive.infolist()
                    if len(entries) > 5000 or sum(e.file_size for e in entries) > 40_000_000 or any(e.flag_bits & 1 for e in entries):
                        raise AdmError("文档加密或解压内容过大", 422, "PARSE_ARCHIVE_LIMIT")
                    if extension == ".docx":
                        content = archive.read("word/document.xml")
                        if re.search(br"<!DOCTYPE|<!ENTITY", content, re.I):
                            raise ValueError("XML entities")
                        tree = ElementTree.fromstring(content)
                        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                        for i, paragraph in enumerate(tree.findall(".//w:p", ns), 1):
                            add(file, f"第{i}段", "".join(t.text or "" for t in paragraph.findall(".//w:t", ns)))
                if extension == ".xlsx":
                    from openpyxl import load_workbook
                    book = load_workbook(path, read_only=True, data_only=True)
                    try:
                        cells = 0
                        for sheet in book:
                            if sheet.max_row > 20000 or sheet.max_column > 200:
                                raise AdmError("Excel范围过大，请拆分", 413, "PARSE_EXCEL_LIMIT")
                            for row in sheet.iter_rows():
                                cells += len(row)
                                if cells > 200000:
                                    raise AdmError("Excel单元格超过上限", 413, "PARSE_EXCEL_LIMIT")
                                populated = [f"{c.coordinate}: {c.value}" for c in row if c.value is not None]
                                if populated:
                                    add(file, f"{sheet.title}!第{row[0].row}行", " | ".join(populated))
                    finally:
                        book.close()
            else:
                raise ValueError("unsupported")
        except AdmError:
            raise
        except Exception:
            raise AdmError("附件损坏、格式不匹配或编码无法读取，请重新提供可读文件", 422, "PARSE_FILE_UNREADABLE") from None
        if len(segments) == start:
            raise AdmError("附件没有可读取文字；扫描PDF请先OCR，不能将空白视为解析成功", 422, "PARSE_OCR_REQUIRED")
    return segments
