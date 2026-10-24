# MCP server

NEXORA includes an **optional** [Model Context Protocol](https://modelcontextprotocol.io)
(MCP) server. It lets a compatible AI assistant use the analysis of NEXORA as tools:
checking code, getting its structure, its symbols and a summary, and looking up the specification.

The assistant decides what code to write. **Whether that code is valid is decided by NEXORA**,
deterministically, with the same checker that `nex check` uses.

## Status

| | |
|-|-|
| Implemented | Yes: `src/nexora/mcp_server.py` |
| Tested | Yes, with the real protocol: `tests/test_mcp.py` starts the server as a process and talks to it through the client of the official SDK |
| SDK | [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), version 2 (tested with 2.3.0) |
| Transport | Standard input and output (*stdio*): the assistant starts the server as a local process |
| Tested with a real assistant | **Only with Claude Code**, in a manual session ([detail](#check-in-claude-code)). It is not an automated test. In no other assistant |
| Does it run code? | **No.** No tool runs the program it receives |

The SDK changed its interface between its versions 1 and 2. This server is written for **2**
(`mcp.server.MCPServer`) and does not work with 1.

## Installation

The SDK is not a dependency of NEXORA. It is installed separately, in the same environment:

```bash
python -m pip install -e ".[mcp]"
```

It installs the `mcp` package (version 2) and its dependencies. NEXORA works the same without it: only
the `mcp_server.py` file imports it.

Check:

```bash
nex-mcp
```

The server waits for messages on the standard input; it writes nothing. Close it with Ctrl+C.
`python -m nexora.mcp_server` is equivalent. If the SDK is not installed, the command says so and
ends.

## Tools

All of them receive the **code as text**. None receives a path, opens a file given by the
caller, or runs anything.

| Tool | Arguments | Returns |
|------|-----------|---------|
| `nexora_check` | `source`, `filename`* | `nexora.diagnostics/1` document: `ok` and the diagnostics |
| `nexora_get_diagnostics` | `source`, `filename`* | Only `ok`, `count` and the list of diagnostics |
| `nexora_inspect` | `source`, `filename`* | `nexora.inspect/3` document: the syntax tree with types |
| `nexora_get_context` | `source`, `filename`* | `nexora.context/2` document: [technical summary](ai-context.md) |
| `nexora_get_symbols` | `source`, `filename`*, `name`*, `function`* | `nexora.symbols/2` document: symbols and references |
| `nexora_get_language_spec` | `section`* | `nexora.spec/2` document: the index of the specification or the text of a section |
| `nexora_get_capabilities` | — | `nexora.capabilities/1` document: keywords, types, built-in functions, error codes and limits |

\* optional.

- `source`: the NEXORA code. At most 256 KiB.
- `filename`: a label for the results (by default `source.nex`). It has to be a simple name
  ending in `.nex`; a path is rejected.
- `section`: an id taken from the list that the tool itself returns, for example
  `7-functions`. It is not a path: it is looked up in the list of headings of the specification.

The formats are in [JSON protocol](json-protocol.md). Every tool returns the document
as structured content and, in addition, as JSON text.

All the tools are declared read-only (`readOnlyHint`), non-destructive and idempotent,
and without access to the outside world (`openWorldHint: false`).

### A program with errors is not an error of the tool

If the code has errors, `nexora_check` **succeeds** and returns `ok: false` with the
diagnostics. A call only fails (`isError`) when the arguments are not valid:

| Situation | Result |
|-----------|--------|
| `source` is missing or is not a text | Error: the validation message of the SDK |
| `filename` is a path | Error: "'filename' is only a label for the results: a simple name ending in .nex, not a path." |
| `source` exceeds 256 KiB | Error: "'source' is larger than the limit of 262144 bytes." |
| `name` or `function` are not identifiers | Error: "… must be a NEXORA identifier." |
| `section` looks like a path or a file name | Error: "'section' must be a section id from the list this tool returns." |
| `section` does not exist | Error: "The specification has no section with the id '…'." |

The errors include no tracebacks or internal paths, and a rejected call does not interrupt the session.

## Configuration

Every assistant is configured in its own way. **There is no universal configuration**: check the
documentation of yours. In every case the command that starts the server has to be given, and that
command has to be that of the virtual environment where NEXORA is installed, with its full path.

| System | Command |
|--------|---------|
| Windows | `C:\path\to\nexora\.venv\Scripts\nex-mcp.exe` |
| Linux and macOS | `/path/to/nexora/.venv/bin/nex-mcp` |

### Example: Claude Code

With its command line:

```bash
claude mcp add nexora -- /path/to/nexora/.venv/bin/nex-mcp
```

Or with a `.mcp.json` file at the root of the project:

```json
{
  "mcpServers": {
    "nexora": {
      "command": "/path/to/nexora/.venv/bin/nex-mcp",
      "args": []
    }
  }
}
```

### Example: Claude Desktop

In its `claude_desktop_config.json` file, the same `mcpServers` block as in the previous example.

The `mcpServers` block has been checked with Claude Code (see below). **In Claude Desktop it has not
been tested**: the example follows the format that client documents. If your version uses another format,
its documentation prevails.

### Check in Claude Code

Done by hand on 14 October 2026, on Windows 11, with Claude Code 2.1.296 in non-interactive
mode, the `mcpServers` block above (with the path of `nex-mcp.exe`) and only three tools
allowed:

```bash
claude -p "…" --mcp-config mcp.json --strict-mcp-config \
  --allowedTools "mcp__nexora__nexora_get_capabilities,mcp__nexora__nexora_check,mcp__nexora__nexora_get_context"
```

What was observed in the log of the session:

| Step | Result |
|------|--------|
| Connection | The server appeared as `connected` and the assistant discovered the seven tools |
| `nexora_get_capabilities` | It returned the `nexora.capabilities/1` document |
| `nexora_check` with a program that passes a `Text` where an `Int` is expected | `ok: false`, diagnostic `E2011` |
| `nexora_check` with the program fixed by the assistant | `ok: true` |
| `nexora_get_context` | It returned the `nexora.context/1` document |

What it shows: that the server negotiates the protocol with a real client other than the SDK and that the
[intended cycle](#the-intended-cycle) can be gone through. What it does **not** show: it is a single session,
with a seven-line program; `nexora_inspect`, `nexora_get_symbols`, `nexora_get_diagnostics` and
`nexora_get_language_spec` were not called from the assistant; and it says nothing about the quality of the
code a model writes. It is not part of the test suite, because it would require calling a
model.

### Trying it without an assistant

With the client of the SDK itself, in Python:

```python
import asyncio, sys
from mcp import Client, StdioServerParameters

async def main():
    server = StdioServerParameters(command=sys.executable, args=["-m", "nexora.mcp_server"])
    async with Client(server) as client:
        tools = await client.list_tools()
        print([tool.name for tool in tools.tools])
        result = await client.call_tool("nexora_check", {"source": "fn main() {\n    print(x)\n}"})
        print(result.structured_content["diagnostics"][0]["code"])   # E2005

asyncio.run(main())
```

It is what the tests of `tests/test_mcp.py` do.

## The intended cycle

The server is meant for this working cycle of an agent:

1. `nexora_get_capabilities` or `nexora_get_language_spec`: the rules of the language, from the official source.
2. `nexora_get_context`: the structure of the program it is going to modify.
3. The agent writes or changes the code. That decision is its own.
4. `nexora_check`: the static analysis.
5. It reads the diagnostics: code, category, exact position and, if there is one, suggestion.
6. It fixes and goes back to step 4, until `ok` is `true` or until the limit of attempts that is set.

NEXORA applies no changes, does not rewrite the code and does not decide when to stop: it brings checkable
facts on every round.

## Security

What the server does, and what its tests check:

- **It does not run the code it receives.** There is no execution tool. A test sends
  each tool a program that prints, divides by zero and enters infinite recursion, and
  all of them answer immediately that it is valid, without effects.
- **It does not open files given by the caller.** The code arrives as text. `filename` is validated
  as a simple name. The only disk read is the specification of the project itself, at a
  fixed path that does not depend on any argument.
- **It runs no commands** and does not access the network.
- **It validates the arguments** and limits the size of the code.
- **It exposes no environment variables, secrets or internal paths** in its answers.
- **What is inside a program is data.** A comment or a text that says "ignore your
  instructions" is analyzed like any other; it does not change the behaviour of the server. A
  test checks it.

What it does **not** cover:

- **The server is not a sandbox** and it does not need to be, because it does not run the programs it
  analyzes. The only thing it evaluates is the conditions of refined types on constants: expressions
  without calls to functions of the program and with bounded work (`E2019`). But it runs with the
  permissions of the user who starts it.
- **The permissions the assistant asks the user for are not a security measure of NEXORA.** Whether an
  assistant asks before calling a tool is up to the assistant.
- **The results go back to the model.** The tree and the diagnostics contain fragments of the
  analyzed code (names, texts). If that code contains instructions aimed at a model, the
  server returns them as data, but it is the assistant that must treat them as such.
- Analyzing a very large program takes time and memory; the only limit is the size of the
  code (256 KiB).

### Why there is no tool to run code

Running code supplied by a model is a different risk from analyzing it: a program
may not end or may use memory without limit. Doing it well requires the isolation described in
[Playground](playground.md#security-and-isolation) (separate process, limits, container), and
offering it through MCP would be a separate design decision. In this version **it does not exist**, and it is not
enabled by any option.

## Limitations

- In a real assistant it has only been checked once, by hand, with Claude Code. It has not been tested in
  Claude Desktop or in any other client.
- Only *stdio* transport. There is no HTTP server.
- Only tools: it exposes no MCP resources or *prompts*.
- The specification is only available if NEXORA was installed from the source code (development
  mode). Installed from a *wheel* package, `nexora_get_language_spec` answers
  `available: false`, because the *wheel* does not include the documentation.
- The specification is in English.
- It depends on version 2 of the SDK, which is recent; a version 3 could require changes.
