from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AttachmentDocumentationContractTests(unittest.TestCase):
    def test_canonical_attachment_runbook_covers_every_release_layer(self):
        runbook = (ROOT / "docs" / "gbrain-attachment-runbook.md").read_text(encoding="utf-8")

        required_contract = (
            "POST /api/entity-attach-file/<URL-encoded-slug>",
            "upload_attachment_via_stargraph.py",
            "durable_storage_verified",
            "canonical_relative_path",
            "size_bytes",
            "sha256",
            "remote_read_verified",
            "storage_disposition",
            "gbrain files verify",
            "Cold-cache recovery",
            "Backup and restore",
            "Regression firewall",
            "Release checklist",
        )
        for marker in required_contract:
            with self.subTest(marker=marker):
                self.assertIn(marker, runbook)

        self.assertIn("Do not call `gbrain files upload` directly", runbook)
        self.assertIn("A Markdown reference, a ledger row", runbook)
        self.assertIn("Never claim partial success", runbook)

    def test_remote_media_runbook_defers_writes_to_canonical_contract(self):
        remote = (ROOT / "docs" / "memory-stargraph-remote-gbrain-media-import-runbook.md").read_text(encoding="utf-8")

        self.assertIn("[GBrain Attachment Safety and Verification](gbrain-attachment-runbook.md)", remote)
        self.assertIn("Direct file-ledger commands from a thin client or ad hoc script are unsupported.", remote)
        self.assertNotRegex(remote, re.compile(r"(?m)^\s*gbrain files upload\s"))
        self.assertNotIn("[[docs/memory-stargraph-remote-media-runbook]]", remote)

    def test_attachment_runbook_is_discoverable_and_release_blocking(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        lowercase_readme = (ROOT / "readme.md").read_text(encoding="utf-8")
        automation = (ROOT / "docs" / "automation-runbook.md").read_text(encoding="utf-8")

        self.assertEqual(readme, lowercase_readme)
        self.assertIn("docs/gbrain-attachment-runbook.md", readme)
        self.assertIn("docs/memory-stargraph-remote-gbrain-media-import-runbook.md", readme)
        self.assertIn("## Attachment Regression Release Gate", automation)
        self.assertIn("gbrain-attachment-runbook.md", automation)
        self.assertIn("durable_storage_verified: true", automation)
        self.assertIn("python3 -m unittest tests.test_documentation_contracts", automation)


if __name__ == "__main__":
    unittest.main()
