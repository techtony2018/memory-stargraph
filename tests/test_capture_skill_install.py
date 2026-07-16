from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "automation" / "install_capture_skills.py"
SPEC = importlib.util.spec_from_file_location("install_capture_skills", SCRIPT)
installer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(installer)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class CaptureSkillInstallTests(unittest.TestCase):
    def test_installer_mirrors_repository_sources_byte_for_byte_and_idempotently(self):
        with tempfile.TemporaryDirectory() as td:
            codex_home = Path(td) / "codex"
            openclaw_home = Path(td) / "openclaw"
            first = installer.install(ROOT, codex_home, openclaw_home)
            second = installer.install(ROOT, codex_home, openclaw_home)

            self.assertEqual(first, {"ok": True, "installed": ["add-capture-link", "get-capture-link"]})
            self.assertEqual(second, first)
            for skill in first["installed"]:
                canonical = tree_digest(ROOT / "skills" / skill)
                self.assertEqual(canonical, tree_digest(codex_home / "skills" / skill))
                self.assertEqual(canonical, tree_digest(openclaw_home / "skills" / skill))


if __name__ == "__main__":
    unittest.main()
