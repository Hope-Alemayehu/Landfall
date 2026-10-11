"""The device ladder: hardware targets ordered from sparse to full connectivity.

IBM devices use calibration snapshots shipped with qiskit-ibm-runtime fake backends
(native gates, coupling map and per-gate error rates). The IonQ target is modelled as
all-to-all connectivity with nominal published-style fidelities, which you can edit below.
"""
from dataclasses import dataclass, field

from qiskit import QuantumCircuit, transpile
from qiskit_ibm_runtime import fake_provider as fp

# Nominal IonQ Forte figures used for the success estimate (illustrative, not live calibration).
IONQ_FORTE = {"err_1q": 2e-4, "err_2q": 4e-3, "err_readout": 5e-3}


@dataclass
class Device:
    key: str
    label: str
    family: str
    native_2q: str
    topology: str
    kind: str  # "ibm" or "ion"
    backend: object = field(default=None, repr=False)

    @property
    def basis(self):
        if self.kind == "ion":
            return ["rz", "rx", "ry", "rzz"]
        return [g for g in self.backend.operation_names
                if g not in ("measure", "delay", "reset", "id", "if_else", "for_loop",
                             "switch_case", "while_loop", "barrier", "measure_2", "reset_2")]


# Representative device per family, ordered by connectivity.
LADDER = [
    ("fake_kolkata", "IBM Kolkata", "Falcon r5", "heavy-hex"),
    ("fake_sherbrooke", "IBM Sherbrooke", "Eagle r3", "heavy-hex"),
    ("fake_fez", "IBM Fez", "Heron r2", "heavy-hex"),
    ("fake_miami", "IBM Miami", "Nighthawk r1", "square lattice"),
    ("ionq_forte", "IonQ Forte", "Trapped ion", "all-to-all"),
]
DEFAULT_DEVICES = ",".join(k for k, *_ in LADDER)

_TOPOLOGY = {k: t for k, _, _, t in LADDER}
_FAMILY = {k: f for k, _, f, _ in LADDER}


def _ibm_backend(key: str):
    cls_name = "Fake" + key.replace("fake_", "").capitalize()
    cls = getattr(fp, cls_name + "V2", None) or getattr(fp, cls_name, None)
    if cls is None:
        raise ValueError(f"Unknown IBM fake backend '{key}' (looked for {cls_name}).")
    return cls()


def get(key: str) -> Device:
    key = key.strip().lower()
    if key in ("ionq", "ionq_forte", "forte"):
        return Device("ionq_forte", "IonQ Forte", "Trapped ion", "ZZ", "all-to-all", "ion")
    if not key.startswith("fake_"):
        key = "fake_" + key
    be = _ibm_backend(key)
    two_q = [g for g in ("ecr", "cz", "cx") if g in be.operation_names]
    label = "IBM " + key.replace("fake_", "").capitalize()
    return Device(key, label, _FAMILY.get(key, "IBM"), two_q[0].upper() if two_q else "?",
                  _TOPOLOGY.get(key, "heavy-hex"), "ibm", be)


def parse(devices: str):
    return [get(k) for k in devices.split(",") if k.strip()]


def compile_to(qc: QuantumCircuit, dev: Device, opt_level: int, seed: int = 11) -> QuantumCircuit:
    """Full hardware compilation: layout, routing and native-gate translation."""
    if dev.kind == "ion":
        return transpile(qc, basis_gates=dev.basis, optimization_level=opt_level, seed_transpiler=seed)
    return transpile(qc, backend=dev.backend, optimization_level=opt_level, seed_transpiler=seed)


def compile_unrouted(qc: QuantumCircuit, dev: Device, opt_level: int, seed: int = 11) -> QuantumCircuit:
    """Same native gates and optimization, but pretend every qubit pair is connected."""
    return transpile(qc, basis_gates=dev.basis, optimization_level=opt_level, seed_transpiler=seed)


def success_estimate(compiled: QuantumCircuit, dev: Device) -> float:
    """Estimated success probability: product of (1 - error) over every gate and readout.

    A standard first-order figure of merit; it ignores idle decoherence and crosstalk.
    """
    p = 1.0
    active = set()
    if dev.kind == "ion":
        for inst in compiled.data:
            n = len(inst.qubits)
            active.update(compiled.find_bit(q).index for q in inst.qubits)
            if inst.operation.name == "rz":
                continue  # virtual Z: free
            p *= 1 - (IONQ_FORTE["err_2q"] if n == 2 else IONQ_FORTE["err_1q"])
        p *= (1 - IONQ_FORTE["err_readout"]) ** len(active)
        return p
    target = dev.backend.target
    for inst in compiled.data:
        name = inst.operation.name
        qargs = tuple(compiled.find_bit(q).index for q in inst.qubits)
        active.update(qargs)
        try:
            err = target[name][qargs].error
        except (KeyError, TypeError, AttributeError):
            err = None
        if err:
            p *= 1 - min(err, 1.0)
    for q in active:
        try:
            err = target["measure"][(q,)].error
        except (KeyError, TypeError, AttributeError):
            err = None
        if err:
            p *= 1 - min(err, 1.0)
    return p
