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
2. **Verify** every optimized circuit is exactly equivalent to the original (unitary comparison up to global phase).
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

## Limitations

- IBM error rates come from the calibration snapshots shipped with `qiskit-ibm-runtime` fake backends, not live data.
- The IonQ Forte model uses nominal fidelities (1Q error 2e-4, 2Q error 4e-3, readout error 5e-3), editable in `landfall/devices.py`. IonQ also compiles circuits again on its side.
- The success estimate ignores idle errors, so it undervalues depth reductions.
- Exact equivalence checking limits circuits to 12 qubits.
- Results depend on the transpiler seed. Landfall fixes it for reproducibility.
- PyZX circuit extraction is not fully deterministic across Python versions, so ZX full counts can differ slightly between environments; the rankings do not change.

## Prior work and credits

Landfall builds on **[ZXScope](https://zxscope.vercel.app/)**, my earlier web tool that runs PyZX reductions on a QASM circuit and shows gate count, T-count, depth and the ZX graph before and after. ZXScope existed before the hackathon and only looked at the circuit before hardware.

**New during the hackathon:** everything in this project. That includes the hardware-aware compilation across a device ladder, the IBM vs. IonQ comparison, routing-overhead and success-probability metrics, exact equivalence verification, the verdict engine, the charts and the one-job hardware check. No ZXScope code is reused here.

Built with [Qiskit](https://www.ibm.com/quantum/qiskit), [qiskit-ibm-runtime](https://github.com/Qiskit/qiskit-ibm-runtime) fake backends and [PyZX](https://github.com/zxcalc/pyzx).

## License

MIT. See `LICENSE`.
