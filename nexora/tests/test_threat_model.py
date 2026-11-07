"""Tests for the gaps listed in docs/threat-model.md: T4 (the network answer), modules and the child environment."""

from __future__ import annotations

import sys
from pathlib import Path


from nexora import cli
from nexora.capabilities import Capabilities, Grants
from nexora.host import LocalHost
from helpers import run_failure_with_host, run_with_host

ROOT = Path(__file__).resolve().parents[1]

NETWORK_PROGRAM = '''
uses network "https://example.com"

fn main() {
    print(Net.get("https://example.com/data"))
}
'''


def network_host() -> LocalHost:
    return LocalHost(
        grants=Grants(network=("https://example.com",)),
        declarations=Capabilities(network=("https://example.com",)),
        network_allowed=True,
    )


class Response:
    status = 200

    def __init__(self, body: bytes = b"ok"):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body[:limit]


def capture_handlers(monkeypatch, body: bytes = b"ok") -> list:
    """Replaces the opener and returns the handlers the host asked for."""
    handlers: list = []

    class Opener:
        def open(self, request, timeout):
            return Response(body)

    import nexora.host

    def build(*given):
        handlers.extend(given)
        return Opener()

    monkeypatch.setattr(nexora.host, "build_opener", build)
    return handlers


# T4: the network answer

def test_the_network_client_ignores_the_proxy_variables_of_the_environment(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    handlers = capture_handlers(monkeypatch)
    assert run_with_host(NETWORK_PROGRAM, network_host()) == "ok\n"
    proxies = [handler for handler in handlers if hasattr(handler, "proxies")]
    assert proxies and all(handler.proxies == {} for handler in proxies)


def test_the_network_client_refuses_to_follow_a_redirect(monkeypatch):
    handlers = capture_handlers(monkeypatch)
    run_with_host(NETWORK_PROGRAM, network_host())
    (redirect,) = [handler for handler in handlers if hasattr(handler, "redirect_request")]
    assert redirect.redirect_request(None, None, 302, "Found", {}, "https://elsewhere.invalid/") is None


def test_a_network_answer_over_one_mebibyte_is_an_error(monkeypatch):
    capture_handlers(monkeypatch, body=b"x" * 1_048_577)
    _, error = run_failure_with_host(NETWORK_PROGRAM, network_host())
    assert error.code == "E3014"


def test_a_network_answer_of_exactly_one_mebibyte_is_accepted(monkeypatch):
    capture_handlers(monkeypatch, body=b"x" * 1_048_576)
    assert run_with_host(NETWORK_PROGRAM, network_host()) == "x" * 1_048_576 + "\n"


# Modules do not inherit capabilities

def write_project(tmp_path: Path, module_declares: bool) -> Path:
    (tmp_path / "data.txt").write_text("hello\n", encoding="utf-8")
    uses = 'uses read "data.txt"\n\n' if module_declares else ""
    (tmp_path / "mod.nex").write_text(
        f'{uses}pub fn load() gives Text {{\n    return read_file("data.txt")\n}}\n', encoding="utf-8"
    )
    main = tmp_path / "main.nex"
    main.write_text(
        'import "mod.nex"\nuses read "data.txt"\n\nfn main() {\n    print(mod.load())\n}\n', encoding="utf-8"
    )
    return main


def test_a_module_that_reads_a_file_must_declare_it_even_if_the_program_does(tmp_path, capsys):
    main = write_project(tmp_path, module_declares=False)
    assert cli.main(["run", "--allow-read", str(tmp_path / "data.txt"), str(main)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "E2026" in captured.err and "mod.nex" in captured.err


def test_a_module_that_declares_what_it_reads_works_when_it_is_granted(tmp_path, monkeypatch, capsys):
    main = write_project(tmp_path, module_declares=True)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["run", "--allow-read", "data.txt", str(main)]) == 0
    assert capsys.readouterr().out == "hello\n\n"


# The environment of a child process

def test_a_child_process_does_not_receive_the_environment_of_the_user(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXORA_THREAT_MODEL_SECRET", "must-not-reach-the-child")
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent))
    command = Path(sys.executable).name
    program = (
        f'uses process "{command}"\n\n'
        "fn main() {\n"
        f'    print(Process.run("{command}", ["-c", "import os; print(\',\'.join(sorted(os.environ)))"]))\n'
        "}\n"
    )
    host = LocalHost(
        grants=Grants(process=(command,)), declarations=Capabilities(process=(command,)), processes_allowed=True
    )
    names = set(run_with_host(program, host).strip().split(","))
    # LC_CTYPE is added by Python on Linux (PEP 538) and __CF_USER_TEXT_ENCODING by macOS to every process that it starts.
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LC_CTYPE", "__CF_USER_TEXT_ENCODING"}
    assert "NEXORA_THREAT_MODEL_SECRET" not in names
    assert names <= allowed, sorted(names - allowed)
