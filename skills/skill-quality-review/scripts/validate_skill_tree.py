#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["PyYAML==6.0.3", "markdown-it-py==4.2.0"]
# ///
"""Run deterministic supplemental checks for one Codex skill directory."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    import yaml
except ImportError:  # Reported as unavailable; never treated as a pass.
    yaml = None

try:
    from markdown_it import MarkdownIt
    from markdown_it.common.utils import normalizeReference as normalize_reference
    from markdown_it.rules_inline.image import image as parse_image
    from markdown_it.rules_inline.link import link as parse_link
except ImportError:  # Reported as unavailable; never treated as a pass.
    MarkdownIt = None
    normalize_reference = None
    parse_image = None
    parse_link = None


STATUS_RANK = {"pass": 0, "not_checked": 1, "unavailable": 2, "fail": 3}
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", re.DOTALL)
MISSING_REFERENCES_KEY = "_skill_quality_missing_references"
MISSING_REFERENCE_SPANS_ATTR = "_skill_quality_missing_reference_spans"
REFERENCE_LINE_DELTAS_KEY = "_skill_quality_reference_line_deltas"
SOURCE_LINE_OFFSET_META_KEY = "_skill_quality_source_line_offset"


@dataclass
class Check:
    status: str = "not_checked"
    details: list[dict[str, str]] = field(default_factory=list)

    def add(self, status: str, message: str, location: str = "") -> None:
        if not self.details or STATUS_RANK[status] > STATUS_RANK[self.status]:
            self.status = status
        self.details.append({"status": status, "message": message, "location": location})


class Validation:
    def __init__(self, skill_dir: Path) -> None:
        self.skill_dir = skill_dir
        self.checks = {
            name: Check()
            for name in (
                "official_validator",
                "yaml_parser",
                "markdown_parser",
                "folder_name",
                "allowed_tools",
                "markdown_links",
                "agents_metadata",
                "file_dependencies",
                "tool_dependencies",
                "executable_dependencies",
            )
        }

    def add(self, check: str, status: str, message: str, location: str = "") -> None:
        self.checks[check].add(status, message, location)

    def payload(self) -> dict[str, object]:
        failed = any(check.status == "fail" for check in self.checks.values())
        incomplete = {"unavailable", "not_checked"}
        complete = not any(
            check.status in incomplete
            or any(detail["status"] in incomplete for detail in check.details)
            for check in self.checks.values()
        )
        status = "fail" if failed else "pass" if complete else "incomplete"
        return {
            "skill": str(self.skill_dir),
            "status": status,
            "complete": complete,
            "checks": {
                name: {"status": check.status, "details": check.details}
                for name, check in self.checks.items()
            },
        }

    def exit_code(self) -> int:
        payload = self.payload()
        if payload["status"] == "fail":
            return 1
        return 0 if payload["complete"] else 2


def run_official_validator(
    result: Validation, quick_validator: Path | None
) -> None:
    if quick_validator is None:
        result.add(
            "official_validator",
            "unavailable",
            "official skill-creator quick_validate.py was not provided",
        )
        return
    if not quick_validator.is_file():
        result.add(
            "official_validator",
            "unavailable",
            "official validator does not exist",
            str(quick_validator),
        )
        return

    try:
        completed = subprocess.run(
            [sys.executable, str(quick_validator), str(result.skill_dir)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        result.add("official_validator", "unavailable", str(error), str(quick_validator))
        return

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    output = "\n".join(part for part in (stdout, stderr) if part)
    if completed.returncode == 0:
        result.add("official_validator", "pass", output or "official validator passed")
    elif "ModuleNotFoundError" in stderr or "No module named" in stderr:
        result.add("official_validator", "unavailable", output, str(quick_validator))
    elif "Traceback (most recent call last)" in stderr:
        result.add("official_validator", "unavailable", output, str(quick_validator))
    else:
        result.add("official_validator", "fail", output or "official validator failed")


def load_yaml(text: str, result: Validation, check: str, location: Path):
    if yaml is None:
        if not result.checks["yaml_parser"].details:
            result.add("yaml_parser", "unavailable", "PyYAML is not installed")
        result.add(check, "not_checked", "YAML parsing was unavailable", str(location))
        return None
    if not result.checks["yaml_parser"].details:
        result.add("yaml_parser", "pass", "PyYAML is available")
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as error:
        result.add(check, "fail", f"invalid YAML: {error}", str(location))
        return None


def contained_lexical_parts(root: Path, path: Path) -> tuple[str, ...] | None:
    root = root.resolve()
    candidate = path if path.is_absolute() else root / path
    try:
        parts = candidate.relative_to(root).parts
    except ValueError:
        return None

    depth = 0
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if depth == 0:
                return None
            depth -= 1
        else:
            depth += 1
    return parts


def path_is_lexically_within(root: Path, path: Path) -> bool:
    return contained_lexical_parts(root, path) is not None


def path_stays_within(root: Path, path: Path) -> bool:
    root = root.resolve()
    parts = contained_lexical_parts(root, path)
    if parts is None:
        return False

    prefix = root
    for part in parts:
        if part in ("", "."):
            continue
        prefix = prefix.parent if part == ".." else prefix / part
        try:
            prefix = prefix.resolve(strict=False)
        except (OSError, RuntimeError):
            return False
        if not prefix.is_relative_to(root):
            return False
    return True


def preflight_skill_md(result: Validation) -> bool:
    skill_md = result.skill_dir / "SKILL.md"
    if path_stays_within(result.skill_dir, skill_md):
        return True

    # ponytail: 로컬 파일은 preflight 뒤 바뀔 수 있음, 검사가 권한 부여 경계가 되면 snapshot으로 재검토
    result.add(
        "official_validator",
        "not_checked",
        "official validator was skipped because SKILL.md leaves the skill boundary",
        str(skill_md),
    )
    result.add(
        "folder_name",
        "fail",
        "SKILL.md leaves the skill boundary through a symlink",
        str(skill_md),
    )
    result.add("yaml_parser", "not_checked", "SKILL.md frontmatter was not read")
    result.add("allowed_tools", "not_checked", "SKILL.md frontmatter was not read")
    return False


def validate_frontmatter(result: Validation) -> str | None:
    skill_md = result.skill_dir / "SKILL.md"
    if not skill_md.is_file():
        result.add("folder_name", "fail", "SKILL.md does not exist", str(skill_md))
        result.add("yaml_parser", "not_checked", "SKILL.md is unavailable")
        return None
    try:
        content = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        result.add("folder_name", "fail", str(error), str(skill_md))
        return None
    match = FRONTMATTER_RE.match(content)
    if not match:
        result.add("folder_name", "fail", "frontmatter could not be read", str(skill_md))
        result.add("yaml_parser", "not_checked", "frontmatter is unavailable", str(skill_md))
        return None
    frontmatter = load_yaml(match.group(1), result, "folder_name", skill_md)
    if frontmatter is None:
        return None
    if not isinstance(frontmatter, dict):
        result.add("folder_name", "fail", "frontmatter must be a mapping", str(skill_md))
        return None
    name = frontmatter.get("name")
    if not isinstance(name, str) or not name:
        result.add("folder_name", "fail", "frontmatter name is unavailable", str(skill_md))
        return None
    if name != result.skill_dir.name:
        result.add(
            "folder_name",
            "fail",
            f"folder '{result.skill_dir.name}' does not match skill name '{name}'",
            str(result.skill_dir),
        )
    else:
        result.add("folder_name", "pass", "folder name matches skill name")
    allowed_tools = frontmatter.get("allowed-tools")
    if allowed_tools is None:
        result.add("allowed_tools", "pass", "allowed-tools is optional and absent")
    elif isinstance(allowed_tools, str) and allowed_tools.strip():
        result.add("allowed_tools", "pass", "allowed-tools is a permission string")
    else:
        result.add(
            "allowed_tools",
            "fail",
            "frontmatter allowed-tools must be a non-empty space-separated string",
            str(skill_md),
        )
    return name


def markdown_files(result: Validation):
    for current, directories, files in os.walk(
        result.skill_dir, followlinks=False
    ):
        current_path = Path(current)
        retained_directories = []
        for name in directories:
            directory = current_path / name
            if directory.is_symlink():
                result.add(
                    "markdown_links",
                    "fail",
                    "Markdown coverage cannot include a directory symlink",
                    str(directory),
                )
            else:
                retained_directories.append(name)
        directories[:] = retained_directories
        for name in sorted(files):
            if name.lower().endswith(".md"):
                yield current_path / name


def mask_frontmatter(text: str) -> str:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return text
    prefix = text[: match.end()]
    masked = "".join(character if character in "\r\n" else " " for character in prefix)
    return masked + text[match.end() :]


def source_line_offset(state, position: int) -> int:
    line_deltas = state.env.get(REFERENCE_LINE_DELTAS_KEY, [])
    parent_line_delta = line_deltas[-1] if line_deltas else 0
    return parent_line_delta + state.src.count("\n", 0, position)


def record_missing_reference(state, silent: bool) -> bool:
    # ponytail: 미정의 shortcut reference는 검사하지 않음, 해당 coverage가 필요하면 전용 rule 추가
    if silent or state.pos >= state.posMax:
        return False

    start = state.pos
    is_image = state.src[start] == "!"
    bracket = start + 1 if is_image else start
    if bracket >= state.posMax or state.src[bracket] != "[":
        return False

    label_start = bracket + 1
    label_end = state.md.helpers.parseLinkLabel(state, bracket, not is_image)
    if label_end < 0:
        return False

    reference_open = label_end + 1
    if reference_open >= state.posMax or state.src[reference_open] != "[":
        return False

    reference_start = reference_open + 1
    reference_end = state.md.helpers.parseLinkLabel(state, reference_open)
    if reference_end < 0:
        return False

    raw_label = state.src[reference_start:reference_end]
    if not raw_label:
        raw_label = state.src[label_start:label_end]
    normalized_label = normalize_reference(raw_label)
    if normalized_label not in state.env.get("references", {}):
        span = (bracket, reference_end + 1)
        seen = getattr(state, MISSING_REFERENCE_SPANS_ATTR, None)
        if seen is None:
            seen = set()
            setattr(state, MISSING_REFERENCE_SPANS_ATTR, seen)
        if span in seen:
            return False
        seen.add(span)
        state.env.setdefault(MISSING_REFERENCES_KEY, []).append(
            {
                "label": raw_label,
                "line_offset": source_line_offset(state, start),
            }
        )
    return False


def parse_image_with_reference_line_origin(state, silent: bool) -> bool:
    if (
        state.src[state.pos] != "!"
        or state.pos + 1 >= state.posMax
        or state.src[state.pos + 1] != "["
    ):
        return parse_image(state, silent)

    image_line_offset = source_line_offset(state, state.pos)
    line_deltas = state.env.setdefault(REFERENCE_LINE_DELTAS_KEY, [])
    line_deltas.append(source_line_offset(state, state.pos + 2))
    try:
        matched = parse_image(state, silent)
        if matched and not silent:
            state.tokens[-1].meta[SOURCE_LINE_OFFSET_META_KEY] = image_line_offset
        return matched
    finally:
        line_deltas.pop()
        if not line_deltas:
            state.env.pop(REFERENCE_LINE_DELTAS_KEY, None)


def parse_link_with_source_line_origin(state, silent: bool) -> bool:
    link_start = state.pos
    token_count = len(state.tokens)
    matched = parse_link(state, silent)
    if matched and not silent:
        link_line_offset = source_line_offset(state, link_start)
        link_open = next(
            token
            for token in state.tokens[token_count:]
            if token.type == "link_open"
        )
        link_open.meta[SOURCE_LINE_OFFSET_META_KEY] = link_line_offset
    return matched


def validate_link_target(
    result: Validation, markdown_path: Path, target: str, line_number: int
) -> None:
    if not target or target.startswith("#") or target.startswith("//"):
        return
    try:
        parsed = urlsplit(target)
    except ValueError as error:
        result.add(
            "markdown_links",
            "fail",
            f"invalid link target '{target}': {error}",
            f"{markdown_path}:{line_number}",
        )
        return
    if parsed.scheme:
        return
    path_text = unquote(parsed.path)
    if not path_text:
        return
    link_path = Path(path_text)
    candidate = link_path if link_path.is_absolute() else markdown_path.parent / link_path
    skill_root = result.skill_dir.resolve()
    if path_is_lexically_within(skill_root, candidate) and not path_stays_within(
        skill_root, candidate
    ):
        result.add(
            "markdown_links",
            "fail",
            f"local target leaves the skill through a symlink: '{target}'",
            f"{markdown_path}:{line_number}",
        )
        return
    if not candidate.exists():
        result.add(
            "markdown_links",
            "fail",
            f"missing local target '{target}'",
            f"{markdown_path}:{line_number}",
        )


def validate_markdown_links(result: Validation) -> None:
    if MarkdownIt is None or normalize_reference is None:
        result.add(
            "markdown_parser",
            "unavailable",
            "markdown-it-py is not installed",
        )
        result.add(
            "markdown_links",
            "not_checked",
            "CommonMark parsing was unavailable",
        )
        return

    result.add("markdown_parser", "pass", "markdown-it-py is available")
    parser = MarkdownIt("commonmark", {"html": True})
    parser.inline.ruler.at("image", parse_image_with_reference_line_origin)
    parser.inline.ruler.at("link", parse_link_with_source_line_origin)
    reference_parser = MarkdownIt("commonmark", {"html": True})
    reference_parser.inline.ruler.before(
        "link", "missing_reference", record_missing_reference
    )
    reference_parser.inline.ruler.at("image", parse_image_with_reference_line_origin)
    found_markdown = False
    skill_root = result.skill_dir.resolve()
    for path in markdown_files(result):
        found_markdown = True
        if not path_stays_within(skill_root, path) or not path.is_file():
            result.add(
                "markdown_links",
                "fail",
                "Markdown file resolves outside the skill or is a broken symlink",
                str(path),
            )
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if path == result.skill_dir / "SKILL.md":
                text = mask_frontmatter(text)
        except (OSError, UnicodeError) as error:
            result.add("markdown_links", "fail", str(error), str(path))
            continue
        environment = {}
        tokens = parser.parse(text, environment)
        references = environment.get("references", {})

        for reference in references.values():
            target = reference.get("href")
            source_map = reference.get("map")
            if isinstance(target, str):
                line_number = source_map[0] + 1 if source_map else 1
                validate_link_target(result, path, target, line_number)

        for token in tokens:
            if token.type != "inline":
                continue
            line_number = token.map[0] + 1 if token.map else 1
            pending_children = list(reversed(token.children or []))
            while pending_children:
                child = pending_children.pop()
                target = None
                if child.type == "link_open":
                    target = child.attrGet("href")
                elif child.type == "image":
                    target = child.attrGet("src")
                if target:
                    target_line = line_number + child.meta.get(
                        SOURCE_LINE_OFFSET_META_KEY, 0
                    )
                    validate_link_target(result, path, target, target_line)
                pending_children.extend(reversed(child.children or []))

            reference_environment = {"references": references}
            reference_parser.parseInline(token.content, reference_environment)
            for missing in reference_environment.get(MISSING_REFERENCES_KEY, []):
                raw_label = missing["label"]
                reference_line = line_number + missing["line_offset"]
                result.add(
                    "markdown_links",
                    "fail",
                    f"missing reference definition '[{raw_label}]'",
                    f"{path}:{reference_line}",
                )
    if found_markdown and not result.checks["markdown_links"].details:
        result.add("markdown_links", "pass", "all local Markdown targets exist")
    elif not found_markdown:
        result.add("markdown_links", "not_checked", "no Markdown files were available")


def validate_agents_metadata(result: Validation, skill_name: str | None) -> set[str] | None:
    path = result.skill_dir / "agents" / "openai.yaml"
    if path.is_symlink() and not path.exists():
        result.add(
            "agents_metadata",
            "fail",
            "agents/openai.yaml is a dangling symlink",
            str(path),
        )
        return None
    if not path_stays_within(result.skill_dir, path):
        result.add(
            "agents_metadata",
            "fail",
            "agents/openai.yaml leaves the skill boundary through a symlink",
            str(path),
        )
        return None
    if not path.exists():
        result.add("agents_metadata", "pass", "agents/openai.yaml is optional and absent")
        return set()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        result.add("agents_metadata", "fail", str(error), str(path))
        return None
    document = load_yaml(text, result, "agents_metadata", path)
    if document is None:
        return None
    if not isinstance(document, dict):
        result.add("agents_metadata", "fail", "document root must be a mapping", str(path))
        return None

    interface = document.get("interface", {})
    if not isinstance(interface, dict):
        result.add("agents_metadata", "fail", "interface must be a mapping", str(path))
        interface = {}
    for key in ("display_name", "short_description", "icon_small", "icon_large", "brand_color", "default_prompt"):
        if key in interface and not isinstance(interface[key], str):
            result.add("agents_metadata", "fail", f"interface.{key} must be a string", str(path))
    short_description = interface.get("short_description")
    if isinstance(short_description, str) and not 25 <= len(short_description) <= 64:
        result.add("agents_metadata", "fail", "short_description must be 25-64 characters", str(path))
    brand_color = interface.get("brand_color")
    if isinstance(brand_color, str) and not re.fullmatch(r"#[0-9A-Fa-f]{6}", brand_color):
        result.add("agents_metadata", "fail", "brand_color must be a six-digit hex color", str(path))
    default_prompt = interface.get("default_prompt")
    if isinstance(default_prompt, str) and skill_name:
        invocation = re.compile(rf"\${re.escape(skill_name)}(?![A-Za-z0-9_-])")
        if not invocation.search(default_prompt):
            result.add("agents_metadata", "fail", f"default_prompt must mention '${skill_name}'", str(path))
    for icon_key in ("icon_small", "icon_large"):
        icon = interface.get(icon_key)
        if isinstance(icon, str):
            icon_path = Path(icon)
            candidate = result.skill_dir / icon_path
            if (
                icon_path.is_absolute()
                or ".." in icon_path.parts
                or not path_stays_within(result.skill_dir, candidate)
            ):
                result.add("agents_metadata", "fail", f"{icon_key} must stay inside the skill", str(path))
            elif not candidate.is_file():
                result.add("agents_metadata", "fail", f"missing {icon_key} target '{icon}'", str(path))

    policy = document.get("policy", {})
    if not isinstance(policy, dict):
        result.add("agents_metadata", "fail", "policy must be a mapping", str(path))
    elif "allow_implicit_invocation" in policy and not isinstance(
        policy["allow_implicit_invocation"], bool
    ):
        result.add("agents_metadata", "fail", "policy.allow_implicit_invocation must be boolean", str(path))

    dependencies = document.get("dependencies", {})
    dependency_shape_valid = isinstance(dependencies, dict)
    if not dependency_shape_valid:
        result.add("agents_metadata", "fail", "dependencies must be a mapping", str(path))
        dependencies = {}
    tools = dependencies.get("tools", [])
    if not isinstance(tools, list):
        result.add("agents_metadata", "fail", "dependencies.tools must be a list", str(path))
        tools = []
        dependency_shape_valid = False
    declared_mcp = set()
    for index, tool in enumerate(tools):
        location = f"{path}:dependencies.tools[{index}]"
        if not isinstance(tool, dict):
            result.add("agents_metadata", "fail", "tool dependency must be a mapping", location)
            dependency_shape_valid = False
            continue
        if tool.get("type") != "mcp":
            result.add("agents_metadata", "fail", "tool dependency type must be 'mcp'", location)
            dependency_shape_valid = False
        value = tool.get("value")
        if not isinstance(value, str) or not value.strip():
            result.add("agents_metadata", "fail", "tool dependency value must be a non-empty string", location)
            dependency_shape_valid = False
        else:
            declared_mcp.add(value.strip())
        for key in ("description", "transport", "url"):
            if key in tool and not isinstance(tool[key], str):
                result.add(
                    "agents_metadata",
                    "fail",
                    f"tool dependency {key} must be a string",
                    location,
                )
                dependency_shape_valid = False
    if not result.checks["agents_metadata"].details:
        result.add("agents_metadata", "pass", "agents/openai.yaml is valid")
    return declared_mcp if dependency_shape_valid else None


def validate_tool_dependencies(
    result: Validation,
    required_tools: set[str],
    declared_mcp: set[str] | None,
    available_tools: set[str],
    available_mcp: set[str],
    tool_catalog_complete: bool,
    mcp_catalog_complete: bool,
) -> None:
    requirements = [("tool", required_tools, available_tools, tool_catalog_complete)]
    if declared_mcp is None:
        result.add(
            "tool_dependencies",
            "not_checked",
            "declared MCP dependencies could not be read",
        )
    else:
        requirements.append(("mcp", declared_mcp, available_mcp, mcp_catalog_complete))
    for kind, required, available, catalog_complete in requirements:
        for name in sorted(required):
            if name in available:
                result.add("tool_dependencies", "pass", f"{kind} dependency '{name}' is available")
            elif catalog_complete:
                result.add("tool_dependencies", "fail", f"missing/stale {kind} dependency '{name}'")
            else:
                result.add("tool_dependencies", "not_checked", f"{kind} dependency '{name}' is unresolved")
    if not required_tools and declared_mcp == set():
        result.add("tool_dependencies", "pass", "no declared runtime tool dependencies")


def validate_files(result: Validation, required: set[str]) -> None:
    skill_root = result.skill_dir.resolve()
    for name in sorted(required):
        path = Path(name)
        candidate = skill_root / path
        if path.is_absolute() or not path_stays_within(skill_root, candidate):
            result.add(
                "file_dependencies",
                "fail",
                f"required file must stay inside the skill: '{name}'",
            )
        elif candidate.is_file():
            result.add("file_dependencies", "pass", f"required file '{name}' exists")
        else:
            result.add("file_dependencies", "fail", f"required file '{name}' is missing")
    if not required:
        result.add("file_dependencies", "pass", "no explicit local file requirements")


def validate_executables(result: Validation, required: set[str]) -> None:
    for name in sorted(required):
        resolved = shutil.which(name)
        if resolved:
            result.add("executable_dependencies", "pass", f"executable '{name}' found", resolved)
        else:
            result.add("executable_dependencies", "fail", f"missing/stale executable dependency '{name}'")
    if not required:
        result.add("executable_dependencies", "pass", "no declared executable dependencies")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_dir", type=Path)
    parser.add_argument("--quick-validator", type=Path)
    parser.add_argument("--available-tool", action="append", default=[])
    parser.add_argument("--available-mcp", action="append", default=[])
    parser.add_argument("--required-file", action="append", default=[])
    parser.add_argument("--required-tool", action="append", default=[])
    parser.add_argument("--required-executable", action="append", default=[])
    parser.add_argument("--tool-catalog-complete", action="store_true")
    parser.add_argument("--mcp-catalog-complete", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    skill_dir = args.skill_dir.resolve()
    result = Validation(skill_dir)
    if not skill_dir.is_dir():
        result.add("folder_name", "fail", "skill directory does not exist", str(skill_dir))
        for check in result.checks:
            if check != "folder_name":
                result.add(check, "not_checked", "skill directory is unavailable")
    else:
        if preflight_skill_md(result):
            run_official_validator(result, args.quick_validator)
            skill_name = validate_frontmatter(result)
        else:
            skill_name = None
        validate_markdown_links(result)
        declared_mcp = validate_agents_metadata(result, skill_name)
        validate_files(result, set(args.required_file))
        validate_tool_dependencies(
            result,
            set(args.required_tool),
            declared_mcp,
            set(args.available_tool),
            set(args.available_mcp),
            args.tool_catalog_complete,
            args.mcp_catalog_complete,
        )
        validate_executables(result, set(args.required_executable))

    payload = result.payload()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['status']}: {skill_dir}")
        for name, check in payload["checks"].items():
            print(f"- {name}: {check['status']}")
            for detail in check["details"]:
                location = f" ({detail['location']})" if detail["location"] else ""
                print(f"  - {detail['status']}: {detail['message']}{location}")
    return result.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
