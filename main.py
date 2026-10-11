"""Landfall: see what your circuit optimizations look like after they hit the hardware.

Press Run, pick a backend in the Select QPU dialog, and set the options in Run settings:
  circuit   preset name: qft5, toffoli, adder, grover3, random_ct
  qasm      optional OpenQASM 2 to analyze instead of a preset (overrides circuit)
  devices   comma-separated device ladder; IBM names are fake-backend names (e.g. fez, torino,
            kyiv) and "ionq" is the all-to-all trapped-ion model
  hardware_check  run the best and worst strategy side by side on the selected backend (one job)
"""
import json
import sys

import matplotlib.pyplot as plt

from landfall import circuits, engine, hardware, report, verdict
from landfall.devices import DEFAULT_DEVICES

IN_BROWSER = sys.platform == "emscripten"


def _pick_device(result, backend):
    """Match the selected backend to an analyzed device so the check uses its winner and loser."""
    win = verdict.winners(result)
    name = hardware.backend_name(backend).lower()
    if "ionq" in name and "ionq_forte" in win:
        return "ionq_forte"
    for dev in win:
        if dev.replace("fake_", "") in name:
            return dev
    # Fall back to the device where the strategies differ the most.
    return max(win, key=lambda d: win[d]["best"]["success"] - win[d]["worst"]["success"])


def _show(fig, filename):
    if IN_BROWSER:
        plt.show()
    else:
        fig.savefig(filename, dpi=160, facecolor=fig.get_facecolor())
        print(f"  saved {filename}")
    plt.close(fig)


def _send(name, payload):
    if IN_BROWSER:
        from js import sendFile
        sendFile(name, "application/json", payload)
    else:
        with open(name, "w") as fh:
            fh.write(payload)


def main(circuit: str = "adder", qasm: str = "", devices: str = "kolkata,sherbrooke,fez,miami,ionq", hardware_check: bool = True, shots: int = 2000):
    print("LANDFALL: does your optimization survive the hardware?\n")
    qc = circuits.load(circuit, qasm)
    desc = circuits.PRESETS.get(qc.name, "custom OpenQASM circuit")
    print(f"Circuit: {qc.name} ({desc}), {qc.num_qubits} qubits")
    print(f"Devices: {devices or DEFAULT_DEVICES}\n")

    result = engine.analyze(qc, devices or DEFAULT_DEVICES)
    report.print_tables(result)

    print("\nWhat happened")
    for line in verdict.explain(result):
        print(f"  - {line}")

    _show(report.plot_gates(result), f"{qc.name}_gates.png")
    _show(report.plot_success_delta(result), f"{qc.name}_success.png")

    check = None
    be = globals().get("backend")
    if hardware_check and be is not None:
        dev = _pick_device(result, be)
        w = verdict.winners(result)[dev]
        # The two halves are compiled together, so only strategies that differ in the circuit itself
        # (not in the Qiskit optimization level) can be compared fairly on hardware.
        fair = [r for r in w["ranked"] if r["strategy"] in ("qiskit_o3", "zx_teleport", "zx_full")]
        best_fair = w["best"] if w["best"] in fair else fair[0]
        a, b = best_fair["strategy"], fair[-1]["strategy"]
        w = {"best": best_fair, "worst": fair[-1]}
        if a == b:
            print("\nAll strategies tie on this device, so there is nothing to compare on hardware.")
        else:
            print(f"\nUsing the ranking for {w['best']['device_label']}: best = {w['best']['strategy_label']}, "
                  f"worst = {w['worst']['strategy_label']}")
            check = hardware.run(result, a, b, be, shots=shots)
            _show(report.plot_hardware(check), f"{qc.name}_hardware.png")
            gap = check["a_fidelity"] - check["b_fidelity"]
            if abs(gap) < 0.01:
                print(f"  The measured gap ({gap:+.3f}) is within shot noise at {shots} shots: "
                      "on this backend the two strategies are indistinguishable.")
            elif gap > 0:
                print("  The predicted winner also measured closer to the ideal output.")
            else:
                print("  The measured result disagrees with the prediction; the estimate ignores idle "
                      "decoherence and crosstalk, and shot noise matters at small gaps.")
            if check["a_fidelity"] > 0.99 and check["b_fidelity"] > 0.99:
                print("  Both are near 1.0: either this backend is noiseless (pick an IBM noise model or an "
                      "IonQ simulator) or the circuit is too small for noise to separate the strategies.")
    elif hardware_check:
        print("\n(No backend available, skipping the hardware check.)")

    payload = {k: v for k, v in result.items() if k != "optimized"}
    payload["verdict"] = verdict.explain(result)
    payload["hardware_check"] = check
    _send(f"landfall_{qc.name}.json", json.dumps(payload, indent=2, default=str))
    print(f"\nDone in {result['elapsed_s']}s of analysis.")


if not IN_BROWSER and __name__ == "__main__":
    main()
