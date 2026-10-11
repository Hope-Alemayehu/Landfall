"""Optimization strategies applied before hardware compilation.

Each strategy maps a normalized circuit to a (hardware-agnostic) optimized circuit.
Hardware compilation (layout, routing, native gates) happens afterwards, the same way for all.
"""
from qiskit import QuantumCircuit, qasm2, transpile

import pyzx as zx

from .circuits import ZX_FRIENDLY

# name -> (short label, description, qiskit optimization level used during hardware compilation)
STRATEGIES = {
    "qiskit_o1": ("Qiskit O1", "Qiskit transpiler, light optimization", 1),
    "qiskit_o3": ("Qiskit O3", "Qiskit transpiler, heaviest optimization", 3),
    "zx_teleport": ("ZX teleport", "PyZX teleport_reduce (moves phases, keeps structure), then Qiskit O3", 3),
    "zx_full": ("ZX full", "PyZX full_reduce + circuit extraction (rebuilds the circuit), then Qiskit O3", 3),
}


def _to_zx(qc: QuantumCircuit) -> "zx.Circuit":
    return zx.Circuit.from_qasm(qasm2.dumps(qc))


def _from_zx(c: "zx.Circuit") -> QuantumCircuit:
    c = zx.basic_optimization(c.to_basic_gates())
    out = QuantumCircuit.from_qasm_str(c.to_qasm())
    return transpile(out, basis_gates=ZX_FRIENDLY, optimization_level=0)


def zx_teleport(qc: QuantumCircuit) -> QuantumCircuit:
    g = _to_zx(qc).to_graph()
    g = zx.teleport_reduce(g)
    return _from_zx(zx.Circuit.from_graph(g))


def zx_full(qc: QuantumCircuit) -> QuantumCircuit:
    g = _to_zx(qc).to_graph()
    zx.full_reduce(g)
    return _from_zx(zx.extract_circuit(g.copy()))


def apply(name: str, qc: QuantumCircuit) -> QuantumCircuit:
    if name == "zx_teleport":
        out = zx_teleport(qc)
    elif name == "zx_full":
        out = zx_full(qc)
    else:
        out = qc.copy()
    out.name = f"{qc.name}:{name}"
    return out
