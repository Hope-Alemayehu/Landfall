"""metrics.equivalent: exact (unitary) and randomized (statevector) checks agree on what is equivalent."""
import random

import pytest
from qiskit import QuantumCircuit, transpile

from landfall import metrics, strategies
from landfall.circuits import ZX_FRIENDLY

SIZES = [3, 10, 12]
METHODS = ["exact", "randomized"]


def _random_circuit(n, gates, seed=5):
    rng = random.Random(seed)
    qc = QuantumCircuit(n)
    qc.h(0)
    qc.t(0)
    qc.cx(0, 1)
    for _ in range(gates):
        r = rng.random()
        if r < 0.4:
            qc.cx(*rng.sample(range(n), 2))
        elif r < 0.6:
            qc.h(rng.randrange(n))
        elif r < 0.8:
            qc.t(rng.randrange(n))
        else:
            qc.rz(rng.choice([0.25, -1.1, 2.0]), rng.randrange(n))
    return qc


def _mutate(qc, kind):
    """Copy of qc with exactly one gate changed."""
    out = QuantumCircuit(qc.num_qubits, global_phase=qc.global_phase)
    done = False
    for inst in qc.data:
        qubits = [qc.find_bit(q).index for q in inst.qubits]
        if not done and kind == "t_to_tdg" and inst.operation.name == "t":
            out.tdg(qubits[0])
            done = True
        elif not done and kind == "cx_swapped" and inst.operation.name == "cx":
            out.cx(qubits[1], qubits[0])
            done = True
        else:
            out.append(inst.operation, qubits)
    assert done
    return out


def _rewrites(qc):
    o3 = transpile(qc, basis_gates=ZX_FRIENDLY, optimization_level=3, seed_transpiler=1)
    o3.global_phase += 0.7  # equivalence is up to global phase
    return {"qiskit_o3": o3, "zx_full": strategies.zx_full(qc)}


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("n", SIZES)
def test_equivalent_rewrites_pass(n, method):
    qc = _random_circuit(n, 2 * n)
    for name, other in _rewrites(qc).items():
        assert metrics.equivalent(qc, other, method)["ok"], name


@pytest.mark.parametrize("kind", ["t_to_tdg", "cx_swapped"])
@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("n", SIZES)
def test_one_changed_gate_fails(n, method, kind):
    qc = _random_circuit(n, 2 * n)
    assert not metrics.equivalent(qc, _mutate(qc, kind), method)["ok"]


def test_method_is_chosen_by_size_and_reported():
    small, large = _random_circuit(6, 10), _random_circuit(7, 10)
    assert metrics.equivalent(small, small) == {"ok": True, "method": "exact"}
    assert metrics.equivalent(large, large) == {"ok": True, "method": "randomized (4 states)"}


def test_different_qubit_counts_fail():
    assert not metrics.equivalent(QuantumCircuit(3), QuantumCircuit(4))["ok"]
