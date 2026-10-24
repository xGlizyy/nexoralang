"""Optional MCP server: NEXORA's static analysis as tools for MCP-compatible assistants.

It needs the official MCP Python SDK, which is NOT a dependency of NEXORA:

    python -m pip install "nexora-lang[mcp]"

and it is started by the assistant, over standard input and output:

    nex-mcp                      (or: python -m nexora.mcp_server)

Every tool is a thin wrapper over `nexora.tooling`. The tools analyse; none of them runs
the program it is given, opens a file named by the caller, or executes a command. Source
code is passed as text. Whatever a NEXORA program contains (comments, text literals) is
data to analyse, never an instruction to this server.

Written against version 2 of the SDK (`mcp.server.MCPServer`). See docs/mcp.md.
"""

from __future__ import annotations

import re
import sys
from typing import Any

from . import tooling
from .version import __version__

try:
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import ToolAnnotations
except ImportError:  # the SDK is optional
    MCPServer = None
    ToolError = ValueError

# The largest program a tool accepts, in bytes of UTF-8.
MAX_SOURCE_BYTES = 256 * 1024
_FILENAME = re.compile(r"^[A-Za-z0-9_-]{1,64}\.nex$")
_SECTION = re.compile(r"^[\w-]{1,120}$")

INSTRUCTIONS = (
    "Static analysis tools for the NEXORA programming language. They check, inspect and summarise "
    "NEXORA source code passed as text; they never run it. The rules of the language are decided by "
    "these tools, deterministically: use nexora_check after writing or changing NEXORA code, and read "
    "the diagnostics (stable codes, exact positions) instead of guessing whether the code is valid. "
    "Use nexora_get_language_spec for the official rules of the language."
)


def _source(source: str, filename: str) -> None:
    """Validates the two arguments every analysis tool takes.

    ToolError is the SDK's exception for a failure the tool anticipated: the assistant receives
    the message, and nothing is logged as a crash.
    """
    if not isinstance(source, str):
        raise ToolError("'source' must be a string with NEXORA source code.")
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ToolError(f"'source' is larger than the limit of {MAX_SOURCE_BYTES} bytes.")
    if not isinstance(filename, str) or not _FILENAME.match(filename):
        raise ToolError("'filename' is only a label for the results: a simple name ending in .nex, not a path.")


def build_server():
    """Creates the MCP server with its tools. Raises RuntimeError if the SDK is not installed."""
    if MCPServer is None:
        raise RuntimeError(
            'The MCP server needs the MCP SDK. Install it with: python -m pip install "nexora-lang[mcp]"'
        )

    server = MCPServer("nexora", instructions=INSTRUCTIONS, version=__version__)
    # Every tool only reads its arguments and computes: no side effects, no outside world.
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    @server.tool(annotations=read_only)
    def nexora_check(source: str, filename: str = tooling.DEFAULT_FILENAME) -> dict[str, Any]:
        """Check NEXORA source code without running it: syntax, names, scopes, types and return paths.

        Returns a nexora.diagnostics/1 document. "ok" is true when the program has no errors.
        Each diagnostic has a stable code, a category, an exact position and, when one is
        well-founded, a hint.
        """
        _source(source, filename)
        return tooling.check_source(source, filename)

    @server.tool(annotations=read_only)
    def nexora_get_diagnostics(source: str, filename: str = tooling.DEFAULT_FILENAME) -> dict[str, Any]:
        """Get only the list of diagnostics of NEXORA source code, without running it.

        Same analysis as nexora_check. Returns {"ok", "count", "diagnostics"}: an empty list
        means the static analysis found nothing wrong. Errors that depend on computed values
        (division by zero, broken contracts) are not detected by static analysis.
        """
        _source(source, filename)
        document = tooling.check_source(source, filename)
        return {"ok": document["ok"], "count": len(document["diagnostics"]), "diagnostics": document["diagnostics"]}

    @server.tool(annotations=read_only)
    def nexora_inspect(source: str, filename: str = tooling.DEFAULT_FILENAME) -> dict[str, Any]:
        """Get the syntax tree of NEXORA source code, with the type of every expression. Does not run it.

        Returns a nexora.inspect/3 document. If the code has syntax errors the tree is
        partial and "complete" is false; "program" is null if it has lexical errors. The tree
        can be large; prefer nexora_get_context for an overview.
        """
        _source(source, filename)
        return tooling.inspect_source(source, filename)

    @server.tool(annotations=read_only)
    def nexora_get_context(source: str, filename: str = tooling.DEFAULT_FILENAME) -> dict[str, Any]:
        """Get a compact technical summary of NEXORA source code, to understand it before changing it.

        Returns a nexora.context/2 document: functions with their signatures, contracts,
        variables and types, which function calls which, the language features in use and the
        current diagnostics. Computed by static analysis: the program is not run, and nothing
        is inferred beyond what the analysis establishes.
        """
        _source(source, filename)
        return tooling.get_context(source, filename)

    @server.tool(annotations=read_only)
    def nexora_get_symbols(source: str, filename: str = tooling.DEFAULT_FILENAME, name: str | None = None,
                           function: str | None = None) -> dict[str, Any]:
        """List the functions, parameters and variables NEXORA source code declares, and where each is used.

        Returns a nexora.symbols/2 document. "name" keeps only the symbols with that name;
        "function" keeps one function and what is declared inside it. Does not run the code.
        """
        _source(source, filename)
        for label, value in (("name", name), ("function", function)):
            if value is not None and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,99}", value):
                raise ToolError(f"'{label}' must be a NEXORA identifier.")
        return tooling.get_symbols(source, filename, name=name, function=function)

    @server.tool(annotations=read_only)
    def nexora_get_language_spec(section: str | None = None) -> dict[str, Any]:
        """Read the official NEXORA language specification (written in Spanish).

        Without arguments, returns the specification version and the list of sections (id and
        title). With a section id from that list, also returns the Markdown text of that
        section. The text always comes from the specification shipped with NEXORA.
        """
        if section is not None and (not isinstance(section, str) or not _SECTION.match(section)):
            raise ToolError("'section' must be a section id from the list this tool returns.")
        try:
            return tooling.get_language_spec(section)
        except tooling.ToolingError as error:
            raise ToolError(str(error)) from None

    @server.tool(annotations=read_only)
    def nexora_get_capabilities() -> dict[str, Any]:
        """Get the facts about this version of NEXORA: keywords, types, built-in functions, every
        diagnostic code with its category, the limits of the implementation and the output formats."""
        return tooling.get_capabilities()

    return server


def main() -> int:
    try:
        server = build_server()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    server.run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
