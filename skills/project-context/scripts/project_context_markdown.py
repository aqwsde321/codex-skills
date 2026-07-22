"""Minimal CommonMark-aware inline link target extraction."""

from __future__ import annotations

import re
import string


ESCAPABLE = frozenset(string.punctuation)
ASCII_WHITESPACE = " \t\r\n"
LIST_MARKER_RE = re.compile(r"(?:[-+*]|\d{1,9}[.)])(?=[ \t])")
ATX_HEADING_RE = re.compile(r" {0,3}#{1,6}(?:[ \t]+|$)")
FENCE_LINE_RE = re.compile(r" {0,3}(?:`{3,}|~{3,})")
THEMATIC_BREAK_RE = re.compile(
    r" {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$"
)
SETEXT_UNDERLINE_RE = re.compile(r" {0,3}(?:=+|-+)[ \t]*$")


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _closing_bracket(text: str, start: int) -> int | None:
    depth = 1
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "`":
            run = 1
            while index + run < len(text) and text[index + run] == "`":
                run += 1
            closing = _backtick_close(text, index, run)
            index = index + run if closing is None else closing
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _destination(text: str, open_paren: int) -> tuple[str, int, int, int] | None:
    index = open_paren + 1
    while index < len(text) and text[index] in ASCII_WHITESPACE:
        index += 1
    if index >= len(text):
        return None

    if text[index] == "<":
        start = index + 1
        index = start
        while index < len(text):
            if text[index] == ">" and not _is_escaped(text, index):
                target = text[start:index]
                return _destination_tail(text, index + 1, target, start, index)
            if text[index] in {"\n", "<"}:
                return None
            index += 1
        return None

    start = index
    target: list[str] = []
    nested = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            if text[index + 1] in ESCAPABLE:
                target.append(text[index + 1])
            else:
                target.extend((char, text[index + 1]))
            index += 2
            continue
        if char == "(":
            nested += 1
            target.append(char)
        elif char == ")":
            if nested == 0:
                return "".join(target), index + 1, start, index
            nested -= 1
            target.append(char)
        elif char in ASCII_WHITESPACE and nested == 0:
            return _destination_tail(text, index, "".join(target), start, index)
        else:
            target.append(char)
        index += 1
    return None


def _destination_tail(
    text: str,
    index: int,
    target: str,
    target_start: int,
    target_end: int,
) -> tuple[str, int, int, int] | None:
    had_whitespace = False
    while index < len(text) and text[index] in ASCII_WHITESPACE:
        had_whitespace = True
        index += 1
    if index >= len(text):
        return None
    if text[index] == ")":
        return target, index + 1, target_start, target_end
    if not had_whitespace or text[index] not in {'"', "'", "("}:
        return None

    closing = ")" if text[index] == "(" else text[index]
    index += 1
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text) and text[index + 1] in ESCAPABLE:
            index += 2
            continue
        if char == closing:
            index += 1
            break
        if closing == ")" and char == "(":
            return None
        index += 1
    else:
        return None

    while index < len(text) and text[index] in ASCII_WHITESPACE:
        index += 1
    if index < len(text) and text[index] == ")":
        return target, index + 1, target_start, target_end
    return None


def _line_end(text: str, index: int) -> int:
    end = text.find("\n", index)
    return len(text) if end == -1 else end


def _indent_columns(text: str, start: int, end: int) -> tuple[int, int]:
    columns = 0
    cursor = start
    while cursor < end:
        if text[cursor] == " ":
            columns += 1
        elif text[cursor] == "\t":
            columns += 4 - columns % 4
        else:
            break
        cursor += 1
    return columns, cursor


def _list_content_indent(text: str, start: int, end: int) -> int | None:
    indent, marker_start = _indent_columns(text, start, end)
    match = LIST_MARKER_RE.match(text, marker_start, end)
    if match is None:
        return None
    content_start = match.end()
    whitespace_columns = 0
    while content_start < end and text[content_start] in " \t":
        if text[content_start] == " ":
            whitespace_columns += 1
        else:
            whitespace_columns += 4 - (indent + len(match.group(0)) + whitespace_columns) % 4
        content_start += 1
    if whitespace_columns == 0:
        return None
    if whitespace_columns > 4:
        whitespace_columns = 1
    return indent + len(match.group(0)) + whitespace_columns


def _starts_nonparagraph_block(line: str) -> bool:
    return bool(
        ATX_HEADING_RE.match(line)
        or FENCE_LINE_RE.match(line)
        or THEMATIC_BREAK_RE.match(line)
        or SETEXT_UNDERLINE_RE.match(line)
        or re.match(r" {0,3}(?:>|</?(?:pre|script|style)(?:[ \t>]|$)|<!--)", line, re.I)
    )


