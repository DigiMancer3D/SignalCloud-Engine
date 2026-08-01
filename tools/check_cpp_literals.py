#!/usr/bin/env python3
"""Catch physical newlines inside ordinary C/C++ string and character literals.

The normal core-only test build does not compile the SDL game target. This
small lexical gate catches the exact malformed-source class that escaped A3a2
without requiring SDL headers or linking the native executable.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LiteralIssue:
    path: Path
    line: int
    column: int
    message: str


def scan_cpp_literals(path: Path) -> list[LiteralIssue]:
    text = path.read_text(encoding="utf-8")
    issues: list[LiteralIssue] = []
    state = "code"
    quote_line = 0
    quote_col = 0
    raw_end = ""
    line = 1
    col = 0
    index = 0

    while index < len(text):
        ch = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        col += 1

        if state == "code":
            if ch == "/" and nxt == "/":
                state = "line_comment"
                index += 1
                col += 1
            elif ch == "/" and nxt == "*":
                state = "block_comment"
                index += 1
                col += 1
            elif ch == "R" and nxt == '"':
                open_paren = text.find("(", index + 2, index + 20)
                if open_paren != -1:
                    delimiter = text[index + 2:open_paren]
                    raw_end = ")" + delimiter + '"'
                    state = "raw"
                    consumed = open_paren - index
                    index = open_paren
                    col += consumed
            elif ch == '"':
                state = "string"
                quote_line, quote_col = line, col
            elif ch == "'":
                previous = text[index - 1] if index else ""
                # C++14 digit separators (for example 8'000'000) are not
                # character literals.
                if previous.isalnum() and nxt.isalnum():
                    pass
                else:
                    state = "char"
                    quote_line, quote_col = line, col
        elif state == "line_comment":
            if ch == "\n":
                state = "code"
        elif state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                index += 1
                col += 1
        elif state == "raw":
            if raw_end and text.startswith(raw_end, index):
                index += len(raw_end) - 1
                col += len(raw_end) - 1
                state = "code"
                raw_end = ""
        elif state in {"string", "char"}:
            if ch == "\\":
                index += 1
                if index < len(text):
                    escaped = text[index]
                    col += 1
                    if escaped == "\n":
                        line += 1
                        col = 0
            elif (state == "string" and ch == '"') or (state == "char" and ch == "'"):
                state = "code"
            elif ch == "\n":
                issues.append(
                    LiteralIssue(
                        path,
                        quote_line,
                        quote_col,
                        f"physical newline inside unterminated {state} literal",
                    )
                )
                state = "code"

        if ch == "\n":
            line += 1
            col = 0
        index += 1

    if state in {"string", "char"}:
        issues.append(LiteralIssue(path, quote_line, quote_col, f"unterminated {state} literal at end of file"))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    all_issues: list[LiteralIssue] = []
    for path in args.paths:
        all_issues.extend(scan_cpp_literals(path))
    for issue in all_issues:
        print(f"{issue.path}:{issue.line}:{issue.column}: error: {issue.message}")
    if all_issues:
        return 1
    print(f"PASS: C/C++ literal preflight ({len(args.paths)} file(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
