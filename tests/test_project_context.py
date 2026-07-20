import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "skills" / "project-context" / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


project_context_agents = load_script("project_context_agents")
project_context_update = load_script("project_context_update")
validate_project_context = load_script("validate_project_context")


class ProjectContextTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "repo"
        self.root.mkdir()
        self.root = self.root.resolve()
        self.git("init")
        self.git("config", "user.name", "Codex")
        self.git("config", "user.email", "codex@example.invalid")
        (self.root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        (self.root / "app.py").write_text("print('hello')\n", encoding="utf-8")
        self.git("add", "README.md", "app.py")
        self.git("commit", "-m", "init fixture")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def git(self, *args):
        completed = subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    def write_context(self):
        source_commit = self.git("rev-parse", "--short", "HEAD")
        context = self.root / "docs" / "project-context.md"
        context.parent.mkdir(parents=True, exist_ok=True)
        context.write_text(
            f"""---
generated_by: project-context
source_commit: {source_commit}
updated_at: 2026-07-20T00:00:00Z
mode: single-page
---

# Project Context

## 목적

Fixture 작업 기준을 기록한다.

## 프로젝트 요약

작은 Python 프로젝트다.

## 기술 스택과 실행 명령

Python으로 실행한다.

## 핵심 모듈·디렉터리

`app.py`가 진입점이다.

## 주요 흐름

프로그램이 인사 문구를 출력한다.

## 작업 전 확인 지점

출력 계약을 유지한다.

## 검증 방법

`python3 app.py`를 실행한다.

## 미확정 사항

없음.

## 근거

- [README](../README.md)
- [Entrypoint](../app.py)

## 갱신 기록

- 초기 문서 생성.
""",
            encoding="utf-8",
        )
        project_context_agents.ensure_file(self.root / "AGENTS.md", create_if_missing=True)
        return context

    def record(self, run_mode="init"):
        return project_context_update.record_metadata(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            run_mode,
            False,
            None,
        )

    def test_init_record_and_validate(self):
        self.write_context()

        metadata = self.record()
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 0, (messages, warnings))
        self.assertEqual(metadata["generator"], "project-context")
        self.assertEqual(metadata["run_mode"], "init")
        self.assertEqual(
            set(metadata),
            {
                "generator",
                "generator_version",
                "updated_at",
                "run_mode",
                "source_commit",
                "source_commit_short",
                "primary_doc",
                "docs",
                "doc_sources",
                "content_hash",
            },
        )

    def test_untracked_files_are_not_collapsed_to_directories(self):
        self.write_context()
        new_source = self.root / "src" / "new.py"
        new_source.parent.mkdir()
        new_source.write_text("value = 1\n", encoding="utf-8")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertIn("src/new.py", plan["source_change_paths"])
        self.assertNotIn("src/", plan["source_change_paths"])
        self.assertIn(
            "docs/project-context.md", plan["generated_context_doc_changes"]
        )
        self.assertNotIn("docs/", plan["source_change_paths"])

    def test_context_only_commit_does_not_make_plan_stale(self):
        self.write_context()
        self.record()
        self.git("add", "AGENTS.md", "docs")
        self.git("commit", "-m", "docs: add project context")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(plan["recommended_action"], "no-op")
        self.assertEqual(plan["source_change_paths"], [])
        self.assertEqual(code, 0, (messages, warnings))
        self.assertFalse(any("stale" in warning for warning in warnings))

    def test_source_change_maps_to_linked_document_and_noop_record_skips(self):
        self.write_context()
        metadata = self.record()
        before_hash = project_context_update.docs_content_hash(
            self.root, project_context_update.discover_docs(self.root, project_context_update.DEFAULT_DOC)
        )
        skipped = project_context_update.record_metadata(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )
        (self.root / "app.py").write_text("print('changed')\n", encoding="utf-8")
        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertTrue(skipped["skipped"])
        self.assertEqual(
            json.loads(
                (self.root / project_context_update.DEFAULT_METADATA).read_text(
                    encoding="utf-8"
                )
            )["updated_at"],
            metadata["updated_at"],
        )
        self.assertEqual(
            plan["affected_docs"], {"docs/project-context.md": ["app.py"]}
        )

    def test_agent_section_is_idempotent_and_backend_neutral(self):
        self.write_context()
        first = (self.root / "AGENTS.md").read_text(encoding="utf-8")

        status, changed = project_context_agents.ensure_file(
            self.root / "AGENTS.md", create_if_missing=True
        )

        self.assertEqual(status, "current")
        self.assertFalse(changed)
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), first)
        self.assertIn("repository instructions for code discovery", first)

    def test_invalid_metadata_is_not_accepted_as_valid(self):
        self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.pop("content_hash")
        metadata.pop("docs")
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertTrue(any("missing content_hash" in message for message in messages))
        self.assertTrue(any("docs must be a string list" in message for message in messages))

    def test_planner_rejects_invalid_metadata_baseline(self):
        self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["updated_at"] = "not-a-timestamp"
        metadata["run_mode"] = "unexpected"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertIsNone(plan["last_update_metadata"])
        self.assertEqual(plan["previous_commit_source"], "docs/project-context.md")
        self.assertEqual(plan["previous_commit"], self.git("rev-parse", "--short", "HEAD"))

    def test_metadata_and_document_source_commits_must_match(self):
        self.write_context()
        self.record()
        original_commit = self.git("rev-parse", "HEAD")
        (self.root / "app.py").write_text("print('next')\n", encoding="utf-8")
        self.git("add", "app.py")
        self.git("commit", "-m", "change fixture")
        next_commit = self.git("rev-parse", "HEAD")
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["source_commit"] = next_commit
        metadata["source_commit_short"] = next_commit[:7]
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertNotEqual(original_commit, next_commit)
        self.assertEqual(code, 1)
        self.assertTrue(any("source_commit does not match" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