def _list_marker_is_valid(text: str, start: int, indent: int) -> bool:
    current_start = start
    current_indent = indent
    while current_indent >= 4:
        cursor = current_start
        intervening_indents: list[int] = []
        found_outer = False
        while cursor > 0:
            previous_end = cursor - 1
            previous_start = text.rfind("\n", 0, previous_end) + 1
            if not text[previous_start:previous_end].strip():
                cursor = previous_start
                continue
            previous_indent, _ = _indent_columns(text, previous_start, previous_end)
            content_indent = _list_content_indent(text, previous_start, previous_end)
            if content_indent is not None and previous_indent < current_indent:
                if (
                    any(value < content_indent for value in intervening_indents)
                    or not content_indent <= current_indent < content_indent + 4
                ):
                    return False
                current_start = previous_start
                current_indent = previous_indent
                found_outer = True
                break
            intervening_indents.append(previous_indent)
            cursor = previous_start
        if not found_outer:
            return False
    return True


def _active_list_ancestor(
    text: str,
    index: int,
    columns: int,
) -> tuple[int, bool, int] | None:
    cursor = index
    crossed_blank = False
    intervening_indents: list[int] = []
    while cursor > 0:
        previous_end = cursor - 1
        previous_start = text.rfind("\n", 0, previous_end) + 1
        if not text[previous_start:previous_end].strip():
            crossed_blank = True
            cursor = previous_start
            continue
        previous_indent, _ = _indent_columns(text, previous_start, previous_end)
        content_indent = _list_content_indent(text, previous_start, previous_end)
        if content_indent is not None and previous_indent < columns:
            if (
                not _list_marker_is_valid(text, previous_start, previous_indent)
                or any(indent < content_indent for indent in intervening_indents)
                or columns < content_indent
            ):
                return None
            return content_indent, crossed_blank, previous_start
        intervening_indents.append(previous_indent)
        cursor = previous_start
    return None


def _indented_code_line(
    text: str,
    index: int,
    cache: dict[int, bool] | None = None,
) -> bool:
    if cache is not None and index in cache:
        return cache[index]

    def remember(value: bool) -> bool:
        if cache is not None:
            cache[index] = value
        return value

    line_end = _line_end(text, index)
    columns, _ = _indent_columns(text, index, line_end)
    if columns < 4:
        return remember(False)

    if index > 0 and cache is not None:
        previous_end = index - 1
        previous_start = text.rfind("\n", 0, previous_end) + 1
        if cache.get(previous_start) is True:
            return remember(True)

    list_context = _active_list_ancestor(text, index, columns)
    if list_context is not None:
        content_indent, crossed_blank, _ = list_context
        return remember(crossed_blank and columns >= content_indent + 4)

    cursor = index
    crossed_blank = False
    indents: list[int] = []
    while cursor > 0:
        previous_end = cursor - 1
        previous_start = text.rfind("\n", 0, previous_end) + 1
        previous_line = text[previous_start:previous_end]
        if not previous_line.strip():
            crossed_blank = True
            cursor = previous_start
            continue
        previous_indent, _ = _indent_columns(text, previous_start, previous_end)
        if not indents and _starts_nonparagraph_block(previous_line):
            return remember(True)
        indents.append(previous_indent)
        if previous_indent < 4:
            return remember(crossed_blank)
        cursor = previous_start
    return remember(crossed_blank or not indents or all(indent >= 4 for indent in indents))


def _backtick_close(text: str, index: int, run: int) -> int | None:
    cursor = index + run
    while cursor < len(text):
        cursor = text.find("`", cursor)
        if cursor == -1:
            return None
        closing_run = 1
        while cursor + closing_run < len(text) and text[cursor + closing_run] == "`":
            closing_run += 1
        if closing_run == run:
            return cursor + closing_run
        cursor += closing_run
    return None


def _label_has_nested_link(text: str, start: int, close: int) -> bool:
    index = start + 1
    while index < close:
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == "`":
            run = 1
            while index + run < close and text[index + run] == "`":
                run += 1
            closing = _backtick_close(text, index, run)
            index = index + run if closing is None or closing > close else closing
            continue
        if text[index] == "[" and not _is_escaped(text, index):
            image = index > start and text[index - 1] == "!" and not _is_escaped(text, index - 1)
            nested_close = _closing_bracket(text, index)
            if (
                not image
                and nested_close is not None
                and nested_close < close
                and nested_close + 1 < close
                and text[nested_close + 1] == "("
            ):
                parsed = _destination(text, nested_close + 1)
                if parsed is not None and parsed[1] <= close:
                    return True
        index += 1
    return False


