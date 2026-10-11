"""Every preset's QASM and Qiskit text (public/presets.json) builds the preset's own circuit."""
import json
import os
import sys

import pytest
from qiskit.quantum_info import Operator

from landfall import circuits, qiskit_input

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from export_presets import OUT, build

with open(OUT, encoding="utf-8") as fh:
    SAVED = {p["name"]: p for p in json.load(fh)}


def test_presets_file_is_up_to_date():
    assert list(SAVED.values()) == build(), "public/presets.json is stale: run python scripts/export_presets.py"


def test_every_preset_is_listed():
    assert {name: p["description"] for name, p in SAVED.items()} == circuits.PRESETS


@pytest.mark.parametrize("name", list(circuits.PRESETS))
@pytest.mark.parametrize("form", ["qasm", "qiskit"])
def test_text_matches_builder(name, form):
    text = SAVED[name][form]
    parsed = circuits.from_qasm(text) if form == "qasm" else qiskit_input.parse(text)
    builder = circuits.from_preset(name)
    assert parsed.num_qubits == builder.num_qubits
    assert Operator(parsed).equiv(Operator(builder)), f"{name} {form} is not the preset's circuit"
