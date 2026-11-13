"""Manage tests/frozen.lock (sha256 of each frozen test file, CRLF normalised to LF).

  python tools/freeze_tests.py <paths...>   add or refresh entries
  python tools/freeze_tests.py --list       show entries
  python tools/freeze_tests.py --check      exit 1 on any mismatch or missing file
"""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "tests" / "frozen.lock"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read_lock() -> dict[str, str]:
    if not LOCK.exists():
        return {}
    return {
        line.split("  ", 1)[1]: line.split("  ", 1)[0]
        for line in LOCK.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def main(args: list[str]) -> int:
    lock = read_lock()
    if args == ["--list"]:
        for p, h in sorted(lock.items()):
            print(f"{h}  {p}")
        return 0
    if args == ["--check"]:
        bad = [p for p, h in lock.items() if not (ROOT / p).exists() or digest(ROOT / p) != h]
        for p in bad:
            print(f"MISMATCH or missing: {p}")
        return 1 if bad else 0
    if not args or args[0].startswith("-"):
        print(__doc__)
        return 2
    for a in args:
        f = Path(a).resolve()
        rel = f.relative_to(ROOT).as_posix()
        lock[rel] = digest(f)
    LOCK.write_text("".join(f"{h}  {p}\n" for p, h in sorted(lock.items())), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
