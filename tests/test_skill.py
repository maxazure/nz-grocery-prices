"""The agent skill: copies in sync, frontmatter valid, helper script works."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

from nzgrocery.output import write_rows

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "nz-grocery-prices"


def _load_sync():
    spec = importlib.util.spec_from_file_location("sync_skills", ROOT / "scripts" / "sync_skills.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    block = text.split("\n---\n", 1)[0][4:]
    fields = {}
    for line in block.splitlines():
        match = re.match(r"^([a-z][a-z0-9_-]*):\s*(.*)$", line)
        if match:
            fields[match.group(1)] = match.group(2)
    return fields


def test_agent_copies_match_canonical_skill():
    sync = _load_sync()
    problems = [p for target in sync.TARGETS for p in sync.differences(target)]
    assert not problems, "\n".join(problems) + "\nRun: python3 scripts/sync_skills.py"


def test_skill_frontmatter_follows_agent_skills_spec():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    fields = _frontmatter(text)
    assert fields["name"] == SKILL_DIR.name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fields["name"]) and len(fields["name"]) <= 64
    assert 0 < len(fields["description"]) <= 1024
    allowed = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    assert set(fields) <= allowed, f"non-portable frontmatter keys: {set(fields) - allowed}"
    assert len(text.splitlines()) < 500


def test_skill_is_local_first():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "Local first" in text
    assert "nz-grocery-prices status" in text


def test_skill_links_resolve():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for link in re.findall(r"\]\(((?:references|scripts)/[^)]+)\)", text):
        assert (SKILL_DIR / link).is_file(), link


def test_latest_prices_script(tmp_path):
    db = tmp_path / "prices.sqlite"
    base = {
        "chain": "newworld", "store_id": "773ad0a0-024e-46c5-a94b-df1cf86d25cc", "store": "New World Albany",
        "department": "produce", "category": "Fruit & Veg / Fruit", "unit_or_size": "kg",
        "price_per": "$3.99 / 1kg", "product_url": "https://example.invalid", "product_id": "133211",
    }
    write_rows([{**base, "fetched_at": "2026-10-11T08:00:00+13:00", "name": "Bananas Yellow Loose",
                 "price_nzd": 4.29, "raw_price_text": "$4.29"}], "sqlite", db)
    write_rows([{**base, "fetched_at": "2026-10-12T08:00:00+13:00", "name": "Bananas Yellow Loose",
                 "price_nzd": 3.99, "raw_price_text": "$3.99"}], "sqlite", db)
    script = SKILL_DIR / "scripts" / "latest_prices.py"
    result = subprocess.run(
        [sys.executable, str(script), str(db), "--chain", "newworld", "--store", "Albany",
         "--search", "banana", "--json"],
        capture_output=True, text=True, check=True,
    )
    rows = json.loads(result.stdout)
    assert [row["price_nzd"] for row in rows] == [3.99]
    assert rows[0]["fetched_at"].startswith("2026-10-12")
