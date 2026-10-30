# Public interfaces and stability

This policy describes the compatibility promise for each interface. It is separate from the
project's pre-1.0 status: the language and programs written in it can still change incompatibly.

| Interface | Status | Compatibility promise |
|-----------|--------|-----------------------|
| `nex` command line | **Stable** | Command names, documented options, exit-code meanings, and machine-readable output contracts listed below are maintained. Additions are allowed. |
| Diagnostics | **Stable** | Diagnostic `code`, `category`, severity, and source positions are machine-readable contracts. English wording (`message`, `label`, `hint`, `notes`) may change. |
| JSON protocols | **Stable per schema version** | A schema identifier such as `nexora.inspect/3` keeps its meaning. Breaking changes require a new version number. Additive changes are validated against the published schema and compatibility tests. |
| Language Server Protocol (LSP) | **Experimental** | Methods, capabilities, and editor behavior may change before 1.0. |
| Model Context Protocol (MCP) | **Experimental** | Tool names, arguments, and behavior may change before 1.0. |
| Python API (`nexora.tooling`) | **Experimental** | Public names and behavior may change before 1.0. |
| Other Python modules (`lexer`, `parser`, `checker`, and implementation modules) | **Internal** | No compatibility promise; consumers should use the CLI or explicitly listed APIs. |

## Stable CLI contract

The stable command names are `run`, `debug`, `check`, `inspect`, `context`, `symbols`, `test`, and
`migrate`. The stable exit codes are:

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Static errors in the program |
| `2` | Invalid command-line use |
| `3` | Program failed while running |
| `4` | Input file could not be read |
| `5` | A contract or refined-type condition failed while running |
| `6` | An example failed, or `nex test` found no examples |
| `70` | Internal NEXORA error |
| `130` | Interrupted with Ctrl+C |

The CLI reference documents command-specific options and output. For text intended for people, exact
wording and formatting are not covered by the compatibility promise. JSON output follows the
versioned schemas below.

## Stable JSON schemas

The currently supported identifiers are `nexora.diagnostics/1`, `nexora.inspect/3`,
`nexora.symbols/2`, `nexora.context/2`, `nexora.spec/2`, `nexora.capabilities/1`,
`nexora.evidence/1`, `nexora.result/1`, and `nexora.test/1`. Each identifier is an independent
contract. A consumer should select behavior by the `schema` field, and a producer must introduce a
new schema version when changing an existing field's meaning or removing/renaming a field.

## Compatibility checks

`tests/test_interface_stability.py` pins the stable CLI command names, exit codes, and schema
identifiers. The CLI, diagnostics, and JSON suites exercise those contracts in real invocations;
the JSON tests also validate produced documents against the checked-in JSON Schemas. LSP and MCP
have protocol tests, but remain experimental until their external compatibility expectations are
defined and tested.
