#!/usr/bin/env python3
"""Read-only audit of recent Codex skill and MCP usage."""

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from itertools import chain
from pathlib import Path


SKILL_PATH_RE = re.compile(
    r"(?:^|[/\\])skills[/\\](?:\.system[/\\])?"
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)[/\\]SKILL\.md"
)
SKILL_TOKEN_RE = re.compile(r"(?<![\w$])\$([A-Za-z0-9][A-Za-z0-9-]*)")
CALL_ID_RE = re.compile(rb'"call_id"\s*:\s*"([^"\\]+)"')
ROLLOUT_DATE_RE = re.compile(r"^rollout-(\d{4}-\d{2}-\d{2})T")
READ_COMMAND_RE = re.compile(
    r"(?:^|[\s\"'`;/|])(?:cat|sed|head|tail|less|bat|awk|perl|rg|grep|find|wc|jq)\b",
    re.IGNORECASE,
)


@dataclass
class AuditStats:
    session_files: int = 0
    subagent_files: int = 0
    unreadable_files: int = 0
    candidate_json_errors: int = 0
    explicit_references: Counter = field(default_factory=Counter)
    skill_loads: Counter = field(default_factory=Counter)
    skill_sessions: dict = field(default_factory=lambda: defaultdict(set))
    observed_personal_skills: set = field(default_factory=set)
    mcp_counts: dict = field(default_factory=lambda: defaultdict(Counter))
    mcp_sessions: dict = field(default_factory=lambda: defaultdict(set))
    seen_explicit_messages: set = field(default_factory=set)
    seen_skill_calls: set = field(default_factory=set)
    seen_mcp_calls: set = field(default_factory=set)
    pending_skill_calls: dict = field(default_factory=dict)


def discover_personal_skills(codex_home):
    skills_dir = codex_home / "skills"
    if not skills_dir.is_dir():
        return {}
    return {
        child.name: child / "SKILL.md"
        for child in skills_dir.iterdir()
        if child.is_dir()
        and not child.name.startswith(".")
        and (child / "SKILL.md").is_file()
    }


def collect_session_files(codex_home, start, end):
    paths = set()
    for directory in (codex_home / "sessions", codex_home / "archived_sessions"):
        if not directory.is_dir():
            continue
        for path in directory.rglob("rollout-*.jsonl"):
            match = ROLLOUT_DATE_RE.match(path.name)
            session_date = None
            try:
                session_date = date.fromisoformat(match.group(1)) if match else None
                modified_date = datetime.fromtimestamp(path.stat().st_mtime).astimezone().date()
            except (OSError, ValueError):
                modified_date = None
            if (session_date and start <= session_date <= end) or (
                modified_date and modified_date >= start
            ):
                paths.add(path)

    return sorted(paths)


