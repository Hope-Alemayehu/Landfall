"""Write public/presets.json: every preset's source as readable OpenQASM 2 and as Qiskit code.

The website loads it so clicking a preset shows (and lets you edit) its code. qft5 is written out
with H, controlled phases and swaps; random_ct is generated from its seeded builder.
tests/test_presets.py checks that every text matches its preset's circuit.

Usage: python scripts/export_presets.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from landfall import circuits

OUT = os.path.join(ROOT, "public", "presets.json")
QASM_HEAD = 'OPENQASM 2.0;\ninclude "qelib1.inc";\n'


def _qft_qasm(n=5):
    lines = [f"// {circuits.PRESETS['qft5']}", "// written out: H and controlled phases on each qubit, then swaps",
             f"qreg q[{n}];"]
    for j in range(n - 1, -1, -1):
        lines.append(f"h q[{j}];")
        for k in range(j - 1, -1, -1):
            lines.append(f"cp(pi/{2 ** (j - k)}) q[{k}],q[{j}];")
    for i in range(n // 2):
        lines.append(f"swap q[{i}],q[{n - 1 - i}];")
    return QASM_HEAD + "\n".join(lines) + "\n"


QFT5_QISKIT = """from qiskit import QuantumCircuit
from math import pi

# 5-qubit Quantum Fourier Transform, written out:
# H and controlled phases on each qubit, then swaps
n = 5
qc = QuantumCircuit(n)
for j in range(n - 1, -1, -1):
    qc.h(j)
    for k in range(j - 1, -1, -1):
        qc.cp(pi / 2 ** (j - k), k, j)
for i in range(n // 2):
    qc.swap(i, n - 1 - i)
"""

TOFFOLI_QASM = QASM_HEAD + """// Toffoli gate: flips q[2] when q[0] and q[1] are both 1
qreg q[3];
ccx q[0],q[1],q[2];
"""

TOFFOLI_QISKIT = """from qiskit import QuantumCircuit

# Toffoli gate: flips qubit 2 when qubits 0 and 1 are both 1
qc = QuantumCircuit(3)
qc.ccx(0, 1, 2)
"""

ADDER_QASM = QASM_HEAD + """// Cuccaro ripple-carry adder, 2+2 bits
// q[0] carry in; a = q[1], q[3]; b = q[2], q[4]; q[5] carry out
qreg q[6];
// MAJ(carry in, b0, a0)
cx q[1],q[2];
cx q[1],q[0];
ccx q[0],q[2],q[1];
// MAJ(a0, b1, a1)
cx q[3],q[4];
cx q[3],q[1];
ccx q[1],q[4],q[3];
// copy the carry out
cx q[3],q[5];
// UMA(a0, b1, a1)
ccx q[1],q[4],q[3];
cx q[3],q[1];
cx q[1],q[4];
// UMA(carry in, b0, a0)
ccx q[0],q[2],q[1];
cx q[1],q[0];
cx q[0],q[2];
"""

ADDER_QISKIT = """from qiskit import QuantumCircuit

# Cuccaro ripple-carry adder, 2+2 bits
# qubit 0 carry in; a = qubits 1, 3; b = qubits 2, 4; qubit 5 carry out
qc = QuantumCircuit(6)

# MAJ(carry in, b0, a0)
qc.cx(1, 2)
qc.cx(1, 0)
qc.ccx(0, 2, 1)
# MAJ(a0, b1, a1)
qc.cx(3, 4)
qc.cx(3, 1)
qc.ccx(1, 4, 3)
# copy the carry out
qc.cx(3, 5)
# UMA(a0, b1, a1)
qc.ccx(1, 4, 3)
qc.cx(3, 1)
qc.cx(1, 4)
# UMA(carry in, b0, a0)
qc.ccx(0, 2, 1)
qc.cx(1, 0)
qc.cx(0, 2)
"""

GROVER3_QASM = QASM_HEAD + """// 3-qubit Grover iteration: oracle marking |101>, then the diffuser
qreg q[3];
h q;
// oracle
x q[1];
h q[2];
ccx q[0],q[1],q[2];
h q[2];
x q[1];
// diffuser
h q;
x q;
h q[2];
ccx q[0],q[1],q[2];
h q[2];
x q;
h q;
"""

GROVER3_QISKIT = """from qiskit import QuantumCircuit

# 3-qubit Grover iteration: oracle marking |101>, then the diffuser
qc = QuantumCircuit(3)
qc.h(range(3))

# oracle
qc.x(1)
qc.h(2)
qc.ccx(0, 1, 2)
qc.h(2)
qc.x(1)

# diffuser
qc.h(range(3))
qc.x(range(3))
qc.h(2)
qc.ccx(0, 1, 2)
qc.h(2)
qc.x(range(3))
qc.h(range(3))
"""


def _gate_list(qc):
    """(name, qubit indices) for a circuit of parameterless gates."""
    return [(i.operation.name, [qc.find_bit(q).index for q in i.qubits]) for i in qc.data]


def _random_ct_texts():
    qc = circuits.from_preset("random_ct")
    gates = _gate_list(qc)
    note = f"{circuits.PRESETS['random_ct']}, seed 1, {len(gates)} gates"
    qasm = [f"// {note}", f"qreg q[{qc.num_qubits}];"]
    qasm += [f"{name} " + ",".join(f"q[{q}]" for q in qubits) + ";" for name, qubits in gates]
    qiskit = ["from qiskit import QuantumCircuit", "", f"# {note}", f"qc = QuantumCircuit({qc.num_qubits})"]
    qiskit += [f"qc.{name}({', '.join(map(str, qubits))})" for name, qubits in gates]
    return QASM_HEAD + "\n".join(qasm) + "\n", "\n".join(qiskit) + "\n"


def build():
    random_qasm, random_qiskit = _random_ct_texts()
    texts = {
        "qft5": (_qft_qasm(), QFT5_QISKIT),
        "toffoli": (TOFFOLI_QASM, TOFFOLI_QISKIT),
        "adder": (ADDER_QASM, ADDER_QISKIT),
        "grover3": (GROVER3_QASM, GROVER3_QISKIT),
        "random_ct": (random_qasm, random_qiskit),
    }
    return [{"name": name, "description": circuits.PRESETS[name], "qasm": texts[name][0], "qiskit": texts[name][1]}
            for name in circuits.PRESETS]


def main():
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(build(), fh, indent=1)
    print(f"wrote {os.path.relpath(OUT, ROOT)} ({os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
