# Landfall

**See what your circuit optimizations look like after they hit the hardware.**

Theme: **Quantum Unlocked** (making quantum compilation intuitive)

## The problem

Circuit optimizers report impressive numbers: fewer gates, lower T-count, shallower depth. But those numbers describe an ideal circuit that never runs anywhere. A real device has its own native gates, its own qubit connectivity and its own error rates. Once a circuit is compiled for it, routing can erase an optimization's gains or reverse them entirely.

Landfall makes that visible. It sends one circuit through several optimization strategies, compiles every result for a ladder of real devices from sparse to fully connected, and shows which strategy actually wins on each one, and why.

## What it does

1. **Optimize** the circuit four ways:
   | Strategy | What it does |
   |---|---|
   | Qiskit O1 | Qiskit's transpiler with light optimization |
   | Qiskit O3 | Qiskit's heaviest optimization (the baseline to beat) |
   | ZX teleport | PyZX `teleport_reduce`: cancels and merges phases through the ZX graph but keeps the circuit's structure, then Qiskit O3 |
   | ZX full | PyZX `full_reduce` plus circuit extraction: rebuilds the circuit from its simplified graph, then Qiskit O3 |
2. **Verify** every optimized circuit is equivalent to the original, up to global phase: by exact unitary comparison up to 6 qubits, and on 4 random input states (statevector simulation) above that.
3. **Compile** each one for a ladder of devices, ordered by connectivity:
   | Device | Family | Native 2Q gate | Connectivity |
   |---|---|---|---|
   | IBM Kolkata | Falcon r5 | CX | heavy-hex |
   | IBM Sherbrooke | Eagle r3 | ECR | heavy-hex |
   | IBM Fez | Heron r2 | CZ | heavy-hex |
   | IBM Miami | Nighthawk r1 | CZ | square lattice |
   | IonQ Forte | Trapped ion | ZZ | all-to-all |
4. **Measure** two-qubit gate count, T-count, depth, routing overhead (extra 2Q gates caused by limited connectivity) and an estimated success probability from each device's error rates.
5. **Explain** the result in plain language: who wins where, how much of the cost is routing, and when the gate count is misleading.
6. **Check on a real backend.** It runs the best and worst strategy side by side in a single job on whatever backend you select and compares each against the ideal output.

## What it found

Five preset circuits, four strategies, five devices. Every optimized circuit is verified exactly equivalent to its original.

- **The best strategy depends on the hardware.** On the 2+2-bit ripple-carry adder, ZX teleport wins on IBM Kolkata (+4.5 points of estimated success over Qiskit O3), IBM Miami and IonQ Forte. Qiskit O3 wins on IBM Sherbrooke and IBM Fez. On a random Clifford+T circuit, Qiskit O3 wins on all three heavy-hex devices while ZX teleport wins on the square lattice and all-to-all devices.
- **Aggressive optimization can backfire badly.** ZX full extraction rebuilds circuits with more CNOTs, and routing multiplies them. On the adder it goes from 44 (Qiskit O3) to 71 two-qubit gates on Kolkata, dropping estimated success from 0.70 to 0.61.
- **ZX teleport is a safe T-count win.** It cuts non-Clifford phases by 40% on QFT (30 to 18) and the adder (28 to 16) without adding two-qubit gates.
- **Routing is the hidden cost.** On heavy-hex devices, up to 58% of two-qubit gates are SWAP overhead. On all-to-all hardware it is zero, so strategy rankings move closer together.
- **Gate count is not the whole story.** On the Toffoli, Qiskit O1 beats Qiskit O3 on IBM Sherbrooke and IBM Fez despite using 9 two-qubit gates instead of 7, because its layout landed on better-calibrated qubits.
- **The measurements agree.** On Qollab's IBM Fez noise model, the adder's predicted winner (Qiskit O3) measured 0.934 Hellinger fidelity to the ideal output against 0.896 for the predicted loser (ZX full), at 2000 shots. At the default of 300 shots both values read lower (fewer shots lower both equally), but the order holds.

## How to run

