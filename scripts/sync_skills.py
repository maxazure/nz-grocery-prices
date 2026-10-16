#!/usr/bin/env python3
"""Copy the canonical agent skill into each agent's discovery folder.

Source of truth: skills/nz-grocery-prices/
Copies (real files, not symlinks, so Windows checkouts and tools that
resolve symlinks still work):

    .claude/skills/nz-grocery-prices/     Claude Code (project skill)
    .agents/skills/nz-grocery-prices/     OpenAI Codex (repo skill)
    .workbuddy/skills/nz-grocery-prices/  Tencent WorkBuddy (project skill)

Usage:
    python3 scripts/sync_skills.py           # write the copies
    python3 scripts/sync_skills.py --check   # exit 1 if any copy is out of date
    python3 scripts/sync_skills.py --zip     # also build dist/nz-grocery-prices-skill.zip
                                             # (SKILL.md at the zip root, for WorkBuddy "Upload Skill")
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = "nz-grocery-prices"
SOURCE = ROOT / "skills" / SKILL
TARGETS = [
    ROOT / ".claude" / "skills" / SKILL,
    ROOT / ".agents" / "skills" / SKILL,
    ROOT / ".workbuddy" / "skills" / SKILL,
]
ZIP_PATH = ROOT / "dist" / f"{SKILL}-skill.zip"
IGNORE = {"__pycache__", ".DS_Store"}


def skill_files(base: Path) -> list[Path]:
    files = []
    for path in sorted(base.rglob("*")):
        if any(part in IGNORE or part.endswith(".pyc") for part in path.relative_to(base).parts):
            continue
        if path.is_file():
            files.append(path.relative_to(base))
    return files


def differences(target: Path) -> list[str]:
    if not target.is_dir():
        return [f"{target.relative_to(ROOT)} is missing"]
    problems = []
    src, dst = set(skill_files(SOURCE)), set(skill_files(target))
    for rel in sorted(src - dst):
        problems.append(f"{target.relative_to(ROOT)}/{rel} is missing")
    for rel in sorted(dst - src):
        problems.append(f"{target.relative_to(ROOT)}/{rel} is not in the canonical skill")
    for rel in sorted(src & dst):
        if not filecmp.cmp(SOURCE / rel, target / rel, shallow=False):
            problems.append(f"{target.relative_to(ROOT)}/{rel} differs from skills/{SKILL}/{rel}")
    return problems


def sync() -> None:
    for target in TARGETS:
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns(*IGNORE, "*.pyc"))
        print(f"synced {target.relative_to(ROOT)}")


def build_zip() -> None:
    ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel in skill_files(SOURCE):
            info = zipfile.ZipInfo(rel.as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ((0o755 if rel.suffix == ".py" else 0o644) << 16)
            archive.writestr(info, (SOURCE / rel).read_bytes())
    print(f"wrote {ZIP_PATH.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Only verify the copies match")
    parser.add_argument("--zip", action="store_true", help="Also build the WorkBuddy upload zip")
    args = parser.parse_args(argv)
    if args.check:
        problems = [p for target in TARGETS for p in differences(target)]
        for problem in problems:
            print(problem, file=sys.stderr)
        if problems:
            print("Run: python3 scripts/sync_skills.py", file=sys.stderr)
            return 1
        print("skill copies are in sync")
        return 0
    sync()
    if args.zip:
        build_zip()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
