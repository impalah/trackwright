"""S-12: the Cubase script must stay ES5. Node runs modern JavaScript, so the other script tests would
pass with ES2015+ syntax that the MIDI Remote engine in Cubase rejects. This test strips comments,
strings and regular expressions and looks for syntax that ES5 does not have."""

from __future__ import annotations

import re

import pytest

from trackwright.cubase import SCRIPT_PATH

FORBIDDEN = {
    "let declaration": r"\blet\s+[A-Za-z_$]",
    "const declaration": r"\bconst\s+[A-Za-z_$]",
    "arrow function": r"=>",
    "class": r"\bclass\s+[A-Za-z_$]",
    "template literal": r"`",
    "spread or rest": r"\.\.\.",
    "for...of": r"\bfor\s*\([^)]*\bof\b",
    "default parameter": r"\bfunction\s*[A-Za-z_$]*\s*\([^)]*=",
    "object method shorthand": (
        r"^\s*(?!(?:if|for|while|switch|catch|function|with)\b)[A-Za-z_$][\w$]*\s*\([^)]*\)\s*\{"
    ),
}


def code_only(source: str) -> str:
    """The script without comments, string literals and regular expression literals."""
    out = []
    i, n = 0, len(source)
    previous = ""
    while i < n:
        c = source[i]
        if source.startswith("//", i):
            i = source.find("\n", i)
            i = n if i < 0 else i
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif c in "'\"":
            j = i + 1
            while j < n and source[j] != c:
                j += 2 if source[j] == "\\" else 1
            out.append('""')
            i = j + 1
        elif c == "/" and previous in "(,=:[!&|?{};" and previous != "":
            j = i + 1
            while j < n and source[j] != "/":
                j += 2 if source[j] == "\\" else 1
            out.append("/r/")
            i = j + 1
        else:
            out.append(c)
            if not c.isspace():
                previous = c
            i += 1
    return "".join(out)


@pytest.mark.parametrize(("name", "pattern"), sorted(FORBIDDEN.items()))
def test_script_has_no_es2015_syntax(name: str, pattern: str) -> None:
    code = code_only(SCRIPT_PATH.read_text(encoding="utf-8"))
    hits = [line.strip() for line in code.splitlines() if re.search(pattern, line)]
    assert hits == [], f"{name} is not ES5: {hits[:3]}"


def test_the_checker_catches_modern_syntax() -> None:
    modern = "var a = `x`\nlet b = 1\nvar f = (x) => x\n// let c = 2\nvar s = 'const d = 3'\n"
    code = code_only(modern)
    found = {name for name, pattern in FORBIDDEN.items() if re.search(pattern, code, re.M)}
    assert found == {"template literal", "let declaration", "arrow function"}
