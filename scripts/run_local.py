"""Run Landfall locally with a noisy simulator standing in for the Qollab backend.

Usage: python scripts/run_local.py [preset]

Needs qiskit-aer (local testing only; Qollab injects `backend` itself).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib

# Charts are only saved here. The default Tk backend aborts the process when Aer's worker
# thread garbage-collects a closed figure ("Tcl_AsyncDelete: async handler deleted by the wrong thread").
matplotlib.use("Agg")

from qiskit_aer import AerSimulator
from qiskit_ibm_runtime.fake_provider import FakeFez

import main

main.backend = AerSimulator.from_backend(FakeFez())
main.main(circuit=sys.argv[1] if len(sys.argv) > 1 else "adder")
