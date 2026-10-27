"""Explicit local CLI capabilities for HTTPS reads and external commands."""

from __future__ import annotations

import sys

import pytest

from nexora import api
from nexora.capabilities import Capabilities, Grants
from nexora.cli import main
from nexora.host import LocalHost
from nexora.worker import handle
from helpers import check_codes, run_failure_with_host, run_with_host


def test_https_requires_a_static_declaration():
    source = '''
fn main() {
    print(Net.get("https://example.com/data"))
}
'''
    assert check_codes(source) == ["E2026"]


def test_https_origin_declaration_covers_its_paths(monkeypatch):
    source = '''
uses network "https://example.com"

fn main() {
    print(Net.get("https://example.com/data"))
}
'''

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            assert limit == 1_048_577
            return b"hello from the network"

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://example.com/data"
            assert timeout == 5
            return Response()

    import nexora.host

    monkeypatch.setattr(nexora.host, "build_opener", lambda *handlers: Opener())
    host = LocalHost(
        grants=Grants(network=("https://example.com",)),
        declarations=Capabilities(network=("https://example.com",)),
        network_allowed=True,
    )
    assert run_with_host(source, host) == "hello from the network\n"


def test_https_requires_both_a_matching_grant_and_an_allowed_environment(monkeypatch):
    source = '''
uses network "https://example.com"

fn main() {
    print(Net.get("https://example.com/data"))
}
'''
    host = LocalHost(
        declarations=Capabilities(network=("https://example.com",)),
        network_allowed=True,
    )
    _, error = run_failure_with_host(source, host)
    assert error.code == "E3008"
    assert "not among the network origins" in error.label

    host = LocalHost(
        grants=Grants(network=("https://example.com",)),
        declarations=Capabilities(network=("https://example.com",)),
    )
    _, error = run_failure_with_host(source, host)
    assert error.code == "E3008"
    assert "environment does not allow network" in error.label


def test_network_capability_only_allows_the_declared_origin():
    source = '''
uses network "https://example.com"

fn main() {
    print(Net.get("https://other.example/data"))
}
'''
    assert check_codes(source) == ["E2026"]


def test_https_rejects_non_https_urls_before_opening_a_connection(monkeypatch):
    source = '''
uses network "https://example.com"

fn main() {
    let url = "http://example.com/data"
    print(Net.get(url))
}
'''

    def unexpected(*args, **kwargs):
        pytest.fail("an HTTP URL must not reach the network client")

    import nexora.host

    monkeypatch.setattr(nexora.host, "build_opener", unexpected)
    host = LocalHost(
        grants=Grants(network=("https://example.com",)),
        declarations=Capabilities(network=("https://example.com",)),
        network_allowed=True,
    )
    _, error = run_failure_with_host(source, host)
    assert error.code == "E3014"


def test_process_requires_a_static_declaration():
    source = '''
fn main() {
    print(Process.run("python", ["--version"]))
}
'''
    assert check_codes(source) == ["E2026"]


def test_process_runs_only_when_declared_granted_and_allowed():
    command = sys.executable.replace("\\", "\\\\")
    source = f'''
uses process "{command}"

fn main() {{
    print(Process.run("{command}", ["-c", "import sys; sys.stdout.write('process output')"]))
}}
'''
    host = LocalHost(
        grants=Grants(process=(sys.executable,)),
        declarations=Capabilities(process=(sys.executable,)),
        processes_allowed=True,
    )
    assert run_with_host(source, host) == "process output\n"


def test_process_fails_without_grant_or_environment_permission():
    command = sys.executable.replace("\\", "\\\\")
    source = f'''
uses process "{command}"

fn main() {{
    print(Process.run("{command}", ["-c", "print('no')"]))
}}
'''
    host = LocalHost(declarations=Capabilities(process=(sys.executable,)), processes_allowed=True)
    _, error = run_failure_with_host(source, host)
    assert error.code == "E3008"
    assert "not among the commands the user allowed" in error.label

    host = LocalHost(
        grants=Grants(process=(sys.executable,)),
        declarations=Capabilities(process=(sys.executable,)),
    )
    _, error = run_failure_with_host(source, host)
    assert error.code == "E3008"
    assert "environment does not allow external processes" in error.label


def test_process_timeout_is_bounded(monkeypatch):
    command = sys.executable.replace("\\", "\\\\")
    source = f'''
uses process "{command}"

fn main() {{
    print(Process.run("{command}", ["-c", "import time; time.sleep(1)"]))
}}
'''
    import nexora.host

    monkeypatch.setattr(nexora.host, "_PROCESS_TIMEOUT_SECONDS", 0.05)
    host = LocalHost(
        grants=Grants(process=(sys.executable,)),
        declarations=Capabilities(process=(sys.executable,)),
        processes_allowed=True,
    )
    _, error = run_failure_with_host(source, host)
    assert error.code == "E3014"
    assert "exceeded 0.05 seconds" in error.label


def test_process_output_is_bounded():
    command = sys.executable.replace("\\", "\\\\")
    source = f'''
uses process "{command}"

fn main() {{
    print(Process.run("{command}", ["-c", "print('x' * 1100000)"]))
}}
'''
    host = LocalHost(
        grants=Grants(process=(sys.executable,)),
        declarations=Capabilities(process=(sys.executable,)),
        processes_allowed=True,
    )
    _, error = run_failure_with_host(source, host)
    assert error.code == "E3014"
    assert "exceeds 1048576 bytes" in error.label


def test_api_without_a_host_denies_network_and_process_access():
    network = '''
uses network "https://example.com"

fn main() {
    print(Net.get("https://example.com"))
}
'''
    process = '''
uses process "python"

fn main() {
    print(Process.run("python", ["--version"]))
}
'''
    for source in (network, process):
        result = api.run_source(source)
        assert result["status"] == "runtime_error"
        assert result["diagnostics"][0]["code"] == "E3008"


def test_playground_worker_denies_network_and_process_access():
    requests = (
        {
            "action": "run",
            "code": '''uses network "https://example.com"\n\nfn main() {\n    print(Net.get("https://example.com"))\n}''',
            "filename": "playground.nex",
            "limits": {},
        },
        {
            "action": "run",
            "code": '''uses process "python"\n\nfn main() {\n    print(Process.run("python", ["--version"]))\n}''',
            "filename": "playground.nex",
            "limits": {},
        },
    )
    for request in requests:
        result = handle(request)
        assert result["status"] == "runtime_error"
        assert result["diagnostics"][0]["code"] == "E3008"


def test_cli_process_permission_runs_a_declared_command(tmp_path, capsys):
    command = sys.executable.replace("\\", "\\\\")
    source = f'''
uses process "{command}"

fn main() {{
    print(Process.run("{command}", ["-c", "import sys; sys.stdout.write('from CLI')"]))
}}
'''
    path = tmp_path / "process.nex"
    path.write_text(source, encoding="utf-8")
    assert main(["run", str(path), "--allow-process", sys.executable]) == 0
    assert capsys.readouterr().out == "from CLI\n"
