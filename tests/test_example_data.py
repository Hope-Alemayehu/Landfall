"""The precomputed example the website shows on first load must match a live analysis."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from export_example import OUT, build


def test_example_is_up_to_date():
    with open(OUT, encoding="utf-8") as fh:
        saved = json.load(fh)
    fresh = json.loads(json.dumps(build()))
    saved.pop("elapsed_s")
    fresh.pop("elapsed_s")
    assert saved == fresh, "public/data/adder.json is stale: run python scripts/export_example.py"
