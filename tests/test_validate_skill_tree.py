import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPOSITORY_ROOT / "skills" / "skill-quality-review" / "scripts" / "validate_skill_tree.py"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
OFFICIAL_VALIDATOR = CODEX_HOME / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"


def line_number_containing(path: Path, needle: str) -> int:
    return next(
        line_number
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        )
        if needle in line
    )


class ValidateSkillTreeTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        if OFFICIAL_VALIDATOR.is_file():
            self.quick_validator = OFFICIAL_VALIDATOR
        else:
            self.quick_validator = self.root / "quick_validate.py"
            self.quick_validator.write_text(
                """import re
import sys
import yaml
from pathlib import Path

content = (Path(sys.argv[1]) / "SKILL.md").read_text(encoding="utf-8")
match = re.match(r"^---\\n(.*?)\\n---", content, re.DOTALL)
try:
    data = yaml.safe_load(match.group(1)) if match else None
except yaml.YAMLError as error:
    print(f"Invalid YAML in frontmatter: {error}")
    raise SystemExit(1)
if not isinstance(data, dict) or not data.get("name") or not data.get("description"):
    print("Invalid frontmatter")
    raise SystemExit(1)
print("Skill is valid!")
""",
                encoding="utf-8",
            )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def make_skill(self, folder="valid-skill", name=None, body=""):
        skill_dir = self.root / folder
        (skill_dir / "agents").mkdir(parents=True)
        (skill_dir / "references").mkdir()
        skill_name = name or folder
        frontmatter = json.dumps(
            {"name": skill_name, "description": "Validate one example skill"}
        )
        (skill_dir / "SKILL.md").write_text(
            f"---\n{frontmatter}\n---\n\n# Example\n\n{body}", encoding="utf-8"
        )
        metadata = {
            "interface": {
                "display_name": "Valid Skill",
                "short_description": "Validate one example skill tree",
                "default_prompt": f"Use ${skill_name} to validate this example.",
            },
            "policy": {"allow_implicit_invocation": False},
        }
        (skill_dir / "agents" / "openai.yaml").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        return skill_dir

    def run_validator(
        self,
        skill_dir,
        *extra,
        isolated_python=False,
        environment=None,
    ):
        if isolated_python:
            command = [sys.executable, "-S"]
        else:
            command = [shutil.which("uv") or "uv", "run", "--script"]
        command.extend(
            [
                str(VALIDATOR),
                str(skill_dir),
                "--quick-validator",
                str(self.quick_validator),
                "--json",
                *extra,
            ]
        )
        run_environment = os.environ.copy()
        if isolated_python:
            run_environment.pop("PYTHONPATH", None)
        if environment:
            run_environment.update(environment)
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env=run_environment,
        )
        return completed, json.loads(completed.stdout)

    def test_valid_skill_passes(self):
        skill_dir = self.make_skill(body="[Reference](references/info.md)\n")
        (skill_dir / "references" / "info.md").write_text("# Info\n", encoding="utf-8")

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["status"], "pass")
        self.assertTrue(payload["complete"])

    def test_detects_folder_name_mismatch(self):
        skill_dir = self.make_skill(folder="wrong-folder", name="declared-name")

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["folder_name"]["status"], "fail")

    def test_rejects_external_skill_md_before_running_the_official_validator(self):
        skill_dir = self.make_skill(folder="external-skill-md")
        skill_md = skill_dir / "SKILL.md"
        external = self.root / "outside-SKILL.md"
        external.write_text(skill_md.read_text(encoding="utf-8"), encoding="utf-8")
        skill_md.unlink()
        skill_md.symlink_to(external)
        sentinel = self.root / "official-validator-ran"
        tripwire = self.root / "tripwire-validator.py"
        tripwire.write_text(
            f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n",
            encoding="utf-8",
        )
        self.quick_validator = tripwire

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertFalse(sentinel.exists())
        self.assertEqual(
            payload["checks"]["official_validator"]["status"], "not_checked"
        )
        self.assertEqual(payload["checks"]["folder_name"]["status"], "fail")

    def test_detects_invalid_skill_frontmatter_yaml(self):
        skill_dir = self.make_skill()
        (skill_dir / "SKILL.md").write_text(
            "---\n{invalid\n---\n\n# Invalid\n", encoding="utf-8"
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertFalse(payload["complete"])
        self.assertEqual(payload["checks"]["official_validator"]["status"], "fail")

    def test_reports_non_utf8_files_as_structured_failures(self):
        cases = []

        invalid_skill = self.make_skill(folder="non-utf8-skill")
        (invalid_skill / "SKILL.md").write_bytes(b"\xff")
        cases.append((invalid_skill, "folder_name"))

        invalid_markdown = self.make_skill(folder="non-utf8-markdown")
        (invalid_markdown / "references" / "bad.md").write_bytes(b"\xff")
        cases.append((invalid_markdown, "markdown_links"))

        invalid_agents = self.make_skill(folder="non-utf8-agents")
        (invalid_agents / "agents" / "openai.yaml").write_bytes(b"\xff")
        cases.append((invalid_agents, "agents_metadata"))

        for skill_dir, check in cases:
            with self.subTest(check=check):
                completed, payload = self.run_validator(skill_dir)

                self.assertEqual(completed.returncode, 1)
                self.assertEqual(payload["status"], "fail")
                self.assertEqual(payload["checks"][check]["status"], "fail")

    def test_detects_invalid_agents_yaml_and_invocation_policy(self):
        invalid_yaml = self.make_skill(folder="invalid-agents")
        (invalid_yaml / "agents" / "openai.yaml").write_text("{invalid", encoding="utf-8")
        invalid_policy = self.make_skill(folder="invalid-policy")
        metadata_path = invalid_policy / "agents" / "openai.yaml"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["policy"]["allow_implicit_invocation"] = "false"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        yaml_completed, yaml_payload = self.run_validator(invalid_yaml)
        policy_completed, policy_payload = self.run_validator(invalid_policy)

        self.assertEqual(yaml_completed.returncode, 1)
        self.assertEqual(yaml_payload["checks"]["agents_metadata"]["status"], "fail")
        self.assertEqual(policy_completed.returncode, 1)
        self.assertEqual(policy_payload["checks"]["agents_metadata"]["status"], "fail")

    def test_rejects_external_agents_metadata_symlink(self):
        skill_dir = self.make_skill(folder="external-agents-metadata")
        metadata_path = skill_dir / "agents" / "openai.yaml"
        external = self.root / "outside-openai.yaml"
        external.write_text(
            metadata_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        metadata_path.unlink()
        metadata_path.symlink_to(external)

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["agents_metadata"]["status"], "fail")
        messages = [
            detail["message"]
            for detail in payload["checks"]["agents_metadata"]["details"]
        ]
        self.assertTrue(any("leaves the skill boundary" in message for message in messages))

    def test_rejects_dangling_agents_metadata_symlink(self):
        skill_dir = self.make_skill(folder="dangling-agents-metadata")
        metadata_path = skill_dir / "agents" / "openai.yaml"
        metadata_path.unlink()
        metadata_path.symlink_to("missing-openai.yaml")

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["agents_metadata"]["status"], "fail")

    def test_detects_invalid_optional_mcp_metadata_types(self):
        for key, invalid_value in (
            ("description", []),
            ("transport", 42),
            ("url", {}),
        ):
            with self.subTest(key=key):
                skill_dir = self.make_skill(folder=f"invalid-mcp-{key}")
                metadata_path = skill_dir / "agents" / "openai.yaml"
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata["dependencies"] = {
                    "tools": [
                        {
                            "type": "mcp",
                            "value": "example-mcp",
                            key: invalid_value,
                        }
                    ]
                }
                metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

                completed, payload = self.run_validator(
                    skill_dir, "--available-mcp", "example-mcp"
                )

                self.assertEqual(completed.returncode, 1)
                self.assertEqual(
                    payload["checks"]["agents_metadata"]["status"], "fail"
                )
                messages = [
                    detail["message"]
                    for detail in payload["checks"]["agents_metadata"]["details"]
                ]
                self.assertTrue(any(key in message for message in messages))

    def test_rejects_whitespace_only_mcp_dependency_identifier(self):
        skill_dir = self.make_skill(folder="whitespace-mcp")
        metadata_path = skill_dir / "agents" / "openai.yaml"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["dependencies"] = {
            "tools": [{"type": "mcp", "value": "   "}]
        }
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        completed, payload = self.run_validator(
            skill_dir, "--available-mcp", "   "
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["agents_metadata"]["status"], "fail")

    def test_detects_broken_markdown_link(self):
        skill_dir = self.make_skill(body="[Missing](references/missing.md)\n")

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_detects_broken_link_inside_image_alt(self):
        skill_dir = self.make_skill(
            folder="link-inside-image-alt",
            body="![[alt](references/missing.md)](image.png)\n",
        )
        (skill_dir / "image.png").touch()

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        missing = [
            detail
            for detail in payload["checks"]["markdown_links"]["details"]
            if detail["message"]
            == "missing local target 'references/missing.md'"
        ]
        self.assertEqual(len(missing), 1)

    def test_detects_broken_nested_image_inside_image_alt(self):
        skill_dir = self.make_skill(
            folder="nested-image-inside-image-alt",
            body=(
                "prefix\n"
                "![outer\n"
                "text ![nested](missing.png)](outer.png)\n"
            ),
        )
        (skill_dir / "outer.png").touch()
        skill_md = skill_dir / "SKILL.md"
        expected_line = line_number_containing(skill_md, "missing.png")

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        missing = [
            detail
            for detail in payload["checks"]["markdown_links"]["details"]
            if detail["message"] == "missing local target 'missing.png'"
        ]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["location"], f"{skill_md.resolve()}:{expected_line}")

    def test_reports_the_source_line_for_a_link_inside_multiline_image_alt(self):
        skill_dir = self.make_skill(
            folder="multiline-link-inside-image-alt",
            body=(
                "prefix\n"
                "![alt\n"
                "text [link](references/missing.md)](image.png)\n"
            ),
        )
        (skill_dir / "image.png").touch()
        skill_md = skill_dir / "SKILL.md"
        expected_line = line_number_containing(
            skill_md, "references/missing.md"
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        missing = [
            detail
            for detail in payload["checks"]["markdown_links"]["details"]
            if detail["message"]
            == "missing local target 'references/missing.md'"
        ]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["location"], f"{skill_md.resolve()}:{expected_line}")

    def test_ignores_link_syntax_inside_skill_frontmatter(self):
        skill_dir = self.make_skill(folder="frontmatter-link")
        frontmatter = json.dumps(
            {
                "name": "frontmatter-link",
                "description": "Review [text](missing.md) syntax",
            }
        )
        (skill_dir / "SKILL.md").write_text(
            f"---\n{frontmatter}\n---\n\n# Body\n", encoding="utf-8"
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_detects_broken_link_after_four_space_indented_backticks(self):
        skill_dir = self.make_skill(
            folder="indented-backticks",
            body=(
                "    ```\n"
                "[Missing](references/missing.md)\n"
                "    ```\n"
            ),
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_code_span_does_not_cross_an_atx_heading_boundary(self):
        skill_dir = self.make_skill(
            folder="heading-code-span",
            body="`open\n# [Missing](references/missing.md)\n`\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_ignores_link_inside_three_space_indented_fence(self):
        skill_dir = self.make_skill(
            folder="valid-indented-fence",
            body=(
                "   ```\n"
                "[Literal](references/not-a-link.md)\n"
                "   ```\n"
            ),
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_ignores_link_inside_blockquote_fence(self):
        skill_dir = self.make_skill(
            folder="blockquote-fence",
            body=(
                "> ```\n"
                "> [Literal](references/not-a-link.md)\n"
            ),
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_ignores_link_syntax_inside_html_comment(self):
        skill_dir = self.make_skill(
            folder="html-comment-link",
            body="<!-- [Literal](references/not-a-link.md) -->\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_ignores_reference_syntax_inside_raw_html_attribute(self):
        skill_dir = self.make_skill(
            folder="html-attribute-reference",
            body='<span title="[Literal][missing-reference]">ok</span>\n',
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_still_detects_missing_reference_after_raw_html(self):
        skill_dir = self.make_skill(
            folder="reference-after-html",
            body='<span title="[Literal][ignored]">ok</span> [Real][missing]\n',
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_ignores_same_html_reference_syntax_inside_code_and_raw_html(self):
        html = '<span title="[Literal][missing-reference]">'
        skill_dir = self.make_skill(
            folder="same-html-in-code",
            body=f"`{html}` {html}ok</span>\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_html_backtick_does_not_hide_a_missing_reference(self):
        skill_dir = self.make_skill(
            folder="html-backtick-before-reference",
            body='<span title="`">ok</span> [Real][missing] `\n',
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_fence_with_trailing_text_does_not_close_the_block(self):
        skill_dir = self.make_skill(
            folder="invalid-fence-close",
            body=(
                "```\n"
                "```not-a-close\n"
                "```\n"
                "[Missing](references/missing.md)\n"
            ),
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_backtick_in_info_string_does_not_open_a_fence(self):
        skill_dir = self.make_skill(
            folder="invalid-fence-open",
            body=(
                "```invalid`info\n"
                "[Missing](references/missing.md)\n"
                "```\n"
            ),
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_rejects_markdown_symlink_that_escapes_the_skill(self):
        skill_dir = self.make_skill(folder="external-markdown-symlink")
        external = self.root / "external.md"
        external.write_text("# External\n", encoding="utf-8")
        (skill_dir / "external.md").symlink_to(external)

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")
        messages = [
            detail["message"]
            for detail in payload["checks"]["markdown_links"]["details"]
        ]
        self.assertTrue(any("outside" in message for message in messages))

    def test_rejects_markdown_target_through_external_symlink_directory(self):
        skill_dir = self.make_skill(
            folder="external-markdown-directory",
            body="[Reference](references/ref.md)\n",
        )
        (skill_dir / "references").rmdir()
        external = self.root / "external-references"
        external.mkdir()
        (external / "ref.md").write_text("# External\n", encoding="utf-8")
        (skill_dir / "references").symlink_to(external, target_is_directory=True)

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_rejects_unreferenced_markdown_directory_symlink(self):
        skill_dir = self.make_skill(folder="unreferenced-symlink-directory")
        (skill_dir / "references").rmdir()
        external = self.root / "unreferenced-external-references"
        external.mkdir()
        (external / "bad.md").write_text(
            "[Missing](missing.md)\n", encoding="utf-8"
        )
        (skill_dir / "references").symlink_to(external, target_is_directory=True)

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")
        messages = [
            detail["message"]
            for detail in payload["checks"]["markdown_links"]["details"]
        ]
        self.assertTrue(any("directory symlink" in message for message in messages))

    def test_rejects_link_that_leaves_and_returns_to_the_skill(self):
        skill_dir = self.make_skill(
            folder="returning-link",
            body="[Return](hop/back/references/info.md)\n",
        )
        (skill_dir / "references" / "info.md").write_text(
            "# Info\n", encoding="utf-8"
        )
        external = self.root / "external-link-hop"
        external.mkdir()
        (skill_dir / "hop").symlink_to(external, target_is_directory=True)
        (external / "back").symlink_to(skill_dir, target_is_directory=True)

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")
        messages = [
            detail["message"]
            for detail in payload["checks"]["markdown_links"]["details"]
        ]
        self.assertTrue(any("local target leaves" in message for message in messages))

    def test_rejects_link_whose_parent_segments_hide_symlink_traversal(self):
        skill_dir = self.make_skill(
            folder="normalized-returning-link",
            body=(
                "[Return](escape/../normalized-returning-link/"
                "references/info.md)\n"
            ),
        )
        (skill_dir / "references" / "info.md").write_text(
            "# Info\n", encoding="utf-8"
        )
        external = self.root / "external-normalized-link-hop"
        external.mkdir()
        (skill_dir / "escape").symlink_to(external, target_is_directory=True)

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        messages = [
            detail["message"]
            for detail in payload["checks"]["markdown_links"]["details"]
        ]
        self.assertTrue(any("local target leaves" in message for message in messages))

    def test_allows_explicit_cross_skill_markdown_link(self):
        target = self.make_skill(folder="linked-skill")
        (target / "references" / "info.md").write_text("# Info\n", encoding="utf-8")
        skill_dir = self.make_skill(
            folder="linking-skill",
            body="[Other](../linked-skill/references/info.md)\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_handles_nested_parentheses_and_ignores_inline_code_links(self):
        skill_dir = self.make_skill(
            folder="markdown-syntax",
            body=(
                "[Nested](references/info_(v1).md)\n\n"
                "`[Literal](references/not-a-link.md)`\n"
            ),
        )
        (skill_dir / "references" / "info_(v1).md").write_text(
            "# Info\n", encoding="utf-8"
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_ignores_reference_syntax_inside_inline_link_title(self):
        skill_dir = self.make_skill(
            folder="reference-syntax-in-link-title",
            body='[Real](references/info.md "[Literal][missing-reference]")\n',
        )
        (skill_dir / "references" / "info.md").write_text(
            "# Info\n", encoding="utf-8"
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_handles_angle_bracket_destination_with_a_parenthesis(self):
        skill_dir = self.make_skill(
            folder="angle-bracket-destination",
            body="[Valid](<references/info).md>)\n",
        )
        (skill_dir / "references" / "info).md").write_text(
            "# Info\n", encoding="utf-8"
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_scans_uppercase_markdown_extensions(self):
        skill_dir = self.make_skill(folder="uppercase-markdown")
        (skill_dir / "references" / "BAD.MD").write_text(
            "[Missing](missing.md)\n", encoding="utf-8"
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_ignores_escaped_link_opening_brackets(self):
        skill_dir = self.make_skill(
            folder="escaped-markdown-syntax",
            body=(
                "\\[Literal](references/not-a-link.md)\n"
                "\\[Literal][missing-reference]\n"
            ),
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_ignores_escaped_link_closing_bracket(self):
        skill_dir = self.make_skill(
            folder="escaped-closing-bracket",
            body="[Literal\\](references/not-a-link.md)\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_detects_link_after_an_escaped_separator(self):
        skill_dir = self.make_skill(
            folder="escaped-separator-before-link",
            body="[a\\](ignored) b](references/missing.md)\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_detects_missing_full_reference_with_escaped_label_bracket(self):
        skill_dir = self.make_skill(
            folder="escaped-full-reference-label",
            body="[a\\] b][missing-reference]\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_reports_a_missing_image_reference_once(self):
        skill_dir = self.make_skill(
            folder="missing-image-reference",
            body="![alt][missing]\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        details = payload["checks"]["markdown_links"]["details"]
        missing = [
            detail
            for detail in details
            if detail["message"] == "missing reference definition '[missing]'"
        ]
        self.assertEqual(len(missing), 1)

    def test_reports_references_from_distinct_image_alt_states(self):
        skill_dir = self.make_skill(
            folder="distinct-image-alt-states",
            body="![[a][missing1]](one.png) ![[b][missing2]](two.png)\n",
        )
        (skill_dir / "one.png").touch()
        (skill_dir / "two.png").touch()

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        messages = [
            detail["message"]
            for detail in payload["checks"]["markdown_links"]["details"]
            if detail["message"].startswith("missing reference definition")
        ]
        self.assertCountEqual(
            messages,
            [
                "missing reference definition '[missing1]'",
                "missing reference definition '[missing2]'",
            ],
        )

    def test_reports_the_source_line_inside_a_multiline_image_alt(self):
        skill_dir = self.make_skill(
            folder="multiline-image-alt-location",
            body="prefix\n![alt\n[a][missing]](img.png)\n",
        )
        (skill_dir / "img.png").touch()
        skill_md = skill_dir / "SKILL.md"
        expected_line = line_number_containing(skill_md, "[a][missing]")

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        missing = [
            detail
            for detail in payload["checks"]["markdown_links"]["details"]
            if detail["message"] == "missing reference definition '[missing]'"
        ]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["location"], f"{skill_md.resolve()}:{expected_line}")

    def test_ignores_escaped_reference_definition_closing_bracket(self):
        skill_dir = self.make_skill(
            folder="escaped-reference-definition",
            body="[Literal\\]: references/not-a-link.md\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_ignores_escaped_reference_use_closing_bracket(self):
        skill_dir = self.make_skill(
            folder="escaped-reference-use",
            body="[Literal\\][missing-reference]\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_ignores_link_inside_multiline_code_span(self):
        skill_dir = self.make_skill(
            folder="multiline-code-span",
            body="`code\n[Literal](references/not-a-link.md)\n`\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_inline_code_span_does_not_cross_paragraph_boundaries(self):
        skill_dir = self.make_skill(
            folder="paragraph-code-span",
            body="`open\n\n[Missing](references/missing.md)\n\n`\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_even_backslashes_leave_a_link_opening_active(self):
        skill_dir = self.make_skill(
            folder="even-backslash-markdown-syntax",
            body="\\\\[Missing](references/missing.md)\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "fail")

    def test_ignores_link_inside_indented_code_block(self):
        skill_dir = self.make_skill(
            folder="indented-link",
            body="    [Literal](references/not-a-link.md)\n",
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["markdown_links"]["status"], "pass")

    def test_checks_executable_presence_without_running_it(self):
        skill_dir = self.make_skill()
        binary_directory = self.root / "bin"
        binary_directory.mkdir()
        sentinel = self.root / "executed"
        tripwire = binary_directory / "tripwire"
        tripwire.write_text(
            f"#!/bin/sh\ntouch '{sentinel}'\n", encoding="utf-8"
        )
        tripwire.chmod(0o755)

        completed, payload = self.run_validator(
            skill_dir,
            "--required-executable",
            "tripwire",
            environment={"PATH": f"{binary_directory}{os.pathsep}{os.environ.get('PATH', '')}"},
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["executable_dependencies"]["status"], "pass")
        self.assertFalse(sentinel.exists())

    def test_checks_required_local_file_without_running_it(self):
        skill_dir = self.make_skill(folder="required-file-skill")
        script_directory = skill_dir / "scripts"
        script_directory.mkdir()
        sentinel = self.root / "required-file-executed"
        script = script_directory / "tripwire.py"
        script.write_text(
            f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n",
            encoding="utf-8",
        )
        (self.root / "outside.py").write_text("# Outside\n", encoding="utf-8")

        present, present_payload = self.run_validator(
            skill_dir, "--required-file", "scripts/tripwire.py"
        )
        missing, missing_payload = self.run_validator(
            skill_dir, "--required-file", "scripts/missing.py"
        )
        escaping, escaping_payload = self.run_validator(
            skill_dir, "--required-file", "../outside.py"
        )

        self.assertEqual(present.returncode, 0)
        self.assertEqual(
            present_payload["checks"]["file_dependencies"]["status"], "pass"
        )
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(
            missing_payload["checks"]["file_dependencies"]["status"], "fail"
        )
        self.assertEqual(escaping.returncode, 1)
        self.assertEqual(
            escaping_payload["checks"]["file_dependencies"]["status"], "fail"
        )
        self.assertFalse(sentinel.exists())

    def test_rejects_required_file_that_leaves_and_returns_to_the_skill(self):
        skill_dir = self.make_skill(folder="returning-required-file")
        scripts = skill_dir / "scripts"
        scripts.mkdir()
        (scripts / "tool.py").write_text("# Tool\n", encoding="utf-8")
        external = self.root / "external-required-hop"
        external.mkdir()
        (scripts / "hop").symlink_to(external, target_is_directory=True)
        (external / "back").symlink_to(scripts, target_is_directory=True)

        completed, payload = self.run_validator(
            skill_dir, "--required-file", "scripts/hop/back/tool.py"
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["file_dependencies"]["status"], "fail")

    def test_rejects_required_file_with_hidden_parent_symlink_traversal(self):
        skill_dir = self.make_skill(folder="normalized-returning-required")
        scripts = skill_dir / "scripts"
        scripts.mkdir()
        (scripts / "tool.py").write_text("# Tool\n", encoding="utf-8")
        external = self.root / "external-normalized-required-hop"
        external.mkdir()
        (skill_dir / "escape").symlink_to(external, target_is_directory=True)

        completed, payload = self.run_validator(
            skill_dir,
            "--required-file",
            "escape/../normalized-returning-required/scripts/tool.py",
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["file_dependencies"]["status"], "fail")

    def test_validates_icon_paths_within_the_skill_boundary(self):
        for case in ("inside", "missing", "parent", "symlink", "returning"):
            with self.subTest(case=case):
                skill_dir = self.make_skill(folder=f"icon-{case}")
                assets = skill_dir / "assets"
                assets.mkdir()
                icon = "assets/icon.svg"
                expected_code = 0

                if case == "inside":
                    (assets / "icon.svg").write_text("<svg/>\n", encoding="utf-8")
                elif case == "missing":
                    icon = "assets/missing.svg"
                    expected_code = 1
                elif case == "parent":
                    (self.root / "outside-parent.svg").write_text(
                        "<svg/>\n", encoding="utf-8"
                    )
                    icon = "../outside-parent.svg"
                    expected_code = 1
                elif case == "symlink":
                    external = self.root / "outside-symlink.svg"
                    external.write_text("<svg/>\n", encoding="utf-8")
                    (assets / "icon.svg").symlink_to(external)
                    expected_code = 1
                else:
                    (assets / "icon.svg").write_text("<svg/>\n", encoding="utf-8")
                    external = self.root / "external-icon-hop"
                    external.mkdir()
                    (assets / "hop").symlink_to(external, target_is_directory=True)
                    (external / "back").symlink_to(assets, target_is_directory=True)
                    icon = "assets/hop/back/icon.svg"
                    expected_code = 1

                metadata_path = skill_dir / "agents" / "openai.yaml"
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata["interface"]["icon_small"] = icon
                metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

                completed, payload = self.run_validator(skill_dir)

                self.assertEqual(completed.returncode, expected_code)
                expected_status = "pass" if expected_code == 0 else "fail"
                self.assertEqual(
                    payload["checks"]["agents_metadata"]["status"],
                    expected_status,
                )

    def test_compares_declared_mcp_without_running_same_named_executable(self):
        skill_dir = self.make_skill(folder="mcp-skill")
        metadata_path = skill_dir / "agents" / "openai.yaml"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["dependencies"] = {
            "tools": [{"type": "mcp", "value": "tripwire-mcp"}]
        }
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        binary_directory = self.root / "mcp-bin"
        binary_directory.mkdir()
        sentinel = self.root / "mcp-executed"
        executable = binary_directory / "tripwire-mcp"
        executable.write_text(f"#!/bin/sh\ntouch '{sentinel}'\n", encoding="utf-8")
        executable.chmod(0o755)
        environment = {
            "PATH": f"{binary_directory}{os.pathsep}{os.environ.get('PATH', '')}"
        }

        present, present_payload = self.run_validator(
            skill_dir,
            "--available-mcp",
            "tripwire-mcp",
            environment=environment,
        )
        unresolved, unresolved_payload = self.run_validator(
            skill_dir, environment=environment
        )
        missing, missing_payload = self.run_validator(
            skill_dir, "--mcp-catalog-complete", environment=environment
        )

        self.assertEqual(present.returncode, 0)
        self.assertEqual(present_payload["checks"]["tool_dependencies"]["status"], "pass")
        self.assertEqual(unresolved.returncode, 2)
        self.assertEqual(
            unresolved_payload["checks"]["tool_dependencies"]["status"],
            "not_checked",
        )
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(missing_payload["checks"]["tool_dependencies"]["status"], "fail")
        self.assertFalse(sentinel.exists())

    def test_allowed_tools_are_permissions_not_required_dependencies(self):
        skill_dir = self.make_skill(folder="allowed-tool-skill")
        skill_path = skill_dir / "SKILL.md"
        frontmatter = json.dumps(
            {
                "name": "allowed-tool-skill",
                "description": "Validate declared tool availability",
                "allowed-tools": "tool-one",
            }
        )
        skill_path.write_text(
            f"---\n{frontmatter}\n---\n\n# Allowed tool\n", encoding="utf-8"
        )

        completed, payload = self.run_validator(skill_dir, "--tool-catalog-complete")

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["checks"]["allowed_tools"]["status"], "pass")
        self.assertEqual(payload["checks"]["tool_dependencies"]["status"], "pass")

    def test_checks_explicit_required_tool_against_the_catalog(self):
        skill_dir = self.make_skill(folder="required-tool-skill")

        present, present_payload = self.run_validator(
            skill_dir,
            "--required-tool",
            "tool-one",
            "--available-tool",
            "tool-one",
        )
        unresolved, unresolved_payload = self.run_validator(
            skill_dir,
            "--required-tool",
            "tool-one",
        )
        missing, missing_payload = self.run_validator(
            skill_dir,
            "--required-tool",
            "tool-one",
            "--tool-catalog-complete",
        )

        self.assertEqual(present.returncode, 0)
        self.assertEqual(
            present_payload["checks"]["tool_dependencies"]["status"], "pass"
        )
        self.assertEqual(unresolved.returncode, 2)
        self.assertEqual(
            unresolved_payload["checks"]["tool_dependencies"]["status"],
            "not_checked",
        )
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(
            missing_payload["checks"]["tool_dependencies"]["status"], "fail"
        )

    def test_rejects_non_string_allowed_tools(self):
        skill_dir = self.make_skill(folder="invalid-allowed-tools")
        skill_path = skill_dir / "SKILL.md"
        frontmatter = json.dumps(
            {
                "name": "invalid-allowed-tools",
                "description": "Reject invalid allowed tools",
                "allowed-tools": ["tool-one"],
            }
        )
        skill_path.write_text(
            f"---\n{frontmatter}\n---\n\n# Allowed tool\n", encoding="utf-8"
        )

        completed, payload = self.run_validator(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["checks"]["allowed_tools"]["status"], "fail")

    def test_default_prompt_requires_an_exact_skill_invocation_token(self):
        cases = (
            ("foo", "Use $foo_bar to validate."),
            ("bar", "Use $barNext to validate."),
        )
        for folder, default_prompt in cases:
            with self.subTest(default_prompt=default_prompt):
                skill_dir = self.make_skill(folder=folder)
                metadata_path = skill_dir / "agents" / "openai.yaml"
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata["interface"]["default_prompt"] = default_prompt
                metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

                completed, payload = self.run_validator(skill_dir)

                self.assertEqual(completed.returncode, 1)
                self.assertEqual(
                    payload["checks"]["agents_metadata"]["status"], "fail"
                )

    def test_mixed_failure_and_unresolved_dependency_is_incomplete(self):
        skill_dir = self.make_skill(folder="mixed-dependency-results")
        metadata_path = skill_dir / "agents" / "openai.yaml"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["dependencies"] = {
            "tools": [{"type": "mcp", "value": "unresolved-mcp"}]
        }
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        completed, payload = self.run_validator(
            skill_dir,
            "--required-tool",
            "missing-tool",
            "--tool-catalog-complete",
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertFalse(payload["complete"])
        self.assertEqual(payload["checks"]["tool_dependencies"]["status"], "fail")
        detail_statuses = {
            detail["status"]
            for detail in payload["checks"]["tool_dependencies"]["details"]
        }
        self.assertEqual(detail_statuses, {"fail", "not_checked"})

    def test_missing_yaml_parser_is_incomplete_not_pass(self):
        skill_dir = self.make_skill()

        completed, payload = self.run_validator(skill_dir, isolated_python=True)

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["status"], "incomplete")
        self.assertFalse(payload["complete"])
        self.assertEqual(payload["checks"]["yaml_parser"]["status"], "unavailable")
        self.assertEqual(
            payload["checks"]["markdown_parser"]["status"], "unavailable"
        )
        self.assertEqual(payload["checks"]["tool_dependencies"]["status"], "not_checked")

    def test_real_yaml_with_official_validator(self):
        self.assertTrue(
            OFFICIAL_VALIDATOR.is_file(),
            f"official validator is unavailable: {OFFICIAL_VALIDATOR}",
        )
        valid = self.make_skill(folder="real-yaml")
        (valid / "SKILL.md").write_text(
            "---\nname: real-yaml\ndescription: Validate a real YAML skill\n---\n\n# Real YAML\n",
            encoding="utf-8",
        )
        (valid / "agents" / "openai.yaml").write_text(
            """interface:
  display_name: "Real YAML"
  short_description: "Validate one real YAML skill tree"
  default_prompt: "Use $real-yaml to validate this example."
policy:
  allow_implicit_invocation: false
""",
            encoding="utf-8",
        )
        invalid = self.make_skill(folder="invalid-real-yaml")
        (invalid / "SKILL.md").write_text(
            "---\nname: [invalid\ndescription: broken\n---\n", encoding="utf-8"
        )

        valid_completed, valid_payload = self.run_validator(valid)
        invalid_completed, invalid_payload = self.run_validator(invalid)

        self.assertEqual(valid_completed.returncode, 0, valid_completed.stderr)
        self.assertEqual(valid_payload["status"], "pass")
        self.assertEqual(invalid_completed.returncode, 1)
        self.assertEqual(
            invalid_payload["checks"]["official_validator"]["status"], "fail"
        )


if __name__ == "__main__":
    unittest.main()
