"""Landfall: see what your circuit optimizations look like after they hit the hardware."""
__version__ = "0.1.0"

from . import circuits, engine, verdict
from .devices import DEFAULT_DEVICES


def analyze(qc, devices=None, log=None):
    """Run every strategy on every device for a QuantumCircuit and return the report.

    qc       any QuantumCircuit up to 12 qubits (measurements, barriers and resets are ignored)
    devices  device keys as a list or comma-separated string, e.g. ["fez", "ionq"]
             (default: kolkata, sherbrooke, fez, miami, ionq)
    log      optional callable for progress lines, e.g. print

    The report has the fields of Qollab's JSON report plus "verdict" (plain-language findings),
    "optimized" (strategy -> optimized QuantumCircuit) and "compiled"
    ((device, strategy) -> compiled QuantumCircuit).
    """
    if devices is None:
        devices = DEFAULT_DEVICES
    elif not isinstance(devices, str):
        devices = ",".join(devices)
    result = engine.analyze(circuits.prepare(qc), devices, log=log or (lambda *_: None), keep_compiled=True)
    result["verdict"] = verdict.explain(result)
    return result
