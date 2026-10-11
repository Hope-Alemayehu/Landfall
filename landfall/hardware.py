"""One-job hardware check.

IonQ backends accept one job per run, so the two circuits being compared are placed
side by side in a single circuit: strategy A on qubits 0..n-1 and strategy B on n..2n-1.
Both halves get the same random input state, so their ideal outputs are identical and
informative. The measured distribution of each half is compared with the ideal one.
"""
import math
import random

from qiskit import ClassicalRegister, QuantumCircuit, transpile
from qiskit.quantum_info import Statevector, hellinger_fidelity

from .strategies import STRATEGIES

GENERIC_BASIS = ["cx", "rz", "rx", "ry", "h", "x"]


def _input_state(n, seed=7):
    rng = random.Random(seed)
    prep = QuantumCircuit(n)
    for q in range(n):
        prep.ry(rng.uniform(0.2, math.pi - 0.2), q)
        prep.rz(rng.uniform(0, 2 * math.pi), q)
    return prep


def _ideal(circ):
    probs = Statevector(circ).probabilities_dict()
    return {k: v for k, v in probs.items() if v > 1e-9}


def _marginal(counts, lo, n, total_bits):
    out = {}
    for key, c in counts.items():
        bits = key.replace(" ", "").zfill(total_bits)
        # Qiskit bitstrings are little-endian: clbit 0 is the rightmost character.
        part = bits[total_bits - lo - n: total_bits - lo]
        out[part] = out.get(part, 0) + c
    return out


def backend_name(backend):
    name = getattr(backend, "name", None)
    if callable(name):
        name = name()
    return str(name or backend)


def build(circ_a, circ_b):
    n = circ_a.num_qubits
    prep = _input_state(n)
    half_a = prep.compose(circ_a)
    half_b = prep.compose(circ_b)
    qc = QuantumCircuit(2 * n, name="landfall_check")
    qc.compose(half_a, range(n), inplace=True)
    qc.compose(half_b, range(n, 2 * n), inplace=True)
    qc.add_register(ClassicalRegister(2 * n, "c"))
    qc.measure(range(2 * n), range(2 * n))
    return qc, _ideal(half_a), _ideal(half_b)


def compile_for(qc, backend, seed=11):
    try:
        return transpile(qc, backend=backend, optimization_level=3, seed_transpiler=seed)
    except Exception:
        return transpile(qc, basis_gates=GENERIC_BASIS, optimization_level=3, seed_transpiler=seed)


def run(result, a, b, backend, shots=2000, log=print):
    circ_a, circ_b = result["optimized"][a], result["optimized"][b]
    n = circ_a.num_qubits
    qc, ideal_a, ideal_b = build(circ_a, circ_b)
    compiled = compile_for(qc, backend)
    name = backend_name(backend)
    log(f"\nHardware check on {name}: {STRATEGIES[a][0]} (qubits 0-{n - 1}) vs "
        f"{STRATEGIES[b][0]} (qubits {n}-{2 * n - 1}), {shots} shots, one job")
    job = backend.run(compiled, shots=shots)
    counts = job.result().get_counts()
    if isinstance(counts, list):
        counts = counts[0]
    meas_a = _marginal(counts, 0, n, 2 * n)
    meas_b = _marginal(counts, n, n, 2 * n)
    check = {
        "backend": name, "shots": shots, "a": a, "b": b,
        "a_label": STRATEGIES[a][0], "b_label": STRATEGIES[b][0],
        "a_fidelity": hellinger_fidelity(ideal_a, meas_a),
        "b_fidelity": hellinger_fidelity(ideal_b, meas_b),
    }
    log(f"  fidelity to ideal: {check['a_label']} {check['a_fidelity']:.3f} | "
        f"{check['b_label']} {check['b_fidelity']:.3f}")
    return check
