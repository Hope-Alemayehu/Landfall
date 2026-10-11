"""Console tables and charts."""
import matplotlib

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

from .metrics import RANDOM_STATES
from .strategies import STRATEGIES
from .verdict import BASELINE, by_device, winners

# Categorical slots 1-4 (validated: adjacent CVD dE >= 9.1, normal-vision >= 22.9 on light surface).
SERIES = {"qiskit_o1": "#2a78d6", "qiskit_o3": "#eb6834", "zx_teleport": "#1baf7a", "zx_full": "#eda100"}
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
DIVERGING = LinearSegmentedColormap.from_list("lf_div", ["#e34948", "#f0efec", "#2a78d6"])


def print_tables(result, log=print):
    lg, eq = result["logical"], result["equivalent"]
    log(f"\nBefore hardware ({result['circuit']}, {result['num_qubits']} qubits)")
    log(f"  {'strategy':<12} {'2Q':>5} {'T/non-Cliff':>11} {'depth':>6}  verified")
    randomized = False
    for s, m in lg.items():
        check = eq.get(s, {})
        star = "*" if check.get("method", "exact") != "exact" else ""
        randomized = randomized or bool(star)
        log(f"  {STRATEGIES[s][0]:<12} {m['two_q']:>5} {m['t']:>11} {m['depth']:>6}  "
            f"{'yes' if check.get('ok') else 'NO'}{star}")
    if randomized:
        log(f"  * randomized check on {RANDOM_STATES} random states")

    log("\nAfter hardware compilation")
    log(f"  {'device':<16} {'native':<7} {'topology':<15} {'strategy':<12} "
        f"{'2Q':>5} {'routing':>8} {'depth':>6} {'est.success':>12}")
    win = winners(result)
    for dev, rows in by_device(result).items():
        for s, r in rows.items():
            star = " *" if win[dev]["best"]["strategy"] == s else ""
            log(f"  {r['device_label']:<16} {r['native_2q']:<7} {r['topology']:<15} {r['strategy_label']:<12} "
                f"{r['two_q']:>5} {r['routing_2q']:>8} {r['depth']:>6} {r['success']:>12.3f}{star}")
    log("  (* best per device; routing = extra 2Q gates caused by limited connectivity)")


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def plot_gates(result):
    """Grouped bars: 2Q gates after compilation, split into circuit gates and routing overhead."""
    rows = by_device(result)
    devs = list(rows)
    strats = [s for s in STRATEGIES if any(s in rows[d] for d in devs)]
    n = len(strats)
    width = 0.8 / n
    fig, ax = plt.subplots(figsize=(10, 4.8), facecolor=SURFACE)
    _style(ax)
    for i, s in enumerate(strats):
        for j, d in enumerate(devs):
            r = rows[d].get(s)
            if not r:
                continue
            x = j - 0.4 + width * (i + 0.5)
            own = r["two_q"] - r["routing_2q"]
            ax.bar(x, own, width * 0.9, color=SERIES[s], edgecolor=SURFACE, linewidth=1)
            if r["routing_2q"]:
                ax.bar(x, r["routing_2q"], width * 0.9, bottom=own, color=SERIES[s], alpha=0.35,
                       hatch="///", edgecolor=SERIES[s], linewidth=0)
            ax.annotate(str(r["two_q"]), (x, r["two_q"]), xytext=(0, 2), textcoords="offset points",
                        ha="center", va="bottom", fontsize=7.5, color=INK_2)
    ax.set_xticks(range(len(devs)))
    ax.set_xticklabels([f"{rows[d][strats[0]]['device_label']}\n{rows[d][strats[0]]['native_2q']} · "
                        f"{rows[d][strats[0]]['topology']}" for d in devs], color=INK, fontsize=8.5)
    ax.set_ylabel("Two-qubit gates after compilation", color=INK_2, fontsize=9)
    handles = [Patch(color=SERIES[s], label=STRATEGIES[s][0]) for s in strats]
    handles.append(Patch(facecolor="#d6d5d0", hatch="///", edgecolor="#8a8984", label="routing (SWAP) overhead"))
    ax.legend(handles=handles, frameon=False, fontsize=8.5, ncol=len(handles), loc="upper left",
              bbox_to_anchor=(0, 1.12), labelcolor=INK)
    ax.set_title(f"{result['circuit']}: what each strategy costs once it lands on hardware",
                 color=INK, fontsize=11, loc="left", pad=30)
    fig.tight_layout()
    return fig


def plot_success_delta(result):
    """Diverging heatmap: change in estimated success vs Qiskit O3, per device."""
    rows = by_device(result)
    devs = [d for d in rows if BASELINE in rows[d]]
    strats = [s for s in STRATEGIES if s != BASELINE and any(s in rows[d] for d in devs)]
    data = [[100 * (rows[d][s]["success"] - rows[d][BASELINE]["success"]) if s in rows[d] else 0
             for d in devs] for s in strats]
    lim = max(1.0, max(abs(v) for row in data for v in row))
    fig, ax = plt.subplots(figsize=(10, 0.7 * len(strats) + 1.6), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.imshow(data, cmap=DIVERGING, vmin=-lim, vmax=lim, aspect="auto")
    win = winners(result)
    for i, s in enumerate(strats):
        for j, d in enumerate(devs):
            v = data[i][j]
            shown = round(v, 1)
            value = "0.0" if shown == 0 else f"{shown:+.1f}"  # no "-0.0" for tiny negatives
            mark = "  best" if win[d]["best"]["strategy"] == s else ""
            ax.text(j, i, f"{value}{mark}", ha="center", va="center", fontsize=9,
                    color="#ffffff" if abs(v) > 0.6 * lim else INK,
                    fontweight="bold" if mark else "normal")
    ax.set_xticks(range(len(devs)))
    ax.set_xticklabels([rows[d][BASELINE]["device_label"] for d in devs], fontsize=9, color=INK)
    ax.set_yticks(range(len(strats)))
    ax.set_yticklabels([STRATEGIES[s][0] for s in strats], fontsize=9, color=INK)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(which="both", length=0)
    ax.set_xticks([x - 0.5 for x in range(1, len(devs))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(strats))], minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.set_title("Estimated success vs Qiskit O3, in percentage points (blue = better, red = worse)",
                 color=INK, fontsize=10.5, loc="left")
    fig.tight_layout()
    return fig


def plot_hardware(check):
    """Measured vs ideal fidelity for the two halves of the one-job experiment."""
    fig, ax = plt.subplots(figsize=(6, 3.2), facecolor=SURFACE)
    _style(ax)
    labels = [check["a_label"], check["b_label"]]
    vals = [check["a_fidelity"], check["b_fidelity"]]
    cols = [SERIES.get(check["a"], "#2a78d6"), SERIES.get(check["b"], "#eb6834")]
    ax.bar(labels, vals, color=cols, width=0.5)
    for x, v in enumerate(vals):
        ax.text(x, v + 0.01, f"{v:.3f}", ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Hellinger fidelity to ideal", color=INK_2, fontsize=9)
    ax.set_title(f"Measured on {check['backend']}", color=INK, fontsize=10.5, loc="left")
    fig.tight_layout()
    return fig
