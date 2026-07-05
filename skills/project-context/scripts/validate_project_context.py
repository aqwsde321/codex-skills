#!/usr/bin/env python3
import argparse
import errno
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


DEFAULT_DOC = "docs/project-context.md"
DEFAULT_DOC_DIR = "docs/project-context"
DEFAULT_METADATA = "docs/project-context/.metadata.json"
TEMP_PLAN = "docs/project-context/_plan.md"
SNAPSHOT_EXCLUDED_PATHS = {DEFAULT_METADATA, TEMP_PLAN}
MAX_INITIAL_DOCS = 8
SMALL_REPO_SOURCE_FILE_LIMIT = 10
SMALL_REPO_DOC_LIMIT = 3
MIN_SUBPAGE_BODY_CHARS = 500
MIN_SINGLE_FILE_SECTION_CHARS = 1500
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SOURCE_COMMIT_RE = re.compile(r"^source_commit:\s*([A-Za-z0-9._/-]+)\s*$", re.MULTILINE)
UPDATED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T")
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]*$")
EVIDENCE_HEADING_RE = re.compile(r"^##\s+근거\s*$", re.MULTILINE)
NEXT_H2_RE = re.compile(r"^##\s+", re.MULTILINE)
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
COMMIT_HASH_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
VOLATILE_FRONTMATTER_RE = re.compile(r"^(source_commit|updated_at|updatedAt):\s*.*$", re.MULTILINE)
HOST_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w:/.-])(?:/[Uu]sers|/home|/private|/var/folders)/[^\s)`>]+")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
AWS_ACCESS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|token|secret|password|passwd|credential)\b\s*[:=]\s*['\"]?"
    r"(?!<|\$|\{|\[|your-|example|placeholder|redacted|xxx|todo|none|null|false|true)"
    r"[A-Za-z0-9_./+=:@-]{12,}"
)
PRIMARY_DOC_SECTION_PATTERNS = {
    "repository overview": re.compile(
        r"^##\s+(?:프로젝트\s*(?:요약|개요)|Repository Overview|Overview)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    "change guidance": re.compile(
        r"^##\s+(?:작업\s*(?:전\s*)?(?:확인|주의|가이드)(?:\s*지점)?|Change Guidance|Working Notes|Agent Notes)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    "testing guidance": re.compile(
        r"^##\s+(?:검증\s*방법|테스트|Testing|Validation|Checks?)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    "workflow/domain guidance": re.compile(
        r"^##\s+(?:주요\s*흐름|업무\s*흐름|도메인|비즈니스|제품\s*로직|"
        r"Workflows?|Business Logic|Product Logic|Domain(?: Concepts?)?)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
}
CONTEXT_DOC_TEXT = "docs/project-context.md"
REPOSITORY_OVERVIEW_TEXT = "repository overview"
ARCHITECTURE_NOTES_TEXT = "architecture notes"
TESTING_GUIDANCE_TEXT = "testing guidance"
SOURCE_MAPS_TEXT = "source maps"
FOLLOW_LINKS_TEXT = "follow its links"
CODEBASE_MEMORY_TEXT = "codebase-memory-mcp"
SKILL_TRIGGER_TEXT = "$project-context"
AGENT_START_MARKER = "<!-- project-context:start -->"
AGENT_END_MARKER = "<!-- project-context:end -->"
PROJECT_CONTEXT_SECTION_RE = re.compile(r"^##\s+Project Context\s*$.*?(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL)
OPENWIKI_SECTION_RE = re.compile(r"^##\s+OpenWiki\s*$.*?(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL)
PRIMARY_SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".gradle",
    ".graphql",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".m",
    ".mm",
    ".php",
    ".proto",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".xml",
    ".yaml",
    ".yml",
}
PRIMARY_SOURCE_NAMES = {
    "Dockerfile",
    "Makefile",
    "justfile",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "go.mod",
    "Cargo.toml",
}
IGNORED_SOURCE_NAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.lock",
    "go.sum",
}


def git_output(root: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "--no-pager", *args],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def git_commit_exists(root: Path, ref: str) -> bool:
    return git_resolve_commit(root, ref) is not None


def git_resolve_commit(root: Path, ref: str) -> str | None:
    return git_output(root, ["rev-parse", "--verify", f"{ref}^{{commit}}"])


def git_full_head(root: Path) -> str | None:
    return git_output(root, ["rev-parse", "HEAD"])


def git_tracked_files(root: Path) -> list[str]:
    output = git_output(root, ["ls-files"])
    return output.splitlines() if output else []


def is_external_target(target: str) -> bool:
    lowered = target.lower()
    return (
        "://" in lowered
        or lowered.startswith("#")
        or lowered.startswith("mailto:")
        or lowered.startswith("tel:")
    )


def clean_target(target: str) -> str:
    target = target.strip()
    target = target.split("#", 1)[0]
    target = target.split("?", 1)[0]
    return unquote(target).strip()


def iter_relative_links(markdown: str):
    for match in LINK_RE.finditer(markdown):
        target = clean_target(match.group(1))
        if not target or is_external_target(target) or target.startswith("/"):
            continue
        yield target


def iter_markdown_links(markdown: str):
    for match in LINK_RE.finditer(markdown):
        target = clean_target(match.group(1))
        if target:
            yield target


def discover_docs(root: Path, primary_doc: str) -> list[str]:
    docs = [primary_doc]
    doc_dir = root / DEFAULT_DOC_DIR
    if doc_dir.exists() and not doc_dir.is_symlink() and doc_dir.is_dir():
        for path in sorted(doc_dir.rglob("*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel not in docs:
                docs.append(rel)
    return docs


def read_json(path: Path) -> tuple[dict | None, str | None]:
    if path.is_symlink():
        return None, "metadata must not be a symlink"
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except OSError as error:
        return None, str(error)
    except json.JSONDecodeError as error:
        return None, f"invalid JSON: {error.msg}"
    if not isinstance(value, dict):
        return None, "metadata root must be an object"
    return value, None


def parse_frontmatter(markdown: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(0).splitlines()[1:-1]:
        key, separator, value = line.partition(":")
        if not separator:
            continue
        fields[key.strip()] = value.strip().strip("'\"")
    return fields


def validate_repo_relative_path(label: str, value: str) -> str | None:
    path = Path(value)
    if value.strip() == "":
        return f"{label} must not be empty"
    if path.is_absolute():
        return f"{label} must be relative to the repository root: {value}"
    if ".." in path.parts:
        return f"{label} must not contain parent directory traversal: {value}"
    return None


def symlink_parent(root: Path, rel_path: str) -> str | None:
    current = root
    for part in Path(rel_path).parent.parts:
        current = current / part
        if current.is_symlink():
            return current.relative_to(root).as_posix()
    return None


def validate_repo_path(root: Path, label: str, value: str) -> str | None:
    path_error = validate_repo_relative_path(label, value)
    if path_error:
        return path_error
    symlink = symlink_parent(root, value)
    if symlink:
        return f"{label} parent must not be a symlink: {symlink}"
    return None


def is_valid_model_id(value: str) -> bool:
    model_id = value.strip()
    return 0 < len(model_id) <= 120 and "://" not in model_id and MODEL_ID_RE.match(model_id) is not None


def stable_doc_bytes(path: Path) -> bytes:
    markdown = path.read_text(encoding="utf-8", errors="replace")
    if not markdown.startswith("---\n"):
        return markdown.encode("utf-8")
    lines = markdown.splitlines(keepends=True)
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        return markdown.encode("utf-8")
    frontmatter = "".join(lines[1:end_index])
    stable_frontmatter = VOLATILE_FRONTMATTER_RE.sub("", frontmatter)
    stable = "".join([lines[0], stable_frontmatter, *lines[end_index:]])
    return stable.encode("utf-8")


def is_expected_snapshot_race_error(error: OSError) -> bool:
    return isinstance(error, (FileNotFoundError, IsADirectoryError, NotADirectoryError)) or error.errno in {
        errno.EISDIR,
        errno.ENOENT,
        errno.ENOTDIR,
    }


def snapshot_file_bytes(path: Path) -> bytes | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if path.suffix == ".md":
            return stable_doc_bytes(path)
        return path.read_bytes()
    except OSError:
        return None


def docs_content_hash(root: Path, docs: list[str]) -> str:
    digest = hashlib.sha256()
    seen_files: set[str] = set()

    def add_file(rel: str, path: Path) -> None:
        if rel in seen_files or rel in SNAPSHOT_EXCLUDED_PATHS:
            return
        content = snapshot_file_bytes(path)
        if content is None:
            return
        seen_files.add(rel)
        digest.update(f"file:{rel}".encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")

    def add_directory(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError as error:
            if is_expected_snapshot_race_error(error):
                digest.update("missing".encode("utf-8"))
                return
            raise
        for path in entries:
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if rel in SNAPSHOT_EXCLUDED_PATHS or path.is_symlink():
                continue
            try:
                if path.is_dir():
                    digest.update(f"dir:{rel}".encode("utf-8"))
                    digest.update(b"\0")
                    add_directory(path)
                elif path.is_file():
                    add_file(rel, path)
            except OSError as error:
                if is_expected_snapshot_race_error(error):
                    continue
                raise

    primary_doc = docs[0] if docs else DEFAULT_DOC
    primary_path = root / primary_doc
    if primary_path.is_file():
        add_file(primary_doc, primary_path)

    doc_dir = root / DEFAULT_DOC_DIR
    if doc_dir.exists() and not doc_dir.is_symlink() and doc_dir.is_dir():
        add_directory(doc_dir)
    return digest.hexdigest()


def is_context_doc_rel(path: str) -> bool:
    return path == DEFAULT_DOC or path.startswith(f"{DEFAULT_DOC_DIR}/")


def is_primary_source_file(path: str) -> bool:
    if is_context_doc_rel(path):
        return False
    name = Path(path).name
    if name in IGNORED_SOURCE_NAMES:
        return False
    if name in PRIMARY_SOURCE_NAMES:
        return True
    return Path(path).suffix in PRIMARY_SOURCE_SUFFIXES


def count_primary_source_files(root: Path) -> int:
    return sum(1 for path in git_tracked_files(root) if is_primary_source_file(path))


def extract_evidence_section(markdown: str) -> str:
    match = EVIDENCE_HEADING_RE.search(markdown)
    if not match:
        return ""
    start = match.end()
    next_heading = NEXT_H2_RE.search(markdown, start)
    end = next_heading.start() if next_heading else len(markdown)
    return markdown[start:end]


def validate_doc(root: Path, doc_rel: str, require_metadata: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    raw_doc_path = root / doc_rel
    if raw_doc_path.is_symlink():
        return [f"document must not be a symlink: {doc_rel}"], warnings
    if not raw_doc_path.exists():
        return [f"missing document: {doc_rel}"], warnings
    if not raw_doc_path.is_file():
        return [f"document is not a file: {doc_rel}"], warnings

    doc_path = raw_doc_path.resolve()
    markdown = doc_path.read_text(encoding="utf-8", errors="replace")
    body = FRONTMATTER_RE.sub("", markdown).strip()
    frontmatter = parse_frontmatter(markdown)
    absolute_links = [
        link
        for link in iter_markdown_links(markdown)
        if link.startswith("/") and not is_external_target(link)
    ]
    for link in absolute_links:
        errors.append(f"{doc_rel}: absolute link path is not allowed: {link}")
    for match in HOST_ABSOLUTE_PATH_RE.finditer(markdown):
        errors.append(f"{doc_rel}: host absolute path is not allowed: {match.group(0)}")
    if PRIVATE_KEY_RE.search(markdown):
        errors.append(f"{doc_rel}: private key material is not allowed")
    if AWS_ACCESS_KEY_RE.search(markdown):
        errors.append(f"{doc_rel}: secret-looking AWS access key is not allowed")
    if SECRET_ASSIGNMENT_RE.search(markdown):
        errors.append(f"{doc_rel}: secret-looking assignment value is not allowed")

    commit_hashes = set(COMMIT_HASH_RE.findall(body))
    if len(commit_hashes) >= 3:
        warnings.append(f"{doc_rel}: persistent commit hash list suspected; keep git evidence in update metadata or temporary plan")

    if require_metadata:
        if not frontmatter:
            errors.append(f"{doc_rel}: missing YAML frontmatter metadata")
        if frontmatter.get("generated_by") != "project-context":
            errors.append(f"{doc_rel}: missing metadata: generated_by: project-context")
        updated_at = frontmatter.get("updated_at")
        if not updated_at or not UPDATED_AT_RE.match(updated_at):
            errors.append(f"{doc_rel}: missing metadata: updated_at ISO-8601 timestamp")
        mode = frontmatter.get("mode")
        if mode not in {"single-page", "multi-page"}:
            errors.append(f"{doc_rel}: missing metadata: mode single-page|multi-page")

    source_commit_match = SOURCE_COMMIT_RE.search(markdown)
    if require_metadata and not source_commit_match:
        errors.append(f"{doc_rel}: missing metadata: source_commit")
    if source_commit_match:
        source_commit = source_commit_match.group(1)
        resolved_commit = git_resolve_commit(root, source_commit)
        if not resolved_commit:
            errors.append(f"{doc_rel}: source_commit does not exist in git: {source_commit}")
        else:
            head = git_full_head(root)
            if head and resolved_commit != head:
                warnings.append(f"{doc_rel}: stale source_commit: {resolved_commit} != {head}")

    evidence_section = extract_evidence_section(markdown)
    if not evidence_section:
        errors.append(f"{doc_rel}: missing section: ## 근거")

    links = list(iter_relative_links(markdown))
    evidence_links = set(iter_relative_links(evidence_section))
    if not links:
        errors.append(f"{doc_rel}: missing relative source links")

    broken_links: list[str] = []
    links_to_index = False
    evidence_source_links: list[str] = []
    doc_dir = doc_path.parent
    index_path = (root / DEFAULT_DOC).resolve()
    for link in links:
        target_path = (doc_dir / link).resolve()
        if target_path == index_path:
            links_to_index = True
        try:
            target_path.relative_to(root)
        except ValueError:
            broken_links.append(f"{link} -> outside repo")
            continue
        if not target_path.exists():
            broken_links.append(link)
            continue
        if link in evidence_links:
            rel = target_path.relative_to(root).as_posix()
            if not is_context_doc_rel(rel):
                evidence_source_links.append(rel)

    for link in broken_links:
        errors.append(f"{doc_rel}: broken source link: {link}")

    if doc_rel.startswith(f"{DEFAULT_DOC_DIR}/") and not links_to_index:
        errors.append(f"{doc_rel}: missing link back to {DEFAULT_DOC}")

    if evidence_section and not evidence_source_links:
        errors.append(f"{doc_rel}: missing source evidence links in ## 근거")

    if doc_rel.startswith(f"{DEFAULT_DOC_DIR}/") and doc_rel != TEMP_PLAN and len(body) < MIN_SUBPAGE_BODY_CHARS:
        warnings.append(f"{doc_rel}: thin page; merge into {DEFAULT_DOC} or expand with source-grounded guidance")
    if doc_rel == DEFAULT_DOC:
        for section_name, pattern in PRIMARY_DOC_SECTION_PATTERNS.items():
            if not pattern.search(markdown):
                warnings.append(f"{doc_rel}: primary doc should include {section_name} section")

    return errors, warnings


def validate_metadata(root: Path, docs: list[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    metadata_path = root / DEFAULT_METADATA
    if metadata_path.is_symlink():
        errors.append(f"update metadata must not be a symlink: {DEFAULT_METADATA}")
        return errors, warnings
    if not metadata_path.exists():
        warnings.append(f"missing update metadata: {DEFAULT_METADATA}")
        return errors, warnings
    if not metadata_path.is_file():
        errors.append(f"update metadata is not a file: {DEFAULT_METADATA}")
        return errors, warnings

    metadata, read_error = read_json(metadata_path)
    if metadata is None:
        errors.append(f"invalid update metadata: {DEFAULT_METADATA}: {read_error}")
        return errors, warnings

    for key in ("updatedAt", "command", "model"):
        value = metadata.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{DEFAULT_METADATA}: missing OpenWiki metadata field: {key}")
    updated_at = metadata.get("updatedAt")
    if isinstance(updated_at, str) and updated_at.strip() and not UPDATED_AT_RE.match(updated_at):
        warnings.append(f"{DEFAULT_METADATA}: updatedAt should be an ISO-8601 timestamp")
    model = metadata.get("model")
    if isinstance(model, str) and model.strip() and not is_valid_model_id(model):
        warnings.append(f"{DEFAULT_METADATA}: model should be an OpenWiki-compatible model id")
    if isinstance(model, str) and model.strip() and model != model.strip():
        warnings.append(f"{DEFAULT_METADATA}: model should not have surrounding whitespace")

    command = metadata.get("command")
    if isinstance(command, str) and command.strip() and command not in {"init", "update"}:
        warnings.append(f"{DEFAULT_METADATA}: unexpected command: {command}")

    resolved_git_head = None
    git_head_ref = metadata.get("gitHead")
    if isinstance(git_head_ref, str) and git_head_ref.strip():
        resolved_git_head = git_resolve_commit(root, git_head_ref.strip())
        if not resolved_git_head:
            errors.append(f"{DEFAULT_METADATA}: gitHead does not exist in git: {git_head_ref.strip()}")
    else:
        warnings.append(f"{DEFAULT_METADATA}: missing gitHead; update planning will fall back to updatedAt")

    source_commit_ref = metadata.get("source_commit")
    if source_commit_ref is not None:
        if not isinstance(source_commit_ref, str) or not source_commit_ref.strip():
            errors.append(f"{DEFAULT_METADATA}: source_commit must be a non-empty string when present")
        else:
            resolved_source_commit = git_resolve_commit(root, source_commit_ref.strip())
            if not resolved_source_commit:
                errors.append(f"{DEFAULT_METADATA}: source_commit does not exist in git: {source_commit_ref.strip()}")
            elif resolved_git_head and resolved_source_commit != resolved_git_head:
                errors.append(f"{DEFAULT_METADATA}: source_commit does not match gitHead")

    if resolved_git_head:
        head = git_full_head(root)
        if head and resolved_git_head != head:
            warnings.append(f"{DEFAULT_METADATA}: stale gitHead: {resolved_git_head} != {head}")

    content_hash = metadata.get("content_hash")
    if not isinstance(content_hash, str) or not content_hash.strip():
        warnings.append(f"{DEFAULT_METADATA}: missing content_hash")
    else:
        current_hash = docs_content_hash(root, docs)
        if content_hash != current_hash:
            warnings.append(f"{DEFAULT_METADATA}: content_hash mismatch; run project_context_update.py record after valid docs changes")

    recorded_docs = metadata.get("docs")
    if isinstance(recorded_docs, list) and all(isinstance(doc, str) for doc in recorded_docs):
        if sorted(recorded_docs) != sorted(docs):
            warnings.append(f"{DEFAULT_METADATA}: docs list does not match current context documents")
    elif recorded_docs is not None:
        warnings.append(f"{DEFAULT_METADATA}: docs must be a string list")

    return errors, warnings


def validate_index_links(root: Path, doc_rel: str, docs: list[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    primary_path = root / doc_rel
    if not primary_path.exists() or not primary_path.is_file():
        return errors, warnings
    subdocs = [doc for doc in docs if doc != doc_rel]
    if not subdocs:
        return errors, warnings

    markdown = primary_path.read_text(encoding="utf-8", errors="replace")
    linked_targets = set()
    for link in iter_relative_links(markdown):
        target_path = (primary_path.parent / link).resolve()
        try:
            linked_targets.add(target_path.relative_to(root).as_posix())
        except ValueError:
            continue

    for subdoc in subdocs:
        if subdoc not in linked_targets:
            errors.append(f"{doc_rel}: missing index link to context page: {subdoc}")

    return errors, warnings


def doc_body_length(root: Path, doc_rel: str) -> int:
    path = root / doc_rel
    if not path.exists() or not path.is_file():
        return 0
    markdown = path.read_text(encoding="utf-8", errors="replace")
    return len(FRONTMATTER_RE.sub("", markdown).strip())


def validate_section_directories(root: Path, docs: list[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    section_docs: dict[str, list[str]] = {}
    for doc in docs:
        if not doc.startswith(f"{DEFAULT_DOC_DIR}/"):
            continue
        remainder = doc[len(DEFAULT_DOC_DIR) + 1 :]
        if "/" not in remainder:
            continue
        section = remainder.split("/", 1)[0]
        section_docs.setdefault(section, []).append(doc)

    for section, section_doc_list in sorted(section_docs.items()):
        if len(section_doc_list) == 1:
            doc = section_doc_list[0]
            body_length = doc_body_length(root, doc)
            if body_length < MIN_SINGLE_FILE_SECTION_CHARS:
                warnings.append(
                    f"{DEFAULT_DOC_DIR}/{section}/: single-file section directory; prefer a broader page or heading unless this boundary is substantial"
                )

    return errors, warnings


def marked_agent_section(text: str) -> str | None:
    start = text.find(AGENT_START_MARKER)
    end = text.find(AGENT_END_MARKER)
    if start == -1 or end == -1 or start > end:
        return None
    return text[start : end + len(AGENT_END_MARKER)]


def is_semantically_current_agent_section(section: str) -> bool:
    return (
        CONTEXT_DOC_TEXT in section
        and REPOSITORY_OVERVIEW_TEXT in section
        and ARCHITECTURE_NOTES_TEXT in section
        and TESTING_GUIDANCE_TEXT in section
        and SOURCE_MAPS_TEXT in section
        and FOLLOW_LINKS_TEXT in section
        and CODEBASE_MEMORY_TEXT in section
        and SKILL_TRIGGER_TEXT in section
    )


def validate(root: Path, doc_rel: str) -> tuple[int, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    temp_plan_path = root / TEMP_PLAN
    if temp_plan_path.exists() or temp_plan_path.is_symlink():
        errors.append(f"temporary plan must be deleted before finish: {TEMP_PLAN}")
    if (root / DEFAULT_DOC_DIR).is_symlink():
        errors.append(f"context doc directory must not be a symlink: {DEFAULT_DOC_DIR}")
    docs = discover_docs(root, doc_rel)
    docs = [doc for doc in docs if doc != TEMP_PLAN]
    metadata_errors, metadata_warnings = validate_metadata(root, docs)
    errors.extend(metadata_errors)
    warnings.extend(metadata_warnings)
    if len(docs) > MAX_INITIAL_DOCS:
        warnings.append(f"many context docs: {len(docs)}; initial OpenWiki-style runs usually stay at {MAX_INITIAL_DOCS} or fewer")
    primary_source_count = count_primary_source_files(root)
    if 0 < primary_source_count <= SMALL_REPO_SOURCE_FILE_LIMIT and len(docs) > SMALL_REPO_DOC_LIMIT:
        warnings.append(
            f"small repo with {primary_source_count} primary source file(s): prefer {DEFAULT_DOC} plus at most 1-2 supporting pages"
        )
    for index, doc in enumerate(docs):
        doc_errors, doc_warnings = validate_doc(root, doc, require_metadata=index == 0)
        errors.extend(doc_errors)
        warnings.extend(doc_warnings)
    index_errors, index_warnings = validate_index_links(root, doc_rel, docs)
    errors.extend(index_errors)
    warnings.extend(index_warnings)
    section_errors, section_warnings = validate_section_directories(root, docs)
    errors.extend(section_errors)
    warnings.extend(section_warnings)

    agent_files = ("AGENTS.md", "CLAUDE.md")
    existing_agent_files = [agent_file for agent_file in agent_files if (root / agent_file).exists()]
    if not existing_agent_files:
        warnings.append("missing AGENTS.md or CLAUDE.md project context reference")

    for agent_file in existing_agent_files:
        agent_path = root / agent_file
        if not agent_path.is_file():
            warnings.append(f"{agent_file} is not a file")
            continue
        agent_text = agent_path.read_text(encoding="utf-8", errors="replace")
        start_count = agent_text.count(AGENT_START_MARKER)
        end_count = agent_text.count(AGENT_END_MARKER)
        if CONTEXT_DOC_TEXT not in agent_text:
            warnings.append(f"{agent_file} does not mention {CONTEXT_DOC_TEXT}")
        if start_count != 1 or end_count != 1:
            warnings.append(f"{agent_file} project context reference should have exactly one marked section")
        marked_section = marked_agent_section(agent_text)
        if marked_section is not None and not is_semantically_current_agent_section(marked_section):
            warnings.append(f"{agent_file} project context reference is stale; run project_context_agents.py")
        marker_start = agent_text.find(AGENT_START_MARKER)
        marker_end = agent_text.find(AGENT_END_MARKER)
        for section_match in PROJECT_CONTEXT_SECTION_RE.finditer(agent_text):
            marked = marker_start != -1 and marker_end != -1 and marker_start < section_match.start() < marker_end
            if not marked:
                warnings.append(f"{agent_file} has unmarked Project Context section; run project_context_agents.py")
                break
        for section_match in OPENWIKI_SECTION_RE.finditer(agent_text):
            marked = marker_start != -1 and marker_end != -1 and marker_start < section_match.start() < marker_end
            if not marked:
                warnings.append(f"{agent_file} has unmarked OpenWiki section; run project_context_agents.py")
                break

    if errors:
        return 1, errors, warnings
    return 0, [f"project context valid: {len(docs)} document(s)"], warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Codex-native project context docs.")
    parser.add_argument("repo_root", nargs="?", default=".", help="Repository root.")
    parser.add_argument("--doc", default=DEFAULT_DOC, help=f"Document path relative to repo root. Default: {DEFAULT_DOC}")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"repo root is not a directory: {root}", file=sys.stderr)
        return 2
    doc_error = validate_repo_path(root, "--doc", args.doc)
    if doc_error:
        print(doc_error, file=sys.stderr)
        return 2

    code, messages, warnings = validate(root, args.doc)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    stream = sys.stderr if code else sys.stdout
    for message in messages:
        print(message, file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
