"""`python -m nexora.worker`: the one-shot process a host starts for each request."""

import json
import os
import subprocess
import sys

import pytest

from nexora import __version__

HELLO = 'fn main() {\n    print("Hello from NEXORA")\n}\n'
POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="the operating-system limits use POSIX `resource` and `signal`")
# The limit of memory is the address space of the process (RLIMIT_AS). The kernel of Linux enforces
# it; the one of macOS accepts it and does not apply it, so there the program keeps growing until
# the machine runs out of memory. Windows has no `resource` at all.
MEMORY_LIMIT_ONLY = pytest.mark.skipif(
    os.name == "nt" or sys.platform == "darwin",
    reason="the operating system does not enforce the limit of address space (RLIMIT_AS)",
)


def worker(request, *, raw: bytes | None = None, timeout: float = 60) -> tuple[int, dict, str]:
    """Runs the worker exactly as a host would: isolated mode, JSON on standard input."""
    data = raw if raw is not None else json.dumps(request).encode("utf-8")
    process = subprocess.run(
        [sys.executable, "-I", "-m", "nexora.worker"], input=data, capture_output=True, timeout=timeout,
    )
    return process.returncode, json.loads(process.stdout.decode("utf-8")), process.stderr.decode("utf-8", "replace")


def test_run():
    code, response, error = worker({"action": "run", "code": HELLO})
    assert (code, error) == (0, "")
    assert (response["status"], response["output"], response["diagnostics"]) == ("success", "Hello from NEXORA\n", [])
    assert response["version"] == __version__
    assert isinstance(response["duration_ms"], int) and response["duration_ms"] >= 0


def test_check_does_not_print_the_program_output():
    code, response, _ = worker({"action": "check", "code": 'fn main() {\n    print("RAN")\n    print(1 / 0)\n}'})
    assert (code, response["action"], response["status"], response["output"]) == (0, "check", "success", "")


def test_diagnostics_use_the_virtual_file_name():
    _, response, _ = worker({"action": "run", "code": "fn main() {\n    print(x)\n}", "filename": "demo.nex"})
    assert response["status"] == "invalid"
    assert (response["diagnostics"][0]["file"], response["diagnostics"][0]["line"]) == ("demo.nex", 2)


def test_limits_from_the_request_are_applied():
    program = 'fn main() {\n    print("0123456789")\n    print("0123456789")\n}'
    _, response, _ = worker({"action": "run", "code": program, "limits": {"output_bytes": 15}})
    assert response["status"] == "output_limit"
    assert response["output"] == "0123456789\n0123"

    grow = 'fn main() {\n    let a = "abcdefgh"\n    let b = a + a + a\n    print(b)\n}'
    _, response, _ = worker({"action": "run", "code": grow, "limits": {"text_chars": 10}})
    assert (response["status"], response["diagnostics"][0]["code"]) == ("runtime_error", "E3006")


def test_info():
    code, response, _ = worker({"action": "info"})
    assert code == 0 and response["version"] == __version__
    assert "fn" in response["keywords"] and "print" in response["builtins"]


def test_non_ascii_text_survives_the_round_trip():
    _, response, _ = worker({"action": "run", "code": 'fn main() {\n    print("año ✓ 日本")\n}'})
    assert response["output"] == "año ✓ 日本\n"


@pytest.mark.parametrize("raw", [
    b"", b"not json", b"[]", b'"text"', b"{}", b'{"action": "run"}', b'{"action": "run", "code": 5}',
    b'{"action": "explode", "code": ""}', b'{"action": "run", "code": "", "filename": 7}',
    b'{"action": "run", "code": "", "limits": "none"}', b"\xff\xfe\x00",
], ids=lambda raw: repr(raw)[:30])
def test_a_malformed_request_gets_a_controlled_answer(raw):
    code, response, error = worker(None, raw=raw)
    assert code == 1
    assert response == {"schema": "nexora.result/1", "status": "internal_error"}
    # Only the kind of failure is logged: no traceback and nothing from the request.
    assert error.startswith("nexora worker failed: ") and "Traceback" not in error and len(error.splitlines()) == 1


def test_an_oversized_request_is_refused():
    code, response, _ = worker(None, raw=b'{"action": "run", "code": "' + b"a" * 1_100_000 + b'"}')
    assert (code, response["status"]) == (1, "internal_error")


def test_the_worker_does_not_echo_source_code_in_its_logs():
    _, _, error = worker(None, raw=b'{"action": "run", "code": 12345678}')
    assert "12345678" not in error


def test_isolated_mode_ignores_python_environment_variables(tmp_path):
    # With -I, a PYTHONPATH or PYTHONSTARTUP planted in the environment has no effect.
    (tmp_path / "json.py").write_text("raise SystemExit('hijacked')\n", encoding="utf-8")
    environment = {**os.environ, "PYTHONPATH": str(tmp_path), "PYTHONSTARTUP": str(tmp_path / "json.py")}
    process = subprocess.run(
        [sys.executable, "-I", "-m", "nexora.worker"], input=json.dumps({"action": "run", "code": HELLO}).encode(),
        capture_output=True, env=environment, cwd=tmp_path,
    )
    assert process.returncode == 0
    assert json.loads(process.stdout)["output"] == "Hello from NEXORA\n"


# Limits enforced by the operating system. They cannot run on Windows, and the limit of memory
# cannot run on macOS either (see MEMORY_LIMIT_ONLY).

DOUBLE = 'fn grow(text: Text, times: Int) gives Text {\n    if times == 0 {\n        return text\n    }\n    return grow(text + text, times - 1)\n}\nfn main() {\n    let big = grow("ab", 40)\n    print("unreachable")\n}'
SLOW = "fn fib(n: Int) gives Int {\n    if n < 2 {\n        return n\n    }\n    return fib(n - 1) + fib(n - 2)\n}\nfn main() {\n    print(fib(45))\n}"


@MEMORY_LIMIT_ONLY
def test_memory_limit_is_enforced_by_the_operating_system():
    _, response, _ = worker({"action": "run", "code": DOUBLE, "limits": {"memory_bytes": 256 * 1024 * 1024}})
    assert response["status"] == "memory_limit"
    assert "unreachable" not in response["output"]
    # It ran out while the program was running: the same status, with its diagnostic (decision 0009).
    assert [diagnostic["code"] for diagnostic in response["diagnostics"]] == ["E3007"]


@POSIX_ONLY
def test_wall_clock_limit_ends_the_process():
    process = subprocess.run(
        [sys.executable, "-I", "-m", "nexora.worker"],
        input=json.dumps({"action": "run", "code": SLOW, "limits": {"wall_seconds": 1}}).encode(),
        capture_output=True, timeout=30,
    )
    assert process.returncode != 0 and process.stdout == b""


@POSIX_ONLY
def test_cpu_limit_ends_the_process():
    process = subprocess.run(
        [sys.executable, "-I", "-m", "nexora.worker"],
        input=json.dumps({"action": "run", "code": SLOW, "limits": {"cpu_seconds": 1}}).encode(),
        capture_output=True, timeout=30,
    )
    assert process.returncode != 0 and process.stdout == b""
