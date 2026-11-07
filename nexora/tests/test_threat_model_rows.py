"""The rows of docs/threat-model.md, run through the real command of each implementation.

Every scenario is run with the Python `nex` and, when NEXORA_NEX names the native `nex` (decision 0027), with that one too, and
both have to give the same exit status and the same diagnostic code. Without NEXORA_NEX only the Python implementation runs.

    NEXORA_NEX=path/to/nex python -m pytest tests/test_threat_model_rows.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = os.environ.get("NEXORA_NEX")
COMMAND = Path(sys.executable).name

IMPLEMENTATIONS = [pytest.param("python", id="python")]
if NATIVE:
    IMPLEMENTATIONS.append(pytest.param("native", id="native"))


@pytest.fixture(params=IMPLEMENTATIONS)
def nex(request, tmp_path):
    """Runs `nex <arguments>` with the working directory at tmp_path and returns (status, stdout, stderr)."""

    def run(*arguments: str, env: dict | None = None) -> tuple[int, str, str]:
        if request.param == "python":
            command = [sys.executable, "-m", "nexora", *arguments]
            environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1"}
        else:
            command = [NATIVE, *arguments]
            environment = dict(os.environ)
        environment.update(env or {})
        done = subprocess.run(command, capture_output=True, cwd=tmp_path, env=environment, timeout=120)
        text = [stream.decode("utf-8", "replace").replace("\r", "") for stream in (done.stdout, done.stderr)]
        return done.returncode, text[0], text[1]

    return run


def code(stderr: str) -> str:
    """The first diagnostic code of an error report, or the empty text."""
    for line in stderr.splitlines():
        if "[E" in line:
            return line.split("[")[1].split("]")[0]
    return ""


def put(folder: Path, name: str, text: str) -> str:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return name


READ = 'uses read "data"\n\nfn main() {\n    print(read_file("data/in.txt"))\n}\n'


@pytest.fixture
def data(tmp_path):
    put(tmp_path, "data/in.txt", "inside\n")
    put(tmp_path, "secret.txt", "outside\n")
    put(tmp_path, "data2/in.txt", "neighbour\n")
    return tmp_path


# T1: declaration, grant and host, all three

def test_t1_a_file_is_read_when_it_is_declared_and_granted(data, nex):
    put(data, "p.nex", READ)
    assert nex("run", "--allow-read", "data", "p.nex")[:2] == (0, "inside\n\n")


def test_t1_declaring_is_not_granting(data, nex):
    put(data, "p.nex", READ)
    status, out, err = nex("run", "p.nex")
    assert (status, out, code(err)) == (3, "", "E3008")


def test_t1_granting_is_not_declaring(data, nex):
    put(data, "p.nex", 'fn main() {\n    print(read_file("data/in.txt"))\n}\n')
    status, out, err = nex("run", "--allow-read", "data", "p.nex")
    assert (status, out, code(err)) == (1, "", "E2026")


def test_t1_reading_is_not_writing(data, nex):
    put(data, "p.nex", 'uses read "data"\n\nfn main() {\n    write_file("data/out.txt", "x")\n}\n')
    status, out, err = nex("run", "--allow-read", "data", "--allow-write", "data", "p.nex")
    assert (status, code(err), (data / "data" / "out.txt").exists()) == (1, "E2026", False)


def test_t1_writing_is_not_reading(data, nex):
    put(data, "p.nex", 'uses write "data"\n\nfn main() {\n    print(read_file("data/in.txt"))\n}\n')
    status, out, err = nex("run", "--allow-read", "data", "--allow-write", "data", "p.nex")
    assert (status, code(err)) == (1, "E2026")


# T2: leaving the granted folder

def escaping(path: str) -> str:
    return f'uses read "data"\n\nfn main() {{\n    let path = "{path}" + ""\n    print(read_file(path))\n}}\n'


@pytest.mark.parametrize(
    "path",
    ["data/../secret.txt", "data2/in.txt", "data/sub/../../secret.txt", "./data/../data2/in.txt"],
    ids=["dot-dot", "similar-prefix", "dot-dot-twice", "dot-dot-sideways"],
)
def test_t2_a_path_that_leaves_the_scope_is_denied(path, data, nex):
    put(data, "p.nex", escaping(path))
    status, out, err = nex("run", "--allow-read", "data", "p.nex")
    assert (status, out, code(err)) == (3, "", "E3008")


def test_t2_an_absolute_path_outside_the_scope_is_denied(data, nex):
    outside = (data / "secret.txt").as_posix()
    put(data, "p.nex", escaping(outside))
    status, out, err = nex("run", "--allow-read", "data", "p.nex")
    assert (status, out, code(err)) == (3, "", "E3008")


def test_t2_a_dot_dot_that_stays_inside_the_scope_is_allowed(data, nex):
    put(data, "data/sub/.keep", "")
    put(data, "p.nex", escaping("data/sub/../in.txt"))
    assert nex("run", "--allow-read", "data", "p.nex")[:2] == (0, "inside\n\n")


def test_t2_a_symbolic_link_that_leaves_the_scope_is_denied(data, nex):
    try:
        (data / "data" / "link.txt").symlink_to(data / "secret.txt")
    except (OSError, NotImplementedError):
        pytest.skip("this system does not let the test create symbolic links")
    put(data, "p.nex", escaping("data/link.txt"))
    status, out, err = nex("run", "--allow-read", "data", "p.nex")
    assert (status, out, code(err)) == (3, "", "E3008")


def link(source: Path, target: Path, directory: bool = False) -> None:
    """Makes `source` lead to `target`: a symbolic link, or a junction on Windows when links are not allowed."""
    try:
        source.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError):
        if os.name != "nt" or not directory:
            pytest.skip("this system does not let the test create symbolic links")
        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(source), str(target)], capture_output=True)
        if done.returncode != 0:
            pytest.skip("this system does not let the test create links or junctions")


def test_t2_a_directory_link_that_leaves_the_scope_is_denied(data, nex):
    link(data / "data" / "up", data, directory=True)
    put(data, "p.nex", escaping("data/up/secret.txt"))
    status, out, err = nex("run", "--allow-read", "data", "p.nex")
    assert (status, out, code(err)) == (3, "", "E3008")


def test_t2_a_dot_dot_after_a_link_is_read_where_the_link_leads(data, nex):
    # `data/up/..` is the parent of where `up` leads, not `data`: the text of the path says it stays inside, the file system does not.
    if os.name == "nt":
        pytest.skip("Win32 removes `..` from the text of a path before it reaches the file system, so the file access agrees with the text")
    link(data / "data" / "up", data / "data2", directory=True)
    put(data, "p.nex", escaping("data/up/../secret.txt"))
    status, out, err = nex("run", "--allow-read", "data", "p.nex")
    assert (status, out, code(err)) == (3, "", "E3008")


def test_t2_a_link_that_leads_nowhere_cannot_be_written_through(data, nex, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    link(data / "data" / "dangling.txt", elsewhere / "created.txt")
    put(data, "p.nex", 'uses write "data"\n\nfn main() {\n    let path = "data/dangling.txt" + ""\n    write_file(path, "x")\n}\n')
    status, out, err = nex("run", "--allow-write", "data", "p.nex")
    assert (elsewhere / "created.txt").exists() is False
    assert status == 3 and code(err) in {"E3008", "E3010"}


def test_t2_a_loop_of_links_is_denied_or_fails_without_reading(data, nex):
    link(data / "data" / "loop", Path("loop"))
    put(data, "p.nex", escaping("data/loop"))
    status, out, err = nex("run", "--allow-read", "data", "p.nex")
    assert (status, out) == (3, "") and code(err) in {"E3008", "E3010"}


# T3: the network, without reaching anything (the hosts end in .invalid and never resolve)

NETWORK = 'uses network "https://nexora.invalid"\n\nfn main() {{\n    let url = "{url}" + ""\n    print(Net.get(url))\n}}\n'


def test_t3_an_origin_that_was_not_granted_is_denied(data, nex):
    put(data, "p.nex", NETWORK.format(url="https://nexora.invalid/x"))
    status, out, err = nex("run", "p.nex")
    assert (status, out, code(err)) == (3, "", "E3008")


def test_t3_an_origin_that_was_not_declared_is_denied(data, nex):
    put(data, "p.nex", NETWORK.format(url="https://other.invalid/x"))
    status, out, err = nex("run", "--allow-network", "https://nexora.invalid", "--allow-network", "https://other.invalid", "p.nex")
    assert (status, out, code(err)) == (3, "", "E3008")


def test_t3_plain_http_never_reaches_the_network(data, nex):
    put(data, "p.nex", NETWORK.format(url="http://nexora.invalid/x"))
    status, out, err = nex("run", "--allow-network", "https://nexora.invalid", "p.nex")
    assert (status, out) == (3, "") and code(err) in {"E3008", "E3014"}
    assert "HTTPS request failed: <urlopen error" not in err or "http" in err.lower()


# T5, T6: processes

def process(command: str, arguments: str = '["-c", "print(1)"]') -> str:
    return f'uses process "{COMMAND}"\n\nfn main() {{\n    print(Process.run("{command}", {arguments}))\n}}\n'


def test_t5_a_declared_and_granted_process_runs(data, nex):
    put(data, "p.nex", process(COMMAND))
    assert nex("run", "--allow-process", COMMAND, "p.nex")[:2] == (0, "1\n\n")


def test_t5_a_process_that_was_not_granted_is_denied(data, nex):
    put(data, "p.nex", process(COMMAND))
    status, out, err = nex("run", "p.nex")
    assert (status, out, code(err)) == (3, "", "E3008")


def test_t5_a_process_that_was_not_declared_is_denied(data, nex):
    put(data, "p.nex", 'fn main() {\n    print(Process.run("' + COMMAND + '", ["-c", "print(1)"]))\n}\n')
    status, out, err = nex("run", "--allow-process", COMMAND, "p.nex")
    assert (status, out, code(err)) == (1, "", "E2026")


def test_t5_there_is_no_shell(data, nex):
    put(data, "p.nex", process(COMMAND, '["-c", "print(1)", ";", "echo", "injected"]'))
    status, out, _ = nex("run", "--allow-process", COMMAND, "p.nex")
    assert "injected" not in out


def test_t6_the_output_of_a_process_is_bounded(data, nex):
    put(data, "p.nex", process(COMMAND, '["-c", "print(\'x\' * 2000000)"]'))
    status, out, err = nex("run", "--allow-process", COMMAND, "p.nex")
    assert (status, out, code(err)) == (3, "", "E3014")


def test_t6_a_process_that_does_not_end_is_stopped(data, nex):
    put(data, "p.nex", process(COMMAND, '["-c", "import time; time.sleep(30)"]'))
    status, out, err = nex("run", "--allow-process", COMMAND, "p.nex")
    assert (status, out, code(err)) == (3, "", "E3014")


def test_t6_a_child_process_does_not_receive_the_environment_of_the_user(data, nex):
    put(data, "p.nex", process(COMMAND, '["-c", "import os; print(os.environ.get(\'NEXORA_THREAT_MODEL_SECRET\', \'absent\'))"]'))
    status, out, _ = nex("run", "--allow-process", COMMAND, "p.nex", env={"NEXORA_THREAT_MODEL_SECRET": "leaked"})
    assert (status, out) == (0, "absent\n\n")


# T8, T9: arguments are not code, and analysis does not run

@pytest.mark.parametrize("argument", ["print(1)", "fn main() { print(1) }", "__import__('os').system('echo hi')"])
def test_t8_an_argument_is_never_treated_as_source_code(argument, nex):
    status, out, err = nex("run", argument)
    assert (status, out, code(err)) == (4, "", "E0001")


def test_t9_checking_does_not_run_the_program(data, nex):
    put(data, "p.nex", 'fn main() {\n    print("must not appear")\n    print(1 / 0)\n}\n')
    assert nex("check", "p.nex")[:2] == (0, "✓ Check passed: p.nex\n")


def test_t9_inspecting_does_not_run_the_program(data, nex):
    put(data, "p.nex", 'fn main() {\n    print("must not appear")\n    print(1 / 0)\n}\n')
    status, out, err = nex("inspect", "p.nex")
    assert (status, err, out.lstrip()[:1]) == (0, "", "{")


# Modules do not inherit capabilities

def test_modules_a_module_must_declare_what_it_reads_even_if_the_program_does(data, nex):
    put(data, "mod.nex", 'pub fn load() gives Text {\n    return read_file("data/in.txt")\n}\n')
    put(data, "p.nex", 'import "mod.nex"\nuses read "data"\n\nfn main() {\n    print(mod.load())\n}\n')
    status, out, err = nex("run", "--allow-read", "data", "p.nex")
    assert (status, out, code(err)) == (1, "", "E2026")


def test_modules_a_module_that_declares_what_it_reads_works_when_it_is_granted(data, nex):
    put(data, "mod.nex", 'uses read "data"\n\npub fn load() gives Text {\n    return read_file("data/in.txt")\n}\n')
    put(data, "p.nex", 'import "mod.nex"\nuses read "data"\n\nfn main() {\n    print(mod.load())\n}\n')
    assert nex("run", "--allow-read", "data", "p.nex")[:2] == (0, "inside\n\n")
