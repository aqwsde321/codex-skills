import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from tools import session_usage_audit


class SessionUsageAuditTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.codex_home = Path(self.temporary_directory.name) / ".codex"
        for name in ("tdd", "code-review", "unused-skill"):
            skill_dir = self.codex_home / "skills" / name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        system_skill = self.codex_home / "skills" / ".system" / "openai-docs"
        system_skill.mkdir(parents=True)
        (system_skill / "SKILL.md").write_text("# system\n", encoding="utf-8")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_session(self, session_date, name, items, archived=False):
        if archived:
            directory = self.codex_home / "archived_sessions"
        else:
            directory = (
                self.codex_home
                / "sessions"
                / f"{session_date:%Y}"
                / f"{session_date:%m}"
                / f"{session_date:%d}"
            )
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"rollout-{session_date.isoformat()}T00-00-00-{name}.jsonl"
        lines = [
            item
            if isinstance(item, str)
            else json.dumps(
                item
                if "timestamp" in item
                else {"timestamp": f"{session_date.isoformat()}T00:00:00Z", **item}
            )
            for item in items
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def session_meta(subagent=False):
        source = {"subagent": {"thread_spawn": {}}} if subagent else "cli"
        return {"type": "session_meta", "payload": {"source": source}}

    def test_collects_completed_skill_and_mcp_usage_without_catalog_noise(self):
        current = date(2026, 7, 18)
        tdd_path = self.codex_home / "skills" / "tdd" / "SKILL.md"
        code_review_path = self.codex_home / "skills" / "code-review" / "SKILL.md"
        root_items = [
            self.session_meta(),
            {
                "timestamp": "2026-07-18T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": f"catalog {code_review_path}"}],
                },
            },
            {
                "timestamp": "2026-07-18T00:00:02Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "use $tdd now; $unknown ignored"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "skill-1",
                    "input": (
                        "const note = 'tools.exec_command({cmd: \\\"sed skills/fake/SKILL.md\\\"})';\n"
                        f"await tools.exec_command({{cmd: \"sed -n 1,200p {tdd_path} {tdd_path}; "
                        "ignore skills/*/SKILL.md and skills/{name}/SKILL.md\"}});"
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {"type": "custom_tool_call_output", "call_id": "skill-1", "output": "ok"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "patch-only",
                    "input": (
                        f"const patch = '{code_review_path}'; "
                        "await tools.apply_patch(patch);"
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "patch-only",
                    "output": "ok",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "unfinished",
                    "arguments": json.dumps({"cmd": f"sed -n 1,20p {code_review_path}"}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "direct-skill",
                    "arguments": json.dumps({"cmd": f"cat {code_review_path}"}),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "direct-skill",
                    "output": "ok",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "home-skill",
                    "arguments": json.dumps(
                        {"cmd": "cat $HOME/.codex/skills/unused-skill/SKILL.md"}
                    ),
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "home-skill",
                    "output": "ok",
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "mcp_tool_call_end",
                    "call_id": "mcp-ok",
                    "invocation": {"server": "graph", "tool": "search"},
                    "result": {"Ok": {"content": []}},
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "mcp_tool_call_end",
                    "call_id": "mcp-error",
                    "invocation": {"server": "graph", "tool": "search"},
                    "result": {"Err": "failed"},
                },
            },
            "{broken mcp_tool_call_end",
        ]
        self.write_session(current, "root", root_items)

        stats, personal = session_usage_audit.audit(self.codex_home, current, current)

        self.assertEqual(set(personal), {"tdd", "code-review", "unused-skill"})
        self.assertEqual(stats.explicit_references, {"tdd": 1})
        self.assertEqual(
            stats.skill_loads,
            {"tdd": 2, "code-review": 1, "unused-skill": 1},
        )
        self.assertEqual(len(stats.skill_sessions["tdd"]), 1)
        self.assertEqual(
            stats.observed_personal_skills,
            {"tdd", "code-review", "unused-skill"},
        )
        self.assertEqual(stats.mcp_counts[("graph", "search")], {"ok": 1, "error": 1})
        self.assertEqual(stats.candidate_json_errors, 1)

    def test_deduplicates_forked_events_and_excludes_subagent_user_messages(self):
        current = date(2026, 7, 18)
        tdd_path = self.codex_home / "skills" / "tdd" / "SKILL.md"
        shared = [
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": "shared-skill",
                    "input": f'await tools.exec_command({{cmd: "sed -n 1,200p {tdd_path}"}});',
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "shared-skill",
                    "output": "ok",
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "mcp_tool_call_end",
                    "call_id": "shared-mcp",
                    "invocation": {"server": "graph", "tool": "trace"},
                    "result": {"Ok": {}},
                },
            },
        ]
        root_user = {
            "timestamp": "2026-07-18T00:00:00Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "$tdd"},
        }
        self.write_session(current, "root", [self.session_meta(), root_user, *shared])
        self.write_session(current, "subagent", [self.session_meta(True), root_user, *shared])

        stats, _ = session_usage_audit.audit(self.codex_home, current, current)

        self.assertEqual(stats.session_files, 2)
        self.assertEqual(stats.subagent_files, 1)
        self.assertEqual(stats.explicit_references, {"tdd": 1})
        self.assertEqual(stats.skill_loads, {"tdd": 1})
        self.assertEqual(stats.mcp_counts[("graph", "trace")], {"ok": 1})

    def test_date_filter_and_archived_sessions(self):
        current = date(2026, 7, 18)
        event = {
            "type": "event_msg",
            "payload": {
                "type": "mcp_tool_call_end",
                "call_id": "current",
                "invocation": {"server": "graph", "tool": "search"},
                "result": {},
            },
        }
        self.write_session(current, "active", [self.session_meta(), event])
        archived_event = {**event, "payload": {**event["payload"], "call_id": "archived"}}
        self.write_session(current, "archived", [self.session_meta(), archived_event], archived=True)
        old = date(2026, 7, 1)
        old_event = {**event, "payload": {**event["payload"], "call_id": "old"}}
        old_path = self.write_session(old, "old", [self.session_meta(), old_event])
        resumed_event = {
            **event,
            "timestamp": "2026-07-18T01:00:00Z",
            "payload": {**event["payload"], "call_id": "resumed"},
        }
        resumed_path = self.write_session(old, "resumed", [self.session_meta(), resumed_event])
        recent_mtime = datetime(2026, 7, 18, 12, tzinfo=timezone.utc).timestamp()
        os.utime(old_path, (recent_mtime, recent_mtime))
        os.utime(resumed_path, (recent_mtime, recent_mtime))

        stats, _ = session_usage_audit.audit(self.codex_home, current, current)

        self.assertEqual(stats.session_files, 4)
        self.assertEqual(stats.mcp_counts[("graph", "search")], {"unknown": 3})


if __name__ == "__main__":
    unittest.main()
