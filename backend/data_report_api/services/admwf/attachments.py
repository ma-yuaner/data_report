"""Controlled file storage for shared ADM master attachments."""

from pathlib import Path
import hashlib
import os
import uuid

from .policy import AdmError


class AdmAttachmentStorage:
    def __init__(self, config):
        self.root = Path(str(config.get("ADM_ATTACHMENT_ROOT") or "/app/var/adm/attachments")).resolve()
        self.maximum = int(config.get("ADM_ATTACHMENT_MAX_BYTES") or 20 * 1024 * 1024)

    @staticmethod
    def _name(upload):
        name = Path(str(getattr(upload, "filename", "") or "").replace("\\", "/")).name.strip()
        if not name:
            raise AdmError("附件文件名不能为空")
        if len(name) > 255:
            raise AdmError("附件文件名不能超过255个字符")
        return name

    def save(self, case_id, upload):
        original_name = self._name(upload)
        extension = Path(original_name).suffix.lower()[:20]
        preview_mimes = {
            ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".gif": "image/gif", ".txt": "text/plain; charset=utf-8",
        }
        case_directory = (self.root / str(int(case_id))).resolve()
        if self.root not in case_directory.parents:
            raise AdmError("附件存储路径无效", 500, "ADM_ATTACHMENT_STORAGE")
        case_directory.mkdir(parents=True, exist_ok=True)
        storage_name = uuid.uuid4().hex + extension
        final_path = (case_directory / storage_name).resolve()
        temporary_path = (case_directory / (storage_name + ".uploading")).resolve()
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary_path.open("xb") as target:
                while True:
                    chunk = upload.stream.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.maximum:
                        raise AdmError(f"附件不能超过{self.maximum // (1024 * 1024)}MB")
                    digest.update(chunk)
                    target.write(chunk)
            if size == 0:
                raise AdmError("附件内容不能为空")
            os.replace(temporary_path, final_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return {
            "originalFileName": original_name,
            "storageKey": f"{int(case_id)}/{storage_name}",
            "fileExtension": extension,
            "mimeType": preview_mimes.get(extension, "application/octet-stream"),
            "fileSize": size,
            "sha256": digest.hexdigest(),
            "previewStatus": "AVAILABLE" if extension in preview_mimes else "UNSUPPORTED",
        }

    def path(self, storage_key):
        target = (self.root / str(storage_key or "")).resolve()
        if self.root not in target.parents or not target.is_file():
            raise AdmError("附件原件不存在", 404, "ADM_ATTACHMENT_NOT_FOUND")
        return target
