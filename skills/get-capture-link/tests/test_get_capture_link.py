from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "get_capture_link.py"
SPEC = importlib.util.spec_from_file_location("get_capture_link", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)

ROOT_SLUG = "notes/memory-starmap-capture-list"
ROOT = f"""# Memory Starmap Capture List

## Capture Items

| id | status | source kind | source | target | node | updated | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CAP-0001 | planned | url | https://example.com/one |  | [[{ROOT_SLUG}/cap-0001]] | 2026-07-15T09:00:00-07:00 | queued |
| CAP-0002 | failed | url | https://example.com/two |  | [[{ROOT_SLUG}/failure]] | 2026-07-15T10:00:00-07:00 | retry needed |
"""


class FakeReadOnlyGBrain:
    def __init__(self, markdown: str):
        self.markdown = markdown
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> str:
        self.calls.append(tuple(args))
        if args == ("get", ROOT_SLUG):
            return self.markdown
        raise AssertionError(f"unexpected gbrain command: {args}")


class GetCaptureLinkTests(unittest.TestCase):
    def test_status_filter_and_exact_clickable_links_are_read_only(self):
        backend = FakeReadOnlyGBrain(ROOT)
        with mock.patch.object(module, "run_gbrain", side_effect=backend):
            result = module.read_capture_backlog(status="failed")

        self.assertEqual([item["id"] for item in result["items"]], ["CAP-0002"])
        self.assertEqual(
            result["items"][0]["link"],
            "[notes/memory-starmap-capture-list/failure]"
            "(http://127.0.0.1:8788/?slug=notes%2Fmemory-starmap-capture-list%2Ffailure)",
        )
        self.assertEqual(backend.calls, [("get", ROOT_SLUG)])

    def test_id_filter_counts_all_rows_and_json_cli_output(self):
        backend = FakeReadOnlyGBrain(ROOT)
        with (
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch("sys.argv", ["get_capture_link.py", "--id", "CAP-0001", "--json"]),
            mock.patch("builtins.print") as output,
        ):
            self.assertEqual(module.main(), 0)

        payload = json.loads(output.call_args.args[0])
        self.assertEqual([item["id"] for item in payload["items"]], ["CAP-0001"])
        self.assertEqual(payload["counts"], {"capturing": 0, "completed": 0, "failed": 1, "planned": 1})
        self.assertEqual(backend.calls, [("get", ROOT_SLUG)])

    def test_invalid_status_is_rejected_before_gbrain_is_called(self):
        backend = FakeReadOnlyGBrain(ROOT)
        with mock.patch.object(module, "run_gbrain", side_effect=backend):
            with self.assertRaisesRegex(ValueError, "status must be"):
                module.read_capture_backlog(status="unknown")
        self.assertEqual(backend.calls, [])


if __name__ == "__main__":
    unittest.main()
