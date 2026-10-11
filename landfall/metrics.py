"""Circuit metrics, before and after hardware compilation."""
import math

from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator

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


def equivalent(a: QuantumCircuit, b: QuantumCircuit) -> bool:
    """Exact unitary equivalence up to global phase (fine up to ~12 qubits)."""
    return Operator(a).equiv(Operator(b))
