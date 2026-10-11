"""Circuit metrics, before and after hardware compilation."""
import math

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator, Statevector

TWO_Q = {"cx", "cz", "ecr", "rzz", "rxx", "ryy", "swap", "ms", "zz", "cp", "crz"}


def two_qubit_count(qc: QuantumCircuit) -> int:
    return sum(1 for i in qc.data if len(i.qubits) == 2)


def two_qubit_depth(qc: QuantumCircuit) -> int:
    return qc.depth(filter_function=lambda i: len(i.qubits) == 2)


def _is_clifford_angle(theta: float) -> bool:
    k = theta / (math.pi / 2)
    return abs(k - round(k)) < 1e-9


def t_count(qc: QuantumCircuit) -> int:
    """Non-Clifford phase count (T, Tdg and arbitrary-angle Rz/P) on a ZX-friendly circuit."""
    n = 0
    for inst in qc.data:
        name = inst.operation.name
        if name in ("t", "tdg"):
            n += 1
        elif name in ("rz", "p", "u1"):
            theta = float(inst.operation.params[0])
            if not _is_clifford_angle(theta):
                n += 1
    return n


def logical(qc: QuantumCircuit) -> dict:
    return {"two_q": two_qubit_count(qc), "t": t_count(qc), "depth": qc.depth(), "gates": qc.size()}


def physical(compiled: QuantumCircuit, unrouted: QuantumCircuit) -> dict:
    two_q = two_qubit_count(compiled)
    base = two_qubit_count(unrouted)
    return {
        "two_q": two_q,
        "depth": compiled.depth(),
        "two_q_depth": two_qubit_depth(compiled),
        "gates": compiled.size(),
        "routing_2q": max(0, two_q - base),  # extra 2Q gates caused by limited connectivity
    }


def footprint(compiled: QuantumCircuit) -> dict:
    """Physical qubits a compiled circuit touches, and its 2Q gate count per coupler ("a-b", a < b)."""
    used, edges = set(), {}
    for inst in compiled.data:
        idx = [compiled.find_bit(q).index for q in inst.qubits]
        used.update(idx)
        if len(idx) == 2:
            key = f"{min(idx)}-{max(idx)}"
            edges[key] = edges.get(key, 0) + 1
    return {"qubits_used": sorted(used), "edge_usage": edges}


EXACT_MAX_QUBITS = 6
RANDOM_STATES = 4
RANDOMIZED = f"randomized ({RANDOM_STATES} states)"


def equivalent(a: QuantumCircuit, b: QuantumCircuit, method: str | None = None) -> dict:
    """Unitary equivalence up to global phase, as {"ok": bool, "method": "exact" | RANDOMIZED}.

    Up to 6 qubits the full unitaries are compared. Above that, building 2^n x 2^n matrices gets
    slow (a 12-qubit QFT took minutes), so both circuits run on 4 seeded random input states:
    every overlap |<U psi|V psi>| must be 1 and every state must show the same global phase.
    method forces "exact" or "randomized".
    """
    if method is None:
        method = "exact" if a.num_qubits <= EXACT_MAX_QUBITS else "randomized"
    if a.num_qubits != b.num_qubits:
        ok = False
    elif method == "exact":
        ok = Operator(a).equiv(Operator(b))
    else:
        ok = _same_on_random_states(a, b)
    return {"ok": bool(ok), "method": "exact" if method == "exact" else RANDOMIZED}


def _same_on_random_states(a: QuantumCircuit, b: QuantumCircuit, seed: int = 2026) -> bool:
    rng = np.random.default_rng(seed)
    dim = 2 ** a.num_qubits
    phase = None
    for _ in range(RANDOM_STATES):
        vec = rng.normal(size=dim) + 1j * rng.normal(size=dim)
        psi = Statevector(vec / np.linalg.norm(vec))
        overlap = np.vdot(psi.evolve(a).data, psi.evolve(b).data)
        if abs(overlap) <= 1 - 1e-9:
            return False
        if phase is None:
            phase = overlap / abs(overlap)  # global phase, fixed by the first state
        elif abs(overlap / abs(overlap) - phase) > 1e-7:
            return False
    return True
