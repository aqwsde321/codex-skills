import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
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

    def run_script(self, script, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT_ROOT / script), *map(str, args)],
            cwd=cwd or self.root,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_context(self):
        source_commit = self.git("rev-parse", "HEAD")
        context = self.root / "docs" / "project-context.md"
        context.parent.mkdir(parents=True, exist_ok=True)
        context.write_text(
            f"""---
generated_by: project-context
source_commit: {source_commit}
updated_at: 2026-07-20T00:00:00.000Z
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
        source_commit = self.git("rev-parse", "HEAD")
        context = self.root / "docs" / "project-context.md"
        context_dir = self.root / "docs" / "project-context"
        context_dir.mkdir(parents=True, exist_ok=True)
        context.write_text(
            f"""---
generated_by: project-context
source_commit: {source_commit}
updated_at: 2026-07-20T00:00:00.000Z
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
        for area, title, description, read_when in (
            ("architecture", "Architecture", "모듈 경계와 진입점", "모듈 소유권이나 시작 흐름 변경"),
            ("workflows", "Workflows", "주요 실행 흐름과 검증 지점", "실행 흐름 변경 또는 동작 검증"),
        ):
            area_dir = context_dir / area
            area_dir.mkdir()
            (area_dir / "index.md").write_text(
                f"""---
title: {title}
description: {description}
read_when: {read_when}
generated_by: project-context-index
---

# {title}

<!-- project-context:index:start -->
<!-- project-context:index:end -->
""",
                encoding="utf-8",
            )
        (context_dir / "architecture" / "overview.md").write_text(
            f"""---
type: architecture
title: Architecture Overview
description: 모듈 구조와 진입점 상세
read_when: 모듈 구조의 구현 근거 확인
---

# Architecture Overview

[Project context](../../project-context.md)

{supporting_body}

## 근거

- [Entrypoint](../../../app.py)
""",
            encoding="utf-8",
        )
        (context_dir / "workflows" / "overview.md").write_text(
            f"""---
type: workflow
title: Workflow Overview
description: 주요 실행 흐름 상세
read_when: 실행 흐름의 구현 근거 확인
---

# Workflow Overview

[Project context](../../project-context.md)

{supporting_body}

## 근거

- [Entrypoint](../../../app.py)
""",
            encoding="utf-8",
        )
        project_context_agents.ensure_file(self.root / "AGENTS.md", create_if_missing=True)
        return context

    def write_legacy_multi_context(self):
        source_commit = self.git("rev-parse", "HEAD")
        context = self.root / "docs" / "project-context.md"
        context_dir = self.root / "docs" / "project-context"
        context_dir.mkdir(parents=True, exist_ok=True)
        context.write_text(
            f"""---
generated_by: project-context
source_commit: {source_commit}
updated_at: 2026-07-20T00:00:00.000Z
mode: multi-page
custom_home: preserve-me
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
        supporting_body = "기존 문서 내용과 알 수 없는 frontmatter를 보존해야 한다. " * 20
        (context_dir / "architecture.md").write_text(
            f"""---
title: Architecture
description: 모듈 경계와 진입점
read_when: 모듈 소유권이나 시작 흐름 변경
custom_field: preserve-me
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

[Architecture](architecture.md)은 실행 흐름의 모듈 경계를 설명한다.

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

    def snapshot_docs_tree(self):
        docs = self.root / "docs"
        return {
            path.relative_to(self.root).as_posix(): (
                "directory" if path.is_dir() else path.read_bytes()
            )
            for path in sorted(docs.rglob("*"))
        }

    def prepare_committed_stale_architecture_index(self):
        context = self.write_multi_context()
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        self.record_and_commit_context("docs: add multi-page context")
        architecture = (
            self.root
            / "docs"
            / "project-context"
            / "architecture"
            / "overview.md"
        )
        architecture.write_text(
            architecture.read_text(encoding="utf-8").replace(
                "description: 모듈 구조와 진입점 상세",
                "description: 모듈 경계와 애플리케이션 진입점 상세",
            ),
            encoding="utf-8",
        )
        self.git("add", "docs/project-context/architecture/overview.md")
        self.git("commit", "-m", "docs: make generated index stale")
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        architecture_index = (
            self.root / "docs/project-context/architecture/index.md"
        )
        return context, architecture_index, before_hash

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
                "schema_version",
                "updated_at",
                "run_mode",
                "source_commit",
                "source_commit_short",
                "reviewed_commit",
                "primary_doc",
                "pages",
                "indexes",
                "doc_sources",
                "doc_hashes",
                "unmapped_resolutions",
                "content_hash",
            },
        )
        self.assertEqual(
            metadata["doc_hashes"],
            project_context_update.page_content_hashes(
                self.root, metadata["pages"]
            ),
        )
        self.assertEqual(metadata["unmapped_resolutions"], [])

    def test_writer_and_validator_share_version_contract(self):
        contract = load_script("project_context_contract")

        self.assertEqual(
            project_context_update.GENERATOR_VERSION,
            contract.GENERATOR_VERSION,
        )
        self.assertEqual(
            validate_project_context.GENERATOR_VERSION,
            contract.GENERATOR_VERSION,
        )
        self.assertEqual(
            project_context_update.SCHEMA_VERSION,
            contract.SCHEMA_VERSION,
        )
        self.assertEqual(
            validate_project_context.SCHEMA_VERSION,
            contract.SCHEMA_VERSION,
        )

    def test_validator_rejects_stale_page_hashes(self):
        self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["doc_hashes"][project_context_update.DEFAULT_DOC] = "0" * 64
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        code, messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertTrue(any("doc_hashes do not match" in message for message in messages))

    def test_validator_reports_broken_internal_link_as_error(self):
        context = self.write_context()
        self.record()
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "[Entrypoint](../app.py)", "[Entrypoint](../missing.py)"
            ),
            encoding="utf-8",
        )

        code, messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertTrue(any("broken link: ../missing.py" in message for message in messages))

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

    def test_record_rejects_fresh_snapshot_after_document_change_with_dirty_source(self):
        context = self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        original_metadata = metadata_path.read_bytes()
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "작은 Python 프로젝트다.", "변경된 Python 프로젝트다."
            ),
            encoding="utf-8",
        )
        (self.root / "app.py").write_text("print('dirty')\n", encoding="utf-8")
        fresh_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        with self.assertRaisesRegex(ValueError, "dirty source worktree changes"):
            project_context_update.record_metadata(
                self.root,
                project_context_update.DEFAULT_DOC,
                project_context_update.DEFAULT_METADATA,
                "update",
                True,
                fresh_hash,
            )

        self.assertEqual(metadata_path.read_bytes(), original_metadata)

    def test_finalize_rejects_changed_docs_while_source_worktree_is_dirty(self):
        context = self.write_context()
        self.record_and_commit_context("docs: add project context")
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata_before = metadata_path.read_bytes()
        previous_source_commit = json.loads(metadata_before)["source_commit"]
        current_head = self.git("rev-parse", "HEAD")
        (self.root / "app.py").write_text("print('dirty')\n", encoding="utf-8")
        context.write_text(
            context.read_text(encoding="utf-8")
            .replace(
                f"source_commit: {previous_source_commit}",
                f"source_commit: {current_head}",
            )
            .replace(
                "프로그램이 인사 문구를 출력한다.",
                "프로그램이 dirty 문구를 출력한다.",
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "dirty source worktree changes"):
            project_context_update.finalize_context(
                self.root,
                project_context_update.DEFAULT_DOC,
                project_context_update.DEFAULT_METADATA,
                "update",
                True,
                before_hash,
            )

        self.assertEqual(metadata_path.read_bytes(), metadata_before)

    def test_metadata_less_finalize_rejects_fresh_snapshot_with_dirty_source(self):
        self.write_context()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        (self.root / "app.py").write_text("print('dirty')\n", encoding="utf-8")
        fresh_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        with self.assertRaisesRegex(ValueError, "dirty source worktree changes"):
            project_context_update.finalize_context(
                self.root,
                project_context_update.DEFAULT_DOC,
                project_context_update.DEFAULT_METADATA,
                "init",
                True,
                fresh_hash,
            )

        self.assertFalse(metadata_path.exists())

    def test_finalize_rejects_project_context_documents_ignored_by_git(self):
        (self.root / ".gitignore").write_text("docs/\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "ignore docs")
        self.write_context()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        (self.root / "app.py").write_text("print('dirty')\n", encoding="utf-8")
        fresh_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        with self.assertRaisesRegex(ValueError, "ignored by Git"):
            project_context_update.finalize_context(
                self.root,
                project_context_update.DEFAULT_DOC,
                project_context_update.DEFAULT_METADATA,
                "init",
                True,
                fresh_hash,
            )

        self.assertFalse(metadata_path.exists())

    def test_finalize_rejects_ignored_agent_entrypoint(self):
        (self.root / ".gitignore").write_text("AGENTS.md\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "ignore agent entrypoint")
        self.write_context()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        fresh_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        with self.assertRaisesRegex(ValueError, "ignored by Git"):
            project_context_update.finalize_context(
                self.root,
                project_context_update.DEFAULT_DOC,
                project_context_update.DEFAULT_METADATA,
                "init",
                True,
                fresh_hash,
            )

        self.assertFalse(metadata_path.exists())

    def test_record_rejects_project_context_documents_ignored_by_git(self):
        (self.root / ".gitignore").write_text("docs/\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "ignore docs")
        self.write_context()

        with self.assertRaisesRegex(ValueError, "ignored by Git"):
            self.record()

        self.assertFalse(
            (self.root / project_context_update.DEFAULT_METADATA).exists()
        )

    def test_record_cli_rejects_changed_docs_while_source_worktree_is_dirty(self):
        context = self.write_context()
        self.record_and_commit_context("docs: add project context")
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata_before = metadata_path.read_bytes()
        previous_source_commit = json.loads(metadata_before)["source_commit"]
        current_head = self.git("rev-parse", "HEAD")
        (self.root / "app.py").write_text("print('dirty')\n", encoding="utf-8")
        context.write_text(
            context.read_text(encoding="utf-8")
            .replace(
                f"source_commit: {previous_source_commit}",
                f"source_commit: {current_head}",
            )
            .replace(
                "프로그램이 인사 문구를 출력한다.",
                "프로그램이 dirty 문구를 출력한다.",
            ),
            encoding="utf-8",
        )

        completed = self.run_script(
            "project_context_update.py",
            "record",
            self.root,
            "--mode",
            "update",
            "--if-changed",
            "--before-hash",
            before_hash,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("dirty source worktree changes", completed.stderr)
        self.assertEqual(metadata_path.read_bytes(), metadata_before)

    def test_write_plan_rejects_dirty_source_without_creating_plan(self):
        self.write_context()
        (self.root / "app.py").write_text("print('dirty')\n", encoding="utf-8")

        completed = self.run_script(
            "project_context_update.py",
            "write-plan",
            self.root,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("dirty source worktree changes", completed.stderr)
        self.assertFalse((self.root / project_context_update.DEFAULT_TEMP_PLAN).exists())

    def test_dirty_agent_marker_only_change_uses_head_baseline(self):
        self.write_context()
        self.record_and_commit_context("docs: add project context")
        agent_path = self.root / "AGENTS.md"
        agent_path.write_text(
            f"# User Rule\n\n{agent_path.read_text(encoding='utf-8')}",
            encoding="utf-8",
        )
        self.git("add", "AGENTS.md")
        self.git("commit", "-m", "docs: add user agent rule")
        agent_path.write_text(
            agent_path.read_text(encoding="utf-8").replace(
                "모든 개념 문서를 미리 읽지 않는다.",
                "각 개념 문서를 미리 읽지 않는다.",
            ),
            encoding="utf-8",
        )

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        self.assertIn("AGENTS.md", plan["source_change_paths"])
        self.assertNotIn("AGENTS.md", plan["dirty_source_change_paths"])

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
        self.assertEqual(
            persisted["generator_version"], project_context_update.GENERATOR_VERSION
        )
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
        self.assertEqual(plan["previous_commit"], self.git("rev-parse", "HEAD"))

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

    def test_document_source_commit_requires_canonical_full_oid(self):
        context = self.write_context()
        original = context.read_text(encoding="utf-8")
        full_head = self.git("rev-parse", "HEAD")
        short_head = self.git("rev-parse", "--short", "HEAD")
        branch = self.git("branch", "--show-current")
        self.git("tag", "fixture-tag")

        for mutable_ref in ("HEAD", branch, "fixture-tag", short_head):
            with self.subTest(source_commit=mutable_ref):
                context.write_text(
                    original.replace(
                        f"source_commit: {full_head}",
                        f"source_commit: {mutable_ref}",
                    ),
                    encoding="utf-8",
                )
                errors, _ = validate_project_context.validate_doc(
                    self.root,
                    validate_project_context.DEFAULT_DOC,
                    require_metadata=True,
                )
                self.assertTrue(
                    any("canonical full commit ID" in error for error in errors),
                    errors,
                )

    def test_canonical_commit_supports_sha256_repositories(self):
        sha256_root = self.root.parent / "sha256-repo"
        completed = subprocess.run(
            ["git", "init", "--object-format=sha256", str(sha256_root)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            self.skipTest("installed Git does not support SHA-256 repositories")
        subprocess.run(
            ["git", "config", "user.name", "Codex"],
            cwd=sha256_root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "codex@example.invalid"],
            cwd=sha256_root,
            check=True,
        )
        (sha256_root / "README.md").write_text("# SHA-256\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=sha256_root, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init sha256 fixture"],
            cwd=sha256_root,
            check=True,
            capture_output=True,
        )
        full_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=sha256_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        self.assertEqual(len(full_head), 64)
        self.assertEqual(
            project_context_update.canonical_commit_oid(sha256_root, full_head),
            full_head,
        )
        self.assertIsNone(
            project_context_update.canonical_commit_oid(sha256_root, full_head[:12])
        )

    def test_body_source_commit_is_not_a_document_baseline(self):
        context = self.write_context()
        full_head = self.git("rev-parse", "HEAD")
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                f"source_commit: {full_head}\n", ""
            )
            + f"\n```yaml\nsource_commit: {full_head}\n```\n",
            encoding="utf-8",
        )
        self.git("add", "AGENTS.md", "docs")
        self.git("commit", "-m", "docs without baseline")

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        errors, _ = validate_project_context.validate_doc(
            self.root,
            validate_project_context.DEFAULT_DOC,
            require_metadata=True,
        )

        self.assertIsNone(
            project_context_update.read_source_commit_from_doc(
                self.root, project_context_update.DEFAULT_DOC
            )
        )
        self.assertIn("review-recent-history", plan["required_actions"])
        self.assertTrue(any("missing metadata: source_commit" in error for error in errors))

    def test_metadata_commit_baselines_require_canonical_full_oids(self):
        self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["source_commit"] = "HEAD"
        metadata["reviewed_commit"] = "HEAD"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        code, messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertTrue(
            any("source_commit must be a canonical full commit ID" in message for message in messages)
        )
        self.assertTrue(
            any("reviewed_commit must be a canonical full commit ID" in message for message in messages)
        )

    def test_generator_version_mismatch_fails_validation(self):
        self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["generator_version"] = str(
            int(project_context_update.GENERATOR_VERSION) - 1
        )
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        code, messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertTrue(
            any("generator_version must be" in message for message in messages)
        )

    def test_atomic_metadata_write_preserves_previous_file_on_replace_failure(self):
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text("old metadata\n", encoding="utf-8")
        safety_os = project_context_update.atomic_write_text.__globals__["os"]

        with mock.patch.object(safety_os, "replace", side_effect=OSError("failed")):
            with self.assertRaisesRegex(OSError, "failed"):
                project_context_update.atomic_write_text(
                    metadata_path, "new metadata\n"
                )

        self.assertEqual(metadata_path.read_text(encoding="utf-8"), "old metadata\n")
        self.assertEqual(list(metadata_path.parent.glob(".metadata.json.*.tmp")), [])

    def test_atomic_write_preserves_existing_mode_and_uses_readable_new_mode(self):
        existing = self.root / "existing.md"
        created = self.root / "created.md"
        existing.write_text("old\n", encoding="utf-8")
        existing.chmod(0o640)

        project_context_update.atomic_write_text(existing, "new\n")
        project_context_update.atomic_write_text(created, "created\n")

        self.assertEqual(existing.stat().st_mode & 0o777, 0o640)
        self.assertEqual(created.stat().st_mode & 0o777, 0o644)

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

        self.assertEqual(legacy_code, 1, legacy_messages)
        self.assertTrue(
            any("generator_version must be" in message for message in legacy_messages)
        )
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
        self.assertIn("일반적인 프로젝트 질문", first)
        self.assertIn("영역 인덱스", first)
        self.assertIn("모든 개념 문서를 미리 읽지 않는다", first)
        self.assertIn("read_when", first)
        self.assertIn("정확한 구현 확인", first)
        self.assertIn("현재 소스가 항상 우선", first)
        self.assertIn("저장소의 코드 탐색 지침", first)
        self.assertIn("생성이나 갱신을 명시적으로 요청", first)
        self.assertIn("문서가 없거나 오래됐다는 이유만으로 쓰기 권한이 생기지 않는다", first)

    def test_old_agent_section_is_replaced_by_context_first_guidance(self):
        stale_section = project_context_agents.SECTION.replace(
            "일반적인 프로젝트 질문", "일상적인 프로젝트 질문"
        )

        next_text, changed = project_context_agents.replace_marked_section(stale_section)

        self.assertTrue(changed)
        self.assertEqual(next_text, project_context_agents.SECTION)
        self.assertTrue(
            validate_project_context.is_semantically_current_agent_section(next_text)
        )

    def test_agent_section_without_write_authority_guard_is_replaced(self):
        stale_section = project_context_agents.SECTION.replace(
            "문서가 없거나 오래됐다는 이유만으로 쓰기 권한이 생기지 않는다",
            "오래된 문서는 자동으로 갱신한다",
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

        self.assertTrue(plan.startswith("# 프로젝트 컨텍스트 임시 계획\n"))
        self.assertIn("## 근거 기반 관계", plan)
        self.assertIn("소스 개념 -> 관계 의미 -> 대상 개념", plan)
        self.assertIn("## 보류한 범위", plan)
        self.assertIn("영역, 소스 근거, 사유", plan)
        self.assertIn(project_context_update.UNMAPPED_START_MARKER, plan)
        self.assertEqual(project_context_update.parse_unmapped_resolutions(plan), [])

    def test_primary_change_decision_heading_satisfies_guidance_check(self):
        context = self.write_context()
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "## 작업 전 확인 지점", "## 변경 판단"
            ),
            encoding="utf-8",
        )
        self.record()

        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 0, messages)
        self.assertFalse(
            any("change guidance section" in warning for warning in warnings)
        )

    def test_finalize_removes_plan_after_valid_noop(self):
        self.write_context()
        self.record()
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        project_context_update.write_temp_plan(
            self.root, project_context_update.DEFAULT_TEMP_PLAN, plan
        )

        result = project_context_update.finalize_context(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )

        self.assertTrue(result["finalized"])
        self.assertFalse(result["metadata_written"])
        self.assertFalse((self.root / project_context_update.DEFAULT_TEMP_PLAN).exists())

    def test_finalize_keeps_plan_and_metadata_when_candidate_is_invalid(self):
        context = self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        original_metadata = metadata_path.read_bytes()
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        plan_path = project_context_update.write_temp_plan(
            self.root, project_context_update.DEFAULT_TEMP_PLAN, plan
        )
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "[Entrypoint](../app.py)", "[Entrypoint](../missing.py)"
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "candidate metadata validation failed"):
            project_context_update.finalize_context(
                self.root,
                project_context_update.DEFAULT_DOC,
                project_context_update.DEFAULT_METADATA,
                "update",
                True,
                before_hash,
            )

        self.assertEqual(metadata_path.read_bytes(), original_metadata)
        self.assertTrue(plan_path.exists())

    def test_finalize_rolls_back_metadata_and_plan_after_final_validation_failure(self):
        self.write_context()
        self.record_and_commit_context("docs: add context")
        (self.root / "app.py").write_text("print('changed')\n", encoding="utf-8")
        self.git("add", "app.py")
        self.git("commit", "-m", "change app")
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        original_metadata = metadata_path.read_bytes()
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        plan_path = project_context_update.write_temp_plan(
            self.root, project_context_update.DEFAULT_TEMP_PLAN, plan
        )
        original_plan = plan_path.read_bytes()

        with mock.patch(
            "validate_project_context.validate",
            side_effect=[
                (0, ["candidate valid"], []),
                (1, ["forced final failure"], []),
            ],
        ):
            with self.assertRaisesRegex(ValueError, "forced final failure"):
                project_context_update.finalize_context(
                    self.root,
                    project_context_update.DEFAULT_DOC,
                    project_context_update.DEFAULT_METADATA,
                    "update",
                    True,
                    before_hash,
                )

        self.assertEqual(metadata_path.read_bytes(), original_metadata)
        self.assertEqual(plan_path.read_bytes(), original_plan)

    def test_finalize_rolls_back_synced_indexes_after_final_validation_failure(self):
        context, architecture_index, before_hash = (
            self.prepare_committed_stale_architecture_index()
        )
        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        plan_path = project_context_update.write_temp_plan(
            self.root, project_context_update.DEFAULT_TEMP_PLAN, plan
        )
        original_plan = plan_path.read_bytes()
        original_home = context.read_bytes()
        original_index = architecture_index.read_bytes()

        with mock.patch(
            "validate_project_context.validate",
            side_effect=[
                (0, ["candidate valid"], []),
                (1, ["forced final failure"], []),
            ],
        ):
            with self.assertRaisesRegex(ValueError, "forced final failure"):
                project_context_update.finalize_context(
                    self.root,
                    project_context_update.DEFAULT_DOC,
                    project_context_update.DEFAULT_METADATA,
                    "update",
                    True,
                    before_hash,
                )

        self.assertEqual(context.read_bytes(), original_home)
        self.assertEqual(architecture_index.read_bytes(), original_index)
        self.assertEqual(plan_path.read_bytes(), original_plan)

    def test_finalize_rejects_dirty_source_before_syncing_stale_indexes(self):
        context, architecture_index, before_hash = (
            self.prepare_committed_stale_architecture_index()
        )
        original_home = context.read_bytes()
        original_index = architecture_index.read_bytes()
        (self.root / "app.py").write_text("print('dirty')\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "dirty source worktree changes"):
            project_context_update.finalize_context(
                self.root,
                project_context_update.DEFAULT_DOC,
                project_context_update.DEFAULT_METADATA,
                "update",
                True,
                before_hash,
            )

        self.assertEqual(context.read_bytes(), original_home)
        self.assertEqual(architecture_index.read_bytes(), original_index)

    def test_finalize_requires_and_records_unmapped_ignore_reason(self):
        self.write_context()
        self.record_and_commit_context("docs: add context")
        (self.root / "notes.txt").write_text("not runtime input\n", encoding="utf-8")
        self.git("add", "notes.txt")
        self.git("commit", "-m", "add unrelated notes")
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        plan_path = project_context_update.write_temp_plan(
            self.root, project_context_update.DEFAULT_TEMP_PLAN, plan
        )

        with self.assertRaisesRegex(ValueError, "must be documented.*or ignored"):
            project_context_update.finalize_context(
                self.root,
                project_context_update.DEFAULT_DOC,
                project_context_update.DEFAULT_METADATA,
                "update",
                True,
                before_hash,
            )

        plan_markdown = plan_path.read_text(encoding="utf-8")
        plan_markdown = plan_markdown.replace(
            '"resolution": "pending"', '"resolution": "ignored"', 1
        ).replace(
            '"reason": ""',
            '"reason": "프로젝트 실행과 무관한 테스트 메모"',
            1,
        )
        plan_path.write_text(plan_markdown, encoding="utf-8")
        result = project_context_update.finalize_context(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )
        metadata = json.loads(
            (self.root / project_context_update.DEFAULT_METADATA).read_text(
                encoding="utf-8"
            )
        )

        self.assertTrue(result["metadata_written"])
        self.assertFalse(plan_path.exists())
        self.assertEqual(
            metadata["unmapped_resolutions"],
            [
                {
                    "path": "notes.txt",
                    "resolution": "ignored",
                    "reason": "프로젝트 실행과 무관한 테스트 메모",
                }
            ],
        )

    def test_finalize_accepts_source_linked_backlog_resolution(self):
        context = self.write_context()
        self.record_and_commit_context("docs: add context")
        (self.root / "notes.txt").write_text("future documentation input\n", encoding="utf-8")
        self.git("add", "notes.txt")
        self.git("commit", "-m", "add future notes")
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        plan_path = project_context_update.write_temp_plan(
            self.root, project_context_update.DEFAULT_TEMP_PLAN, plan
        )
        current_head = self.git("rev-parse", "HEAD")
        context_markdown = context.read_text(encoding="utf-8")
        old_source_commit = project_context_update.parse_frontmatter(
            context_markdown
        )["source_commit"]
        context_markdown = context_markdown.replace(
            f"source_commit: {old_source_commit}",
            f"source_commit: {current_head}",
        ).replace(
            "## 근거",
            "## 문서화 백로그\n\n"
            "- 메모 문서화 보류 — 근거: [notes](../notes.txt) — 사유: 후속 기능 확정 필요\n\n"
            "## 근거",
        )
        context.write_text(context_markdown, encoding="utf-8")
        plan_markdown = plan_path.read_text(encoding="utf-8").replace(
            '"resolution": "pending"', '"resolution": "backlog"', 1
        ).replace(
            '"reason": ""', '"reason": "후속 기능 확정 필요"', 1
        )
        plan_path.write_text(plan_markdown, encoding="utf-8")

        result = project_context_update.finalize_context(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
            "update",
            True,
            before_hash,
        )
        metadata = json.loads(
            (self.root / project_context_update.DEFAULT_METADATA).read_text(
                encoding="utf-8"
            )
        )

        self.assertTrue(result["metadata_written"])
        self.assertEqual(
            metadata["unmapped_resolutions"][0]["resolution"], "backlog"
        )

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
            self.assertIn("## 문서 구조 문제", rendered)
            self.assertIn("[single-page-primary-too-large]", rendered)
            self.assertIn(project_context_update.DEFAULT_DOC, rendered)

    def test_three_subpages_warn_only_for_isolated_peer_relationships(self):
        context_dir = self.root / "docs" / "project-context"
        context_dir.mkdir(parents=True)
        docs = [
            validate_project_context.DEFAULT_DOC,
            "docs/project-context/domain/a.md",
            "docs/project-context/domain/b.md",
            "docs/project-context/domain/c.md",
        ]
        domain_dir = context_dir / "domain"
        domain_dir.mkdir()
        (domain_dir / "a.md").write_text(
            "A sends data to [B](b.md).\n",
            encoding="utf-8",
        )
        (domain_dir / "b.md").write_text("B\n", encoding="utf-8")
        (domain_dir / "c.md").write_text("C\n", encoding="utf-8")

        _, warnings = validate_project_context.validate_context_relationships(
            self.root, validate_project_context.DEFAULT_DOC, docs
        )
        _, two_page_warnings = validate_project_context.validate_context_relationships(
            self.root, validate_project_context.DEFAULT_DOC, docs[:3]
        )

        self.assertEqual(len(warnings), 1)
        self.assertIn("docs/project-context/domain/c.md", warnings[0])
        self.assertEqual(two_page_warnings, [])

    def test_semantic_relationships_require_meaningful_prose_links(self):
        self.write_multi_context()
        architecture = self.root / "docs" / "project-context" / "architecture" / "overview.md"
        workflows_rel = "docs/project-context/workflows/overview.md"
        architecture.write_text(
            architecture.read_text(encoding="utf-8").replace(
                "- [Entrypoint](../../../app.py)",
                "- [Entrypoint](../../../app.py)\n- [Workflow evidence](../workflows/overview.md)",
            ),
            encoding="utf-8",
        )
        concepts = [
            "docs/project-context/architecture/overview.md",
            workflows_rel,
        ]

        evidence_only = project_context_update.collect_semantic_relationships(
            self.root, concepts
        )
        architecture.write_text(
            architecture.read_text(encoding="utf-8").replace(
                "## 근거",
                "## 관련 문서\n\n"
                "- [Workflow overview](../workflows/overview.md), "
                "[Workflow details](../workflows/overview.md)\n\n"
                "## 근거",
            ),
            encoding="utf-8",
        )
        bare_list = project_context_update.collect_semantic_relationships(
            self.root, concepts
        )
        architecture.write_text(
            architecture.read_text(encoding="utf-8").replace(
                "- [Workflow overview](../workflows/overview.md), "
                "[Workflow details](../workflows/overview.md)",
                "- [Workflow overview](../workflows/overview.md)<br>"
                "[Workflow details](../workflows/overview.md)",
            ),
            encoding="utf-8",
        )
        html_bare_list = project_context_update.collect_semantic_relationships(
            self.root, concepts
        )
        architecture.write_text(
            architecture.read_text(encoding="utf-8").replace(
                "- [Workflow overview](../workflows/overview.md)<br>"
                "[Workflow details](../workflows/overview.md)",
                "[Workflow overview](../workflows/overview.md)은 구조 결정 뒤의 실행 흐름을 설명한다.",
            ),
            encoding="utf-8",
        )
        semantic = project_context_update.collect_semantic_relationships(
            self.root, concepts
        )

        self.assertEqual(evidence_only["neighbors"][concepts[0]], [])
        self.assertEqual(bare_list["neighbors"][concepts[0]], [])
        self.assertEqual(html_bare_list["neighbors"][concepts[0]], [])
        self.assertEqual(semantic["outgoing"][concepts[0]], [workflows_rel])
        self.assertEqual(semantic["incoming"][workflows_rel], [concepts[0]])

    def test_navigation_only_links_do_not_create_semantic_relationships(self):
        self.write_multi_context()
        architecture_rel = "docs/project-context/architecture/overview.md"
        workflows_rel = "docs/project-context/workflows/overview.md"
        architecture = self.root / architecture_rel
        baseline = architecture.read_text(encoding="utf-8")

        for navigation in (
            "관련 문서: [흐름](../workflows/overview.md), "
            "[상세](../workflows/overview.md)",
            "[흐름](../workflows/overview.md)&nbsp;"
            "[상세](../workflows/overview.md)",
            "[흐름](../workflows/overview.md)<!-- nav -->"
            "[상세](../workflows/overview.md)",
        ):
            with self.subTest(navigation=navigation):
                architecture.write_text(
                    baseline.replace(
                        "## 근거", f"## 관련 문서\n\n{navigation}\n\n## 근거"
                    ),
                    encoding="utf-8",
                )
                relationships = (
                    project_context_update.collect_semantic_relationships(
                        self.root, [architecture_rel, workflows_rel]
                    )
                )

                self.assertEqual(relationships["outgoing"][architecture_rel], [])

    def test_navigation_labels_are_language_independent(self):
        self.write_multi_context()
        architecture_rel = "docs/project-context/architecture/overview.md"
        workflows_rel = "docs/project-context/workflows/overview.md"
        architecture = self.root / architecture_rel
        baseline = architecture.read_text(encoding="utf-8")
        links = (
            "[흐름](../workflows/overview.md), "
            "[상세](../workflows/overview.md)"
        )

        for navigation in (
            f"Related docs: {links}",
            f"Related links {links}",
            f"Related pages: {links}",
            "Related pages: [흐름](../workflows/overview.md) and "
            "[상세](../workflows/overview.md)",
            f"Links: {links}",
            "Links: [흐름](../workflows/overview.md) or "
            "[상세](../workflows/overview.md)",
            "Links: [흐름](../workflows/overview.md)",
            f"References {links}",
            f"See also {links}",
            f"Documentos relacionados: {links}",
            "Documentos relacionados: [흐름](../workflows/overview.md) y "
            "[상세](../workflows/overview.md)",
            f"関連文書： {links}",
            "関連文書： [흐름](../workflows/overview.md) と "
            "[상세](../workflows/overview.md)",
            "관련 문서: [흐름](../workflows/overview.md) 및 "
            "[상세](../workflows/overview.md)",
        ):
            with self.subTest(navigation=navigation):
                architecture.write_text(
                    baseline.replace(
                        "## 근거", f"## 관련 문서\n\n{navigation}\n\n## 근거"
                    ),
                    encoding="utf-8",
                )
                relationships = (
                    project_context_update.collect_semantic_relationships(
                        self.root, [architecture_rel, workflows_rel]
                    )
                )
                self.assertEqual(relationships["outgoing"][architecture_rel], [])

        for sentence in (
            "The flow depends on [Workflow](../workflows/overview.md).",
            "Dependency: [Workflow](../workflows/overview.md) controls recovery.",
            "Related pages: [Workflow](../workflows/overview.md) and "
            "the fallback handles recovery.",
        ):
            with self.subTest(sentence=sentence):
                architecture.write_text(
                    baseline.replace(
                        "## 근거", f"## 관련 문서\n\n{sentence}\n\n## 근거"
                    ),
                    encoding="utf-8",
                )
                relationships = (
                    project_context_update.collect_semantic_relationships(
                        self.root, [architecture_rel, workflows_rel]
                    )
                )
                self.assertEqual(
                    relationships["outgoing"][architecture_rel], [workflows_rel]
                )

    def test_semantic_relation_labels_without_trailing_prose_create_relationships(self):
        self.write_multi_context()
        architecture_rel = "docs/project-context/architecture/overview.md"
        workflows_rel = "docs/project-context/workflows/overview.md"
        architecture = self.root / architecture_rel
        baseline = architecture.read_text(encoding="utf-8")

        for sentence in (
            "Depends on: [Workflow](../workflows/overview.md)",
            "Depends on: [Workflow](../workflows/overview.md), "
            "[Fallback](../workflows/overview.md)",
            "Calls: [Payment service](../workflows/overview.md)",
            "**Depends on:** [Workflow](../workflows/overview.md)",
            "**Depends on:** [Workflow](../workflows/overview.md) and "
            "[Fallback](../workflows/overview.md)",
            "__Calls:__ [Payment service](../workflows/overview.md)",
            "**Depends on**: [Workflow](../workflows/overview.md)",
            "__Calls__: [Payment service](../workflows/overview.md)",
        ):
            with self.subTest(sentence=sentence):
                architecture.write_text(
                    baseline.replace(
                        "## 근거", f"## 관련 문서\n\n{sentence}\n\n## 근거"
                    ),
                    encoding="utf-8",
                )
                relationships = (
                    project_context_update.collect_semantic_relationships(
                        self.root, [architecture_rel, workflows_rel]
                    )
                )
                self.assertEqual(
                    relationships["outgoing"][architecture_rel], [workflows_rel]
                )

    def test_source_affected_page_adds_semantic_one_hop_review_candidate(self):
        self.write_multi_context()
        architecture = self.root / "docs" / "project-context" / "architecture" / "overview.md"
        workflows = self.root / "docs" / "project-context" / "workflows" / "overview.md"
        architecture.write_text(
            architecture.read_text(encoding="utf-8").replace(
                "## 근거",
                "**Depends on:** [Workflow overview](../workflows/overview.md) and "
                "[Workflow details](../workflows/overview.md)\n\n## 근거",
            ),
            encoding="utf-8",
        )
        workflows.write_text(
            workflows.read_text(encoding="utf-8").replace(
                "- [Entrypoint](../../../app.py)", "- [README](../../../README.md)"
            ),
            encoding="utf-8",
        )
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        self.record_and_commit_context("docs: add linked wiki")
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )
        project_context_update.record_metadata(
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

        architecture_rel = "docs/project-context/architecture/overview.md"
        workflows_rel = "docs/project-context/workflows/overview.md"
        self.assertIn(architecture_rel, plan["affected_docs"])
        self.assertEqual(
            plan["related_review_candidates"],
            {architecture_rel: [workflows_rel]},
        )

    def test_changed_page_hash_adds_incoming_semantic_review_candidate(self):
        self.write_multi_context()
        architecture = self.root / "docs" / "project-context" / "architecture" / "overview.md"
        workflows = self.root / "docs" / "project-context" / "workflows" / "overview.md"
        architecture.write_text(
            architecture.read_text(encoding="utf-8").replace(
                "## 근거",
                "[Workflow overview](../workflows/overview.md)은 구조의 실행 순서를 설명한다.\n\n## 근거",
            ),
            encoding="utf-8",
        )
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        self.record()
        workflows.write_text(
            workflows.read_text(encoding="utf-8").replace(
                "# Workflow Overview", "# Workflow Overview\n\n검토할 규칙이 바뀌었다."
            ),
            encoding="utf-8",
        )

        plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )

        architecture_rel = "docs/project-context/architecture/overview.md"
        workflows_rel = "docs/project-context/workflows/overview.md"
        self.assertIn(workflows_rel, plan["changed_context_pages"])
        self.assertEqual(
            plan["related_review_candidates"],
            {workflows_rel: [architecture_rel]},
        )

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

    def test_sync_index_creates_missing_area_index(self):
        self.write_multi_context()
        missing_index = (
            self.root / "docs" / "project-context" / "architecture" / "index.md"
        )
        missing_index.unlink()

        result = project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        created = missing_index.read_text(encoding="utf-8")
        self.record()
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertIn(
            "docs/project-context/architecture/index.md",
            result["created_indexes"],
        )
        self.assertIn("generated_by: project-context-index", created)
        self.assertIn("[Architecture Overview](overview.md)", created)
        self.assertEqual(code, 0, (messages, warnings))

    def test_generated_area_index_uses_one_area_suffix(self):
        singular = project_context_update.new_area_index_markdown("domain")
        custom = project_context_update.new_area_index_markdown("custom-area")

        self.assertIn("title: 도메인", singular)
        self.assertIn("description: 도메인 영역의 프로젝트 컨텍스트", singular)
        self.assertIn("description: custom area 영역의 프로젝트 컨텍스트", custom)
        self.assertNotIn("영역 영역", singular)
        self.assertNotIn("영역 영역", custom)

    def test_legacy_wiki_migration_is_read_only_until_applied(self):
        self.write_legacy_multi_context()
        before = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in sorted((self.root / "docs").rglob("*"))
            if path.is_file()
        }

        plan = project_context_update.build_wiki_migration(
            self.root, project_context_update.DEFAULT_DOC
        )
        update_plan = project_context_update.build_plan(
            self.root,
            project_context_update.DEFAULT_DOC,
            project_context_update.DEFAULT_METADATA,
        )
        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in sorted((self.root / "docs").rglob("*"))
            if path.is_file()
        }

        self.assertEqual(before, after)
        self.assertEqual(plan["from_schema_version"], 1)
        self.assertEqual(plan["to_schema_version"], 2)
        self.assertEqual(update_plan["recommended_action"], "migrate-wiki-schema")
        self.assertTrue(update_plan["migration_required"])
        self.assertEqual(
            plan["moves"]["docs/project-context/architecture.md"],
            "docs/project-context/architecture/overview.md",
        )
        self.assertEqual(len(plan["created_indexes"]), 2)

    def test_wiki_migration_apply_rejects_dirty_source_without_writing(self):
        self.write_legacy_multi_context()
        before = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in sorted((self.root / "docs").rglob("*"))
            if path.is_file()
        }
        (self.root / "app.py").write_text("print('dirty')\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "dirty source worktree changes"):
            project_context_update.apply_wiki_migration(
                self.root, project_context_update.DEFAULT_DOC, "update"
            )

        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in sorted((self.root / "docs").rglob("*"))
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_wiki_migration_rolls_back_partial_destination_write(self):
        self.write_legacy_multi_context()
        before = self.snapshot_docs_tree()
        failure_target = (
            self.root / "docs/project-context/workflows/overview.md"
        )
        atomic_write_text = project_context_update.atomic_write_text

        def fail_workflow_write(path, markdown):
            if path == failure_target:
                raise OSError("forced migration write failure")
            atomic_write_text(path, markdown)

        with mock.patch.object(
            project_context_update,
            "atomic_write_text",
            side_effect=fail_workflow_write,
        ):
            with self.assertRaisesRegex(OSError, "forced migration write failure"):
                project_context_update.apply_wiki_migration(
                    self.root, project_context_update.DEFAULT_DOC, "update"
                )

        self.assertEqual(self.snapshot_docs_tree(), before)
        result = project_context_update.apply_wiki_migration(
            self.root, project_context_update.DEFAULT_DOC, "update"
        )
        self.assertTrue(result["applied"])

    def test_wiki_migration_rolls_back_after_metadata_failure(self):
        self.write_legacy_multi_context()
        before = self.snapshot_docs_tree()

        with mock.patch.object(
            project_context_update,
            "record_metadata",
            side_effect=OSError("forced metadata failure"),
        ):
            with self.assertRaisesRegex(OSError, "forced metadata failure"):
                project_context_update.apply_wiki_migration(
                    self.root, project_context_update.DEFAULT_DOC, "update"
                )

        self.assertEqual(self.snapshot_docs_tree(), before)
        result = project_context_update.apply_wiki_migration(
            self.root, project_context_update.DEFAULT_DOC, "update"
        )
        self.assertTrue(result["applied"])

    def test_legacy_wiki_migration_preserves_content_and_rewrites_links(self):
        self.write_legacy_multi_context()

        result = project_context_update.apply_wiki_migration(
            self.root, project_context_update.DEFAULT_DOC, "update"
        )
        architecture = self.root / "docs" / "project-context" / "architecture" / "overview.md"
        workflows = self.root / "docs" / "project-context" / "workflows" / "overview.md"
        home = (self.root / "docs" / "project-context.md").read_text(encoding="utf-8")
        architecture_markdown = architecture.read_text(encoding="utf-8")
        workflows_markdown = workflows.read_text(encoding="utf-8")
        metadata = json.loads(
            (self.root / project_context_update.DEFAULT_METADATA).read_text(
                encoding="utf-8"
            )
        )
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertTrue(result["applied"])
        self.assertFalse((self.root / "docs" / "project-context" / "architecture.md").exists())
        self.assertIn("custom_field: preserve-me", architecture_markdown)
        self.assertIn("type: concept", architecture_markdown)
        self.assertIn("[Entrypoint](../../../app.py)", architecture_markdown)
        self.assertIn("[Project context](../../project-context.md)", architecture_markdown)
        self.assertIn("[Architecture](../architecture/overview.md)", workflows_markdown)
        self.assertIn("[아키텍처](project-context/architecture/index.md)", home)
        self.assertIn("custom_home: preserve-me", home)
        self.assertEqual(metadata["schema_version"], 2)
        self.assertEqual(metadata["pages"], result["pages"])
        self.assertEqual(metadata["indexes"], result["indexes"])
        self.assertEqual(code, 0, (messages, warnings))

    def test_legacy_wiki_migration_normalizes_v1_primary_metadata(self):
        context = self.write_legacy_multi_context()
        full_head = self.git("rev-parse", "HEAD")
        context.write_text(
            context.read_text(encoding="utf-8")
            .replace(f"source_commit: {full_head}", f"source_commit: {full_head[:7]}")
            .replace(
                "updated_at: 2026-07-20T00:00:00.000Z",
                "updated_at: 2026-07-20T09:00:00+09:00",
            ),
            encoding="utf-8",
        )

        result = project_context_update.apply_wiki_migration(
            self.root, project_context_update.DEFAULT_DOC, "update"
        )
        fields = project_context_update.parse_frontmatter(
            context.read_text(encoding="utf-8")
        )
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertTrue(result["applied"])
        self.assertEqual(fields["source_commit"], full_head)
        self.assertEqual(fields["updated_at"], "2026-07-20T00:00:00.000Z")
        self.assertEqual(code, 0, (messages, warnings))

    def test_wiki_migration_does_not_claim_unreviewed_source_commits(self):
        self.write_legacy_multi_context()
        documented_commit = self.git("rev-parse", "HEAD")
        (self.root / "app.py").write_text("print('unreviewed')\n", encoding="utf-8")
        self.git("add", "app.py")
        self.git("commit", "-m", "unreviewed source change")

        project_context_update.apply_wiki_migration(
            self.root, project_context_update.DEFAULT_DOC, "update"
        )
        metadata = json.loads(
            (self.root / project_context_update.DEFAULT_METADATA).read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(metadata["source_commit"], documented_commit)
        self.assertEqual(metadata["reviewed_commit"], documented_commit)

    def test_home_only_legacy_metadata_migrates_without_creating_empty_areas(self):
        self.write_context()
        metadata = self.record()
        metadata.pop("schema_version")
        metadata["docs"] = metadata.pop("pages")
        metadata.pop("indexes")
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        result = project_context_update.apply_wiki_migration(
            self.root, project_context_update.DEFAULT_DOC, "update"
        )
        persisted = json.loads(metadata_path.read_text(encoding="utf-8"))
        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(result["moves"], {})
        self.assertEqual(result["created_indexes"], [])
        self.assertEqual(persisted["schema_version"], 2)
        self.assertEqual(persisted["pages"], [project_context_update.DEFAULT_DOC])
        self.assertEqual(persisted["indexes"], [])
        self.assertFalse((self.root / "docs" / "project-context" / "index.md").exists())
        self.assertEqual(code, 0, (messages, warnings))

    def test_legacy_wiki_migration_rejects_destination_collision(self):
        self.write_legacy_multi_context()
        collision = self.root / "docs" / "project-context" / "architecture" / "overview.md"
        collision.parent.mkdir()
        collision.write_text("do not overwrite\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "migration destination already exists"):
            project_context_update.build_wiki_migration(
                self.root, project_context_update.DEFAULT_DOC
            )

        self.assertEqual(collision.read_text(encoding="utf-8"), "do not overwrite\n")

    def test_wiki_migration_rejects_unknown_future_schema(self):
        self.write_context()
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["schema_version"] = 3
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "unsupported.*schema_version: 3"):
            project_context_update.build_wiki_migration(
                self.root, project_context_update.DEFAULT_DOC
            )

    def test_sync_index_requires_complete_subpage_metadata(self):
        self.write_multi_context()
        workflow_path = self.root / "docs" / "project-context" / "workflows" / "overview.md"
        workflow_path.write_text(
            workflow_path.read_text(encoding="utf-8").replace(
                "read_when: 실행 흐름의 구현 근거 확인\n", ""
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "missing context metadata: read_when"):
            project_context_update.sync_context_index(
                self.root, project_context_update.DEFAULT_DOC
            )

    def test_sync_index_rejects_dirty_source_before_writing(self):
        context = self.write_multi_context()
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        architecture = (
            self.root
            / "docs"
            / "project-context"
            / "architecture"
            / "overview.md"
        )
        architecture.write_text(
            architecture.read_text(encoding="utf-8").replace(
                "description: 모듈 구조와 진입점 상세",
                "description: 모듈 경계와 애플리케이션 진입점 상세",
            ),
            encoding="utf-8",
        )
        architecture_index = (
            self.root / "docs/project-context/architecture/index.md"
        )
        original_home = context.read_bytes()
        original_index = architecture_index.read_bytes()
        (self.root / "app.py").write_text("print('dirty')\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "dirty source worktree changes"):
            project_context_update.sync_context_index(
                self.root, project_context_update.DEFAULT_DOC
            )

        self.assertEqual(context.read_bytes(), original_home)
        self.assertEqual(architecture_index.read_bytes(), original_index)

    def test_sync_index_allows_dirty_source_when_nothing_would_change(self):
        self.write_multi_context()
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        (self.root / "app.py").write_text("print('dirty')\n", encoding="utf-8")

        result = project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )

        self.assertFalse(result["changed"])

    def test_sync_index_rolls_back_partial_index_writes(self):
        context = self.write_multi_context()
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        architecture = (
            self.root
            / "docs"
            / "project-context"
            / "architecture"
            / "overview.md"
        )
        workflows = (
            self.root
            / "docs"
            / "project-context"
            / "workflows"
            / "overview.md"
        )
        architecture.write_text(
            architecture.read_text(encoding="utf-8").replace(
                "description: 모듈 구조와 진입점 상세",
                "description: 모듈 경계와 애플리케이션 진입점 상세",
            ),
            encoding="utf-8",
        )
        workflows.write_text(
            workflows.read_text(encoding="utf-8").replace(
                "description: 주요 실행 흐름 상세",
                "description: 주요 실행·복구 흐름 상세",
            ),
            encoding="utf-8",
        )
        index_paths = [
            context,
            self.root / "docs/project-context/architecture/index.md",
            self.root / "docs/project-context/workflows/index.md",
        ]
        originals = {path: path.read_bytes() for path in index_paths}
        atomic_write_text = project_context_update.atomic_write_text
        write_count = 0

        def fail_second_write(path, markdown):
            nonlocal write_count
            write_count += 1
            if write_count == 2:
                raise OSError("forced index write failure")
            atomic_write_text(path, markdown)

        with mock.patch.object(
            project_context_update,
            "atomic_write_text",
            side_effect=fail_second_write,
        ):
            with self.assertRaisesRegex(OSError, "forced index write failure"):
                project_context_update.sync_context_index(
                    self.root, project_context_update.DEFAULT_DOC
                )

        self.assertGreaterEqual(write_count, 2)
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_validator_detects_stale_deterministic_index(self):
        self.write_multi_context()
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        architecture_path = self.root / "docs" / "project-context" / "architecture" / "overview.md"
        architecture_path.write_text(
            architecture_path.read_text(encoding="utf-8").replace(
                "description: 모듈 구조와 진입점 상세",
                "description: 모듈 경계와 애플리케이션 진입점 상세",
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

    def test_validator_rejects_project_context_documents_ignored_by_git(self):
        self.write_context()
        self.record_and_commit_context("docs: add project context")
        (self.root / ".gitignore").write_text("docs/\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "ignore docs")

        code, messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertTrue(any("ignored by Git" in message for message in messages))

    def test_validator_rejects_ignored_agent_entrypoint(self):
        (self.root / ".gitignore").write_text("AGENTS.md\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "ignore agent entrypoint")
        self.write_context()
        self.record()

        code, messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertTrue(any("ignored by Git" in message for message in messages))

    def test_plan_does_not_call_a_committed_stale_index_no_op(self):
        self.write_multi_context()
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        self.record()
        self.git("add", "AGENTS.md", "docs")
        self.git("commit", "-m", "docs: add multi-page context")
        architecture = self.root / "docs" / "project-context" / "architecture" / "overview.md"
        architecture.write_text(
            architecture.read_text(encoding="utf-8").replace(
                "description: 모듈 구조와 진입점 상세",
                "description: 모듈 경계와 애플리케이션 진입점 상세",
            ),
            encoding="utf-8",
        )
        self.git("add", "docs/project-context/architecture/overview.md")
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
            "docs/project-context/architecture/overview.md",
            plan["generated_context_doc_changes"],
        )
        self.assertIn(
            project_context_update.DEFAULT_DOC,
            plan["generated_context_doc_changes"],
        )

    def test_sync_index_requires_exact_marker_pair(self):
        context = self.write_multi_context()
        missing_index = (
            self.root / "docs" / "project-context" / "workflows" / "index.md"
        )
        missing_index.unlink()
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

        self.assertFalse(missing_index.exists())

    def test_sync_index_inserts_missing_home_marker_for_multi_page_init(self):
        context = self.write_multi_context()
        for index_path in (
            self.root / "docs" / "project-context"
        ).glob("*/index.md"):
            index_path.unlink()
        context.write_text(
            context.read_text(encoding="utf-8")
            .replace("<!-- project-context:index:start -->\n", "")
            .replace("<!-- project-context:index:end -->\n", ""),
            encoding="utf-8",
        )

        result = project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )

        home = context.read_text(encoding="utf-8")
        self.assertEqual(home.count("<!-- project-context:index:start -->"), 1)
        self.assertEqual(home.count("<!-- project-context:index:end -->"), 1)
        self.assertEqual(
            result["created_indexes"],
            [
                "docs/project-context/architecture/index.md",
                "docs/project-context/workflows/index.md",
            ],
        )
        self.assertTrue(
            (self.root / "docs/project-context/architecture/index.md").is_file()
        )
        self.assertTrue(
            (self.root / "docs/project-context/workflows/index.md").is_file()
        )
        architecture_index = (
            self.root / "docs/project-context/architecture/index.md"
        ).read_text(encoding="utf-8")
        workflows_index = (
            self.root / "docs/project-context/workflows/index.md"
        ).read_text(encoding="utf-8")
        self.assertIn("title: 아키텍처", architecture_index)
        self.assertIn("# 아키텍처", architecture_index)
        self.assertIn("title: 워크플로", workflows_index)
        self.assertIn("# 워크플로", workflows_index)

    def test_sync_index_removes_home_marker_after_last_concept_is_deleted(self):
        context = self.write_multi_context()
        project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )
        shutil.rmtree(self.root / project_context_update.DEFAULT_DOC_DIR)
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "mode: multi-page", "mode: single-page"
            ),
            encoding="utf-8",
        )
        docs = validate_project_context.discover_docs(
            self.root, validate_project_context.DEFAULT_DOC
        )

        stale_errors, _ = (
            validate_project_context.validate_deterministic_context_index(
                self.root, validate_project_context.DEFAULT_DOC, docs
            )
        )
        result = project_context_update.sync_context_index(
            self.root, project_context_update.DEFAULT_DOC
        )

        markdown = context.read_text(encoding="utf-8")
        self.assertTrue(
            any("home-only wiki must not contain" in error for error in stale_errors)
        )
        self.assertTrue(result["changed"])
        self.assertFalse(result["skipped"])
        self.assertEqual(result["changed_docs"], [project_context_update.DEFAULT_DOC])
        self.assertNotIn("<!-- project-context:index:start -->", markdown)
        self.assertNotIn("<!-- project-context:index:end -->", markdown)

    def test_sync_index_rejects_duplicate_concept_titles_across_areas(self):
        self.write_multi_context()
        workflows = (
            self.root / "docs" / "project-context" / "workflows" / "overview.md"
        )
        workflows.write_text(
            workflows.read_text(encoding="utf-8").replace(
                "title: Workflow Overview", "title: Architecture Overview"
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "duplicate concept title"):
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

        self.assertTrue(
            any("split into indexed concept pages" in error for error in single_errors)
        )
        self.assertEqual(single_warnings, [])
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
        metadata.pop("pages")
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        code, messages, warnings = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertTrue(any("missing content_hash" in message for message in messages))
        self.assertTrue(any("pages must be a string list" in message for message in messages))

    def test_primary_updated_at_requires_utc_millisecond_timestamp(self):
        context = self.write_context()
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "updated_at: 2026-07-20T00:00:00.000Z",
                "updated_at: 2026-07-22Tgarbage",
            ),
            encoding="utf-8",
        )
        self.record()

        code, messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertTrue(
            any("updated_at must be a UTC millisecond timestamp" in message for message in messages)
        )

    def test_updated_at_requires_a_real_utc_datetime(self):
        context = self.write_context()
        context.write_text(
            context.read_text(encoding="utf-8").replace(
                "updated_at: 2026-07-20T00:00:00.000Z",
                "updated_at: 2026-99-99T99:99:99.999Z",
            ),
            encoding="utf-8",
        )
        self.record()
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["updated_at"] = "2026-99-99T99:99:99.999Z"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        code, messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertEqual(
            sum(
                "updated_at must be a UTC millisecond timestamp" in message
                for message in messages
            ),
            2,
        )

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
        self.assertEqual(plan["previous_commit"], self.git("rev-parse", "HEAD"))

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
        self.git("add", "AGENTS.md")
        self.git("commit", "-m", "docs: add custom agent rules")

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

    def test_cli_entrypoints_do_not_write_bytecode_into_skill_tree(self):
        copied_scripts = self.root.parent / "copied-scripts"
        shutil.copytree(
            SCRIPT_ROOT,
            copied_scripts,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        env = os.environ.copy()
        env.pop("PYTHONDONTWRITEBYTECODE", None)

        for script in (
            "project_context_update.py",
            "project_context_agents.py",
            "validate_project_context.py",
        ):
            source = (copied_scripts / script).read_text(encoding="utf-8")
            self.assertIn(
                "from __future__ import annotations",
                source.splitlines()[:3],
            )
            completed = subprocess.run(
                [sys.executable, str(copied_scripts / script), "--help"],
                cwd=self.root,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

        self.assertEqual(list(copied_scripts.rglob("*.pyc")), [])
        self.assertEqual(list(copied_scripts.rglob("__pycache__")), [])

    def test_skill_router_delegates_commands_to_single_workflow_reference(self):
        skill_root = SCRIPT_ROOT.parent
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        workflow = (skill_root / "references" / "update-workflow.md").read_text(
            encoding="utf-8"
        )
        authoring = (skill_root / "references" / "authoring.md").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("project_context_update.py", skill)
        self.assertNotIn("project_context_agents.py", skill)
        self.assertIn("project_context_update.py snapshot", workflow)
        self.assertIn("project_context_update.py finalize", workflow)
        self.assertIn("`_plan.md`나 문서를 만들기 전에", workflow)
        self.assertIn("홈의 `source_commit`만", workflow)
        self.assertNotIn("홈·concept의 `source_commit`", workflow)
        for heading in (
            "## 프로젝트 요약",
            "## 변경 판단",
            "## 검증 방법",
            "## 주요 흐름",
        ):
            self.assertIn(f"`{heading}`", authoring)
        self.assertNotIn("정확한 표제어는 문맥에 맞게", authoring)

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
        self.assertIs(
            project_context_update.iter_relative_links,
            validate_project_context.iter_relative_links,
        )
        self.assertEqual(
            validate_project_context.is_semantically_current_agent_section.__module__,
            "project_context_agents",
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

    def test_record_repairs_derived_metadata_without_trusting_invalid_hash(self):
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
                "schema_version": 1,
                "pages": [],
                "indexes": ["docs/wrong/index.md"],
                "doc_sources": {},
                "doc_hashes": {},
                "unmapped_resolutions": "invalid",
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

        self.assertFalse(result.get("review_only", False))
        self.assertEqual(persisted["generator"], project_context_update.GENERATOR)
        self.assertEqual(
            persisted["generator_version"], project_context_update.GENERATOR_VERSION
        )
        self.assertEqual(persisted["run_mode"], "update")
        self.assertEqual(persisted["schema_version"], 2)
        inventory = project_context_update.wiki_inventory(
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
            project_context_update.DEFAULT_DOC,
        )
        self.assertEqual(
            persisted["pages"],
            inventory["pages"],
        )
        self.assertEqual(persisted["indexes"], inventory["indexes"])
        self.assertEqual(
            persisted["doc_sources"],
            project_context_update.collect_doc_sources(
                self.root, persisted["pages"]
            ),
        )
        self.assertEqual(
            persisted["doc_hashes"],
            project_context_update.page_content_hashes(
                self.root, persisted["pages"]
            ),
        )
        self.assertEqual(persisted["unmapped_resolutions"], [])
        self.assertEqual(persisted["content_hash"], before_hash)
        self.assertEqual(code, 0, (messages, warnings))

    def test_update_cli_rejects_managed_path_overrides_without_mutation(self):
        self.write_context()
        readme = self.root / "README.md"
        package_json = self.root / "package.json"
        package_json.write_text('{"private": true}\n', encoding="utf-8")
        original_readme = readme.read_text(encoding="utf-8")
        original_package_json = package_json.read_text(encoding="utf-8")

        cases = (
            ("write-plan", "--plan-path", "README.md"),
            ("delete-plan", "--plan-path", "README.md"),
            ("record", "--metadata", "package.json"),
            ("sync-index", "--doc", "README.md"),
        )
        for command, option, value in cases:
            with self.subTest(command=command, option=option):
                completed = self.run_script(
                    "project_context_update.py",
                    command,
                    self.root,
                    option,
                    value,
                )
                self.assertEqual(completed.returncode, 2, completed.stderr)

        self.assertEqual(readme.read_text(encoding="utf-8"), original_readme)
        self.assertEqual(
            package_json.read_text(encoding="utf-8"), original_package_json
        )

    def test_finalize_cli_validates_and_reports_noop(self):
        self.write_context()
        self.record()
        before_hash = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        completed = self.run_script(
            "project_context_update.py",
            "finalize",
            self.root,
            "--mode",
            "update",
            "--if-changed",
            "--before-hash",
            before_hash,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            "project context finalized: metadata unchanged", completed.stdout
        )

    def test_validator_cli_rejects_primary_doc_override(self):
        completed = self.run_script(
            "validate_project_context.py",
            self.root,
            "--doc",
            "README.md",
        )

        self.assertEqual(completed.returncode, 2, completed.stderr)

    def test_validator_rejects_nested_git_directory(self):
        nested = self.root / "nested"
        nested.mkdir()

        code, messages, _ = validate_project_context.validate(
            nested, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertTrue(any("Git top-level" in message for message in messages))

    def test_managed_write_helpers_reject_non_contract_paths(self):
        self.write_context()

        with self.assertRaisesRegex(ValueError, "must be docs/project-context/_plan.md"):
            project_context_update.write_temp_plan(
                self.root, "README.md", {"docs": []}
            )
        with self.assertRaisesRegex(ValueError, "must be docs/project-context/_plan.md"):
            project_context_update.delete_temp_plan(self.root, "README.md")
        with self.assertRaisesRegex(
            ValueError, "must be docs/project-context/.metadata.json"
        ):
            project_context_update.record_metadata(
                self.root,
                project_context_update.DEFAULT_DOC,
                "package.json",
                "update",
                False,
                None,
            )

    def test_delete_plan_rejects_non_project_context_content(self):
        plan_path = self.root / project_context_update.DEFAULT_TEMP_PLAN
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text("# User notes\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "non-project-context plan"):
            project_context_update.delete_temp_plan(
                self.root, project_context_update.DEFAULT_TEMP_PLAN
            )

        self.assertTrue(plan_path.is_file())
        self.assertEqual(plan_path.read_text(encoding="utf-8"), "# User notes\n")

    def test_write_plan_rejects_non_project_context_content(self):
        plan_path = self.root / project_context_update.DEFAULT_TEMP_PLAN
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text("# User notes\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "non-project-context plan"):
            project_context_update.write_temp_plan(
                self.root,
                project_context_update.DEFAULT_TEMP_PLAN,
                {"docs": []},
            )

        self.assertEqual(plan_path.read_text(encoding="utf-8"), "# User notes\n")

    def test_write_plan_rejects_ignored_context_paths_before_writing(self):
        (self.root / ".gitignore").write_text("docs/\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "ignore docs")
        plan_path = self.root / project_context_update.DEFAULT_TEMP_PLAN

        with self.assertRaisesRegex(ValueError, "ignored by Git"):
            project_context_update.write_temp_plan(
                self.root,
                project_context_update.DEFAULT_TEMP_PLAN,
                {"recommended_action": "create-docs", "docs": []},
            )

        self.assertFalse(plan_path.exists())
        self.assertFalse((self.root / "docs").exists())

    def test_write_and_delete_plan_accept_legacy_english_sentinel(self):
        plan_path = self.root / project_context_update.DEFAULT_TEMP_PLAN
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text("# Project Context Draft Plan\nlegacy\n", encoding="utf-8")

        project_context_update.write_temp_plan(
            self.root,
            project_context_update.DEFAULT_TEMP_PLAN,
            {"recommended_action": "no-op", "docs": []},
        )

        self.assertTrue(
            plan_path.read_text(encoding="utf-8").startswith(
                "# 프로젝트 컨텍스트 임시 계획\n"
            )
        )
        _, deleted = project_context_update.delete_temp_plan(
            self.root, project_context_update.DEFAULT_TEMP_PLAN
        )
        self.assertTrue(deleted)
        self.assertFalse(plan_path.exists())

    def test_agent_helper_rejects_nested_git_directory_before_writing(self):
        nested = self.root / "nested"
        nested.mkdir()

        completed = self.run_script(
            "project_context_agents.py",
            nested,
            cwd=nested,
        )

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("Git top-level", completed.stderr)
        self.assertFalse((nested / "AGENTS.md").exists())

    def test_agent_helper_rejects_ignored_entrypoint_before_writing(self):
        (self.root / ".gitignore").write_text("AGENTS.md\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "ignore agent entrypoint")

        completed = self.run_script("project_context_agents.py", self.root)

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("ignored by Git", completed.stderr)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_agent_helper_rejects_symlink_target_before_other_writes(self):
        outside = self.root.parent / "outside-agents.md"
        outside.write_text("outside\n", encoding="utf-8")
        (self.root / "CLAUDE.md").symlink_to(outside)

        with self.assertRaisesRegex(ValueError, "CLAUDE.md must not be a symlink"):
            project_context_agents.ensure_agent_files(self.root)

        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")

    def test_supporting_doc_symlink_is_an_error(self):
        self.write_multi_context()
        outside = self.root.parent / "outside-context.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        symlink = self.root / "docs" / "project-context" / "linked.md"
        symlink.symlink_to(outside)

        with self.assertRaisesRegex(ValueError, "must not contain symlinks"):
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            )
        code, messages, _ = validate_project_context.validate(
            self.root, validate_project_context.DEFAULT_DOC
        )

        self.assertEqual(code, 1)
        self.assertTrue(any("must not be a symlink" in message for message in messages))

    def test_snapshot_ignores_metadata_and_temporary_plan(self):
        self.write_context()
        docs = project_context_update.discover_docs(
            self.root, project_context_update.DEFAULT_DOC
        )
        before = project_context_update.docs_content_hash(self.root, docs)
        metadata_path = self.root / project_context_update.DEFAULT_METADATA
        plan_path = self.root / project_context_update.DEFAULT_TEMP_PLAN
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text('{"changed": true}\n', encoding="utf-8")
        plan_path.write_text("# Project Context Draft Plan\nchanged\n", encoding="utf-8")

        after = project_context_update.docs_content_hash(
            self.root,
            project_context_update.discover_docs(
                self.root, project_context_update.DEFAULT_DOC
            ),
        )

        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
