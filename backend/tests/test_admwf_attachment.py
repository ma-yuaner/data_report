from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data_report_api.services.admwf.attachments import AdmAttachmentStorage
from data_report_api.services.admwf.policy import AdmError


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


if __name__ == "__main__":
    unittest.main()
