from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data_report_api.services.admwf.attachments import AdmAttachmentStorage
from data_report_api.services.admwf.policy import AdmError
from data_report_api.services.admwf.service import AdmWorkflowService


class Upload:
    def __init__(self, filename, content, mimetype="text/html"):
        self.filename = filename
        self.stream = BytesIO(content)
        self.mimetype = mimetype


class AdmAttachmentStorageTest(unittest.TestCase):
    def test_uses_generated_path_and_safe_preview_mime(self):
        with TemporaryDirectory() as root:
            storage = AdmAttachmentStorage({"ADM_ATTACHMENT_ROOT": root, "ADM_ATTACHMENT_MAX_BYTES": 100})
            saved = storage.save(7, Upload("../../proof.txt", b"evidence"))
            self.assertEqual(saved["originalFileName"], "proof.txt")
            self.assertEqual(saved["mimeType"], "text/plain; charset=utf-8")
            self.assertEqual(storage.path(saved["storageKey"]).read_bytes(), b"evidence")
            self.assertEqual(Path(saved["storageKey"]).parts[0], "7")

    def test_rejects_oversize_file_without_leaving_partial_file(self):
        with TemporaryDirectory() as root:
            storage = AdmAttachmentStorage({"ADM_ATTACHMENT_ROOT": root, "ADM_ATTACHMENT_MAX_BYTES": 3})
            with self.assertRaises(AdmError):
                storage.save(8, Upload("proof.pdf", b"four"))
            self.assertEqual(list(Path(root).rglob("*.uploading")), [])

    def test_line_attachment_is_bound_to_selected_line_and_checks_responsibility(self):
        class Repository:
            def __init__(self):
                self.added = []

            @staticmethod
            def get_case(case_id):
                return {
                    "case": {"id": case_id, "case_status": "ACTIVE", "coordinator_id": 7},
                    "lines": [
                        {"id": 11, "line_status": "PROCESSING", "leader_id": 5, "operator_id": 6},
                        {"id": 12, "line_status": "PROCESSING", "leader_id": 5, "operator_id": 8},
                    ],
                }

            def add_attachment(self, case_id, actor, category, metadata, line_id=None):
                self.added.append((case_id, actor, category, metadata, line_id))
                return {"attachments": [{"id": 1, "source_line_id": line_id}]}

        with TemporaryDirectory() as root:
            repository = Repository()
            service = AdmWorkflowService(
                {"ADM_ATTACHMENT_ROOT": root, "ADM_ATTACHMENT_MAX_BYTES": 100},
                repository=repository,
                catalog=object(),
            )
            user = {"id": 6, "display_name": "操作员", "permissions": ["adm.view"]}
            result = service.upload_attachment(user, 3, Upload("proof.txt", b"proof"), "APPEAL", "11")
            self.assertEqual(repository.added[-1][-1], 11)
            self.assertEqual(result["attachments"][0]["sourceLineId"], 11)

            with self.assertRaisesRegex(AdmError, "不在该ADM主单办理范围内"):
                service.upload_attachment(user, 3, Upload("other.txt", b"proof"), "APPEAL", "12")
            with self.assertRaisesRegex(AdmError, "不属于当前ADM主单"):
                service.upload_attachment(user, 3, Upload("missing.txt", b"proof"), "APPEAL", "99")


if __name__ == "__main__":
    unittest.main()
