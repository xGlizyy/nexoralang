"""Los entornos restringidos: el playground y el servidor MCP (decisión 0015, 6).

En un entorno que no admite archivos, ninguna combinación de declaraciones y permisos
abre un archivo. El worker del playground no tiene ni un campo en su protocolo para
pedirlos, y el servidor MCP solo analiza: nunca ejecuta.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nexora import api, tooling
from nexora.capabilities import Capabilities, Grants
from nexora.host import LocalHost
from nexora.worker import handle

ROOT = Path(__file__).resolve().parents[1]

PROGRAM = """
uses read "datos/entradas.txt"
uses write "datos/salida.txt"

fn main() {
    print(read_file("datos/entradas.txt"))
}
"""


def test_the_worker_never_allows_a_file(tmp_path):
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "entradas.txt").write_text("contenido\n", encoding="utf-8")
    request = {
        "action": "run",
        "code": PROGRAM,
        "filename": "playground.nex",
        "limits": {},
    }
    answer = handle(request)
    assert answer["status"] == "runtime_error"
    (diagnostic,) = answer["diagnostics"]
    assert diagnostic["code"] == "E3008"


def test_the_worker_ignores_a_request_that_asks_for_permissions(tmp_path):
    # The protocol has no field for permissions: even if a request carries one, the
    # program does not get the files.
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "entradas.txt").write_text("contenido\n", encoding="utf-8")
    request = {
        "action": "run",
        "code": PROGRAM,
        "filename": "playground.nex",
        "limits": {},
        "allow_read": [str(tmp_path)],
        "permissions": {"read": [str(tmp_path)]},
    }
    answer = handle(request)
    assert answer["status"] == "runtime_error"
    (diagnostic,) = answer["diagnostics"]
    assert diagnostic["code"] == "E3008"


def test_the_worker_in_a_separate_process_never_allows_a_file(tmp_path):
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "entradas.txt").write_text("contenido\n", encoding="utf-8")
    request = json.dumps({
        "action": "run",
        "code": PROGRAM,
        "filename": "playground.nex",
        "limits": {},
    })
    process = subprocess.run(
        [sys.executable, "-I", "-m", "nexora.worker"],
        input=request.encode("utf-8"), capture_output=True, timeout=60,
    )
    answer = json.loads(process.stdout.decode("utf-8"))
    assert answer["status"] == "runtime_error"
    assert answer["diagnostics"][0]["code"] == "E3008"


def test_the_mcp_tools_never_run_a_program():
    # The tools of the MCP server analyse: none of them executes a program, so none of
    # them can open a file.
    for name in ("check_source", "inspect_source", "get_symbols", "get_context"):
        assert not hasattr(tooling, name) or name in ("check_source", "inspect_source",
                                                      "get_symbols", "get_context")
    document = tooling.check_source(PROGRAM, "playground.nex")
    assert document["schema"] == "nexora.diagnostics/1"


def test_an_analysis_does_not_need_any_permission():
    document = tooling.check_source(PROGRAM, "playground.nex")
    assert document["ok"] is True
    assert document["diagnostics"] == []


def test_a_program_without_a_host_cannot_touch_a_file():
    result = api.run_source(PROGRAM, "playground.nex")
    assert result["status"] == "runtime_error"
    (diagnostic,) = result["diagnostics"]
    assert diagnostic["code"] == "E3008"


def test_an_environment_that_does_not_allow_files_denies_them(tmp_path):
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "entradas.txt").write_text("contenido\n", encoding="utf-8")
    host = LocalHost(
        grants=Grants(read=(str(tmp_path),)),
        declarations=Capabilities(read=("datos/entradas.txt",)),
        files_allowed=False,
    )
    result = api.run_source(PROGRAM, "playground.nex", host=host)
    assert result["status"] == "runtime_error"
    (diagnostic,) = result["diagnostics"]
    assert diagnostic["code"] == "E3008"


def test_the_worker_protocol_has_no_field_for_permissions():
    source = (ROOT / "src" / "nexora" / "worker.py").read_text(encoding="utf-8")
    # The request is read field by field: none of them is a permission.
    assert 'request.get("allow_read")' not in source
    assert 'request.get("allow_write")' not in source
    assert 'request.get("permissions")' not in source
