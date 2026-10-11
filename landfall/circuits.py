"""Preset benchmark circuits and QASM loading."""
import random

from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import QFTGate

# Gate set that both Qiskit and PyZX understand well.
ZX_FRIENDLY = ["cx", "cz", "h", "x", "z", "s", "sdg", "t", "tdg", "rz"]

PRESETS = {
    "qft5": "5-qubit Quantum Fourier Transform (structured, many small rotations)",
    "toffoli": "Toffoli gate in Clifford+T (tiny, already near optimal)",
    "adder": "Ripple-carry adder, 2+2 bits (arithmetic, Toffoli heavy)",
    "grover3": "3-qubit Grover iteration (oracle + diffuser)",
    "random_ct": "Random 6-qubit Clifford+T circuit (unstructured)",
}


def _qft(n=5):
    qc = QuantumCircuit(n, name="qft5")
    qc.append(QFTGate(n), range(n))
    return qc


def _toffoli():
    qc = QuantumCircuit(3, name="toffoli")
    qc.ccx(0, 1, 2)
    return qc


def _adder():
    # Cuccaro-style ripple-carry adder on 2-bit registers: a(2), b(2), carry-in, carry-out.
    qc = QuantumCircuit(6, name="adder")
    cin, a, b, cout = 0, [1, 3], [2, 4], 5

    def maj(c, bb, aa):
        qc.cx(aa, bb); qc.cx(aa, c); qc.ccx(c, bb, aa)

    def uma(c, bb, aa):
        qc.ccx(c, bb, aa); qc.cx(aa, c); qc.cx(c, bb)

    maj(cin, b[0], a[0])
    maj(a[0], b[1], a[1])
    qc.cx(a[1], cout)
    uma(a[0], b[1], a[1])
    uma(cin, b[0], a[0])
    return qc


def _grover3():
    qc = QuantumCircuit(3, name="grover3")
    qc.h(range(3))
    # oracle marks |101>
    qc.x(1); qc.h(2); qc.ccx(0, 1, 2); qc.h(2); qc.x(1)
    # diffuser
    qc.h(range(3)); qc.x(range(3))
    qc.h(2); qc.ccx(0, 1, 2); qc.h(2)
    qc.x(range(3)); qc.h(range(3))
    return qc


def _random_ct(n=6, depth=120, seed=1):
    """Random CNOT + H + phase circuit with T gates (reproducible, no PyZX global state)."""
    rng = random.Random(seed)
    qc = QuantumCircuit(n, name="random_ct")
    phases = ["t", "tdg", "s", "sdg", "z"]
    for _ in range(depth):
        r = rng.random()
        if r < 0.5:
            c, t = rng.sample(range(n), 2)
            qc.cx(c, t)
        elif r < 0.7:
            qc.h(rng.randrange(n))
        else:
            getattr(qc, rng.choice(phases))(rng.randrange(n))
    return qc


_BUILDERS = {"qft5": _qft, "toffoli": _toffoli, "adder": _adder,
             "grover3": _grover3, "random_ct": _random_ct}


def normalize(qc: QuantumCircuit) -> QuantumCircuit:
    """Strip measurements/barriers and lower to a gate set PyZX can read."""
    clean = QuantumCircuit(qc.num_qubits, name=qc.name)
    for inst in qc.data:
        if inst.operation.name in ("barrier", "measure", "reset", "delay"):
            continue
        clean.append(inst.operation, [qc.find_bit(q).index for q in inst.qubits])
    out = transpile(clean, basis_gates=ZX_FRIENDLY, optimization_level=0)
    out.name = qc.name
    return out


def load(preset: str = "qft5", qasm: str = "") -> QuantumCircuit:
    """Return a normalized circuit from a preset name or an OpenQASM 2 string."""
    if qasm and qasm.strip():
        text = qasm.strip()
        if "OPENQASM" not in text:
            text = 'OPENQASM 2.0;\ninclude "qelib1.inc";\n' + text
        qc = QuantumCircuit.from_qasm_str(text)
        qc.name = "custom"
    else:
        key = preset.strip().lower()
        if key not in _BUILDERS:
            raise ValueError(f"Unknown preset '{preset}'. Choose one of: {', '.join(PRESETS)}")
        qc = _BUILDERS[key]()
    if qc.num_qubits > 12:
        raise ValueError("Landfall checks exact equivalence, so circuits are limited to 12 qubits.")
    return normalize(qc)