1. Press **Run**.
2. In **Select QPU**, pick a backend. For the hardware check, an IBM noise model (such as IBM Fez) or an IonQ simulator shows real differences. The ideal simulators will show both strategies near 1.0.
3. In **Run settings**:
   - `circuit`: `qft5`, `toffoli`, `adder`, `grover3` or `random_ct`
   - `qasm`: paste OpenQASM 2 to analyze your own circuit (up to 12 qubits); this overrides `circuit`
   - `devices`: comma-separated list. Any IBM fake backend name works (`torino`, `kyiv`, `marrakesh`, ...); `ionq` is the trapped-ion model
   - `hardware_check`: run the one-job comparison on the selected backend
   - `shots`: shots for the hardware check

The console shows the tables and the explanation, followed by two charts (gate cost per device with routing overhead hatched, and the success-estimate change against Qiskit O3) and the hardware-check chart. A full JSON report is offered as a download.

## Website

The same analysis runs as a website. Pick a preset or paste a circuit, choose devices, and Landfall shows the verdict, a strategy-by-device grid of estimated success against Qiskit O3, a chip view (the selected device's qubit map with the qubits the compiled circuit uses and its busiest couplers lit up), two-qubit gate cost with routing overhead hatched, before and after metrics per strategy, the optimized and compiled QASM, and the same JSON report Qollab produces.

- **Inputs.** OpenQASM 2 or 3 (paste it or drop a `.qasm` file), or Qiskit code in the Qiskit tab; up to 12 qubits and 5,000 gates. Clicking a preset loads its code into the editor in either form, ready to edit; unedited preset code is analyzed as the preset itself, so its numbers match exactly.
- **Qiskit code is never executed.** `landfall/qiskit_input.py` parses it with Python's `ast` module and interprets an allowlist: one `QuantumCircuit`, standard gate calls, `range` loops, arithmetic with `pi` and `QFTGate`. Anything else is rejected with its line number.
- **Instant first load.** The page opens on a precomputed analysis of the adder preset (`public/data/adder.json`); Analyze calls the live API.
- **The hardware check stays on Qollab.** The website estimates; Qollab measures.

Run it locally:

```
python -m venv .venv
.venv\Scripts\activate             (macOS or Linux: source .venv/bin/activate)
pip install -r requirements.txt fastapi uvicorn
python scripts/dev_server.py       (then open http://127.0.0.1:8000)
```

Tests: `pip install pytest`, then `python -m pytest tests`. After changing the analysis, run `python scripts/export_example.py` to refresh the precomputed example, and after changing a preset, `python scripts/export_presets.py` to refresh the preset code in `public/presets.json` (tests fail when either is stale). `python scripts/export_devices.py` regenerates the chip maps in `public/devices/`.

Deploy notes (Vercel):

- One Vercel project from this repo, FastAPI framework preset. `api/index.py` is the function; `public/` is served from the CDN.
- `pyproject.toml` holds the website's pinned dependencies and `tool.vercel.entrypoint = "api.index:app"`. Vercel reads it instead of `requirements.txt`, which stays Qollab's, and never treats `main.py` as the web app.
- `vercel.json` sets a 60 second maximum duration and keeps tests and scripts out of the function.
- The function bundle is about 290 MB of the 500 MB Python limit (about 365 MB if Vercel adds precompiled bytecode).
- Vercel caps a function response at 4.5 MB, so for very large circuits the compiled QASM is left out of the response and the page says so.

## Use from Python

```python
from qiskit import QuantumCircuit
from landfall import analyze

qc = QuantumCircuit(3)
qc.h(0)
qc.cx(0, 1)
qc.ccx(0, 1, 2)

report = analyze(qc, devices=["fez", "ionq"])   # default: all five devices
print(report["verdict"][0])
for row in report["rows"]:
    print(row["device_label"], row["strategy_label"], row["two_q"], round(row["success"], 3))
```

`analyze(qc)` takes any `QuantumCircuit` up to 12 qubits (measurements, barriers and resets are ignored). The report has the fields of Qollab's JSON report (`input`, `logical`, `equivalent`, `rows`, `verdict` and so on) plus `optimized` (strategy to optimized `QuantumCircuit`) and `compiled` ((device, strategy) to compiled `QuantumCircuit`). Each row also lists `qubits_used` and `edge_usage` (two-qubit gates per physical coupler), which the chip view draws. Run it from the repo root after `pip install -r requirements.txt`.

## How it works

```
circuit ──► normalize ──► 4 strategies ──► equivalence check
                              │
                              ▼
            for each device: layout + routing + native gates (Qiskit)
                              │
                              ▼
           metrics ──► success estimate ──► verdict ──► charts
                              │
                              ▼
     best vs worst, side by side in ONE circuit ──► selected backend ──► fidelity
```

- **Routing overhead** is the 2Q count on the real device minus the 2Q count for the same strategy, gate set and optimization level with every qubit pair connected.
- **Estimated success** is the product of (1 - error) over every compiled gate and every readout, using the device's calibration data. It is a standard first-order figure of merit and ignores idle decoherence and crosstalk.
- **The one-job hardware check.** IonQ backends accept one job per run, so both circuits go into one: strategy A on qubits 0 to n-1, strategy B on qubits n to 2n-1. Both start from the same random product state so their ideal outputs are identical and non-trivial. Each half's measured distribution is compared with the ideal distribution using Hellinger fidelity.
- The two halves are compiled together, so the hardware check only compares strategies that differ in the circuit itself (Qiskit O3, ZX teleport, ZX full), not in the Qiskit optimization level. Gaps under 0.5/sqrt(shots) are reported as shot noise.
- **Ties.** A challenger must beat Qiskit O3 by at least 0.5 points of estimated success to be called the winner.

## Code

| File | Role |
|---|---|
| `main.py` | Entry point and run settings |
| `landfall/circuits.py` | Presets and QASM loading |
| `landfall/strategies.py` | The four optimization strategies |
| `landfall/devices.py` | Device ladder, hardware compilation, success estimate |
| `landfall/metrics.py` | Metrics and equivalence check |
| `landfall/engine.py` | Runs every strategy on every device |
| `landfall/verdict.py` | Plain-language findings |
| `landfall/report.py` | Tables and charts |
| `landfall/hardware.py` | One-job side-by-side hardware check |
| `landfall/qiskit_input.py` | Safe reader for the website's Qiskit tab |
| `api/index.py` | Web API (FastAPI, one Vercel Function) |
| `public/` | Website: `index.html`, `app.js`, `style.css`, chip maps and the precomputed example |
| `scripts/` | Local dev server, data exports and the local hardware-check runner |
| `tests/` | Equivalence check, Qiskit-tab reader and example-data tests |

## Limitations

- IBM error rates come from the calibration snapshots shipped with `qiskit-ibm-runtime` fake backends, not live data.
- The IonQ Forte model uses nominal fidelities (1Q error 2e-4, 2Q error 4e-3, readout error 5e-3), editable in `landfall/devices.py`. IonQ also compiles circuits again on its side.
- The success estimate ignores idle errors, so it undervalues depth reductions.
- Circuits are limited to 12 qubits. Up to 6 qubits equivalence is checked exactly; above that it is checked on 4 random input states, which catches any real difference with overwhelming probability but is not a proof.
- Results depend on the transpiler seed. Landfall fixes it for reproducibility.
- PyZX circuit extraction is not fully deterministic across Python versions, so ZX full counts can differ slightly between environments; the rankings do not change.

## Prior work and credits

Landfall builds on **[ZXScope](https://zxscope.vercel.app/)**, my earlier web tool that runs PyZX reductions on a QASM circuit and shows gate count, T-count, depth and the ZX graph before and after. ZXScope existed before the hackathon and only looked at the circuit before hardware.

**New during the hackathon:** everything in this project. That includes the hardware-aware compilation across a device ladder, the IBM vs. IonQ comparison, routing-overhead and success-probability metrics, exact equivalence verification, the verdict engine, the charts and the one-job hardware check. No ZXScope code is reused here.

Built with [Qiskit](https://www.ibm.com/quantum/qiskit), [qiskit-ibm-runtime](https://github.com/Qiskit/qiskit-ibm-runtime) fake backends and [PyZX](https://github.com/zxcalc/pyzx).

## License

MIT. See `LICENSE`.
