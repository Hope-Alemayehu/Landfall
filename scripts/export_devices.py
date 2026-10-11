"""Export device geometry for the website's chip view to public/devices/<key>.json.

Usage: python scripts/export_devices.py [--png DIR]

Coordinates come from Qiskit's built-in gate maps when one matches the qubit count; otherwise
they are derived from the coupling map (heavy-hex rows, or a square grid). Every layout is
checked: each coupler must join two qubits exactly one grid unit apart.
"""
import ast
import inspect
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from landfall import devices as dv

OUT = os.path.join(ROOT, "public", "devices")
IONQ_QUBITS = 36  # IonQ Forte


def builtin_coords():
    """Qiskit's hard-coded [row, col] maps from plot_gate_map, keyed by qubit count."""
    from qiskit.visualization import gate_map
    tree = ast.parse(inspect.getsource(gate_map.plot_gate_map).lstrip())
    maps = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Subscript)
                and getattr(node.targets[0].value, "id", None) == "qubit_coordinates_map"):
            maps[ast.literal_eval(node.targets[0].slice)] = ast.literal_eval(node.value)
    return maps


def heavy_hex_coords(n, edges):
    """Rows are runs of consecutively numbered, coupled qubits; bridge qubits join two rows."""
    adj = {q: set() for q in range(n)}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    rows, row_of, q = [], {}, 0
    while q < n:
        run = [q]
        while run[-1] + 1 < n and run[-1] + 1 in adj[run[-1]]:
            run.append(run[-1] + 1)
        if len(run) > 2:
            for i in run:
                row_of[i] = len(rows)
            rows.append(run)
        q = run[-1] + 1
    bridges = [q for q in range(n) if q not in row_of]
    offset = {0: 0}
    for b in bridges:  # bridges between row r and r+1 align the two rows' columns
        up, down = sorted(adj[b], key=lambda x: row_of[x])
        r = row_of[up]
        if r in offset and r + 1 not in offset:
            offset[r + 1] = offset[r] + (up - rows[r][0]) - (down - rows[r + 1][0])
    coords = [None] * n
    for r, run in enumerate(rows):
        for i in run:
            coords[i] = [offset[r] + i - run[0], 2 * r]
    for b in bridges:
        up = min(adj[b], key=lambda x: row_of[x])
        coords[b] = [coords[up][0], coords[up][1] + 1]
    shift = min(c[0] for c in coords)
    return [[x - shift, y] for x, y in coords]


def grid_coords(n, edges):
    for w in range(2, n):
        if n % w == 0 and all((b - a == 1 and a // w == b // w) or b - a == w for a, b in edges):
            return [[q % w, q // w] for q in range(n)]
    return None


def check(coords, edges):
    longest = max(math.dist(coords[a], coords[b]) for a, b in edges)
    unique = len({tuple(c) for c in coords}) == len(coords)
    return abs(longest - 1) < 1e-9 and unique


def export(key, label, family, topology):
    dev = dv.get(key)
    if dev.kind == "ion":
        r = IONQ_QUBITS / (2 * math.pi)  # neighbours one unit apart around the ring
        coords = [[round(r * math.cos(2 * math.pi * i / IONQ_QUBITS - math.pi / 2), 3),
                   round(r * math.sin(2 * math.pi * i / IONQ_QUBITS - math.pi / 2), 3)]
                  for i in range(IONQ_QUBITS)]
        return {"key": key, "label": label, "family": family, "topology": topology,
                "native_2q": dev.native_2q, "num_qubits": IONQ_QUBITS, "all_to_all": True,
                "edges": [], "coords": coords}, "ring"
    n = dev.backend.num_qubits
    edges = sorted({tuple(sorted(e)) for e in dev.backend.coupling_map.get_edges()})
    builtin = builtin_coords().get(n)
    if builtin and check([[c, r] for r, c in builtin], edges):
        coords, source = [[c, r] for r, c in builtin], "qiskit gate_map"
    elif (coords := grid_coords(n, edges)) is not None:
        source = "square grid"
    else:
        coords, source = heavy_hex_coords(n, edges), "heavy-hex rows"
    if not check(coords, edges):
        raise SystemExit(f"{key}: layout check failed ({source})")
    return {"key": key, "label": label, "family": family, "topology": topology,
            "native_2q": dev.native_2q, "num_qubits": n, "all_to_all": False,
            "edges": [list(e) for e in edges], "coords": coords}, source


def render(data, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    xs, ys = zip(*data["coords"])
    fig, ax = plt.subplots(figsize=(max(4, (max(xs) - min(xs)) * 0.45), max(3, (max(ys) - min(ys)) * 0.45)))
    for a, b in data["edges"]:
        ax.plot([xs[a], xs[b]], [ys[a], ys[b]], color="#b9b4aa", lw=1.5, zorder=1)
    ax.scatter(xs, ys, s=160, color="#f0efec", edgecolors="#7a4a2a", zorder=2)
    for i, (x, y) in enumerate(data["coords"]):
        ax.text(x, y, str(i), ha="center", va="center", fontsize=5.5, zorder=3)
    ax.set_title(f"{data['label']} ({data['num_qubits']} qubits, {len(data['edges'])} couplers)", fontsize=9)
    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.axis("off")
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def main():
    png_dir = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None
    os.makedirs(OUT, exist_ok=True)
    for key, label, family, topology in dv.LADDER:
        data, source = export(key, label, family, topology)
        with open(os.path.join(OUT, f"{key}.json"), "w") as fh:
            json.dump(data, fh, separators=(",", ":"))
        print(f"{key:<16} {data['num_qubits']:>4} qubits {len(data['edges']):>4} couplers  layout: {source}")
        if png_dir:
            os.makedirs(png_dir, exist_ok=True)
            render(data, os.path.join(png_dir, f"{key}.png"))


if __name__ == "__main__":
    main()
