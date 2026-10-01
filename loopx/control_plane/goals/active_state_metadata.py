from __future__ import annotations

import json
import re
from html import escape, unescape

from .active_state_sections import active_state_sections


USER_TODO_HEADER_MARKERS = (
    "user todo",
    "owner review reading queue",
    "owner reading queue",
)
AGENT_TODO_HEADER_MARKERS = (
    "agent todo",
    "codex todo",
    "project agent todo",
)
TODO_ARCHIVE_HEADER_MARKERS = (
    "todo archive",
    "work archive",
    "completed archive",
    "completed work",
    "完成归档",
    "待办归档",
)


def markdown_frontmatter_string(value: str) -> str:
    encoded = json.dumps(value, ensure_ascii=False)
    for separator in ("\x85", "\u2028", "\u2029"):
        encoded = encoded.replace(separator, f"\\u{ord(separator):04x}")
    return encoded


def markdown_blockquote(value: str) -> str:
    return "\n".join(f"> {escape(line, quote=False)}" for line in value.splitlines())


def active_state_section_text(state_text: str, heading: str) -> str:
    _, body = split_state_frontmatter(state_text)
    sections = active_state_sections(
        body, (heading,), section_heading_pattern=re.compile(r"^## (.+?)[ \t]*$"),
    )
    section_lines = [line for line in sections[heading] if line]
    if heading == "Objective" and section_lines and all(
        line.startswith("> ") for line in section_lines
    ):
        text = " ".join(unescape(line[2:]) for line in section_lines)
    else:
        text = " ".join(
            line.strip().removeprefix("- ").strip()
            for line in section_lines
            if line.strip() and not line.lstrip().startswith("<!--")
        )
    return " ".join(text.split())


def split_state_frontmatter(state_text: str) -> tuple[dict[str, str], str]:
    """Decode generated string metadata; retain the legacy unquoted input form."""
    match = re.match(r"\A---[ \t]*\r?\n(.*?)^---[ \t]*(?:\r?\n|\Z)", state_text, re.M | re.S)
    if match is None:
        return {}, state_text
    result: dict[str, str] = {}
    # JSON strings may contain Unicode separators: only physical LF ends a field.
    for line in match.group(1).split("\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.startswith('"'):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                pass  # Legacy writers did not escape backslashes as JSON.
            else:
                if isinstance(decoded, str):
                    result[key.strip()] = decoded
                    continue
        result[key.strip()] = value.strip('"')
    return result, state_text[match.end():]


def parse_state_frontmatter(state_text: str) -> dict[str, str]:
    return split_state_frontmatter(state_text)[0]


def todo_role_for_heading(heading: str) -> str | None:
    normalized = heading.strip().lower()
    if any(marker in normalized for marker in TODO_ARCHIVE_HEADER_MARKERS):
        return None
    if any(marker in normalized for marker in USER_TODO_HEADER_MARKERS):
        return "user"
    if any(marker in normalized for marker in AGENT_TODO_HEADER_MARKERS):
        return "agent"
    return None
