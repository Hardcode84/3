#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pre-commit hook that sorts file and library lists in CMake files.

Sorts the positional argument blocks of known CMake commands
(e.g. add_library, target_link_libraries) without reformatting anything else.

Use ``# cmake-sort: off`` / ``# cmake-sort: on`` to guard regions that
should not be touched.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# CMake keywords that start a new argument section and act as block
# separators.  Entries are matched case-insensitively.
_KEYWORDS: set[str] = {
    "ADDITIONAL_HEADER_DIRS",
    "ADD_TO_PARENT",
    "CACHE",
    "COMMON_CAPI_LINK_LIBS",
    "DECLARED_SOURCES",
    "DEPENDS",
    "DIALECT_NAME",
    "EMBED_CAPI_LINK_LIBS",
    "EXCLUDE_FROM_LIBMLIR",
    "IMPORTED",
    "INSTALL_COMPONENT",
    "INSTALL_DESTINATION",
    "INSTALL_PREFIX",
    "INTERFACE",
    "LINK_LIBS",
    "MODULE",
    "MODULE_NAME",
    "OBJECT",
    "OUTPUT_DIRECTORY",
    "PRIVATE",
    "PRIVATE_LINK_LIBS",
    "PUBLIC",
    "RELATIVE_INSTALL_ROOT",
    "ROOT_DIR",
    "ROOT_PREFIX",
    "SHARED",
    "SOURCES",
    "STATIC",
}

# Commands whose argument lists we consider sortable.
_SORTABLE_COMMANDS: re.Pattern[str] = re.compile(
    r"""
    ^\s*(?:
        add_library
      | add_executable
      | add_mlir_library
      | add_mlir_dialect_library
      | add_mlir_public_c_api_library
      | add_llvm_executable
      | target_link_libraries
      | target_sources
      | set
    )\s*\(
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _is_keyword(token: str) -> bool:
    return token in _KEYWORDS


def _is_sortable_value(token: str) -> bool:
    """Return True if *token* looks like a plain value (file or lib name)."""
    # Skip cmake variables, generator expressions, flags, paths with
    # slashes (directory args), and quoted strings.
    if token.startswith(("$", "-", '"')):
        return False
    if "/" in token:
        return False
    return True


def _sort_block(lines: list[str]) -> list[str]:
    """Sort a contiguous block of plain-value lines, preserving indent."""
    if len(lines) <= 1:
        return lines
    # Detect indent from first line.
    indent = len(lines[0]) - len(lines[0].lstrip())
    # Stable-sort by stripped content, case-insensitive.
    return sorted(lines, key=lambda l: l.strip().lower())


def _process_command(body_lines: list[str]) -> list[str]:
    """Given the *body* lines of a command invocation, sort each block."""
    result: list[str] = []
    current_block: list[str] = []

    def flush() -> None:
        result.extend(_sort_block(current_block))
        current_block.clear()

    for line in body_lines:
        stripped = line.strip()

        # Empty lines or closing paren act as block separators.
        # Also catch values with a trailing ")" glued on (e.g. "Impl)").
        if not stripped or stripped.endswith(")"):
            flush()
            result.append(line)
            continue

        # Keyword line -- flush previous block, emit as-is.
        first_token = stripped.split()[0].rstrip(")")
        if _is_keyword(first_token):
            flush()
            result.append(line)
            continue

        # Comment lines break the block (they might be section headers).
        if stripped.startswith("#"):
            flush()
            result.append(line)
            continue

        # Check if this is a sortable value.
        if _is_sortable_value(first_token):
            current_block.append(line)
        else:
            # Non-sortable value (variable, path, flag) -- flush and
            # pass through.
            flush()
            result.append(line)

    flush()
    return result


def process_file(path: Path) -> bool:
    """Process a single CMake file.  Return True if it was modified."""
    text = path.read_text()
    lines = text.splitlines(keepends=True)

    out: list[str] = []
    i = 0
    changed = False
    sorting_enabled = True

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Respect disable/enable guards.
        if stripped == "# cmake-sort: off":
            sorting_enabled = False
            out.append(line)
            i += 1
            continue
        if stripped == "# cmake-sort: on":
            sorting_enabled = True
            out.append(line)
            i += 1
            continue

        if not sorting_enabled or not _SORTABLE_COMMANDS.match(line):
            out.append(line)
            i += 1
            continue

        # Collect the full command invocation (until balanced parens).
        cmd_lines: list[str] = [line]
        depth = line.count("(") - line.count(")")
        i += 1
        while i < len(lines) and depth > 0:
            cmd_lines.append(lines[i])
            depth += lines[i].count("(") - lines[i].count(")")
            i += 1

        # Skip commands that contain bracket arguments ([=[ ... ]=]) --
        # these are multi-line string literals (e.g. embedded C code).
        cmd_text = "".join(cmd_lines)
        if "[=[" in cmd_text or "]=]" in cmd_text:
            out.extend(cmd_lines)
            continue

        # First line is the command header (name + first arg like target
        # name).  Last line typically just has ")".  Sort the body in
        # between.
        if len(cmd_lines) <= 2:
            out.extend(cmd_lines)
            continue

        header = cmd_lines[0]
        body = cmd_lines[1:]
        sorted_body = _process_command(body)

        out.append(header)
        if sorted_body != body:
            changed = True
        out.extend(sorted_body)

    if changed:
        path.write_text("".join(out))
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="CMake files to process.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if files would change, but do not modify them.",
    )
    args = parser.parse_args()

    failed: list[Path] = []
    for path in args.files:
        if not path.is_file():
            continue
        if process_file(path):
            failed.append(path)

    if failed:
        verb = "would be sorted" if args.check else "sorted"
        for p in failed:
            print(f"{verb}: {p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
