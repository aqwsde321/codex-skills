import io
import json
import tempfile
import unittest
from pathlib import Path

from tools import migrate_project_context


PROJECT_BLOCK = """before

<!-- project-context:start -->
## Project Context
generated
<!-- project-context:end -->

after
"""


class MigrateProjectContextTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "repo"
        (self.root / ".git").mkdir(parents=True)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_dry_run_does_not_change_files(self):
        agents = self.root / "AGENTS.md"
        agents.write_text(PROJECT_BLOCK, encoding="utf-8")
        context = self.root / "docs/project-context.md"
        context.parent.mkdir()
        context.write_text("context\n", encoding="utf-8")
        output = io.StringIO()

        result = migrate_project_context.run([self.root], output=output)

        self.assertEqual(result, 0)
        self.assertEqual(agents.read_text(encoding="utf-8"), PROJECT_BLOCK)
        self.assertTrue(context.exists())
        self.assertIn("DRY-RUN", output.getvalue())

    def test_apply_archives_artifacts_and_removes_both_marker_types(self):
        agents = self.root / "AGENTS.md"
        agents.write_text(
            PROJECT_BLOCK
            + "\n<!-- codebase-memory-mcp:start -->\nold cmm\n<!-- codebase-memory-mcp:end -->\n",
            encoding="utf-8",
        )
        context = self.root / "docs/project-context.md"
        context.parent.mkdir()
        context.write_text("context\n", encoding="utf-8")
        metadata = self.root / "docs/project-context/.metadata.json"
        metadata.parent.mkdir()
        metadata.write_text("{}\n", encoding="utf-8")
        database = self.root / ".codebase-memory/graph.db"
        database.parent.mkdir()
        database.write_text("graph\n", encoding="utf-8")
        backup = Path(self.temporary_directory.name) / "backup"

        result = migrate_project_context.run(
            [self.root], apply=True, backup_root=backup, output=io.StringIO()
        )

        self.assertEqual(result, 0)
        updated = agents.read_text(encoding="utf-8")
        self.assertEqual(updated, "before\n\nafter\n")
        self.assertFalse(context.exists())
        self.assertFalse(metadata.exists())
        self.assertFalse(database.exists())
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        repo_backup = Path(manifest["repositories"][0]["backup"])
        self.assertTrue((repo_backup / "artifacts/docs/project-context.md").is_file())
        self.assertTrue((repo_backup / "artifacts/docs/project-context/.metadata.json").is_file())
        self.assertTrue((repo_backup / "artifacts/.codebase-memory/graph.db").is_file())
        self.assertEqual(
            (repo_backup / "instructions/AGENTS.md").read_text(encoding="utf-8"),
            PROJECT_BLOCK
            + "\n<!-- codebase-memory-mcp:start -->\nold cmm\n<!-- codebase-memory-mcp:end -->\n",
        )

    def test_malformed_marker_aborts_before_changes(self):
        agents = self.root / "AGENTS.md"
        agents.write_text("<!-- project-context:start -->\nmissing end\n", encoding="utf-8")
        context = self.root / "docs/project-context.md"
        context.parent.mkdir()
        context.write_text("context\n", encoding="utf-8")
        output = io.StringIO()

        result = migrate_project_context.run(
            [self.root],
            apply=True,
            backup_root=Path(self.temporary_directory.name) / "backup",
            output=output,
        )

        self.assertEqual(result, 2)
        self.assertTrue(context.exists())
        self.assertIn("missing marker end", output.getvalue())

    def test_symlink_artifact_is_refused(self):
        target = Path(self.temporary_directory.name) / "outside.md"
        target.write_text("keep\n", encoding="utf-8")
        docs = self.root / "docs"
        docs.mkdir()
        (docs / "project-context.md").symlink_to(target)

        result = migrate_project_context.run([self.root], output=io.StringIO())

        self.assertEqual(result, 2)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep\n")

    def test_symlink_parent_is_refused(self):
        outside = Path(self.temporary_directory.name) / "outside"
        outside.mkdir()
        context = outside / "project-context.md"
        context.write_text("keep\n", encoding="utf-8")
        (self.root / "docs").symlink_to(outside)

        result = migrate_project_context.run([self.root], output=io.StringIO())

        self.assertEqual(result, 2)
        self.assertEqual(context.read_text(encoding="utf-8"), "keep\n")

    def test_apply_preserves_openwiki_and_codegraph_and_is_idempotent(self):
        agents = self.root / "AGENTS.md"
        agents.write_text(PROJECT_BLOCK, encoding="utf-8")
        openwiki = self.root / "openwiki/index.md"
        openwiki.parent.mkdir()
        openwiki.write_text("wiki\n", encoding="utf-8")
        codegraph = self.root / ".codegraph/index.db"
        codegraph.parent.mkdir()
        codegraph.write_text("graph\n", encoding="utf-8")
        backup = Path(self.temporary_directory.name) / "backup"

        first = migrate_project_context.run(
            [self.root], apply=True, backup_root=backup, output=io.StringIO()
        )
        second = migrate_project_context.run(
            [self.root], apply=True, output=io.StringIO()
        )

        self.assertEqual(first, 0)
        self.assertEqual(second, 0)
        self.assertEqual(openwiki.read_text(encoding="utf-8"), "wiki\n")
        self.assertEqual(codegraph.read_text(encoding="utf-8"), "graph\n")


if __name__ == "__main__":
    unittest.main()
