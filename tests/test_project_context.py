import importlib.util
import json
import subprocess
import sys
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

    def write_multi_context(self):
        source_commit = self.git("rev-parse", "--short", "HEAD")
        context = self.root / "docs" / "project-context.md"
        context_dir = self.root / "docs" / "project-context"
        context_dir.mkdir(parents=True, exist_ok=True)
        context.write_text(
            f"""---
generated_by: project-context
source_commit: {source_commit}
updated_at: 2026-07-20T00:00:00Z
mode: multi-page
---

# Project Context

## 프로젝트 요약

작은 Python 프로젝트다.

## 작업 전 확인 지점

출력 계약을 유지한다.

<!-- project-context:index:start -->
<!-- project-context:index:end -->

## 근거

- [README](../README.md)
""",
            encoding="utf-8",
        )
        supporting_body = "이 문서는 관련 구조와 변경 기준을 source 근거로 설명한다. " * 20
        (context_dir / "architecture.md").write_text(
            f"""---
title: Architecture
description: 모듈 경계와 진입점
read_when: 모듈 소유권이나 시작 흐름 변경
---

# Architecture

[Project context](../project-context.md)

{supporting_body}

## 근거

- [Entrypoint](../../app.py)
""",
            encoding="utf-8",
        )
        (context_dir / "workflows.md").write_text(
            f"""---
title: Workflows
description: 주요 실행 흐름과 검증 지점
read_when: 실행 흐름 변경 또는 동작 검증
---

# Workflows

[Project context](../project-context.md)

{supporting_body}

## 근거

- [Entrypoint](../../app.py)
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

    def record_and_commit_context(self, message):
        self.record()
        self.git("add", "AGENTS.md", "docs")
        self.git("commit", "-m", message)

    def test_init_record_and_validate(self):
        self.write_context()

        metadata = self.record()
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 0, (messages, warnings))
        self.assertEqual(metadata["generator"], "project-context")
        self.assertEqual(metadata["run_mode"], "init")
        self.assertEqual(metadata["source_commit"], metadata["reviewed_commit"])
        self.assertEqual(
            set(metadata),
            {
                "generator",
                "generator_version",
                "updated_at",
                "run_mode",
                "source_commit",
                "source_commit_short",
                "reviewed_commit",
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
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        record_result = project_context_update.record_metadata(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(plan["recommended_action"], "no-op")
        self.assertEqual(plan["required_actions"], ["no-op"])
        self.assertFalse(plan["structure_review_required"])
        self.assertEqual(plan["structure_issues"], [])
        self.assertEqual(plan["source_change_paths"], [])
        self.assertTrue(record_result["skipped"])
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

    def test_reviewed_commit_advances_without_document_changes(self):
        self.write_context()
        initial_metadata = self.record()
        self.git("add", "AGENTS.md", "docs")
        self.git("commit", "-m", "docs: add project context")
        (self.root / "internal.txt").write_text("reviewed\n", encoding="utf-8")
        self.git("add", "internal.txt")
        self.git("commit", "-m", "add internal source")
        current_head = self.git("rev-parse", "HEAD")
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        result = project_context_update.record_metadata(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )
        persisted = json.loads(
            (self.root / project_context_update.DEFAULT_METADATA).read_text(
                encoding="utf-8"
            )
        )
        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertTrue(result["review_only"])
        self.assertEqual(persisted["source_commit"], initial_metadata["source_commit"])
        self.assertEqual(persisted["reviewed_commit"], current_head)
        self.assertEqual(plan["recommended_action"], "no-op")
        self.assertEqual(code, 0, (messages, warnings))

    def test_dirty_source_is_not_approved_by_reviewed_commit(self):
        self.write_context()
        initial_metadata = self.record()
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        (self.root / "app.py").write_text("print('dirty')\n", encoding="utf-8")

        result = project_context_update.record_metadata(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )
        persisted = json.loads(
            (self.root / project_context_update.DEFAULT_METADATA).read_text(
                encoding="utf-8"
            )
        )
        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertTrue(result["skipped"])
        self.assertEqual(
            persisted["reviewed_commit"], initial_metadata["reviewed_commit"]
        )
        self.assertEqual(plan["affected_docs"], {"docs/project-context.md": ["app.py"]})

    def test_legacy_metadata_backfills_reviewed_commit(self):
        self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.pop("reviewed_commit")
        metadata["generator_version"] = "18"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        result = project_context_update.record_metadata(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )
        persisted = json.loads(metadata_path.read_text(encoding="utf-8"))
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertTrue(result["review_only"])
        self.assertEqual(persisted["reviewed_commit"], self.git("rev-parse", "HEAD"))
        self.assertEqual(persisted["generator_version"], "20")
        self.assertEqual(code, 0, (messages, warnings))

    def test_invalid_reviewed_commit_fails_validation_and_planner_falls_back(self):
        self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["reviewed_commit"] = "deadbeef"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(plan["previous_commit_source"], "docs/project-context/.metadata.json#source_commit")
        self.assertEqual(code, 1)
        self.assertTrue(any("reviewed_commit does not exist" in message for message in messages))

    def test_divergent_reviewed_commit_fails_validation_and_planner_falls_back(self):
        self.write_context()
        self.record()
        current_branch = self.git("branch", "--show-current")
        self.git("checkout", "-b", "divergent-review")
        (self.root / "README.md").write_text("# Divergent fixture\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "divergent fixture")
        divergent_commit = self.git("rev-parse", "HEAD")
        self.git("checkout", current_branch)

        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["reviewed_commit"] = divergent_commit
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        code, messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(plan["previous_commit_source"], "docs/project-context/.metadata.json#source_commit")
        self.assertEqual(code, 1)
        self.assertTrue(any("reviewed_commit must be between source_commit and HEAD" in message for message in messages))

        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        result = project_context_update.record_metadata(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )
        persisted = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertTrue(result["review_only"])
        self.assertEqual(persisted["reviewed_commit"], self.git("rev-parse", "HEAD"))

    def test_planner_falls_back_to_document_when_metadata_commits_are_invalid(self):
        self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["reviewed_commit"] = "deadbeef"
        metadata["source_commit"] = "cafebabe"
        metadata["source_commit_short"] = "cafebabe"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertEqual(plan["previous_commit_source"], "docs/project-context.md")
        self.assertEqual(plan["previous_commit"], self.git("rev-parse", "--short", "HEAD"))

    def test_reverted_committed_source_change_advances_reviewed_commit(self):
        self.write_context()
        initial_metadata = self.record()
        self.git("add", "AGENTS.md", "docs")
        self.git("commit", "-m", "docs: add project context")
        (self.root / "app.py").write_text("print('changed')\n", encoding="utf-8")
        self.git("add", "app.py")
        self.git("commit", "-m", "change fixture")
        (self.root / "app.py").write_text("print('hello')\n", encoding="utf-8")
        self.git("add", "app.py")
        self.git("commit", "-m", "revert fixture change")
        current_head = self.git("rev-parse", "HEAD")
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        result = project_context_update.record_metadata(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )
        persisted = json.loads(
            (self.root / project_context_update.DEFAULT_METADATA).read_text(
                encoding="utf-8"
            )
        )

        self.assertTrue(result["review_only"])
        self.assertEqual(persisted["source_commit"], initial_metadata["source_commit"])
        self.assertEqual(persisted["reviewed_commit"], current_head)

    def test_reverted_general_agent_instruction_advances_reviewed_commit(self):
        self.write_context()
        self.record()
        self.git("add", "AGENTS.md", "docs")
        self.git("commit", "-m", "docs: add project context")
        agent_path = self.root / "AGENTS.md"
        marker_only = agent_path.read_text(encoding="utf-8")
        agent_path.write_text(f"# User Rule\n\n{marker_only}", encoding="utf-8")
        self.git("add", "AGENTS.md")
        self.git("commit", "-m", "add user agent rule")
        agent_path.write_text(marker_only, encoding="utf-8")
        self.git("add", "AGENTS.md")
        self.git("commit", "-m", "revert user agent rule")
        current_head = self.git("rev-parse", "HEAD")
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        result = project_context_update.record_metadata(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )

        self.assertTrue(result["review_only"])
        self.assertEqual(result["reviewed_commit"], current_head)

    def test_record_repairs_source_metadata_from_document_frontmatter(self):
        self.write_context()
        initial_metadata = self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["source_commit"] = "deadbeef"
        metadata["source_commit_short"] = "deadbeef"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        result = project_context_update.record_metadata(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )
        persisted = json.loads(metadata_path.read_text(encoding="utf-8"))
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertTrue(result["review_only"])
        self.assertEqual(persisted["source_commit"], initial_metadata["source_commit"])
        self.assertEqual(
            persisted["source_commit_short"],
            self.git("rev-parse", "--short", initial_metadata["source_commit"]),
        )
        self.assertEqual(code, 0, (messages, warnings))

    def test_only_v18_missing_reviewed_commit_is_a_legacy_warning(self):
        self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["generator_version"] = "18"
        metadata.pop("reviewed_commit")
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        legacy_code, legacy_messages, legacy_warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        metadata["reviewed_commit"] = None
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        null_code, null_messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        metadata.pop("reviewed_commit")
        metadata["generator_version"] = "21"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        future_code, future_messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(legacy_code, 0, legacy_messages)
        self.assertTrue(any("missing reviewed_commit" in warning for warning in legacy_warnings))
        self.assertEqual(null_code, 1)
        self.assertTrue(any("must be a non-empty string" in message for message in null_messages))
        self.assertEqual(future_code, 1)
        self.assertTrue(any("missing reviewed_commit" in message for message in future_messages))

    def test_agent_section_is_idempotent_and_backend_neutral(self):
        self.write_context()
        first = (self.root / "AGENTS.md").read_text(encoding="utf-8")

        status, changed = project_context_agents.ensure_file(
            self.root / "AGENTS.md", create_if_missing=True
        )

        self.assertEqual(status, "current")
        self.assertFalse(changed)
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), first)
        self.assertIn("ordinary project questions", first)
        self.assertIn("do not preload every supporting page", first)
        self.assertIn("read_when", first)
        self.assertIn("exact implementation verification", first)
        self.assertIn("current source remains authoritative", first)
        self.assertIn("repository instructions for code discovery", first)
        self.assertIn("explicitly requests creation or refresh", first)
        self.assertIn("missing or stale context alone does not authorize writes", first)

    def test_old_agent_section_is_replaced_by_context_first_guidance(self):
        stale_section = project_context_agents.SECTION.replace(
            "ordinary project questions", "routine project questions"
        )

        next_text, changed = project_context_agents.replace_marked_section(stale_section)

        self.assertTrue(changed)
        self.assertEqual(next_text, project_context_agents.SECTION)
        self.assertTrue(
            validate_project_context.is_semantically_current_agent_section(next_text)
        )

    def test_agent_section_without_write_authority_guard_is_replaced(self):
        stale_section = project_context_agents.SECTION.replace(
            "missing or stale context alone does not authorize writes",
            "stale context should be refreshed",
        )

        next_text, changed = project_context_agents.replace_marked_section(stale_section)

        self.assertFalse(
            validate_project_context.is_semantically_current_agent_section(stale_section)
        )
        self.assertTrue(changed)
        self.assertEqual(next_text, project_context_agents.SECTION)

    def test_temp_plan_scaffolds_relationships_and_deferred_coverage(self):
        plan = project_context_update.format_temp_plan(
            {"recommended_action": "no-op", "docs": [project_context_update.DEFAULT_DOC]}
        )

        self.assertIn("## Evidence-backed Relationships", plan)
        self.assertIn("source concept -> relationship meaning -> target concept", plan)
        self.assertIn("## Deferred Coverage", plan)
        self.assertIn("area, source anchor, and reason", plan)

    def test_plan_renderers_surface_required_structure_review(self):
        plan = {
            "recommended_action": "update-affected-docs",
            "required_actions": [
                "update-affected-docs",
                "review-document-structure",
            ],
            "structure_issues": [
                {
                    "code": "single-page-primary-too-large",
                    "path": project_context_update.DEFAULT_DOC,
                    "message": "single-page primary body exceeds its limit",
                }
            ],
            "docs": [project_context_update.DEFAULT_DOC],
        }

        rendered_plan = project_context_update.format_plan(plan)
        rendered_temp_plan = project_context_update.format_temp_plan(plan)

        for rendered in (rendered_plan, rendered_temp_plan):
            self.assertIn(
                "required_actions: update-affected-docs, review-document-structure",
                rendered,
            )
            self.assertIn("## Document Structure Issues", rendered)
            self.assertIn("[single-page-primary-too-large]", rendered)
            self.assertIn(project_context_update.DEFAULT_DOC, rendered)

    def test_three_subpages_warn_only_for_isolated_peer_relationships(self):
        context_dir = self.root / "docs" / "project-context"
        context_dir.mkdir(parents=True)
        docs = [
            validate_project_context.DEFAULT_DOC,
            "docs/project-context/a.md",
            "docs/project-context/b.md",
            "docs/project-context/c.md",
        ]
        (context_dir / "a.md").write_text(
            "[Index](../project-context.md)\n\nA sends data to [B](b.md).\n",
            encoding="utf-8",
        )
        (context_dir / "b.md").write_text(
            "[Index](../project-context.md)\n", encoding="utf-8"
        )
        (context_dir / "c.md").write_text(
            "[Index](../project-context.md)\n", encoding="utf-8"
        )

        _, warnings = validate_project_context.validate_context_relationships(
            self.root, validate_project_context.DEFAULT_DOC, docs
        )
        _, two_page_warnings = validate_project_context.validate_context_relationships(
            self.root, validate_project_context.DEFAULT_DOC, docs[:3]
        )

        self.assertEqual(len(warnings), 1)
        self.assertIn("docs/project-context/c.md", warnings[0])
        self.assertEqual(two_page_warnings, [])

    def test_sync_index_is_deterministic_and_multi_page_validates(self):
        context = self.write_multi_context()

        first = project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        first_markdown = context.read_text(encoding="utf-8")
        second = project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        self.record()
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertLess(
            first_markdown.index("[Architecture]"),
            first_markdown.index("[Workflows]"),
        )
        self.assertIn("읽을 때: 모듈 소유권이나 시작 흐름 변경", first_markdown)
        self.assertEqual(code, 0, (messages, warnings))
        self.assertFalse(any("testing guidance" in warning for warning in warnings))
        self.assertFalse(any("workflow/domain guidance" in warning for warning in warnings))

    def test_sync_index_requires_complete_subpage_metadata(self):
        self.write_multi_context()
        workflow_path = self.root / "docs" / "project-context" / "workflows.md"
        workflow_path.write_text(
            workflow_path.read_text(encoding="utf-8").replace(
                "read_when: 실행 흐름 변경 또는 동작 검증\n", ""
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "missing index metadata: read_when"):
            project_context_update.sync_context_index(
                self.root, project_context_update.DEFAULT_DOC
            )

    def test_validator_detects_stale_deterministic_index(self):
        self.write_multi_context()
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        architecture_path = self.root / "docs" / "project-context" / "architecture.md"
        architecture_path.write_text(
            architecture_path.read_text(encoding="utf-8").replace(
                "description: 모듈 경계와 진입점",
                "description: 모듈 경계와 애플리케이션 진입점",
            ),
            encoding="utf-8",
        )
        docs = validate_project_context.discover_docs(
            self.root, validate_project_context.DEFAULT_DOC
        )

        errors, _ = validate_project_context.validate_deterministic_context_index(
            self.root, validate_project_context.DEFAULT_DOC, docs
        )

        self.assertTrue(any("deterministic context index is stale" in error for error in errors))

    def test_plan_does_not_call_a_committed_stale_index_no_op(self):
        self.write_multi_context()
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        self.record()
        self.git("add", "AGENTS.md", "docs")
        self.git("commit", "-m", "docs: add multi-page context")
        architecture = self.root / "docs" / "project-context" / "architecture.md"
        architecture.write_text(
            architecture.read_text(encoding="utf-8").replace(
                "description: 모듈 경계와 진입점",
                "description: 모듈 경계와 애플리케이션 진입점",
            ),
            encoding="utf-8",
        )
        self.git("add", "docs/project-context/architecture.md")
        self.git("commit", "-m", "docs: change context index metadata")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertEqual(plan["recommended_action"], "review-generated-doc-changes")
        self.assertTrue(plan["metadata_document_state_stale"])
        self.assertTrue(plan["context_index_stale"])
        self.assertIn(
            "docs/project-context/architecture.md",
            plan["generated_context_doc_changes"],
        )
        self.assertIn(
            project_context_update.DEFAULT_DOC,
            plan["generated_context_doc_changes"],
        )

    def test_sync_index_requires_exact_marker_pair(self):
        context = self.write_multi_context()
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "<!-- project-context:index:end -->", ""
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "exactly one start and end marker"):
            project_context_update.sync_context_index(
                self.root, project_context_update.DEFAULT_DOC
            )

    def test_subpages_require_multi_page_mode(self):
        context = self.write_multi_context()
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "mode: multi-page", "mode: single-page"
            ),
            encoding="utf-8",
        )
        docs = validate_project_context.discover_docs(
            self.root, validate_project_context.DEFAULT_DOC
        )

        errors, warnings = validate_project_context.validate_primary_mode(
            self.root, validate_project_context.DEFAULT_DOC, docs
        )

        self.assertTrue(any("mode must be multi-page" in error for error in errors))
        self.assertEqual(warnings, [])

    def test_primary_size_budgets_split_large_context(self):
        context = self.write_context()
        context.write_text(
            context.read_text(encoding="utf-8") + ("상세 흐름을 반복한다. " * 1000),
            encoding="utf-8",
        )

        single_errors, single_warnings = validate_project_context.validate_primary_size(
            self.root, validate_project_context.DEFAULT_DOC
        )
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "mode: single-page", "mode: multi-page"
            ),
            encoding="utf-8",
        )
        multi_errors, multi_warnings = validate_project_context.validate_primary_size(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(single_errors, [])
        self.assertTrue(any("split into indexed supporting pages" in warning for warning in single_warnings))
        self.assertTrue(any("keep the router" in error for error in multi_errors))
        self.assertEqual(multi_warnings, [])

    def test_plan_requires_structure_review_for_oversized_single_page(self):
        context = self.write_context()
        context.write_text(
            context.read_text(encoding="utf-8") + ("상세 흐름을 반복한다. " * 1000),
            encoding="utf-8",
        )
        self.record_and_commit_context("docs: add oversized project context")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertEqual(plan["recommended_action"], "review-document-structure")
        self.assertEqual(plan["required_actions"], ["review-document-structure"])
        self.assertTrue(plan["structure_review_required"])
        self.assertEqual(
            [issue["code"] for issue in plan["structure_issues"]],
            ["single-page-primary-too-large"],
        )

    def test_plan_requires_structure_review_for_oversized_multi_page_router(self):
        context = self.write_multi_context()
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        context.write_text(
            context.read_text(encoding="utf-8") + ("라우터 상세를 반복한다. " * 500),
            encoding="utf-8",
        )
        self.record_and_commit_context("docs: add oversized context router")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertEqual(plan["recommended_action"], "review-document-structure")
        self.assertEqual(
            [issue["code"] for issue in plan["structure_issues"]],
            ["multi-page-primary-too-large"],
        )

    def test_plan_requires_structure_review_for_mode_document_count_mismatch(self):
        context = self.write_multi_context()
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "mode: multi-page", "mode: single-page"
            ),
            encoding="utf-8",
        )
        self.record_and_commit_context("docs: add mismatched project context")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertEqual(plan["recommended_action"], "review-document-structure")
        self.assertEqual(
            [issue["code"] for issue in plan["structure_issues"]],
            ["primary-mode-mismatch"],
        )

    def test_plan_requires_structure_review_for_invalid_primary_mode(self):
        context = self.write_context()
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "mode: single-page", "mode: invalid"
            ),
            encoding="utf-8",
        )
        self.record_and_commit_context("docs: add invalid project context mode")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertEqual(plan["recommended_action"], "review-document-structure")
        self.assertEqual(
            [issue["code"] for issue in plan["structure_issues"]],
            ["invalid-primary-mode"],
        )

    def test_structure_review_is_required_alongside_source_update(self):
        context = self.write_context()
        context.write_text(
            context.read_text(encoding="utf-8") + ("상세 흐름을 반복한다. " * 1000),
            encoding="utf-8",
        )
        self.record_and_commit_context("docs: add oversized project context")
        (self.root / "app.py").write_text("print('changed')\n", encoding="utf-8")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertEqual(plan["recommended_action"], "update-affected-docs")
        self.assertEqual(
            plan["required_actions"],
            ["update-affected-docs", "review-document-structure"],
        )
        self.assertTrue(plan["structure_review_required"])

    def test_temp_plan_does_not_trigger_structure_review(self):
        self.write_context()
        self.record()
        project_context_update.write_temp_plan(
            self.root,
            project_context_update.DEFAULT_TEMP_PLAN,
            {"recommended_action": "update-affected-docs", "docs": []},
        )

        issues = project_context_update.document_structure_issues(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        self.assertEqual(issues, [])

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

    def test_unmarked_agent_section_is_preserved(self):
        agent_path = self.root / "AGENTS.md"
        custom = "# Rules\n\n## Project Context\n\nKEEP-CUSTOM-RULE\n"
        agent_path.write_text(custom, encoding="utf-8")

        status, changed = project_context_agents.ensure_file(
            agent_path, create_if_missing=False
        )
        first = agent_path.read_text(encoding="utf-8")
        second, second_changed = project_context_agents.replace_marked_section(first)

        self.assertEqual(status, "updated")
        self.assertTrue(changed)
        self.assertIn(custom.rstrip(), first)
        self.assertIn("KEEP-CUSTOM-RULE", first)
        self.assertEqual(first.count(project_context_agents.START_MARKER), 1)
        self.assertFalse(second_changed)
        self.assertEqual(second, first)

        self.write_context()
        self.record()
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )
        self.assertEqual(code, 0, (messages, warnings))

    def test_validator_rejects_missing_and_symlinked_agent_marker(self):
        self.write_context()
        self.record()
        agent_path = self.root / "AGENTS.md"
        agent_path.write_text("# Missing marker\n", encoding="utf-8")

        missing_code, missing_messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        agent_path.unlink()
        outside_agent = self.root.parent / "outside-agents.md"
        outside_agent.write_text(project_context_agents.SECTION, encoding="utf-8")
        agent_path.symlink_to(outside_agent)
        symlink_code, symlink_messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(missing_code, 1)
        self.assertTrue(any("marked section" in message for message in missing_messages))
        self.assertEqual(symlink_code, 1)
        self.assertTrue(any("must not be a symlink" in message for message in symlink_messages))

    def test_validator_rejects_primary_mode_mismatch(self):
        context = self.write_context()
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "mode: single-page", "mode: multi-page"
            ),
            encoding="utf-8",
        )
        self.record()

        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1, warnings)
        self.assertTrue(any("metadata mode must be single-page" in message for message in messages))

    def test_update_cli_rejects_non_git_directory(self):
        non_repo = self.root.parent / "not-a-repo"
        non_repo.mkdir()
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_ROOT / "project_context_update.py"),
                "plan",
                str(non_repo),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("git rev-parse --show-toplevel failed", completed.stderr)
        with self.assertRaises(ValueError):
            project_context_update.build_plan(
                non_repo,
                project_context_update.DEFAULT_DOC,
                project_context_update.DEFAULT_METADATA,
            )

    def test_git_paths_are_lossless_for_unicode_arrow_and_rename(self):
        unicode_path = self.root / "한글.py"
        arrow_path = self.root / "literal -> arrow.py"
        unicode_path.write_text("value = 1\n", encoding="utf-8")
        arrow_path.write_text("value = 2\n", encoding="utf-8")
        self.git("add", "한글.py", "literal -> arrow.py")
        self.git("commit", "-m", "add unusual paths")
        context = self.write_context()
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "## 갱신 기록",
                "- [Unicode](../한글.py)\n"
                "- [Arrow](../literal%20-%3E%20arrow.py)\n\n"
                "## 갱신 기록",
            ),
            encoding="utf-8",
        )
        self.record()

        self.git("mv", "한글.py", "새 이름.py")
        arrow_path.write_text("value = 3\n", encoding="utf-8")
        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertIn("한글.py", plan["source_change_paths"])
        self.assertIn("새 이름.py", plan["source_change_paths"])
        self.assertIn("literal -> arrow.py", plan["source_change_paths"])
        self.assertIn(
            {"old_path": "한글.py", "path": "새 이름.py"},
            plan["renamed_paths"],
        )
        self.assertFalse(
            any(rename.get("old_path") == "literal" for rename in plan["renamed_paths"])
        )
        self.assertIn("docs/project-context.md", plan["affected_docs"])

    def test_non_utf8_git_path_is_safely_serialized(self):
        rows = project_context_update.parse_status_z(b"?? \xff.py\0")
        escaped_path = rows[0]["path"]
        plan = {
            "recommended_action": "review-unmapped-changes",
            "source_change_paths": [escaped_path],
            "unmapped_changes": [escaped_path],
        }
        rendered = project_context_update.safe_json_dumps(plan)
        plan_path = project_context_update.write_temp_plan(
            self.root, project_context_update.DEFAULT_TEMP_PLAN, plan
        )

        self.assertEqual(escaped_path, r"\xff.py")
        self.assertIn(r"\\xff.py", rendered)
        self.assertIn(r"\xff.py", plan_path.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(rendered)["source_change_paths"], [r"\xff.py"])

    def test_parenthesized_markdown_link_is_valid_and_code_links_are_ignored(self):
        route = self.root / "app" / "(auth)" / "page.tsx"
        route.parent.mkdir(parents=True)
        route.write_text("export default function Page() {}\n", encoding="utf-8")
        self.git("add", "app/(auth)/page.tsx")
        self.git("commit", "-m", "add route group")
        context = self.write_context()
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "## 갱신 기록",
                "- [Route](../app/(auth)/page.tsx)\n\n## 갱신 기록",
            ),
            encoding="utf-8",
        )
        self.record()

        sample = (
            "[Route](../app/(auth)/page.tsx)\n"
            "`[Inline code](../missing.py)`\n"
            "<!-- [Comment](../missing.py) -->\n"
            "```md\n[Fence](../missing.py)\n```\n"
        )
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(
            list(project_context_update.iter_relative_links(sample)),
            ["../app/(auth)/page.tsx"],
        )
        self.assertEqual(
            list(validate_project_context.iter_relative_links(sample)),
            ["../app/(auth)/page.tsx"],
        )
        self.assertEqual(code, 0, (messages, warnings))

    def test_validator_rejects_stale_doc_sources_values(self):
        self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["doc_sources"][project_context_update.DEFAULT_DOC] = [
            "does/not/exist.py"
        ]
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        code, messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertTrue(any("doc_sources do not match" in message for message in messages))

    def test_record_repairs_all_derived_metadata_when_docs_are_unchanged(self):
        self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.update(
            {
                "generator": "wrong",
                "generator_version": "0",
                "updated_at": "invalid",
                "run_mode": "invalid",
                "primary_doc": "docs/wrong.md",
                "docs": [],
                "doc_sources": {},
                "content_hash": "invalid",
            }
        )
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        result = project_context_update.record_metadata(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )
        persisted = json.loads(metadata_path.read_text(encoding="utf-8"))
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertTrue(result["review_only"])
        self.assertEqual(persisted["generator"], project_context_update.GENERATOR)
        self.assertEqual(
            persisted["generator_version"], project_context_update.GENERATOR_VERSION
        )
        self.assertEqual(persisted["run_mode"], "update")
        self.assertEqual(
            persisted["docs"],
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        self.assertEqual(
            persisted["doc_sources"],
            project_context_update.collect_doc_sources(
                self.root, persisted["docs"]
            ),
        )
        self.assertEqual(persisted["content_hash"], before_hash)
        self.assertEqual(code, 0, (messages, warnings))


if __name__ == "__main__":
    unittest.main()