def is_subagent_session(first_line):
    try:
        item = json.loads(first_line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    if item.get("type") != "session_meta":
        return False
    source = (item.get("payload") or {}).get("source")
    if isinstance(source, dict):
        return "subagent" in source
    return source == "subagent"


def in_date_window(item, start, end):
    timestamp = item.get("timestamp")
    if not isinstance(timestamp, str):
        return False
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    event_date = parsed.astimezone().date() if parsed.tzinfo else parsed.date()
    return start <= event_date <= end


def call_input(payload):
    for key in ("input", "arguments"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def matching_parenthesis(source, opening):
    depth = 0
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if char == "*" and following == "/":
                block_comment = False
                index += 1
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
        elif char == "/" and following == "/":
            line_comment = True
            index += 1
        elif char == "/" and following == "*":
            block_comment = True
            index += 1
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def actual_tool_calls(source, tool_name):
    target = f"tools.{tool_name}"
    calls = []
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    index = 0
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if char == "*" and following == "/":
                block_comment = False
                index += 1
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
        elif char == "/" and following == "/":
            line_comment = True
            index += 1
        elif char == "/" and following == "*":
            block_comment = True
            index += 1
        elif source.startswith(target, index):
            opening = index + len(target)
            while opening < len(source) and source[opening].isspace():
                opening += 1
            if opening < len(source) and source[opening] == "(":
                end = matching_parenthesis(source, opening)
                if end:
                    calls.append(source[index:end])
                    index = end - 1
        index += 1
    return calls


def skill_read_inputs(payload):
    text = call_input(payload)
    if not text:
        return []
    payload_type = payload.get("type")
    name = payload.get("name")
    if payload_type == "function_call" and name == "exec_command":
        return [text] if READ_COMMAND_RE.search(text) else []
    if name in ("read_mcp_resource", "skills_read"):
        return [text]
    if payload_type == "custom_tool_call" and name == "exec":
        command_calls = [
            call
            for call in actual_tool_calls(text, "exec_command")
            if READ_COMMAND_RE.search(call)
        ]
        resource_calls = actual_tool_calls(text, "read_mcp_resource")
        return command_calls + resource_calls
    return []


def personal_skill_names(text, personal_skills):
    found = set()
    for name, path in personal_skills.items():
        variants = (
            str(path),
            f".codex/skills/{name}/SKILL.md",
            f"~/.codex/skills/{name}/SKILL.md",
            f"$HOME/.codex/skills/{name}/SKILL.md",
            f"${{HOME}}/.codex/skills/{name}/SKILL.md",
            f"$CODEX_HOME/skills/{name}/SKILL.md",
            f"${{CODEX_HOME}}/skills/{name}/SKILL.md",
        )
        if any(variant in text for variant in variants):
            found.add(name)
    return found


def record_completed_skill_call(stats, call_id):
    pending = stats.pending_skill_calls.pop(call_id, None)
    if not pending or call_id in stats.seen_skill_calls:
        return
    references, personal_names, session_id = pending
    stats.seen_skill_calls.add(call_id)
    stats.skill_loads.update(references)
    for name in references:
        stats.skill_sessions[name].add(session_id)
    stats.observed_personal_skills.update(personal_names)


def record_explicit_references(item, stats, known_skills, start, end):
    payload = item.get("payload") or {}
    if item.get("type") != "event_msg" or payload.get("type") != "user_message":
        return
    if not in_date_window(item, start, end):
        return
    message = payload.get("message")
    if not isinstance(message, str):
        return
    digest = hashlib.blake2b(message.encode("utf-8"), digest_size=12).digest()
    message_key = (item.get("timestamp"), digest)
    if message_key in stats.seen_explicit_messages:
        return
    stats.seen_explicit_messages.add(message_key)
    for name in set(SKILL_TOKEN_RE.findall(message)) & known_skills:
        stats.explicit_references[name] += 1


def record_mcp_call(item, stats, session_id, start, end):
    payload = item.get("payload") or {}
    if item.get("type") != "event_msg" or payload.get("type") != "mcp_tool_call_end":
        return
    if not in_date_window(item, start, end):
        return
    call_id = payload.get("call_id")
    if call_id and call_id in stats.seen_mcp_calls:
        return
    invocation = payload.get("invocation") or {}
    server = invocation.get("server")
    tool = invocation.get("tool")
    if not isinstance(server, str) or not isinstance(tool, str):
        return
    if call_id:
        stats.seen_mcp_calls.add(call_id)
    result = payload.get("result") or {}
    if isinstance(result, dict) and "Err" in result:
        status = "error"
    elif isinstance(result, dict) and "Ok" in result:
        status = "ok"
    else:
        status = "unknown"
    key = (server, tool)
    stats.mcp_counts[key][status] += 1
    stats.mcp_sessions[key].add(session_id)


def scan_session(path, stats, personal_skills, start, end):
    session_id = str(path)
    stats.session_files += 1
    try:
        handle = path.open("rb")
    except OSError:
        stats.unreadable_files += 1
        return
    with handle:
        first_line = handle.readline()
        subagent = is_subagent_session(first_line)
        if subagent:
            stats.subagent_files += 1

        for raw_line in chain((first_line,), handle):
            pending_output = False
            if stats.pending_skill_calls and b"call_output" in raw_line:
                match = CALL_ID_RE.search(raw_line)
                pending_output = bool(
                    match
                    and match.group(1).decode("utf-8", errors="ignore")
                    in stats.pending_skill_calls
                )

            interesting = (
                b"mcp_tool_call_end" in raw_line
                or (
                    b"SKILL.md" in raw_line
                    and (b"function_call" in raw_line or b"tool_call" in raw_line)
                )
                or (not subagent and b"user_message" in raw_line and b"$" in raw_line)
                or pending_output
            )
            if not interesting:
                continue

            try:
                item = json.loads(raw_line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                stats.candidate_json_errors += 1
                continue

            payload = item.get("payload") or {}
            payload_type = payload.get("type")

            if payload_type in ("function_call_output", "custom_tool_call_output"):
                call_id = payload.get("call_id")
                if isinstance(call_id, str):
                    if in_date_window(item, start, end):
                        record_completed_skill_call(stats, call_id)
                    else:
                        stats.pending_skill_calls.pop(call_id, None)

            if payload_type in ("function_call", "custom_tool_call"):
                inputs = skill_read_inputs(payload)
                references = Counter(
                    match.group("name")
                    for text in inputs
                    for match in SKILL_PATH_RE.finditer(text)
                )
                call_id = payload.get("call_id")
                if references and isinstance(call_id, str) and call_id not in stats.seen_skill_calls:
                    stats.pending_skill_calls.setdefault(
                        call_id,
                        (
                            references,
                            set().union(
                                *(personal_skill_names(text, personal_skills) for text in inputs)
                            ),
                            session_id,
                        ),
                    )

            if not subagent:
                record_explicit_references(item, stats, set(personal_skills), start, end)
            record_mcp_call(item, stats, session_id, start, end)


def audit(codex_home, start, end):
    personal_skills = discover_personal_skills(codex_home)
    stats = AuditStats()
    for path in collect_session_files(codex_home, start, end):
        scan_session(path, stats, personal_skills, start, end)
    return stats, personal_skills


def total(counter):
    return sum(counter.values())


def format_report(stats, personal_skills, start, end):
    root_files = stats.session_files - stats.subagent_files
    lines = [
        f"Codex 사용 감사: {start.isoformat()} ~ {end.isoformat()}",
        f"검사 세션 파일: {stats.session_files:,} (root {root_files:,}, sub-agent {stats.subagent_files:,})",
    ]
    if stats.candidate_json_errors:
        lines.append(f"후보 JSON 오류: {stats.candidate_json_errors:,}")
    if stats.unreadable_files:
        lines.append(f"읽기 실패 파일: {stats.unreadable_files:,}")

    lines.extend(["", "Skills (명시참조=$name, 로드=SKILL.md 읽기 시도 proxy)"])
    skill_names = set(stats.explicit_references) | set(stats.skill_loads)
    if skill_names:
        lines.append(f"{'skill':32} {'명시참조':>8} {'로드세션':>8} {'로드':>8}")
        for name in sorted(
            skill_names,
            key=lambda value: (
                -(stats.explicit_references[value] + stats.skill_loads[value]),
                value,
            ),
        ):
            lines.append(
                f"{name:32} {stats.explicit_references[name]:8,d} "
                f"{len(stats.skill_sessions[name]):8,d} {stats.skill_loads[name]:8,d}"
            )
    else:
        lines.append("관측 없음")

    observed = set(stats.explicit_references) | stats.observed_personal_skills
    unused = sorted(set(personal_skills) - observed)
    lines.append("")
    lines.append(f"개인 스킬 관측 없음 ({len(unused)}): {', '.join(unused) if unused else '없음'}")

    lines.extend(["", "MCP (완료 이벤트 기준)"])
    if stats.mcp_counts:
        lines.append(f"{'server/tool':48} {'세션':>7} {'ok':>7} {'error':>7} {'unknown':>7}")
        for key in sorted(stats.mcp_counts, key=lambda value: (-total(stats.mcp_counts[value]), value)):
            counts = stats.mcp_counts[key]
            label = f"{key[0]}/{key[1]}"
            lines.append(
                f"{label:48} {len(stats.mcp_sessions[key]):7,d} "
                f"{counts['ok']:7,d} {counts['error']:7,d} {counts['unknown']:7,d}"
            )
    else:
        lines.append("관측 없음")

    lines.extend(
        [
            "",
            "Hooks",
            "실행/실패 이력 관측 불가: session JSONL에 lifecycle hook 이벤트 없음.",
            "주의: skill 로드는 활성화 전용 이벤트가 아닌 파일 읽기 시도 proxy임.",
        ]
    )
    return "\n".join(lines)


def positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("1 이상의 정수여야 함")
    return parsed


def main():
    parser = argparse.ArgumentParser(
        description="최근 Codex session JSONL에서 skill/MCP 실제 사용 신호를 읽기 전용 집계"
    )
    parser.add_argument("--days", type=positive_int, default=14, help="감사 기간(기본: 14일)")
    args = parser.parse_args()

    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    end = date.today()
    start = end - timedelta(days=args.days - 1)
    stats, personal_skills = audit(codex_home, start, end)
    print(format_report(stats, personal_skills, start, end))


if __name__ == "__main__":
    main()
