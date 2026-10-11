"""Landfall web API, served as one Vercel Function (entrypoint set in pyproject.toml).

POST /api/analyze  {"preset" | "qasm" | "qiskit": str, "devices": [str]} -> analysis report
GET  /api/presets  preset names and descriptions
GET  /api/health   {"status": "ok"}
"""
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore", category=SyntaxWarning)  # pyzx docstring escapes
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from qiskit import qasm2

import landfall
from landfall import circuits, qiskit_input, verdict
from landfall.devices import LADDER
from landfall.strategies import STRATEGIES

MAX_TEXT = 100_000  # characters of pasted QASM or Qiskit code
MAX_GATES = 5_000  # gates in the input circuit
MAX_COMPILED_QASM = 2_500_000  # characters; Vercel caps a function response at 4.5 MB
WEB_DEVICES = [k for k, *_ in LADDER]
TOO_MANY_QUBITS = f"Landfall analyzes circuits up to {circuits.MAX_QUBITS} qubits."

app = FastAPI(title="Landfall", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")


class AnalyzeRequest(BaseModel):
    preset: str | None = None
    qasm: str | None = None
    qiskit: str | None = None
    devices: list[str] | None = None


def _device_keys(names):
    if names is None:
        return WEB_DEVICES
    keys = set()
    for name in names:
        k = name.strip().lower()
        k = "ionq_forte" if k in ("ionq", "forte") else k if k.startswith(("fake_", "ionq_")) else "fake_" + k
        if k not in WEB_DEVICES:
            raise HTTPException(400, f"Unknown device '{name}'. Choose from: kolkata, sherbrooke, fez, miami, ionq.")
        keys.add(k)
    if not keys:
        raise HTTPException(400, "Pick at least one device.")
    return [k for k in WEB_DEVICES if k in keys]


def _circuit(req: AnalyzeRequest):
    given = [(k, v) for k, v in (("preset", req.preset), ("qasm", req.qasm), ("qiskit", req.qiskit))
             if v and v.strip()]
    if len(given) != 1:
        raise HTTPException(400, 'Send exactly one circuit: a preset name, OpenQASM in "qasm" or Qiskit code in "qiskit".')
    kind, text = given[0]
    if len(text) > MAX_TEXT:
        raise HTTPException(400, f"The input is too long ({len(text):,} characters; the limit is {MAX_TEXT:,}).")
    try:
        if kind == "preset":
            return circuits.from_preset(text)
        if kind == "qiskit":
            return qiskit_input.parse(text)
        return circuits.from_qasm(text)
    except qiskit_input.QiskitInputError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        message = re.sub(r"^(?:<input>:)?(\d+),\d+:\s*", r"line \1: ", str(exc).strip().strip('"'))
        prefix = "Could not read the OpenQASM: " if kind == "qasm" else ""
        raise HTTPException(400, prefix + (message or type(exc).__name__))


def _to_json(report):
    out = {k: v for k, v in report.items() if k not in ("optimized", "compiled")}
    compiled = {key: qasm2.dumps(c) for key, c in report["compiled"].items()}
    include = sum(map(len, compiled.values())) <= MAX_COMPILED_QASM
    out["rows"] = [dict(r, compiled_qasm=compiled[(r["device"], r["strategy"])] if include else None)
                   for r in report["rows"]]
    out["compiled_qasm_omitted"] = not include
    out["optimized_qasm"] = {s: qasm2.dumps(c) for s, c in report["optimized"].items()}
    out["best"] = {d: w["best"]["strategy"] for d, w in verdict.winners(report).items()}
    out["strategies"] = {s: {"label": label, "description": desc} for s, (label, desc, _) in STRATEGIES.items()}
    return out


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    qc = _circuit(req)
    devices = _device_keys(req.devices)
    if qc.num_qubits > circuits.MAX_QUBITS:
        raise HTTPException(400, TOO_MANY_QUBITS)
    if qc.size() > MAX_GATES:
        raise HTTPException(400, f"The circuit has {qc.size():,} gates; the limit is {MAX_GATES:,}.")
    try:
        report = landfall.analyze(qc, devices)
    except ValueError as exc:  # unsupported operations, unbound parameters
        raise HTTPException(400, str(exc))
    return _to_json(report)


@app.get("/api/presets")
def presets():
    return [{"name": k, "description": v} for k, v in circuits.PRESETS.items()]


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError):
    parts = []
    for err in exc.errors():
        if err.get("type") == "json_invalid":
            return JSONResponse(status_code=400, content={"detail": "Invalid request: the body is not valid JSON."})
        where = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
        parts.append(f"{where}: {err['msg']}" if where else err["msg"])
    return JSONResponse(status_code=400, content={"detail": "Invalid request. " + "; ".join(parts)})


@app.exception_handler(Exception)
async def _unexpected(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": f"Analysis failed unexpectedly: {exc}"})
