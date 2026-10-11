"""Qiskit tab parser: supported code builds the same unitary as real Qiskit; everything else is rejected.

Only these tests run the snippets with real Qiskit (exec), to get the reference circuit. The parser
itself never executes user code.
"""
import re
from pathlib import Path

import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator

from landfall import qiskit_input
from landfall.qiskit_input import SUGGEST, QiskitInputError, parse

VALID = {
    "bell_with_measure": """
from qiskit import QuantumCircuit
qc = QuantumCircuit(2, 2)
qc.h(0)
qc.cx(0, 1)
qc.measure([0, 1], [0, 1])
""",
    "ghz_loop": """
from qiskit import QuantumCircuit
n = 5
qc = QuantumCircuit(n)
qc.h(0)
for i in range(n - 1):
    qc.cx(i, i + 1)
qc.barrier()
qc.measure_all()
qc.draw()
""",
    "rotations_and_pi": """
from math import pi
import math
import numpy as np
from qiskit import QuantumCircuit
circ = QuantumCircuit(3)
circ.rx(pi / 4, 0)
circ.ry(-math.pi / 3, 1)
circ.rz(2 * np.pi / 7, 2)
circ.p(pi ** 0.5, 0)
circ.u(pi / 2, 0.1, -0.2, 1)
circ.cp(pi / 8, 0, 2)
circ.crx(0.3, 1, 0)
circ.cry(0.4, 2, 1)
circ.crz(-0.5, 0, 1)
circ.rxx(0.6, 0, 1)
circ.ryy(0.7, 1, 2)
circ.rzz(0.8, 0, 2)
circ.sx(1); circ.s(0); circ.sdg(1); circ.t(2); circ.tdg(0); circ.y(1); circ.z(2); circ.x(0)
""",
    "multi_qubit_and_broadcast": """
from qiskit import QuantumCircuit
qc = QuantumCircuit(4)
qc.h(range(4))
qc.ccx(0, 1, 2)
qc.cswap(3, 0, 1)
qc.swap(2, 3)
qc.cy(0, 3)
qc.cz(1, 2)
qc.ch(2, 0)
qc.x([0, 2])
qc.cx([0, 1], [2, 3])
print(qc)
qc
""",
    "qft_and_nested_loops": """
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFTGate
from numpy import pi
qc = QuantumCircuit(6)
for i in range(3):
    for j in range(i + 1, 6):
        qc.cp(pi / 2 ** (j - i), i, j)
qc.append(QFTGate(4), range(4))
qc.append(QFTGate(2), [5, 4])
for k in range(0, 6, 2):
    qc.rz(k * pi / 16 + 0.1, (k + 1) % 6)
    qc.ry(-k // 3 * 0.25, -1)
""",
}

MALICIOUS = {
    "import os": "import os",
    "from os import system": "from os import system",
    "import subprocess": "import subprocess",
    "star import": "from qiskit import *",
    "__import__": "__import__('os').system('echo hi')",
    "open()": "open('/etc/passwd')",
    "exec": "exec('print(1)')",
    "eval": "eval('1+1')",
    "dunder attribute": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.__class__",
    "dunder chain call": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\n"
                         "qc.__class__.__bases__[0].__subclasses__()",
    "dunder in assignment": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nx = qc.__class__",
    "getattr": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\ngetattr(qc, 'h')(0)",
    "lambda": "f = lambda: 0",
    "def": "def f():\n    pass",
    "class": "class A:\n    pass",
    "while True": "while True:\n    pass",
    "try": "try:\n    pass\nexcept Exception:\n    pass",
    "with open": "with open('x') as f:\n    pass",
    "huge range": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nfor i in range(10**9):\n    qc.h(0)",
    "nested loops over the cap": "for i in range(10000):\n    for j in range(10000):\n        pass",
    "huge power": "x = 9 ** 9 ** 9",
    "huge broadcast": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.h(range(10**8))",
    "star argument": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.h(*[0])",
    "comprehension": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.h([i for i in range(2)])",
    "string argument": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.h('0')",
    "conditional expression": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.h(0) if True else None",
    "call inside print": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nprint(open('x'))",
    "call inside draw": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.draw(output=__import__('os'))",
    "unsupported method": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.save_statevector()",
    "keyword arguments": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.cx(control_qubit=0, target_qubit=1)",
    "13 qubits": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(13)",
    "million qubits": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(10**6)",
    "over 5,000 gates": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nfor i in range(5001):\n    qc.h(0)",
    "qubit out of range": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.h(5)",
    "syntax error": "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2",
}


def _reference(code):
    """Run the snippet with real Qiskit (tests only) and keep its unitary part."""
    namespace = {}
    exec(code, namespace)
    real = next(v for v in namespace.values() if isinstance(v, QuantumCircuit))
    out = QuantumCircuit(real.num_qubits)
    for inst in real.data:
        if inst.operation.name not in ("measure", "barrier"):
            out.append(inst.operation, [real.find_bit(q).index for q in inst.qubits])
    return out


@pytest.mark.parametrize("name", VALID)
def test_valid_code_matches_real_qiskit(name, capsys):
    code = VALID[name]
    parsed = parse(code)
    reference = _reference(code)
    assert parsed.num_qubits == reference.num_qubits
    assert Operator(parsed).equiv(Operator(reference)), name


CAPS = {"13 qubits", "million qubits", "over 5,000 gates"}  # the QASM tab has the same caps, so no suggestion


@pytest.mark.parametrize("name", MALICIOUS)
def test_unsupported_code_is_rejected(name):
    with pytest.raises(QiskitInputError) as info:
        parse(MALICIOUS[name])
    message = str(info.value)
    assert message.startswith("Line "), message
    assert (SUGGEST in message) == (name not in CAPS), message


def test_rejection_names_line_and_construct():
    with pytest.raises(QiskitInputError) as info:
        parse("from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nwhile True:\n    qc.h(0)")
    assert str(info.value).startswith("Line 3: `while True: qc.h(0)` (while loop) is not supported")


def test_missing_circuit():
    with pytest.raises(QiskitInputError, match="No circuit found"):
        parse("from math import pi\nx = pi / 2")


def test_parser_never_executes_code():
    source = Path(qiskit_input.__file__).read_text()
    assert not re.search(r"\b(exec|eval|compile|__import__)\s*\(", source)
