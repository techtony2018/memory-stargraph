from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "get-capture-link"
    / "scripts"
    / "get_capture_link.py"
)
SPEC = importlib.util.spec_from_file_location("get_capture_link", SCRIPT)
capture = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(capture)


class GetCaptureLinkTests(unittest.TestCase):
    def test_read_root_prefers_stargraph_endpoint(self):
        endpoint = subprocess.CompletedProcess(
            ["curl"],
            0,
            json.dumps({"content": "# Capture backlog\n"}),
            "",
        )
        with (
            mock.patch.object(capture.subprocess, "run", return_value=endpoint) as run,
            mock.patch.object(capture, "run_gbrain") as cli,
        ):
            content = capture.read_root()

        self.assertEqual(content, "# Capture backlog\n")
        self.assertEqual(run.call_args.args[0][0], "curl")
        cli.assert_not_called()

    def test_read_root_falls_back_to_cli_for_read_compatibility(self):
        endpoint = subprocess.CompletedProcess(["curl"], 22, "", "unavailable")
        with (
            mock.patch.object(capture.subprocess, "run", return_value=endpoint),
            mock.patch.object(capture, "run_gbrain", return_value="# CLI fallback\n") as cli,
        ):
            content = capture.read_root()

        self.assertEqual(content, "# CLI fallback\n")
        cli.assert_called_once_with("get", capture.ROOT_SLUG)


if __name__ == "__main__":
    unittest.main()
