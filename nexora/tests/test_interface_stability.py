"""Compatibility guards for interfaces declared stable in the public policy."""

from pathlib import Path

from nexora import cli
from nexora.schemas import all_schemas

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs" / "interface-stability.md"


def test_stability_policy_classifies_every_public_interface():
    text = POLICY.read_text(encoding="utf-8")
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in text.splitlines()
        if line.strip().startswith("|")
    ]
    for interface, status in (
        ("`nex` command line", "Stable"),
        ("Diagnostics", "Stable"),
        ("JSON protocols", "Stable per schema version"),
        ("Language Server Protocol (LSP)", "Experimental"),
        ("Model Context Protocol (MCP)", "Experimental"),
        ("Python API (`nexora.tooling`)", "Experimental"),
        ("Other Python modules", "Internal"),
    ):
        assert any(
            len(row) >= 2 and row[0].startswith(interface) and row[1].startswith(f"**{status}**")
            for row in rows
        )


def test_stable_cli_command_names_remain_available():
    parser = cli._build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")
    assert set(subparsers.choices) == {
        "run", "debug", "check", "inspect", "context", "symbols", "test", "migrate",
    }


def test_stable_cli_exit_code_meanings_remain_pinned():
    assert {
        cli.EXIT_OK: "Success",
        cli.EXIT_INVALID_PROGRAM: "Static errors in the program",
        cli.EXIT_USAGE: "Invalid command-line use",
        cli.EXIT_RUNTIME_ERROR: "Program failed while running",
        cli.EXIT_UNREADABLE_FILE: "Input file could not be read",
        cli.EXIT_CONTRACT_VIOLATION: "A contract or refined-type condition failed while running",
        cli.EXIT_TEST_FAILED: "An example failed, or `nex test` found no examples",
        cli.EXIT_INTERNAL_ERROR: "Internal NEXORA error",
        cli.EXIT_INTERRUPTED: "Interrupted with Ctrl+C",
    } == {
        0: "Success",
        1: "Static errors in the program",
        2: "Invalid command-line use",
        3: "Program failed while running",
        4: "Input file could not be read",
        5: "A contract or refined-type condition failed while running",
        6: "An example failed, or `nex test` found no examples",
        70: "Internal NEXORA error",
        130: "Interrupted with Ctrl+C",
    }


def test_stable_json_schema_identifiers_remain_pinned():
    documented = POLICY.read_text(encoding="utf-8")
    for schema in all_schemas().values():
        versioned_id = schema["properties"]["schema"]["const"]
        assert f"`{versioned_id}`" in documented
