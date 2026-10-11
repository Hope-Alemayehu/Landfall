"""Safe reader for the website's Qiskit tab.

Pasted code is parsed with ast and interpreted against an allowlist; it is never executed.
Supported: imports of QuantumCircuit, QFTGate and pi; one QuantumCircuit(n) or (n, m);
standard gate calls; measure, measure_all and barrier (ignored, like everywhere in Landfall);
qc.append(QFTGate(k), range(...)); for loops over range(); numeric variables; arithmetic
with + - * / // % ** and pi. Everything else is rejected with the line and the construct.
"""
import ast
import math

from qiskit import QuantumCircuit
from qiskit.circuit.library import QFTGate

from .circuits import MAX_QUBITS

MAX_GATES = 5_000
MAX_ITERATIONS = 10_000  # loop iterations in total
MAX_STEPS = 200_000  # statements executed in total
MAX_CLBITS = 1_000
MAX_LIST = 64  # qubits in one broadcast argument
SUGGEST = "Paste qasm2.dumps(qc) into the QASM tab instead."

# gate -> (number of angle parameters, number of qubits); parameters come first, as in Qiskit
GATES = {
    **{g: (0, 1) for g in ("h", "x", "y", "z", "s", "sdg", "t", "tdg", "sx")},
    **{g: (1, 1) for g in ("rx", "ry", "rz", "p")},
    "u": (3, 1),
    **{g: (0, 2) for g in ("cx", "cy", "cz", "ch", "swap")},
    **{g: (1, 2) for g in ("cp", "crx", "cry", "crz", "rxx", "ryy", "rzz")},
    **{g: (0, 3) for g in ("ccx", "cswap")},
}
IGNORED = {"measure", "measure_all", "barrier", "draw"}
FROM_IMPORTS = {"qiskit": {"QuantumCircuit"}, "qiskit.circuit.library": {"QFTGate"},
                "math": {"pi"}, "numpy": {"pi"}}
MODULE_IMPORTS = {"math", "numpy"}  # for math.pi / np.pi
CONSTRUCTS = {
    ast.FunctionDef: "def", ast.AsyncFunctionDef: "async def", ast.Lambda: "lambda", ast.ClassDef: "class",
    ast.While: "while loop", ast.If: "if statement", ast.IfExp: "conditional expression",
    ast.With: "with statement", ast.Try: "try statement", ast.Return: "return", ast.Delete: "del",
    ast.Global: "global", ast.Nonlocal: "nonlocal", ast.AugAssign: "augmented assignment (+=)",
    ast.ListComp: "list comprehension", ast.GeneratorExp: "generator expression",
    ast.DictComp: "dict comprehension", ast.SetComp: "set comprehension", ast.Subscript: "indexing",
    ast.Dict: "dictionary", ast.JoinedStr: "f-string", ast.Await: "await", ast.Yield: "yield",
    ast.Starred: "star argument", ast.Compare: "comparison", ast.BoolOp: "boolean operator",
}


class QiskitInputError(ValueError):
    """Pasted code that falls outside the supported subset."""


def parse(code: str) -> QuantumCircuit:
    """Interpret pasted Qiskit code and return the circuit it builds."""
    try:
        tree = ast.parse(code, mode="exec")  # parsing only: nothing is compiled to bytecode or run
    except SyntaxError as exc:
        raise QiskitInputError(f"Line {exc.lineno}: Python syntax error ({exc.msg}). {SUGGEST}")
    except (ValueError, RecursionError, MemoryError):
        raise QiskitInputError(f"The code could not be parsed. {SUGGEST}")
    reader = _Reader(code)
    try:
        reader.run(tree.body)
    except RecursionError:
        raise QiskitInputError(f"An expression is nested too deeply. {SUGGEST}")
    if reader.circuit is None:
        raise QiskitInputError("No circuit found. Start with qc = QuantumCircuit(n).")
    reader.circuit.name = "custom"
    return reader.circuit


