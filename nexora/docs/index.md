# NEXORA documentation

NEXORA is a new programming language, at an early stage of development. This documentation
describes what the current version really does: every example program and every output shown on
these pages is run by the automated tests and compared against the real output of the interpreter.

## Where to start

| If you want to… | Read |
|-----------------|------|
| Install NEXORA | [Installation](installation.md) |
| Write and run your first program | [Getting started](getting-started.md) |
| Read complete programs | [`examples/`](../examples/README.md) |
| Know what it **cannot** do yet | [Limitations](limitations.md) |

## Language guides

| Guide | Contents |
|-------|----------|
| [Types](types.md) | Types, `List[T]` lists, inference, annotations, operators, conversions, refined types (`where`) and records |
| [Functions](functions.md) | Parameters, `return`, return paths, `if` / `else`, recursion |
| [Contracts](contracts.md) | `needs`, `promises` and `trust`, with the explanation of each rule |

## Reference

| Document | Contents |
|----------|----------|
| [Language specification](language-spec.md) | The normative reference for language version 0.13: lexical grammar, EBNF grammar, types, scopes, semantics, permissions, Unicode and errors; executable examples |
| [CLI reference](cli-reference.md) | Commands, options, output formats and exit codes of `nex` |
| [Diagnostics](diagnostics.md) | How to read an error, categories and every code |
| [Automated tools and AI](ai-tooling.md) | What NEXORA offers a tool or an agent, the Python API and what does not exist |
| [Structured context](ai-context.md) | `nex context` and `nex symbols`: a summary and the symbols of a program, without running it |
| [JSON protocol](json-protocol.md) | Every JSON format, its versions, its rules and its JSON Schemas |
| [MCP server](mcp.md) | Optional server for compatible AI assistants: installation, tools and security |
| [LSP](lsp.md) | VS Code, Neovim, Helix and Emacs integration through `nexora-lsp` |
| [`nex inspect` schema](inspect-schema.md) | Every node and field of the syntax tree in JSON |
| [Playground](playground.md) | Run NEXORA from the browser: architecture, API, limits, isolation and deployment |

## Project

| Document | Contents |
|----------|----------|
| [Architecture](architecture.md) | The stages of the interpreter, the modules and where to add features |
| [Testing](testing.md) | What is tested, how to run it and coverage |
| [Technical decisions](decisions/README.md) | Why the language is the way it is, and the incompatible changes |
| [Roadmap](roadmap.md) | What is done and verified, and what is pending |
| [Limitations](limitations.md) | What does not exist and the known risks |
| [Changelog](../CHANGELOG.md) | What changed in each version |
| [Contributing](../CONTRIBUTING.md) | Development environment and checks before proposing a change |
| [Security](../SECURITY.md) | The real scope of the protections and how to report a problem |

## Status of each part

| Status | What it means in this documentation |
|--------|-------------------------------------|
| No mark | Implemented and covered by tests |
| **Experimental** | Only a feature explicitly marked Experimental has provisional rules. No feature in the language specification is currently marked Experimental |
| **Planned** | Does not exist. It only appears in [Limitations](limitations.md) and in the [roadmap](roadmap.md) |

The documentation is in English, like the words of the language and the error messages.
