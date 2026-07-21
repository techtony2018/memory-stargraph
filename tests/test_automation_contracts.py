from pathlib import Path
import re
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AutomationContractTests(unittest.TestCase):
    def test_worker_role_titles_are_user_facing_only(self):
        expected = {
            "gbrain-x-intelligence-capture": {
                "title": "GBrain Intelligence Researcher",
                "rrule": "FREQ=DAILY;BYHOUR=0;BYMINUTE=15;BYSECOND=0",
                "target_thread_id": "{{GBRAIN_X_INTELLIGENCE_THREAD_ID}}",
                "role_files": ("prompt.md", "heartbeat-prompt.md", "thread-bootstrap.md"),
            },
            "memory-stargraph-daily-learning-intake": {
                "title": "Memory Stargraph Quality & Learning Analyst",
                "rrule": "FREQ=DAILY;BYHOUR=1;BYMINUTE=0;BYSECOND=0",
                "target_thread_id": "{{LEARNING_INTAKE_THREAD_ID}}",
                "role_files": ("prompt.md", "heartbeat-prompt.md", "thread-bootstrap.md"),
            },
            "memory-stargraph-wish-to-reallity": {
                "title": "Memory Stargraph Developer",
                "rrule": "FREQ=DAILY;BYHOUR=3;BYMINUTE=30;BYSECOND=0",
                "target_thread_id": "{{WISH_TO_REALLITY_THREAD_ID}}",
                "role_files": ("prompt.md", "heartbeat-prompt.md", "thread-bootstrap.md"),
            },
            "memory-stargraph-divergent-product-discovery": {
                "title": "Memory Stargraph Product Strategist",
                "rrule": "FREQ=WEEKLY;BYDAY=SU;BYHOUR=4;BYMINUTE=0;BYSECOND=0",
                "target_thread_id": "{{PRODUCT_DISCOVERY_THREAD_ID}}",
                "role_files": ("prompt.md", "heartbeat-prompt.md", "thread-bootstrap.md"),
            },
            "memory-stargraph-capture-link-drain": {
                "title": "Memory Stargraph Knowledge Curator",
                "rrule": "FREQ=DAILY;BYHOUR=0;BYMINUTE=0;BYSECOND=0",
                "target_thread_id": "{{CAPTURE_LINK_THREAD_ID}}",
                "role_files": ("prompt.md", "heartbeat-prompt.md", "thread-bootstrap.md"),
            },
            "memory-stargraph-goal-steward-daily-review": {
                "title": "Memory Stargraph Product Owner",
                "rrule": "FREQ=DAILY;BYHOUR=7;BYMINUTE=30;BYSECOND=0",
                "target_thread_id": "{{STEWARD_THREAD_ID}}",
                "role_files": ("prompt.md", "steward-thread-prompt.md"),
            },
            "memory-stargraph-ux-engineer-daily-dogfood": {
                "title": "Memory Stargraph UX Engineer",
                "rrule": "FREQ=DAILY;BYHOUR=2;BYMINUTE=0;BYSECOND=0",
                "target_thread_id": "{{UX_ENGINEER_THREAD_ID}}",
                "role_files": ("prompt.md", "heartbeat-prompt.md", "thread-bootstrap.md"),
            },
        }

        for automation_id, contract in expected.items():
            directory = ROOT / "automations" / automation_id
            definition = tomllib.loads((directory / "automation.toml").read_text())

            self.assertEqual(definition["id"], automation_id)
            self.assertEqual(definition["name"], contract["title"])
            self.assertEqual(definition["rrule"], contract["rrule"])
            self.assertEqual(definition["timezone"], "America/Los_Angeles")
            self.assertEqual(definition["destination"], "thread")
            self.assertEqual(
                definition["target_thread_id"], contract["target_thread_id"]
            )
            for role_file in contract["role_files"]:
                self.assertIn(
                    contract["title"],
                    (directory / role_file).read_text(),
                    f"{automation_id}/{role_file} missing user-facing role title",
                )

    def test_ux_engineer_dogfoods_deployed_app_with_bounded_authority(self):
        directory = ROOT / "automations/memory-stargraph-ux-engineer-daily-dogfood"
        definition = tomllib.loads((directory / "automation.toml").read_text())
        contract = "\n".join(
            (directory / name).read_text()
            for name in ("prompt.md", "heartbeat-prompt.md", "thread-bootstrap.md")
        )
        self.assertEqual(definition["id"], "memory-stargraph-ux-engineer-daily-dogfood")
        self.assertEqual(definition["name"], "Memory Stargraph UX Engineer")
        self.assertEqual(definition["rrule"], "FREQ=DAILY;BYHOUR=2;BYMINUTE=0;BYSECOND=0")
        self.assertEqual(definition["timezone"], "America/Los_Angeles")
        self.assertEqual(definition["destination"], "thread")
        self.assertEqual(definition["target_thread_id"], "{{UX_ENGINEER_THREAD_ID}}")
        for phrase in (
            "http://127.0.0.1:8788/api/health",
            "dashboard-managed",
            "demanding human user",
            "rolling seven-day",
            "reuse a suitable Memory Stargraph tab",
            "Chrome CDP",
            "environment=test",
            "synthetic=true",
            "test_run=true",
            "pair_id=ux-dogfood:{invocation_id}:{journey_slug}",
            "at most three planned TODOs",
            "must not implement fixes",
            "Goal-linked Run",
            "dated UX report",
            "manual trigger",
            "no fixed cutoff",
        ):
            self.assertIn(phrase, contract)
        prompt = (directory / "prompt.md").read_text()
        for prohibition in (
            "must not deploy",
            "must not perform destructive operations",
            "must not auto-approve resolver proposals",
        ):
            self.assertIn(prohibition, prompt)

    def test_ux_engineer_evidence_reaches_product_owner_and_learning_intake(self):
        paths = (
            ROOT / "automations/README.md",
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/prompt.md",
            ROOT
            / "automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md",
            ROOT / "automations/memory-stargraph-daily-learning-intake/prompt.md",
        )
        contract = "\n".join(path.read_text() for path in paths)
        for phrase in (
            "memory-stargraph-ux-engineer-daily-dogfood",
            "Memory Stargraph UX Engineer",
            "Daily 2:00 AM",
            "UX reports",
            "journey coverage",
            "repeated UX",
            "data-quality patterns",
        ):
            self.assertIn(phrase, contract)

    def test_daily_learning_intake_runs_yoda_evaluator_before_promoting_gaps(self):
        prompt = (ROOT / "automations/memory-stargraph-daily-learning-intake/prompt.md").read_text()
        readme = (ROOT / "automations/README.md").read_text()
        runbook = (ROOT / "docs/automation-runbook.md").read_text()
        script = ROOT / "scripts/automation/yoda_gap_evaluator.py"
        contract = "\n".join((prompt, readme, runbook))

        self.assertTrue(script.exists())
        for phrase in (
            "Yoda Evaluator",
            "scripts/automation/yoda_gap_evaluator.py run",
            "at least 10",
            "Ask Yoda API",
            "environment=test",
            "synthetic=true",
            "test_run=true",
            "same question in Codex",
            "compare",
            "TODO",
            "deduplicate",
        ):
                self.assertIn(phrase, contract)

    def test_deployment_packaging_includes_yoda_evaluator_and_worker_api_helpers(self):
        deploy = (ROOT / "scripts/automation/deploy_targets.sh").read_text()

        for path in (
            "scripts/automation/yoda_gap_evaluator.py",
            "scripts/automation/gbrain_worker_api.py",
            "scripts/automation/source_sync_preflight.py",
            "tests/test_yoda_gap_evaluator.py",
            "tests/test_todo_backlog_compaction.py",
            "tests/test_source_sync_preflight.py",
        ):
            self.assertIn(path, deploy)

    def test_daily_learning_intake_has_source_sync_preflight_contract(self):
        prompt = (
            ROOT / "automations/memory-stargraph-daily-learning-intake/prompt.md"
        ).read_text()
        runbook = (ROOT / "docs/automation-runbook.md").read_text()
        contract = "\n".join((prompt, runbook))

        for phrase in (
            "source-sync preflight",
            "checkout HEAD",
            "origin/main",
            "dashboard service version",
            "required script existence",
            "fast-forward-only sync",
            "dirty or divergent checkout",
            "verified dashboard service copy",
            "preserve unrelated local changes",
        ):
            self.assertIn(phrase, contract)

    def test_sre_automations_use_distinct_tasks_with_one_worker_contract(self):
        daily_dir = ROOT / "automations/memory-stargraph-sre-daily-reliability"
        weekly_dir = ROOT / "automations/memory-stargraph-sre-weekly-resilience"
        shared_dir = ROOT / "automations/memory-stargraph-sre"
        daily = tomllib.loads((daily_dir / "automation.toml").read_text())
        weekly = tomllib.loads((weekly_dir / "automation.toml").read_text())
        prompt = (shared_dir / "prompt.md").read_text()
        bootstrap = (shared_dir / "thread-bootstrap.md").read_text()
        heartbeats = "\n".join(
            ((daily_dir / "heartbeat-prompt.md").read_text(),
             (weekly_dir / "heartbeat-prompt.md").read_text())
        )
        contract = "\n".join((prompt, bootstrap, heartbeats))

        self.assertEqual(daily["id"], "memory-stargraph-sre-daily-reliability")
        self.assertEqual(daily["name"], "Memory Stargraph SRE Daily Reliability")
        self.assertEqual(daily["rrule"], "FREQ=DAILY;BYHOUR=3;BYMINUTE=0;BYSECOND=0")
        self.assertEqual(weekly["id"], "memory-stargraph-sre-weekly-resilience")
        self.assertEqual(weekly["name"], "Memory Stargraph SRE Weekly Resilience")
        self.assertEqual(weekly["rrule"], "FREQ=WEEKLY;BYDAY=SU;BYHOUR=11;BYMINUTE=0;BYSECOND=0")
        for definition in (daily, weekly):
            self.assertEqual(definition["timezone"], "America/Los_Angeles")
            self.assertEqual(definition["destination"], "thread")
            self.assertEqual(definition["worker_prompt_file"], "../memory-stargraph-sre/prompt.md")
            self.assertEqual(definition["thread_bootstrap_file"], "../memory-stargraph-sre/thread-bootstrap.md")
        self.assertEqual(daily["target_thread_id"], "{{SRE_DAILY_THREAD_ID}}")
        self.assertEqual(weekly["target_thread_id"], "{{SRE_WEEKLY_THREAD_ID}}")
        self.assertNotEqual(daily["target_thread_id"], weekly["target_thread_id"])
        for phrase in (
            "source-sync preflight",
            "checkout HEAD",
            "origin/main HEAD",
            "deployed Memory Stargraph version",
            "selected source path",
            "clean stale",
            "fast-forward safely",
            "dirty or divergent",
            "do not overwrite user work",
            "Product Owner can verify",
        ):
            self.assertIn(phrase, contract)

        for phrase in (
            "Memory Stargraph SRE", "live Codex task state",
            "active Goal-linked Runs or leases", "performs no health probing",
            "task-local deferral", "deferred_due_to_worker_activity",
            "at most one completed daily review", "at most one completed weekly review",
            "7-day and 30-day baselines", "capacity headroom",
            "documented last-known-good", "chaos_skipped_no_safe_target",
            "resolver_probe_skipped_isolation_unverified",
            "pair_id=sre:{mode}:{invocation_id}:{probe_slug}",
            "must not implement product or GBrain code", "manual trigger",
            "no fixed cutoff",
        ):
            self.assertIn(phrase, contract)
        self.assertIn("mode=daily_reliability", heartbeats)
        self.assertIn("mode=weekly_resilience", heartbeats)

    def test_recurring_workers_share_source_sync_evidence_schema(self):
        worker_prompts = (
            ROOT / "automations/gbrain-x-intelligence-capture/prompt.md",
            ROOT / "automations/memory-stargraph-capture-link-drain/prompt.md",
            ROOT / "automations/memory-stargraph-daily-learning-intake/prompt.md",
            ROOT / "automations/memory-stargraph-divergent-product-discovery/prompt.md",
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/prompt.md",
            ROOT / "automations/memory-stargraph-sre/prompt.md",
            ROOT / "automations/memory-stargraph-ux-engineer-daily-dogfood/prompt.md",
            ROOT / "automations/memory-stargraph-wish-to-reallity/prompt.md",
        )
        runbook = (ROOT / "docs/automation-runbook.md").read_text()
        required_fields = (
            "workspace_path",
            "branch",
            "local_head",
            "upstream_ref",
            "upstream_head",
            "dirty_state",
            "divergent_state",
            "deployed_service_version",
            "required_script_existence",
            "selected_source_path",
            "selected_source_surface",
            "action_taken",
        )

        self.assertIn("Shared recurring-worker source-sync evidence schema", runbook)
        for prompt_path in worker_prompts:
            prompt = prompt_path.read_text()
            self.assertIn("shared recurring-worker source-sync evidence schema", prompt)
            for field in required_fields:
                self.assertIn(field, prompt, f"{prompt_path} missing {field}")

    def test_weekly_resilience_has_safe_noop_fault_target_until_owner_approval(self):
        sre = (ROOT / "automations/memory-stargraph-sre/prompt.md").read_text()
        runbook = (ROOT / "docs/automation-runbook.md").read_text()
        contract = sre + "\n" + runbook

        for phrase in (
            "synthetic-noop-fault-harness",
            "report-only harness",
            "without stopping, restarting, throttling, deleting, mutating, or redirecting production",
            "Product Owner approval",
            "chaos_skipped_no_safe_target",
            "post-probe health verification",
        ):
            self.assertIn(phrase, contract)

    def test_sre_evidence_reaches_owner_learning_and_engineer(self):
        paths = (
            ROOT / "automations/README.md",
            ROOT / "docs/automation-runbook.md",
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/prompt.md",
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md",
            ROOT / "automations/memory-stargraph-daily-learning-intake/prompt.md",
            ROOT / "automations/memory-stargraph-wish-to-reallity/prompt.md",
        )
        contract = "\n".join(path.read_text() for path in paths)
        for phrase in (
            "memory-stargraph-sre-daily-reliability",
            "memory-stargraph-sre-weekly-resilience",
            "Daily 3:00 AM",
            "Sunday 11:00 AM",
            "SRE Runs",
            "capacity headroom",
            "reliability incidents",
            "repeated reliability",
            "released its SRE lease",
            "critical SRE handoff",
            "resolver_probe_skipped_isolation_unverified",
            "chaos_skipped_no_safe_target",
        ):
            self.assertIn(phrase, contract)

    def test_product_owner_confirms_health_and_hands_incidents_to_sre(self):
        owner_paths = (
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/prompt.md",
            ROOT
            / "automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md",
        )
        sre = (ROOT / "automations/memory-stargraph-sre/prompt.md").read_text()
        sre_bootstrap = (
            ROOT / "automations/memory-stargraph-sre/thread-bootstrap.md"
        ).read_text()
        runbook = (ROOT / "docs/automation-runbook.md").read_text()
        owner = "\n".join(path.read_text() for path in owner_paths)

        for phrase in (
            "healthy, unhealthy, or unverified",
            "restricted or unknown execution context",
            "authoritative host-context route",
            "independent corroboration",
            "never report an outage from a transport failure alone",
            "mode=incident_response",
            "originating Product Owner task id",
            "affected target",
            "America/Los_Angeles timestamp",
            "finish the Product Owner review",
            "persistent daily SRE task",
        ):
            self.assertIn(phrase, owner + "\n" + runbook)

        for phrase in (
            "mode=incident_response",
            "verified quiet time",
            "originating Product Owner task id",
            "bounded documented remediation",
            "Goal-linked Run",
            "incident report",
            "send a concise result back",
            "resolver events",
        ):
            self.assertIn(phrase, sre + "\n" + runbook)
        for phrase in (
            "healthy, unhealthy, or unverified",
            "authoritative host context",
            "independent corroboration",
            "must not remediate an unverified target",
        ):
            self.assertIn(phrase, sre)
        self.assertIn(
            "daily SRE task also accepts `mode=incident_response`",
            sre_bootstrap,
        )

    def test_product_owner_worker_watch_has_eta_and_silent_failure_mitigation(self):
        directory = ROOT / "automations/memory-stargraph-goal-steward-daily-review"
        definition = tomllib.loads((directory / "automation.toml").read_text())
        prompt = (directory / "prompt.md").read_text()
        bootstrap = (directory / "steward-thread-prompt.md").read_text()
        readme = (ROOT / "automations/README.md").read_text()
        runbook = (ROOT / "docs/automation-runbook.md").read_text()
        contract = "\n".join((prompt, bootstrap, readme, runbook))

        self.assertEqual(definition["id"], "memory-stargraph-goal-steward-daily-review")
        self.assertEqual(definition["name"], "Memory Stargraph Product Owner")
        self.assertEqual(definition["timezone"], "America/Los_Angeles")
        self.assertEqual(definition["destination"], "thread")
        self.assertEqual(definition["target_thread_id"], "{{STEWARD_THREAD_ID}}")
        self.assertEqual(
            definition["rrule"],
            "FREQ=DAILY;BYHOUR=7;BYMINUTE=30;BYSECOND=0",
        )
        for phrase in (
            "Codex permits only one heartbeat per task",
            "role-specific estimated durations",
            "Expected role durations and watch windows",
            "interim Worker Watch windows",
            "morning full-review window",
            "very fast no-op check",
            "Memory Stargraph Developer",
            "progress within 30 minutes",
            "by 7:00 AM",
            "Memory Stargraph SRE weekly resilience",
            "by 2:30 PM",
            "missing start",
            "stale in-progress",
            "wrong destination task",
            "system error",
            "model out of capacity",
            "modal out of capacity",
            "blocked_or_silent",
            "send a bounded follow-up",
            "canonical worker task",
            "route confirmed infrastructure or health failures to the daily SRE task",
            "Do not duplicate worker-owned implementation",
            "defers because another worker is active",
            "temporary 10-minute watch",
            "retry or dispatch the originally blocked worker",
            "deferred_due_to_worker_activity",
        ):
            self.assertIn(phrase, contract)

    def test_product_owner_reports_dimension_score_trends(self):
        owner_prompt = (
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/prompt.md"
        ).read_text()
        owner_bootstrap = (
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md"
        ).read_text()
        runbook = (ROOT / "docs/automation-runbook.md").read_text()
        contract = "\n".join((owner_prompt, owner_bootstrap, runbook))

        for phrase in (
            "seven dimension scores",
            "day-over-day deltas/trends",
            "not only the weighted total",
            "no prior dimension baseline",
            "goal-progress-ledger.json",
        ):
            self.assertIn(phrase, contract)

    def test_product_owner_chains_worker_blocker_watches(self):
        owner_prompt = (
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/prompt.md"
        ).read_text()
        owner_bootstrap = (
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md"
        ).read_text()
        runbook = (ROOT / "docs/automation-runbook.md").read_text()
        contract = "\n".join((owner_prompt, owner_bootstrap, runbook))

        for phrase in (
            "defers because a different worker is active",
            "verify the blocking worker",
            "new 10-minute temporary watch for the actual blocking worker",
            "pending retry chain",
            "originally blocked worker",
        ):
            self.assertIn(phrase, contract)

    def test_product_owner_manual_dispatch_requires_send_and_readback_verification(self):
        owner_prompt = (
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/prompt.md"
        ).read_text()
        owner_bootstrap = (
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md"
        ).read_text()
        runbook = (ROOT / "docs/automation-runbook.md").read_text()
        contract = "\n".join((owner_prompt, owner_bootstrap, runbook))

        for phrase in (
            "Manual worker dispatch verification",
            "list_threads",
            "send_message_to_thread",
            "read_thread",
            "destination task id",
            "active or terminal turn",
            "no active or terminal readback",
            "bounded recovery follow-up",
            "Do not claim dispatch success from a send call alone",
        ):
            self.assertIn(phrase, contract)

    def test_engineer_and_ux_engineer_coordinate_with_deployment_leases(self):
        engineer = (
            ROOT / "automations/memory-stargraph-wish-to-reallity/prompt.md"
        ).read_text()
        ux = (
            ROOT / "automations/memory-stargraph-ux-engineer-daily-dogfood/prompt.md"
        ).read_text()
        contract_paths = (
            ROOT / "automations/memory-stargraph-wish-to-reallity/prompt.md",
            ROOT / "automations/memory-stargraph-ux-engineer-daily-dogfood/prompt.md",
            ROOT / "docs/automation-runbook.md",
            ROOT
            / "docs/superpowers/specs/2026-07-16-memory-stargraph-ux-engineer-design.md",
            ROOT
            / "docs/superpowers/plans/2026-07-16-memory-stargraph-ux-engineer.md",
        )
        contracts = {path: path.read_text() for path in contract_paths}
        docs = "\n".join(contracts[path] for path in contract_paths[2:])

        for phrase in (
            "active-change marker",
            "invocation id",
            "start time",
            "intended scope",
            "deployment fingerprint",
            "ui_version",
            "served HTML/JS asset version or hash",
            "local process cwd when available",
            "active UX Run/lease",
            "wait for UX to acknowledge and terminalize",
            "stale UX lease",
            "stale Developer marker",
            "Product Owner",
            "only after every required target passes",
            "leave active or failed change evidence visible",
        ):
            self.assertIn(phrase, engineer)

        for phrase in (
            "active-change marker",
            "deployment fingerprint",
            "active UX Run/lease",
            "re-read active Runs",
            "Developer priority wins",
            "before and after every journey",
            "discard all observations from the unstable run",
            "create or update no TODOs",
            "deferred_due_to_active_change",
            "before/after evidence",
        ):
            self.assertIn(phrase, ux)

        expected_stable_fields = {
            "health_state",
            "ui_version",
            "served_html_js_identity",
            "process_cwd",
            "source_deployment_identity",
        }
        volatile_fields = {"health_observed_at", "source_timestamp"}
        stable_line_pattern = re.compile(
            r"Stable deployment fingerprint fields:\s*([^\n]+)"
        )
        for path, contract in contracts.items():
            match = stable_line_pattern.search(contract)
            self.assertIsNotNone(
                match, f"{path} must define the stable fingerprint fields"
            )
            stable_fields = set(re.findall(r"`([^`]+)`", match.group(1)))
            self.assertEqual(expected_stable_fields, stable_fields, str(path))
            self.assertTrue(volatile_fields.isdisjoint(stable_fields), str(path))
            self.assertIn("health_observed_at", contract, str(path))
            self.assertIn("source timestamp", contract, str(path))
            self.assertIn(
                "excluded from deployment fingerprint equality", contract, str(path)
            )
            self.assertNotIn("health source state and timestamp", contract, str(path))

        self.assertNotIn("any fingerprint field changes", ux)
        self.assertIn(
            "Differences in `health_observed_at` or source timestamps alone never cause deferral",
            ux,
        )
        self.assertIn(
            "defer only when an active-change marker appears, health is unhealthy or unstable, or the stable deployment fingerprint changes",
            ux.lower(),
        )

        marker = engineer.index("active-change marker")
        editing = engineer.index("editing code", marker)
        self.assertLess(marker, editing)
        ux_lease = ux.index("active UX Run/lease")
        reread = ux.index("re-read active Runs", ux_lease)
        self.assertLess(ux_lease, reread)

        for phrase in (
            "Goal-linked Runs as cooperative change and UX leases",
            "scheduled and manual invocations",
            "no fixed kickoff or cutoff time",
            "must not silently deploy through an active UX lease",
        ):
            self.assertIn(phrase, docs)

    def test_every_worker_uses_dst_aware_pacific_reporting(self):
        workers = (
            "gbrain-x-intelligence-capture",
            "memory-stargraph-daily-learning-intake",
            "memory-stargraph-wish-to-reallity",
            "memory-stargraph-divergent-product-discovery",
            "memory-stargraph-goal-steward-daily-review",
            "memory-stargraph-capture-link-drain",
            "memory-stargraph-ux-engineer-daily-dogfood",
            "memory-stargraph-sre",
        )
        required = (
            "America/Los_Angeles",
            "timezone-aware ISO 8601",
            "PDT in summer",
            "PST in winter",
            "Do not use a fixed UTC-8 offset",
        )
        for worker in workers:
            prompt = (ROOT / "automations" / worker / "prompt.md").read_text()
            prompt_lower = prompt.lower()
            for phrase in required:
                self.assertIn(
                    phrase.lower(), prompt_lower, f"{worker} missing {phrase}"
                )

    def test_workers_notify_product_owner_after_terminal_or_deferred_runs(self):
        workers = (
            "gbrain-x-intelligence-capture",
            "memory-stargraph-daily-learning-intake",
            "memory-stargraph-wish-to-reallity",
            "memory-stargraph-divergent-product-discovery",
            "memory-stargraph-capture-link-drain",
            "memory-stargraph-ux-engineer-daily-dogfood",
            "memory-stargraph-sre",
        )
        required = (
            "Keep the detailed report in this worker task",
            "After a terminal outcome or deferral",
            "notify the canonical Memory Stargraph Product Owner task",
            "compact completion payload",
            "worker task id",
            "automation id",
            "invocation id",
            "terminal status",
            "Run/report slugs",
            "blockers",
            "approvals needed",
            "requested Product Owner follow-up",
            "product_owner_notification_pending",
            "product_owner_notification_status: pending_unacknowledged_delivery",
            "full compact payload",
        )
        for worker in workers:
            prompt = (ROOT / "automations" / worker / "prompt.md").read_text()
            prompt_lower = prompt.lower()
            for phrase in required:
                self.assertIn(
                    phrase.lower(), prompt_lower, f"{worker} missing {phrase}"
                )

        owner_prompt = (
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/prompt.md"
        ).read_text()
        for phrase in (
            "Worker notification and verification contract",
            "Workers keep their full reports in their own persistent tasks",
            "On notification, enter or inspect the worker's persistent task",
            "Do not accept a worker notification as completion by itself",
            "Do not rely on workers being able to call cross-thread messaging tools",
            "product_owner_notification_status: pending_unacknowledged_delivery",
            "acknowledged_by_product_owner",
        ):
            self.assertIn(phrase, owner_prompt)

    def test_capture_worker_is_persistent_midnight_and_manually_triggerable(self):
        definition = tomllib.loads(
            (
                ROOT
                / "automations/memory-stargraph-capture-link-drain/automation.toml"
            ).read_text()
        )
        prompt = (
            ROOT / "automations/memory-stargraph-capture-link-drain/prompt.md"
        ).read_text()
        self.assertEqual(definition["id"], "memory-stargraph-capture-link-drain")
        self.assertEqual(
            definition["rrule"], "FREQ=DAILY;BYHOUR=0;BYMINUTE=0;BYSECOND=0"
        )
        self.assertEqual(definition["timezone"], "America/Los_Angeles")
        self.assertEqual(definition["destination"], "thread")
        self.assertIn("{{CAPTURE_LINK_THREAD_ID}}", definition["target_thread_id"])
        self.assertIn("manual", prompt.lower())
        self.assertIn("there is no fixed cutoff", prompt.lower())

    def test_capture_worker_freezes_and_drains_every_selected_item(self):
        prompt = (
            ROOT / "automations/memory-stargraph-capture-link-drain/prompt.md"
        ).read_text()
        self.assertIn("first authoritative snapshot", prompt)
        self.assertIn("planned` to `capturing", prompt)
        self.assertIn("every frozen item", prompt)
        self.assertIn("completed` or `failed", prompt)
        self.assertIn("created after the frozen snapshot", prompt)

    def test_capture_worker_routes_to_most_specific_local_skill_and_reuses_media(self):
        prompt = (
            ROOT / "automations/memory-stargraph-capture-link-drain/prompt.md"
        ).read_text()
        self.assertIn("~/.codex/skills/<skill>/SKILL.md", prompt)
        self.assertIn("~/.openclaw/skills/<skill>/SKILL.md", prompt)
        self.assertIn("gbrain-capture-link", prompt)
        self.assertIn("gbrain-pdf-capture", prompt)
        self.assertIn("gb-capture-linkedin", prompt)
        self.assertIn("must not upload or copy the bytes again", prompt)

    def test_capture_worker_enriches_two_entities_only_when_snapshot_is_empty(self):
        directory = ROOT / "automations/memory-stargraph-capture-link-drain"
        prompt = (directory / "prompt.md").read_text()
        heartbeat = (directory / "heartbeat-prompt.md").read_text()
        bootstrap = (directory / "thread-bootstrap.md").read_text()
        readme = (ROOT / "automations/README.md").read_text()
        contract = "\n".join((prompt, heartbeat, bootstrap, readme))

        required = (
            "zero planned items",
            "do not run entity enrichment",
            "maximum of two enrichment slots",
            "effective type is `person` first",
            "organizations or companies",
            "teams or projects",
            "products or technologies",
            "other public entities",
            "previous 30 days",
            "no_eligible_candidates",
            "agent-reach",
            "already_sufficient",
            "must not create capture backlog requests",
            "do not automatically create product TODOs",
            "Memory Stargraph Quality & Learning Analyst",
        )
        for phrase in required:
            self.assertIn(phrase, contract)

        self.assertIn(
            "A non-empty first authoritative snapshot always takes priority",
            prompt,
        )
        self.assertIn(
            "The total cap remains two attempted entities per invocation",
            prompt,
        )

    def test_capture_worker_reserves_entities_before_enrichment_and_terminalizes_run(self):
        prompt = (
            ROOT / "automations/memory-stargraph-capture-link-drain/prompt.md"
        ).read_text()

        branch = prompt.index("set invocation mode to `empty_queue_enrichment`")
        active_run = prompt.index("create an active Goal-linked Run", branch)
        selection = prompt.index("Select and reserve", active_run)
        mutation = prompt.index("Before changing a selected entity", selection)
        self.assertLess(active_run, selection)
        self.assertLess(selection, mutation)

        required = (
            "persist and read back the selected entity slugs",
            "reservation collision",
            "earlier reservation timestamp",
            "when timestamps are equal, the lexically lowest invocation id wins",
            "must not mutate an entity until its reservation is verified",
            "success, failure, or interruption",
            "unexpected crash leaves the active Run",
            "truthful per-entity evidence",
        )
        for phrase in required:
            self.assertIn(phrase, prompt)

    def test_capture_worker_ranks_every_fallback_category_deterministically(self):
        prompt = (
            ROOT / "automations/memory-stargraph-capture-link-drain/prompt.md"
        ).read_text()

        categories = (
            "people",
            "organizations or companies",
            "teams or projects",
            "products or technologies",
            "other public entities",
        )
        for category in categories:
            self.assertIn(
                f"For {category}, rank eligible candidates by: deficiency first; "
                "never-reviewed first; oldest enrichment or review timestamp; "
                "then lexical slug",
                prompt,
            )

        self.assertIn("previous 30 days", prompt)
        self.assertIn("reserved by another active enrichment Run", prompt)

    def test_cdp_probe_reuses_matching_tab_and_only_closes_created_tab(self):
        probe = (ROOT / "scripts" / "automation" / "cdp_probe.mjs").read_text()
        self.assertIn("context.pages()", probe)
        self.assertIn("targetOrigin", probe)
        self.assertIn("createdPage", probe)
        self.assertIn("if (createdPage)", probe)
        self.assertNotIn("finally {\n  await page.close().catch", probe)

    def test_slug_link_and_browser_hygiene_contract_is_tracked(self):
        canonical = "http://127.0.0.1:8788/?slug=<URL-encoded-slug>"
        self.assertIn(canonical, (ROOT / "AGENTS.md").read_text())
        self.assertIn(canonical, (ROOT / "docs" / "automation-runbook.md").read_text())
        prompt = (ROOT / "automations" / "memory-stargraph-wish-to-reallity" / "prompt.md").read_text()
        self.assertIn("reuse", prompt.lower())
        self.assertIn("Markdown link", prompt)
        self.assertIn("in-app browser", prompt)
        self.assertIn("fall back to Chrome CDP", prompt)
        self.assertIn("Do not skip visual verification", prompt)

    def test_wish_worker_compacts_completed_todos_before_and_after_run(self):
        prompt = (ROOT / "automations" / "memory-stargraph-wish-to-reallity" / "prompt.md").read_text()
        runbook = (ROOT / "docs" / "automation-runbook.md").read_text()
        command = "python3 scripts/automation/compact_sg_todo_backlog.py --apply --json"

        self.assertGreaterEqual(prompt.count(command), 2)
        self.assertIn("full batch of 50 completed TODO rows", prompt)
        self.assertIn("TODO compaction/archive result", prompt)
        self.assertIn(command, runbook)
        self.assertIn("completed-archive-0001", runbook)
        self.assertIn("0-49 completed rows", runbook)

    def test_wish_worker_lands_pushed_work_on_main(self):
        prompt = (ROOT / "automations" / "memory-stargraph-wish-to-reallity" / "prompt.md").read_text()

        self.assertIn("Push the work branch to origin", prompt)
        self.assertIn("merge the pushed work into `main`", prompt)
        self.assertIn("push `main` to origin", prompt)
        self.assertIn("`main` merge/push result", prompt)

    def test_retrospective_uses_timezone_aware_pacific_timestamp(self):
        script = (ROOT / "scripts" / "automation" / "retrospect.sh").read_text()

        self.assertIn('ZoneInfo("America/Los_Angeles")', script)
        self.assertIn('pacific_stamp=', script)
        self.assertNotIn("date -u", script)

    def test_wish_runbook_requires_auditable_yoda_probe_provenance(self):
        prompt = (ROOT / "automations" / "memory-stargraph-wish-to-reallity" / "prompt.md").read_text()
        runbook = (ROOT / "docs" / "resolver-feedback-loop-runbook.md").read_text()
        contract = prompt + "\n" + runbook

        self.assertIn("probe_yoda_resolver_telemetry.py", contract)
        self.assertIn("environment=test", contract)
        self.assertIn("synthetic=true", contract)
        self.assertIn("test_run=true", contract)
        self.assertIn("stable `pair_id`", contract)
        self.assertIn("API unit-test harness", runbook)
        self.assertIn("Browser/CDP", runbook)
        self.assertIn("provider-down benchmark", runbook)
        self.assertIn("Do not use raw curl", runbook)


if __name__ == "__main__":
    unittest.main()
