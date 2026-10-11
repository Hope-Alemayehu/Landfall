"""Turns the numbers into plain-language findings."""
from collections import defaultdict

from .strategies import STRATEGIES

BASELINE = "qiskit_o3"
TIE = 0.005  # differences under half a percentage point are treated as ties


def _label(s):
    return STRATEGIES[s][0]


def by_device(result):
    table = defaultdict(dict)
    for r in result["rows"]:
        table[r["device"]][r["strategy"]] = r
    return table


def winners(result):
    """Best and worst strategy per device, ranked by estimated success."""
    out = {}
    for dev, rows in by_device(result).items():
        ranked = sorted(rows.values(), key=lambda r: (-r["success"], r["two_q"]))
        best = ranked[0]
        base = rows.get(BASELINE)
        if base is not None and best["success"] - base["success"] < TIE:
            best = base  # a challenger has to beat the baseline clearly to be called the winner
        out[dev] = {"best": best, "worst": ranked[-1], "ranked": ranked}
    return out


def explain(result):
    """Return a list of short findings, most important first."""
    lines = []
    lg = result["logical"]
    win = winners(result)
    rows = by_device(result)
    if not win:
        return ["No devices could be compiled."]

    # 1. Does the ranking flip across hardware?
    best_set = {w["best"]["strategy"] for w in win.values()}
    if len(best_set) > 1:
        groups = defaultdict(list)
        for dev, w in win.items():
            groups[w["best"]["strategy_label"]].append(w["best"]["device_label"])
        parts = [f"{s} on {', '.join(d)}" for s, d in groups.items()]
        lines.append("The best strategy depends on the hardware: " + "; ".join(parts) + ".")
    else:
        s = next(iter(best_set))
        lines.append(f"{_label(s)} wins or ties on every device tested; no strategy beats it by more "
                     f"than {100 * TIE:.1f} points here.")

    # 2. What ZX did before any hardware was involved.
    base = result["input"]
    if "zx_teleport" in lg:
        t = lg["zx_teleport"]
        if t["t"] < base["t"]:
            lines.append(f"ZX teleport cut non-Clifford phases from {base['t']} to {t['t']} "
                         f"without restructuring the circuit (2Q gates {base['two_q']} -> {t['two_q']}).")
    if "zx_full" in lg:
        f = lg["zx_full"]
        if f["two_q"] > base["two_q"]:
            lines.append(f"ZX full rebuilt the circuit from its graph and came out with more 2Q gates "
                         f"({base['two_q']} -> {f['two_q']}); circuit extraction trades structure for compactness.")
        elif f["two_q"] < base["two_q"]:
            lines.append(f"ZX full shrank the circuit to {f['two_q']} 2Q gates (from {base['two_q']}) "
                         f"before compilation.")

    # 3. How much of the cost is routing, per topology.
    share = []
    for dev, rs in rows.items():
        r = rs.get(BASELINE) or next(iter(rs.values()))
        if r["two_q"]:
            share.append((r["routing_2q"] / r["two_q"], r))
    if share:
        hi = max(share, key=lambda x: x[0])
        lo = min(share, key=lambda x: x[0])
        if hi[0] > 0:
            lines.append(f"Routing is the hidden cost: on {hi[1]['device_label']} ({hi[1]['topology']}) "
                         f"{hi[0]:.0%} of 2Q gates are SWAP overhead; on {lo[1]['device_label']} "
                         f"({lo[1]['topology']}) it is {lo[0]:.0%}.")

    # 4. Per-device verdicts.
    for dev, w in win.items():
        b, worst = w["best"], w["worst"]
        if abs(w["ranked"][0]["success"] - worst["success"]) < TIE:
            lines.append(f"{b['device_label']}: all strategies are within {100 * TIE:.1f} points "
                         f"(est. success {b['success']:.2f}); no meaningful difference.")
            continue
        base_row = rows[dev].get(BASELINE)
        gain = ""
        if base_row and b["strategy"] != BASELINE:
            gain = (f", {100 * (b['success'] - base_row['success']):+.1f} pts vs Qiskit O3 "
                    f"({base_row['two_q']} -> {b['two_q']} 2Q gates)")
            if b["two_q"] > base_row["two_q"]:
                gain += (" despite MORE 2Q gates, because layout placed it on better-calibrated qubits:"
                         " gate count alone is not the whole story")
        ties = [r["strategy_label"] for r in w["ranked"]
                if r["strategy"] not in (b["strategy"], worst["strategy"])
                and abs(b["success"] - r["success"]) < TIE]
        if ties:
            gain += f"; tied with {', '.join(ties)}"
        lines.append(f"{b['device_label']}: {b['strategy_label']} is best "
                     f"(est. success {b['success']:.2f}{gain}); {worst['strategy_label']} is worst "
                     f"({worst['success']:.2f}).")
    return lines
