"""Pre-commit encoding check -- fail if any scripts/*.py contains non-ASCII bytes.

Usage:
    python scripts/_check_encoding.py          # check scripts/ directory
    python scripts/_check_encoding.py path/... # check specific paths

Exit code: 0 = clean, 1 = violations found.

Install as a git pre-commit hook:
    echo 'python scripts/_check_encoding.py' > .git/hooks/pre-commit
    (on Windows use the shell appropriate for your git install)
"""
from __future__ import annotations

import pathlib
import sys


def check(paths) -> list[tuple[str, int, str]]:
    violations = []
    for p in paths:
        p = pathlib.Path(p)
        if p.is_dir():
            targets = list(p.glob("*.py"))
        else:
            targets = [p]
        for f in sorted(targets):
            try:
                text = f.read_text(encoding="utf-8")
            except Exception as e:
                violations.append((str(f), 0, f"read error: {e}"))
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if any(ord(c) > 127 for c in line):
                    violations.append((str(f), lineno, line.strip()[:80]))
    return violations


def main() -> int:
    paths = sys.argv[1:] or ["scripts"]
    violations = check(paths)
    if violations:
        print(f"[check_encoding] {len(violations)} non-ASCII line(s) found:")
        for fname, lineno, line in violations:
            safe = line.encode("ascii", errors="replace").decode()
            print(f"  {fname}:{lineno}: {safe}")
        print("[check_encoding] Replace Unicode symbols with ASCII equivalents.")
        return 1
    print(f"[check_encoding] Clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
