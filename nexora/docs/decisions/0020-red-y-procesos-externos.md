# 0020 — Network requests and external processes

- **Status:** accepted.
- **Version:** 0.13.0.
- **Date:** 2026-10-27.
- **Related to:** [decision 0015](0015-entrada-argumentos-archivos-y-permisos.md), which defines the
  declaration, user grant and environment permission model. This decision extends that model; it does
  not change file permissions.

## Context

Decision 0015 deliberately left network access and external processes out of scope. The interpreter
has never opened a socket or launched a child process. This decision adds those operations for
programs run with the local CLI, while keeping them unavailable in the web Playground and in the
in-memory API unless a host explicitly implements and enables them.

## Decision

### Declaring and granting access

A program declares a network origin or an executable at the top of its file:

```nexora
uses network "https://api.example.com"
uses process "python"
```

The person running it grants the same scope explicitly:

```sh
nex run program.nex --allow-network https://api.example.com --allow-process python
```

The declaration, CLI grant and environment switch all have to allow the operation. A missing
declaration is reported as `E2026`; a missing grant or a restricted host is `E3008`. Static analysis
checks literal URLs and executable names. The host checks every call, including values computed at
run time.

### Network

`Net.get(url: Text) gives Text` sends one HTTPS GET request and returns a UTF-8 response body. The
URL's origin must exactly match a declared and granted origin. Only the default HTTPS port is
accepted. Redirects and inherited proxy configuration are not used. Requests stop after five seconds
or one MiB of response bytes. An invalid URL, HTTP failure, invalid UTF-8, timeout or oversized body
stops the program with `E3014`.

### External process

`Process.run(command: Text, arguments: List[Text]) gives Text` starts the executable directly, with
the listed arguments, no shell and no standard input. It returns UTF-8 standard output only when the
program exits successfully. Standard error from a failed process appears in an `E3014` diagnostic.
The command must be declared and granted exactly. A process has five seconds; standard output and
standard error are each limited to one MiB. The child receives a small environment containing only
the system `PATH` and the variables required to launch programs on Windows.

Allowing a process lets that executable run with the operating-system permissions of the user who
started NEXORA. The command and its arguments are therefore a deliberate trust boundary; this is not
a sandbox for running untrusted code.

### Restricted hosts

The API's default `NoHost` rejects both operations. The Playground worker continues to use `NoHost`
for program execution; its protocol cannot grant either capability. The production worker also runs
inside a Docker container with `--network none`. The feature is available to local CLI programs that
explicitly request it, not to public Playground programs.

## Consequences

- `E3014` reports failures in network requests and external programs.
- The CLI has repeatable `--allow-network ORIGIN` and `--allow-process COMMAND` options for `nex run`
  and `nex test`.
- The parser, checker and interpreter remain free of operating-system imports. The `host` module is
  the only runtime module that opens network connections or starts external programs.
- The capability declaration and grant make access deliberate; they do not isolate an explicitly
  permitted executable from the local user's other permissions.