def _quote_prefix(text: str, index: int, line_end: int) -> tuple[int, int]:
    indent, cursor = _indent_columns(text, index, line_end)
    if indent > 3 or cursor >= line_end or text[cursor] != ">":
        return 0, cursor
    quote_depth = 0
    while cursor < line_end and text[cursor] == ">":
        quote_depth += 1
        cursor += 1
        if cursor < line_end and text[cursor] in " \t":
            cursor += 1
        quote_indent, next_cursor = _indent_columns(text, cursor, line_end)
        if quote_indent <= 3 and next_cursor < line_end and text[next_cursor] == ">":
            cursor = next_cursor
            continue
        if quote_indent > 3:
            return quote_depth, cursor
        cursor = next_cursor
        break
    return quote_depth, cursor


def _fence_line_parts(
    text: str,
    index: int,
    line_end: int,
) -> tuple[str, int, str, tuple[str, int, int]] | None:
    indent, cursor = _indent_columns(text, index, line_end)
    container = ("top", 0, 0)
    quote_depth, quote_cursor = _quote_prefix(text, index, line_end)
    if quote_depth:
        cursor = quote_cursor
        container = ("quote", quote_depth, 0)
    else:
        list_context = _active_list_ancestor(text, index, indent)
        if list_context is not None and indent < list_context[0] + 4:
            container = ("list", list_context[2], list_context[0])
        elif indent >= 4:
            return None

    if cursor >= line_end or text[cursor] not in {"`", "~"}:
        return None
    marker = text[cursor]
    run = 1
    while cursor + run < line_end and text[cursor + run] == marker:
        run += 1
    if run < 3:
        return None
    return marker, run, text[cursor + run : line_end], container


def _line_in_fence_container(
    text: str,
    index: int,
    line_end: int,
    container: tuple[str, int, int],
) -> bool:
    kind, identity, content_indent = container
    if kind == "top":
        return True
    if kind == "quote":
        quote_depth, _ = _quote_prefix(text, index, line_end)
        return quote_depth >= identity
    if not text[index:line_end].strip():
        return True
    indent, _ = _indent_columns(text, index, line_end)
    return indent >= content_indent


def iter_inline_links(markdown: str):
    """Yield destination text and source spans, excluding images and code/comments."""
    index = 0
    fence: tuple[str, int, tuple[str, int, int]] | None = None
    indented_code_cache: dict[int, bool] = {}
    line_start = True
    while index < len(markdown):
        if line_start:
            line_end = _line_end(markdown, index)
            line_indent, _ = _indent_columns(markdown, index, line_end)
            fence_line = _fence_line_parts(markdown, index, line_end)
            if fence is not None and _line_in_fence_container(
                markdown, index, line_end, fence[2]
            ):
                if (
                    fence_line is not None
                    and fence[0] == fence_line[0]
                    and fence_line[1] >= fence[1]
                    and (fence[2][0] == "list" or fence[2] == fence_line[3])
                    and (
                        fence[2][0] != "list"
                        or line_indent < fence[2][2] + 4
                    )
                    and not fence_line[2].strip(" \t\r")
                ):
                    fence = None
                index = len(markdown) if line_end == len(markdown) else line_end + 1
                line_start = True
                continue
            if fence is not None:
                fence = None
            if fence_line is not None and not (
                fence_line[0] == "`" and "`" in fence_line[2]
            ):
                fence = fence_line[0], fence_line[1], fence_line[3]
                index = len(markdown) if line_end == len(markdown) else line_end + 1
                line_start = True
                continue
            if _indented_code_line(markdown, index, indented_code_cache):
                index = len(markdown) if line_end == len(markdown) else line_end + 1
                line_start = True
                continue
        if markdown.startswith("<!--", index):
            end = markdown.find("-->", index + 4)
            index = len(markdown) if end == -1 else end + 3
            line_start = index > 0 and markdown[index - 1] == "\n"
            continue
        if markdown[index] == "`":
            run = 1
            while index + run < len(markdown) and markdown[index + run] == "`":
                run += 1
            closing = _backtick_close(markdown, index, run)
            index = index + run if closing is None else closing
            line_start = index > 0 and markdown[index - 1] == "\n"
            continue
        if markdown[index] == "[" and not _is_escaped(markdown, index):
            image = index > 0 and markdown[index - 1] == "!" and not _is_escaped(markdown, index - 1)
            close = _closing_bracket(markdown, index)
            if close is not None and close + 1 < len(markdown) and markdown[close + 1] == "(":
                if not image and _label_has_nested_link(markdown, index, close):
                    index += 1
                    continue
                parsed = _destination(markdown, close + 1)
                if parsed is not None:
                    target, index, target_start, target_end = parsed
                    if target and not image:
                        yield target, target_start, target_end
                    line_start = index > 0 and markdown[index - 1] == "\n"
                    continue
        line_start = markdown[index] == "\n"
        index += 1


def iter_inline_link_targets(markdown: str):
    """Yield rendered inline-link destinations, excluding images and code/comments."""
    for target, _, _ in iter_inline_links(markdown):
        yield target
