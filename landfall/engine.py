"""Runs every strategy on every device and collects the numbers."""
import time

from . import devices as dv
from . import metrics as mt
from . import strategies as st


def analyze(qc, device_keys: str = dv.DEFAULT_DEVICES, strategy_keys=None, seed: int = 11, log=print):
    strategy_keys = strategy_keys or list(st.STRATEGIES)
    devs = dv.parse(device_keys)
    t0 = time.time()

    optimized, logical, checks = {}, {}, {}
    for s in strategy_keys:
        try:
            out = st.apply(s, qc)
            optimized[s] = out
            logical[s] = mt.logical(out)
            checks[s] = mt.equivalent(qc, out)
        except Exception as exc:  # a strategy failing should not sink the whole report
            log(f"  ! {st.STRATEGIES[s][0]} failed: {exc}")
    log(f"  optimized {len(optimized)} strategies in {time.time() - t0:.1f}s")

    rows = []
    for d in devs:
        t1 = time.time()
        if d.kind == "ibm" and qc.num_qubits > d.backend.num_qubits:
            log(f"  ! skipping {d.label}: circuit needs {qc.num_qubits} qubits")
            continue
        for s, circ in optimized.items():
            level = st.STRATEGIES[s][2]
            compiled = dv.compile_to(circ, d, level, seed)
            unrouted = dv.compile_unrouted(circ, d, level, seed)
            row = {"device": d.key, "device_label": d.label, "family": d.family,
                   "topology": d.topology, "native_2q": d.native_2q,
                   "strategy": s, "strategy_label": st.STRATEGIES[s][0]}
            row.update(mt.physical(compiled, unrouted))
            row["success"] = dv.success_estimate(compiled, d)
            rows.append(row)
        log(f"  compiled for {d.label:<16} ({d.native_2q}, {d.topology}) in {time.time() - t1:.1f}s")

    return {
        "circuit": qc.name,
        "num_qubits": qc.num_qubits,
        "input": mt.logical(qc),
        "logical": logical,
        "equivalent": checks,
        "optimized": optimized,
        "rows": rows,
        "devices": [d.key for d in devs],
        "elapsed_s": round(time.time() - t0, 1),
    }