class _Reader:
    def __init__(self, source):
        self.source = source
        self.values = {}  # numeric variables, including loop variables
        self.symbols = {}  # imported names: alias -> "QuantumCircuit" | "QFTGate" | "pi"
        self.modules = {}  # module alias -> "math" | "numpy"
        self.circuit = None
        self.circuit_var = None
        self.iterations = 0
        self.steps = 0

    # errors ---------------------------------------------------------------------------------
    def _fail(self, node, what, suggest=True):
        tail = f" {SUGGEST}" if suggest else ""  # the QASM tab has the same qubit and gate caps
        raise QiskitInputError(f"Line {getattr(node, 'lineno', '?')}: {what}.{tail}")

    def _snippet(self, node):
        text = ast.get_source_segment(self.source, node) or type(node).__name__
        text = " ".join(text.split())
        return text if len(text) <= 40 else text[:37] + "..."

    def _unsupported(self, node):
        kind = CONSTRUCTS.get(type(node))
        detail = f" ({kind})" if kind else ""
        self._fail(node, f"`{self._snippet(node)}`{detail} is not supported in the Qiskit tab")

    # statements -------------------------------------------------------------------------------
    def run(self, body):
        for node in body:
            self.steps += 1
            if self.steps > MAX_STEPS:
                self._fail(node, f"the code runs more than {MAX_STEPS:,} steps")
            if isinstance(node, ast.ImportFrom):
                self._import_from(node)
            elif isinstance(node, ast.Import):
                self._import(node)
            elif isinstance(node, ast.Assign):
                self._assign(node)
            elif isinstance(node, ast.For):
                self._for(node)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                self._call(node.value)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Name):
                continue  # a bare `qc` line, as notebooks use to display the circuit
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                continue  # a docstring
            elif isinstance(node, ast.Pass):
                continue
            else:
                self._unsupported(node.value if isinstance(node, ast.Expr) else node)

    def _import_from(self, node):
        allowed = FROM_IMPORTS.get(node.module or "")
        for alias in node.names:
            if node.level or allowed is None or alias.name not in allowed:
                self._fail(node, f"`{self._snippet(node)}` is not allowed; only QuantumCircuit (from qiskit), "
                                 "QFTGate (from qiskit.circuit.library) and pi (from math or numpy) can be imported")
            self.symbols[alias.asname or alias.name] = alias.name

    def _import(self, node):
        for alias in node.names:
            if alias.name not in MODULE_IMPORTS:
                self._fail(node, f"`{self._snippet(node)}` is not allowed; only `import math` and "
                                 "`import numpy` (for pi) can be imported this way")
            self.modules[alias.asname or alias.name] = alias.name

    def _assign(self, node):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            self._unsupported(node)
        name, value = node.targets[0].id, node.value
        if isinstance(value, ast.Call) and self._is_symbol(value.func, "QuantumCircuit"):
            self._new_circuit(name, value)
        else:
            self.values[name] = self._number(value)
            if name == self.circuit_var:
                self._fail(node, f"`{name}` is the circuit and cannot be reassigned")

    def _new_circuit(self, name, call):
        if self.circuit is not None:
            self._fail(call, "only one QuantumCircuit can be defined")
        if call.keywords or not 1 <= len(call.args) <= 2:
            self._fail(call, "use QuantumCircuit(n) or QuantumCircuit(n, m) with numbers")
        sizes = [self._int(a) for a in call.args]
        if not 1 <= sizes[0] <= MAX_QUBITS:
            self._fail(call, f"QuantumCircuit({sizes[0]}): Landfall analyzes circuits up to {MAX_QUBITS} qubits",
                       suggest=False)
        if len(sizes) == 2 and not 0 <= sizes[1] <= MAX_CLBITS:
            self._fail(call, f"QuantumCircuit(n, {sizes[1]}): use 0 to {MAX_CLBITS:,} classical bits")
        self.circuit, self.circuit_var = QuantumCircuit(*sizes), name
        self.values.pop(name, None)

    def _for(self, node):
        if node.orelse or not isinstance(node.target, ast.Name):
            self._unsupported(node)
        items = self._range(node.iter)
        self.iterations += len(items)
        if self.iterations > MAX_ITERATIONS:
            self._fail(node, f"loops run more than {MAX_ITERATIONS:,} iterations in total")
        for i in items:
            self.values[node.target.id] = i
            self.run(node.body)

    def _call(self, call):
        func = call.func
        if isinstance(func, ast.Name) and func.id == "print":
            return self._ignore_args(call)
        if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
            self._fail(call, f"`{self._snippet(call)}` is not supported; only gate calls on the circuit are")
        if self.circuit is None or func.value.id != self.circuit_var:
            self._fail(call, f"`{self._snippet(call)}` is not supported; call gates on the circuit "
                             "(qc = QuantumCircuit(n) first)")
        method = func.attr
        if method in IGNORED:
            if method in ("measure", "barrier"):
                for arg in call.args:
                    self._qubits(arg)
            return self._ignore_args(call, check_args=method not in ("measure", "barrier"))
        if method == "append":
            return self._append_qft(call)
        if method not in GATES:
            self._fail(call, f"`{self._snippet(call)}`: `{method}` is not a supported gate (supported: "
                             f"{', '.join(GATES)}, measure, barrier, append(QFTGate(k), ...))")
        if call.keywords:
            self._fail(call, f"`{self._snippet(call)}`: pass gate arguments by position, not by keyword")
        n_params, n_qubits = GATES[method]
        if len(call.args) != n_params + n_qubits:
            self._fail(call, f"`{method}` takes {n_params} angle(s) and {n_qubits} qubit(s), "
                             f"got {len(call.args)} argument(s)")
        params = [self._number(a) for a in call.args[:n_params]]
        qubits = [self._qubits(a) for a in call.args[n_params:]]
        self._apply(call, lambda: getattr(self.circuit, method)(*params, *qubits))

    def _append_qft(self, call):
        if call.keywords or len(call.args) != 2:
            self._fail(call, "only qc.append(QFTGate(k), qubits) is supported")
        gate = call.args[0]
        if not (isinstance(gate, ast.Call) and self._is_symbol(gate.func, "QFTGate")
                and len(gate.args) == 1 and not gate.keywords):
            self._fail(call, f"`{self._snippet(call)}`: only QFTGate(k) can be appended")
        k = self._int(gate.args[0])
        qubits = self._qubits(call.args[1])
        qubits = qubits if isinstance(qubits, list) else [qubits]
        if not 1 <= k <= MAX_QUBITS or len(qubits) != k:
            self._fail(call, f"QFTGate({k}) needs exactly {k} qubits, got {len(qubits)}")
        self._apply(call, lambda: self.circuit.append(QFTGate(k), qubits))

    def _apply(self, call, add):
        try:
            add()
        except Exception as exc:  # out-of-range or repeated qubits, raised by Qiskit itself
            self._fail(call, f"`{self._snippet(call)}`: {str(exc).strip(chr(39) + chr(34)).rstrip('.')}")
        if len(self.circuit.data) > MAX_GATES:
            self._fail(call, f"the circuit has more than {MAX_GATES:,} gates", suggest=False)

    def _ignore_args(self, call, check_args=True):
        """draw(), print(qc), measure_all(): ignored, but arguments must still be plain values."""
        args = (call.args if check_args else []) + [k.value for k in call.keywords]
        for arg in args:
            if not (isinstance(arg, ast.Constant) or isinstance(arg, ast.Name)):
                self._unsupported(arg)

    # expressions ------------------------------------------------------------------------------
    def _is_symbol(self, node, symbol):
        return isinstance(node, ast.Name) and self.symbols.get(node.id) == symbol

    def _number(self, node):
        if isinstance(node, ast.Constant):
            if type(node.value) in (int, float):
                return node.value
            self._fail(node, f"`{self._snippet(node)}` is not a number")
        if isinstance(node, ast.Name):
            if node.id in self.values:
                return self.values[node.id]
            if self.symbols.get(node.id) == "pi":
                return math.pi
            self._fail(node, f"`{node.id}` is not defined (only numbers, loop variables and pi are)")
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id in self.modules and node.attr == "pi":
            return math.pi
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = self._number(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp):
            return self._binop(node)
        if isinstance(node, ast.Attribute):
            self._fail(node, f"attribute access `{self._snippet(node)}` is not supported (only math.pi / np.pi)")
        self._unsupported(node)

    def _binop(self, node):
        a, b = self._number(node.left), self._number(node.right)
        op = node.op
        try:
            if isinstance(op, ast.Pow):
                if abs(b) > 64 or abs(a) > 2 ** 32:
                    self._fail(node, f"`{self._snippet(node)}`: the power is too large")
                v = a ** b
            elif isinstance(op, ast.Add):
                v = a + b
            elif isinstance(op, ast.Sub):
                v = a - b
            elif isinstance(op, ast.Mult):
                v = a * b
            elif isinstance(op, ast.Div):
                v = a / b
            elif isinstance(op, ast.FloorDiv):
                v = a // b
            elif isinstance(op, ast.Mod):
                v = a % b
            else:
                self._unsupported(node)
        except ZeroDivisionError:
            self._fail(node, f"`{self._snippet(node)}` divides by zero")
        except OverflowError:
            self._fail(node, f"`{self._snippet(node)}` is too large")
        if isinstance(v, complex) or (isinstance(v, float) and not math.isfinite(v)) or abs(v) > 1e18:
            self._fail(node, f"`{self._snippet(node)}` is not a usable number")
        return v

    def _int(self, node):
        v = self._number(node)
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        if not isinstance(v, int):
            self._fail(node, f"`{self._snippet(node)}` must be a whole number")
        return v

    def _range(self, node):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range"
                and 1 <= len(node.args) <= 3 and not node.keywords):
            self._fail(node, f"`{self._snippet(node)}`: loops and qubit lists must use range(...)")
        try:
            items = range(*[self._int(a) for a in node.args])
        except ValueError:
            self._fail(node, f"`{self._snippet(node)}`: the step cannot be zero")
        if len(items) > MAX_ITERATIONS:
            self._fail(node, f"`{self._snippet(node)}` has {len(items):,} items; the limit is {MAX_ITERATIONS:,}")
        return items

    def _qubits(self, node):
        """A qubit index, or a list of them (range(...), [..] or (..)) for broadcasting."""
        if isinstance(node, ast.Call):
            items = self._range(node)
        elif isinstance(node, (ast.List, ast.Tuple)):
            items = [self._int(e) for e in node.elts]
        else:
            return self._int(node)
        if len(items) > MAX_LIST:
            self._fail(node, f"`{self._snippet(node)}` lists more than {MAX_LIST} qubits")
        return list(items)
