"""Write public/data/adder.json: the API response for the adder preset on the default devices.

The website shows it on first load, so visitors see results without waiting for the function to
start. Rerun this after changing the analysis (tests/test_example_data.py fails when it is stale).

Usage: python scripts/export_example.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api.index import AnalyzeRequest, analyze

OUT = os.path.join(ROOT, "public", "data", "adder.json")


def build():
    """Exactly what POST /api/analyze {"preset": "adder"} returns."""
    return analyze(AnalyzeRequest(preset="adder"))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(build(), fh, separators=(",", ":"))
    print(f"wrote {os.path.relpath(OUT, ROOT)} ({os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
