"""Compares `nex debug` of the native executable with the Python one, with scripted debugger commands.

    NEXORA_NEX=selfhost/build/nex_cli.exe PYTHONPATH=nexora/src python selfhost/compare_debug_cli.py FILE.nex [FILE.nex ...]

Python reads the commands from a file given to `nexora.cli._debug`, and the executable from the file named by NEXORA_DEBUG_CONSOLE
(the same file). The standard output, the standard error and the status must be equal for every script.
"""

import os
import subprocess
import sys
import tempfile

ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

SCRIPTS = [
    ("", []),
    ("q\n", []),
    ("\n\n\n\nq\n", []),
    ("s\ns\ns\ns\ns\ns\ns\ns\nq\n", []),
    ("c\n", []),
    ("help\nfoo\nbreakpoints\nb 1\nb 99999\nb nofile:1\nd 1\nd zzz\nbreak\nc\n", []),
    ("b 3\nc\nc\nc\nq\n", []),
    ("s\nb 2\nb 4\nbreakpoints\nc\nd 2\nc\nc\n", []),
    ("c\n", ["--breakpoint", "2"]),
    ("c\nc\nc\n", ["--breakpoint", "3", "--breakpoint", "5"]),
    ("s\ns\ns\n", ["--max-steps", "3"]),
    ("c\n", ["--max-steps", "2"]),
    ("c\n", ["--breakpoint", "9999"]),
    ("c\n", ["--max-steps", "0"]),
]

PYTHON_SIDE = (
    "import sys\n"
    "from nexora import cli\n"
    "path, console, options = sys.argv[1], sys.argv[2], sys.argv[3:]\n"
    "stops = [int(options[i + 1]) for i, o in enumerate(options) if o == '--breakpoint']\n"
    "steps = [int(options[i + 1]) for i, o in enumerate(options) if o == '--max-steps']\n"
    "kwargs = {'breakpoints': tuple(stops)}\n"
    "if steps: kwargs['max_steps'] = steps[-1]\n"
    "with open(console, encoding='utf-8') as commands:\n"
    "    sys.exit(cli._debug(path, 'text', console=commands, **kwargs))\n"
)


def run(command, env, stdin):
    done = subprocess.run(command, capture_output=True, env=env, input=stdin)
    clean = lambda data: data.replace(b"\r\n", b"\n")
    return clean(done.stdout), clean(done.stderr), done.returncode


def main(files):
    native = os.environ.get("NEXORA_NEX")
    if not native:
        sys.exit("set NEXORA_NEX to the native executable")
    different = 0
    total = 0
    with tempfile.TemporaryDirectory() as folder:
        console = os.path.join(folder, "console.txt")
        for path in files:
            for commands, options in SCRIPTS:
                total += 1
                with open(console, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(commands)
                stdin = b"Ada\nGrace\n"
                expected = run([sys.executable, "-c", PYTHON_SIDE, path, console, *options], ENV, stdin)
                found = run([native, "debug", *options, path], dict(ENV, NEXORA_DEBUG_CONSOLE=console), stdin)
                if expected != found:
                    different += 1
                    print(f"DIFFERENT {path} {options} {commands!r}: status {expected[2]} / {found[2]}")
    print(f"{len(files)} files, {total} runs, {different} different")
    sys.exit(1 if different else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
