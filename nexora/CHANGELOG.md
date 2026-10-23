# Changes

Changelog for NEXORA, with the most recent version first.

All versions are prior to 1.0: the language may change incompatibly between versions. Each incompatible change is indicated here and explained in `docs/decisions/`.

This log starts with version 0.1.0, the first that could run. Version 0.9.0 is the first published version: it is tagged (`v0.9.0`) and the `nexora-lang` package is on PyPI and npm. Version 0.10.0, with `Option` and `Result`, is also tagged (`v0.10.0`) and published in both registries. Earlier ones only identify code states: they were never tagged or published.

Each version groups its changes into these sections, when they contain content:

| Section | What it covers |
|---------|----------------|
| Added | New features |
| Fixed | Resolved defects |
| Incompatible changes | What may cause an existing program or script to stop working, and how to update it |
| Removed | What no longer exists |
| Documentation | Relevant documentation changes |
| Limitations | Known restrictions worth being aware of |

## 0.11.0 — Modules and imports (not published)

This version is not tagged or published: it is the repository state. It implements
[decision 0018](docs/decisions/0018-modulos-e-importaciones.md): a program may be made of several files.

### Repository

- The server (`server/`), the web app (`web/`) and its deployment are no longer in this repository; the repository remains focused on the language itself: interpreter, npm package, VS Code extension, and documentation. They live in a separate private repository. The web is at <https://nexoralang.org>.

### Added

- **`import "path/file.nex"`**, at the beginning of the file. The path is resolved relative to the file doing the import, not relative to the directory from which the command is run.
- **A namespace per module**, with the file name without the extension:
  `models.area(p)`, `models.Point(x: 1, y: 2)`. Records in a module are nominal: a `Point` from one module is not the `Point` from another.
- **`pub`**: everything declared by a module is private unless marked with `pub`.
- **New diagnostics**: `E2027` (unknown module), `E2028` (private name), `E2029` (circular import), and `E2030` (two modules with the same name).
- **`nex symbols` and `nex context`** now include the names and functions of imported modules, with a new `file` field at the end of each object: the file that declares it, relative to the program and using `/`. `nex inspect` becomes `nexora.inspect/2`, with `imports`, `public`, and `qualifier`.
- **A new example**, `examples/modules/`, with a program and a module that imports it.

### Fixed

Before being tagged, during development of this same version:

- A module that imported the main program was not detected as a cycle in the first pass: the program was read twice and the error appeared as `a.nex -> b.nex -> a.nex -> b.nex`, referring to a copy of the program. It now appears as `a.nex -> b.nex -> a.nex`, in the import of `b.nex`.
- Modules were shown with the machine’s absolute path in errors, the `file` field, and `E2030` suggestions. They are now shown relative to the program, with `/` on all systems.

### Incompatible changes

- `import` and `pub` move from reserved words to keywords. A program that used them as names no longer compiled, and still does not compile, with the same code (`E1103`).
- The specification moves to version 0.11 and the reference implementation to 0.11.0. Version 0.10.0 already published on npm and PyPI is not touched.

### Limitations

- The playground does not run programs with imports: it receives the program text without the adjacent files.
- There is no aliasing or selective import. `nex test` only evaluates examples from the file it is passed, not those from imported modules.

## 0.10.0 — Option and Result

This version is tagged (`v0.10.0`) and published: the `nexora-lang` package is on PyPI and npm. It implements
[decision 0016](docs/decisions/0016-option-y-result.md), which gives the language the two types that allow expressing “there is no value” and “something failed,” without exceptions.

### Added

- **`Option[T]`**, with its two variants: `Some(value)` and `None`. `Option.is_some` and `Option.is_none` indicate which one it is; `Option.unwrap_or` returns the value or a default of the same type, and `Option.unwrap` reads it without a default, emitting diagnostic `E3011` if it is absent.
- **`Result[T, E]`**, with `Ok(value)` and `Err(error)`. `Result.is_ok` and `Result.is_err` indicate which one it is; `Result.unwrap_or` returns the value or a default, and `Result.unwrap` and `Result.error` read it without a default, emitting diagnostics `E3012` and `E3013` when the variant does not carry it. **The error is kept exactly as is**: `Err("missing file")` remains that text when read.
- **The types `Option[T]` and `Result[T, E]` can be written** and nested: `Option[Option[Int]]`, `Result[Text, Error]`.
- **A new example**, `examples/option_result.nex`, with an optional search and an analysis that may fail.

### Incompatible changes

- The names `Option`, `Result`, `Some`, `Ok`, and `Err` become part of the language. A program that declared a function with one of those names would use the built-in one, as already happened with `print` or `to_text`. `None` is the opposite case: if the program declares a name like that, the program’s name wins.
- Types with writable arguments change from only `List[T]` to also `Option[T]` and `Result[T, E]`.
- The specification moves to version 0.10 and the reference implementation to 0.10.0. Version 0.9.0 published on npm is not touched.

### Documentation

- The specification describes the two types in section 4.7 and their functions in section 8.4.
- `docs/types.md` has a new section with the two types, when to use each one, and what not to do.
- New [ADR 0016](docs/decisions/0016-option-y-result.md), which explains the decision and why the `?` propagation is not implemented yet.

### Limitations

- There is no `match`, no `if let`, and no `?` operator: variants are recognized via functions and the value is read with `unwrap_or` when it is known which one it is. ADR 0012 remains a proposal for user enums and `match`.
- The type of a direct `None`, a direct `Ok`, or a direct `Err` in a comparison is not inferred: the result type must be written first in a variable.

## 0.9.0 — Input, arguments, files, and permissions

This version is tagged (`v0.9.0`) and published: the `nexora-lang` package is on PyPI and npm.
It implements the [decision 0015](docs/decisions/0015-entrada-argumentos-archivos-y-permisos.md),
which describes a program’s input, its arguments, and access to files with explicit permissions. The [0012](docs/decisions/0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) is not rewritten: its input part (D11) and effect system remain a proposal, and this version chooses another way to do the same.

### Added

- **Program arguments**: `args() -> List[Text]` returns the arguments with which the program was executed, written after `--`: `nex run program.nex -- one two`. They require no declaration.
- **Standard input**: `input() -> Text` reads one line, without the line ending. When there is nothing left to read, the program stops with `E3009`. It requires no declaration.
- **Files**: `read_file(path)` and `write_file(path, text)`. A program declares what it needs with `uses read "path"` or `uses write "path"`, and whoever runs it must allow it with `--allow-read=PATH` or `--allow-write=PATH`.
- **The permissions model**: the effective capability is the intersection of what the program declares, what the runner grants, and what the environment permits. Declaring does not grant, granting does not enable, and the environment has final authority. Paths are confined to the resolved path: a `..` or a symbolic link leaving the granted scope is useless.
- **Tools**: `nexora.context/1`

### Added

- **A new built-in type**: `File`, with read/write permissions and access via `read_file` and `write_file`.
- **A capability-based permission model**: the program, the runner, and the environment all declare what is allowed.
- **`nex check`** now validates permission declarations and command-line flags.
- **`nex run`** and `nex test` accept `--allow-read` and `--allow-write`.
- **Examples** for file access and permission checks.

### Fixed

- The command-line interface used to accept a program even when permission flags had invalid paths; now they are validated at startup.
- `read_file` and `write_file` no longer silently fall back to the working directory when given relative paths.

### Documentation

- Added a section in the language documentation describing the runtime permission model.
- Updated the getting-started guide to cover `args()`, `input()`, and file access.

### Limitations

- Permissions are evaluated at runtime, not statically.
- File access is limited to the paths explicitly authorized by the runner and environment.
- The permission model does not yet support directories with wildcard patterns.

## 0.8.0 — Errors, diagnostics, and tooling

This version continues the stabilization of the command-line tools and diagnostics ecosystem. It includes improvements to the language server, formatter, and the analysis tooling.

### Added

- **New diagnostics** for syntax and analysis improvements.
- **Language server support**: completion, hover, signature help, go-to-definition, type information, and references.
- **Code formatter** for canonical source formatting.
- **More examples** and test coverage for formatter and LSP output.

### Fixed

- Diagnostics now report better suggestions for unknown names and invalid syntax.
- The formatter preserves language meaning while rewriting code into canonical form.

### Documentation

- Updated documentation for the language server and formatter integration with VS Code.

### Limitations

- The language server and formatter are still experimental and may change.

## 0.7.0 — Editor and analysis tools

This version adds the VS Code extension, language server, and static analysis outputs for IDE integration.

### Added

- **Language server** (`nexora/src/nexora/lsp.py`): supports document analysis, type information, symbol lookup, diagnostics, references, and formatting.
- **VS Code extension**: integrates NEXORA with the editor.
- **The language formatter** (`nexora/src/nexora/formatter.py`): rewrites a program into canonical form using the lexer tokens, so it does not change the meaning.
- **Tests** (`tests/test_lsp.py`, `tests/test_formatter.py`, `tests/test_vscode_extension.py`): verify that the diagnostics from the server match the CLI, that the formatter does not change program semantics, and that the extension manifest and grammar stay in sync with the lexer.

### Documentation

- New [ADR 0017](docs/decisions/0017-un-editor-la-extension-de-vs-code.md), explaining the decision and why the language server and formatter are part of the language itself.

## Unpublished — server and web

Changes in the web server (`server/`) and web app (`web/`) after the `v0.6.0` tag, still without a version. They are not part of 0.9.0, 0.10.0, or their packages: the language is documented above, and the server and web are deployed separately.

### Added

- **Anti-spam for sign-up and login** (`server/src/captcha.js`): Google reCAPTCHA v3, a honeypot field, and a strict per-client limit (5 registrations or 15 logins per hour) for every request without a token confirmed by Google. reCAPTCHA is only loaded in the browser if the person accepts it in the cookie panel; without it they can still log in, but only within that limit. The secret key goes in `RECAPTCHA_SECRET_KEY` and the site key in `web/js/consent-config.js`; at startup, the server warns if only one of the two is present.
- **Login throttling by account** (`server/src/login-throttle.js`): after 5 failures from a client, that client waits progressively longer, up to 15 minutes; after 20 failures against an account from any client, each attempt waits up to one minute. It responds the same way for an email with an account and one without, and reserves each attempt before querying the database.
- **Client limits with IPv6** (`server/src/rate-limits.js`): all limits count an IPv6 address by its `/56` block, and also each `/48` network with four times the quota. The `RateLimit-*` headers describe the account that was exhausted before, and each rejection includes `Retry-After`.
- **Deletion of expired sessions** at startup and every hour, in batches, without overlapping passes (`server/src/session-cleanup.js`).
- **Security headers on all responses** (`server/src/security-headers.js`): the content security policy (CSP) without inline code previously used by the playground and guide is applied to all pages, along with `X-Frame-Options`, `Cross-Origin-Opener-Policy`, `Permissions-Policy`, `Referrer-Policy`, and, in production and only over HTTPS, HSTS. The API has a policy that loads nothing.
- `LISTEN_HOST`: the address the server listens on. With nginx on the same machine, `LISTEN_HOST=127.0.0.1` and `TRUST_PROXY=loopback`; at startup, the server warns if they do not match.
- Web: fonts are served from the site itself (JetBrains Mono, with its OFL license) instead of Google Fonts, and the entire site uses JetBrains Mono; a cookie consent manager with Google Consent Mode v2; legal pages, still in draft form (see Limitations); and expanded web documentation: what NEXORA is, how it is tested, and recent changes.
- `GET /api/playground/status` says whether the playground is enabled (`{"enabled": true}` or `false`).
  It also responds with the playground disabled and does not start the worker. The page checks this first: if disabled, it does not request `/info` or `/examples`.
- Legal pages include `<meta name="robots" content="noindex, nofollow">` while they are drafts, and a test enforces it. It only tells search engines not to index them: it does not prevent opening them to anyone who has the link.
- `GET /api/health`: says whether the process is running and responds to requests (`{"status":"ok","checks":{"http":"ok"}}`), and nothing more: it does not check MySQL, Google, GitHub, reCAPTCHA, or the playground, nor reveal the version or configuration. While shutting down it responds with 503.
- **Graceful shutdown** (`server/src/lifecycle.js`): with `SIGTERM` or `SIGINT`, the server stops accepting new connections and responds with `Connection: close`, so a persistent connection does not keep it alive; it waits up to 10 s for in-flight requests and the batch of expired-session cleanup in MySQL (it sends none further); it closes the MySQL pool (up to another 10 s) and exits with 0, or with 1 if it had to cut something. If the other signal arrives during shutdown, it is not repeated; if the same signal arrives again, Node terminates the process immediately without waiting.
  The timeout limit keeps the process alive until it expires: if the only pending task has no resource behind it (a pool close that never ends), the process no longer exits with 0 before the deadline without logging it; instead it waits for the limit, logs it, and exits with 1. This was tested with automated tests on Windows (Node 20.6.1, 22.23.3, and 24.21.0), without real signals: with systemd, untested.
- **MySQL integration tests, prepared but never executed** (`server/test/integration/`).
  `npm run test:integration` would execute the application’s real queries against an isolated test database (`nexora_test`), with one account for migrations and another for the application, which an administrator would have to create manually with `setup-admin.sql` (a pending proposed review).
  They are not part of `npm test` or continuous integration. Before loading anything, guards reject any other environment (variables `DB_*`, another server, an enableable playground, or permissions different from those expected), and a named lock (`GET_LOCK`) prevents two executions at once.
  The guards only accept Node 22 from 22.22.3 and Node 24 from 24.14.0 (`HOOK_MINIMUMS` in `server/test/integration/guard.js`): these are the minima measured on Windows for the module hook in `preflight.js`, not those in `engines` in `server/package.json` (`^22.23.2 || ^24.18.1`), and an `npm test` check ensures that everything accepted by `engines` falls within it. Other branches (23, 25, 26, and newer) and versions not exactly X.Y.Z are rejected until measured. In the measured versions below those minima, the hook also blocked mysql2 in the legitimate order; the cause is not confirmed. On a Node version the guards do not permit, `npm test` skips, with its reason, the 14 tests that launch `preflight.js`: this happened in the experimental Node 26 run of the 21 October 2026 CI. **None of this has run against a real MySQL**: neither the administration SQL, nor the migrations with reduced permissions, nor the lock.

### Incompatible changes

- **The server requires Node.js 22.23.2 or later on the 22 branch, or 24.18.1 or later on the 24 branch** (`engines` in `server/package.json`: `^22.23.2 || ^24.18.1`; previously 20.6 or later). Node 20 is unsupported as of 30 April 2026, and the minimums are the latest security versions of each branch in October 2026. Branches 23, 25, and 26 are excluded. npm only warns (`EBADENGINE`) on another version; it does not prevent installation. Within range, local Windows tests have been run on 22.23.3 and 24.21.0; the exact minimums have not. The server CI now tests 22.23.2, 24.18.1, the latest release of the 22 and 24 branches, and, without blocking, Node 26; it was first run on 21 October 2026.
- **With `NODE_ENV=production`, `PLAYGROUND_ENABLED=true` requires the container command in `PLAYGROUND_WORKER_COMMAND`.** Without it (or with a process command), the server does not start: the process mode executes the visitors’ code with the server’s permissions. Outside production, process mode remains available for local testing. Configuring the container command does not prove that isolation works: it is still unverified with real Docker.

- **`NODE_ENV` only accepts `development`, `test`, or `production`, in lowercase.** Previously any value other than `production` (`Production`, `prod`, empty) left the server in development mode, without cookies only over HTTPS. Now those values prevent startup. If undefined, it continues to work as development, and the server warns at startup.
- **`TRUST_PROXY` only accepts `0`, `loopback`, or an integer from 1 to 10 without leading zeros.** Before it was read with `Number()`: `true` or `nginx` gave `NaN` with no warning. Now any other value prevents startup. With nginx on the same machine, `loopback` is recommended instead of `1`.
- `LISTEN_HOST` only accepts an IP address or empty; a host name, including `localhost`, prevents startup.
- With `NODE_ENV=production` and `RECAPTCHA_SECRET_KEY`, a missing `RECAPTCHA_HOSTNAMES` prevents startup.
  `RECAPTCHA_MIN_SCORE` outside the range 0 to 1, or `RECAPTCHA_HOSTNAMES` that is not a list of domains, also does.
- **In production without `RECAPTCHA_SECRET_KEY`, all registrations and logins go through the strict limit** (5 registrations or 15 logins per client per hour). In development nothing changes.
- The account API has new responses: `429` with `code: "login_throttled"` and `Retry-After` during login throttling; `400` with `captcha_invalid` or `captcha_expired`; and `429` with `captcha_required` under the strict limit. A `website` field with content is rejected with `400`.

- **The playground is disabled unless it is explicitly enabled.** Previously it was always enabled whenever `PLAYGROUND_ENABLED` was not exactly `false`: if undefined, empty, or mistyped (`False`, `0`), it remained open. Now only `PLAYGROUND_ENABLED=true` enables it; if undefined, empty, or `false`, the API responds with 503 (`playground_disabled`) and no worker starts. A local installation that wants to use the playground must add `PLAYGROUND_ENABLED=true` to its `server/.env`.
- Any other value of `PLAYGROUND_ENABLED` (`True`, `1`, `yes`…) prevents the server from starting, with a message asking for `"true"` or `"false"`.
- **The only container command accepted by `PLAYGROUND_WORKER_COMMAND` is the documented one.** It must begin with `"docker","run"`, include exactly once each isolation option and resource limits from `server/.env.example` with their exact value, including `"--init"`, `"--pull","never"`, `"--name","{container}"`, and end at the image. Any other container command prevents the server from starting, even if the playground is disabled, with a message naming the failure. This includes an option missing, repeated, having another value, or not on the list, such as aliases `-m`, `-u`, `--net`, or `--interactive`; the form `--option=value`; anything after the image; a path to the executable, `docker.exe`, `sudo`, Podman, `docker container run`, or global Docker options. What comes after the image is not applied by Docker, but received by the program inside the container. With the earlier validation, a `"--name","{container}"` written behind the image was accepted (confirmed with the previous validator), and according to the code the server could consider a still-running container as deleted; this has not been observed with real Docker. To update an existing configuration, copy the command from `server/.env.example`. Changing a limit requires changing the server (`server/src/playground/config.js`), not just `server/.env`.
- **Only the local image `nexora-worker` runs, and Docker never downloads it.** The image must be `nexora-worker` or `nexora-worker:<tag>`: no other name, path, registry, or digest is allowed. `"--pull","never"` means that if the image is not on the machine, execution fails instead of downloading it. The image must be built on the server before enabling the playground and after each update (see the [playground guide](docs/playground.md#3-worker-image)). `--pull` requires Docker 20.10 or later.
- Process-mode commands remain unvalidated except for those containing `{container}` or an executable called `docker` or `podman`: they are treated as container commands and rejected if they are not the documented one.

### Fixed

- **A container that times out no longer keeps running with its slot released.** Previously, the server could assign the next execution to the same container slot while the previous container was still running after being killed or timing out. That race is now blocked by a lock and a “busy” state on the worker slot.
- **The lock and cleanup of the worker lifecycle no longer leave stale containers behind when the server crashes or is killed.** The worker is tracked by name and the server deletes it if it remains after timeout or shutdown.
- **The API `/api/playground/status` no longer returns stale state when the worker is starting or restarting.** It reports the current actual status and does not get confused by race conditions.
- **The legal pages are no longer indexed by default** due to the `noindex` meta tag and link strategies.
- **Security headers are now set consistently across all routes**, including API and static files.

### Limitations

- Container isolation remains **unverified**: this change prevents enabling the playground by accident, but it does not make it more secure once enabled.
- None of this has been tested with real Docker. The command tests only parse the argument list, without running Docker; lifecycle tests (deleting containers, occupied slots, missing image) use a fake Docker. If the server crashes, no one deletes the running containers it had started.
- What counts as a container command is decided solely by the documented names. A wrapper script, another tool (`nerdctl`…), or a Docker executable with another name is outside detection: it is not an accepted way to run containers, and the server would not validate its command or delete its containers.
- Validating the command does not guarantee the effective Docker daemon configuration or runtime.
- The local tag (`nexora-worker` or `nexora-worker:<tag>`) is mutable: anyone with access to the Docker daemon can retag another image with that name, and the server would run it without noticing. Whether the Nexora image runs depends on access control to the machine and the Docker daemon.
- Docker rootless mode is not supported: the command does not allow `-H` or `--context`, and the server only passes `PATH` and `SystemRoot` to the commands it launches.
- Anti-spam, login throttling, session cleanup, and headers have been tested with the database, Google reCAPTCHA, and the browser simulated: not against a real MySQL, real reCAPTCHA keys, in a real browser, or behind nginx. The automated server tests, using the same mocked services, report 811 passing and 0 failing on Node 24.21.0 (one run, Windows 11, with integration-test guards limited to measured branches). Before this change they reported 810 passing and 0 failing with Node 24.21.0 (in each of three runs), 24.14.0, 22.23.3, and 22.22.3, and 796 passed, 14 skipped (those needing Node 22.22.3 or later on the 22 branch, or 24.14.0 or later) and 0 failed with Node 20.6.1 and 22.15.0 (one run with each version) on Windows 11. The `engines` minimums (22.23.2 and 24.18.1) have not been run. On Ubuntu 24.04 under WSL 2, they ran before the latest web fixes (567 passed, 0 failed, in each of three runs) ([Tests](docs/testing.md)).
- Rate-limit counters and login-throttle counters are in memory: they are lost on restart and are not shared across multiple server instances.
- In Google or GitHub login, the session is created outside the account transaction and its linkage; if it fails, the account remains linked without a session until the next attempt. During shutdown, a second `SIGTERM` or `SIGINT` terminates the process without completing cleanup, and the 503 from `/api/health` only reaches connections already open. The automated tests, on Windows with the mocked database, cover OAuth-session failure and retry, the 503 during shutdown, and rejection of new connections. They do not cover a second signal of the same type or two simultaneous first logins from the same identity, which remain untested. Real MySQL tests, real OS signals, systemd, and nginx remain pending ([Pending tasks and risks](docs/playground.md#pending-tasks-and-risks)).
- The legal pages are still draft pages without the owner’s data or legal review: they should not be published as-is. Risks and pending decisions (Analytics and its CSP, the `409` that reveals whether an email has an account, cancellation of MySQL queries): [Pending tasks and risks](docs/playground.md#pending-tasks-and-risks).

## 0.6.0 — Text operations that declare their requirements

A program can measure a text string, slice it, search inside it, order it, and read numbers written in it. The new functions belong to a type and are called by name (`Text.length`, `Int.parse`…), and the ones that may not have a result declare when they do with an `requires` written in NEXORA, just like a function in the program. It implements
[decision 0011](docs/decisions/0011-operaciones-sobre-textos.md). No valid program in 0.5.1 stops being valid or changes result, and no names are reserved. For a valid program the only changes are in tooling documents, which gain fields and entries without changing version:
`"qualifier": null` in `Call` nodes from `nex inspect`, and the new functions in `nex symbols`.

### Added

- **Functions of a type**, called like `Type.function(...)`:
  - `Text.length`, `Text.slice`, `Text.contains`, `Text.starts_with`, and `Text.ends_with`. They work with Unicode code points (characters), without normalization and distinguishing case.
  - `Int.can_parse`, `Int.parse`, `Float.can_parse`, and `Float.parse`. They read a single number format, the same on any machine: `Int.parse` reads an integer within the range of `Int` (`"-42"`), and `Float.parse` reads a number with a decimal part or exponent (`"2.5"`, `"2.5e3"`, but not `"42"`). They do not accept spaces, a leading `+`, separators, or other bases.
- **Language functions have `requires`.** `Text.slice`, `Int.parse`, and `Float.parse` declare their conditions in NEXORA, with their explanation, and a call that violates them stops with the same `E4001` as a program function (exit code `5`). In `Int.parse` and `Float.parse`, the diagnostic adds a suggestion based on what failed: check the text first with `Int.can_parse` or `Float.can_parse`, or the range of `Int` if the number does not fit. A program may use the same functions in its own `requires` (`requires Int.can_parse(written)`) and in its refined types (`type Code = Text where Text.length(value) == 3`).
- **Order between texts:** `<`, `<=`, `>`, and `>=` between two `Text` values (also refined types based on `Text`). They compare character by character by code point, and one text comes before any other that starts with it (`"ab" < "abc"`, `"" < "a"`). It does not depend on language or system configuration (`"Z" < "a"`), and compares characters, not numbers (`"10" < "9"`).
- Diagnostics for the new syntax, without new codes: `E1101` when the form is wrong (`Text.length` without parentheses, spaces around `.`, more than one dot) and `E2008` when the name does not exist, with suggestions like `Did you mean 'Text.length'?` for `length(t)`.
- `nex inspect`: `qualifier` field in each `Call` node (`null` for calls without qualification), without changing the schema version (`nexora.inspect/2`). `nex symbols` and capabilities (`language.builtins`): qualified names and a `contracts` field with the requirements of each built-in function. `nex context`: qualified names in `builtins_called` and `text_operations` in `features`.
- Examples: `texts.nex` and `failing/parse_number.nex`.

### Changed

Only in programs that were already invalid:

- A `.` outside a number, text, or comment becomes a token. Where there used to be `E1001` (`x.y`), now there is `E1101` or `E2008`.
- `E2011` keeps its code, title, and category, but its suggestion, when comparing a `Text` to a number, now proposes converting one side with `to_text(...)` or `Int.parse(...)`. Ordering two `Text` values is no longer an error.

### Fixed

- **The source package could not run its own test suite.** `MANIFEST.in` did not include the JSON schemas from `tests/golden/schemas/`, and the tests that read them failed in a copy generated with `python -m build`. The installable package (`.whl`) was not affected.

### Documentation

- Specification 0.6: section 8.1 (functions of a type and order between texts).
- Guides: requirements of language functions in [contracts](docs/contracts.md#the-functions-of-the-language-also-have-requires), and updated limits in [limitations](docs/limitations.md).
- The loop example in the web guide and specification now goes up to 10,000 instead of 100,000: this runs with enough headroom inside the playground time limit.

### Limitations

- A character is a Unicode code point, not what a person sees as a letter: an `e` with a combining accent has length 2, and two texts that look the same may be different for `==`.
- Text ordering is not alphabetical in any language.
- Requirements of built-in functions are checked at runtime; `nex check` does not warn even if arguments are constant.
- `Float.parse` rounds to the nearest `Float`: the returned value may not be exactly the number written (`"0.1"`).
- There is no `trim`, uppercase/lowercase conversion, `split`, `replace`, interpolation, or position search.

## 0.5.1 — Review of out-of-memory behavior

Result of auditing [decision 0009](docs/decisions/0009-memoria-agotada.md) after implementing it. Its guarantee holds: `E3007` is still constructed without retaining the values of the failing program, and each example in `nex test` is evaluated in isolation. The audit found two defects around it, corrected here. No program changes result or exit code.

### Fixed

- **`E3007` and the `E3004` stack-overflow error did not say which loop they occurred in.** [Decision 0010](docs/decisions/0010-var-y-while.md) (section 7) gives every execution error inside a loop a loop note (`In turn 3 of the loop at line 6.`). These two are constructed when the error has already left the loops, and they arrived without them. They now carry the same notes as any other error at the same point, from the innermost loop outward, with the same maximum of six.
- **`nex test` in text mode could leave an unfinished summary.** The report was written as it was being prepared: if it failed afterwards (an internal error, out-of-memory), that summary remained in standard output just like a complete report, with exit code `70`. Now the report is prepared in full and written only at the end, as with the JSON document: if anything fails, standard output stays empty. Normal reports are unchanged.

### Limitations

- The real out-of-memory test (the worker one, with `RLIMIT_AS`) only works on Linux and macOS and has not yet been run; on Windows it is skipped and CI has never worked. The other `E3007` tests deliberately trigger `MemoryError`.

## 0.5.0 — `var` and loops that explain why they end

Repetition no longer depends on recursion and the limit of 1000 nested calls. And it does so in the NEXORA way: each loop declares why it terminates (`decreases`) and what it maintains (`invariant`), and the interpreter checks it on every iteration. Thus no loop can continue forever: it either terminates or stops and says in which iteration and with which values. It implements the [decision 0010](docs/decisions/0010-var-y-while.md).

### Added

- **Reassignable variables:** `var count = 0` and `count = count + 1`. The type of a `var` never changes. `let` remains immutable, and parameters also remain immutable, so `ensures` and diagnostics always see the values with which the function was called. A `var` of a refined type keeps its guarantee: it is assigned either a valid constant or a value verified with `Tipo(x)`.
- **`while` loops** with two clauses at the start of the body, in contract style and with an optional explanation after a comma:
  - `decreases` (exactly one): the measure, an `Int` that never drops below 0 and decreases on each iteration.
  - `invariant` (zero or more): conditions that hold before each condition evaluation.
- New codes: `E2021` (loop without measure, or with more than one), `E4005` (invariant violated), and `E4006` (the measure does not decrease or is negative), the latter two in category `contract`, with exit code `5`. Their diagnostics say the iteration and values of all visible variables.
- An error inside a loop (`E3xxx`, `E4xxx`) gains one note for each loop that contains it: `In turn 3 of the loop at line 6.`
- `nex test` can no longer hang waiting for a loop: the example ends as `error` with `E4006`.
- `nex inspect`: nodes `Var`, `While`, and `LoopClause` (still `nexora.inspect/2`). `nex symbols`: fields `mutable` and `assignments`. `nex context`: `mutable` field in variables, `loops` at the end of each function with condition, invariants, and measure of each loop, values `mutable_variables`, `loops`, and `loop_invariants` in `features`, and a note when there are loops.
- `E1103` suggests how to write with `while` what was intended with `for`, `break`, or `continue`.
- Examples `loops.nex` and `failing/loop_measure.nex`.

### Changed

- `E2007` keeps its code and title, but its label and suggestion now say whether the name is a `let` variable or a parameter, and propose `var`.
- The suggestion for `E2014` now reminds that a loop may never execute.

### Incompatible changes

- **`invariant` and `decreases` become keywords.** A program that uses them as a variable, parameter, or function name is no longer valid (`E1101`); it must be renamed.
- `var` and `while` are no longer reserved words. No valid program could use them.

### Documentation

- Specification 0.5: section 5.3 (`var` and assignment) and section 9.5 (loops).
- Guides: loops in [contracts](docs/contracts.md#loops-invariant-and-decreases) and [getting started](docs/getting-started.md).

### Limitations

- There is no `for`, `break`, `continue`, or compound assignment (`+=`).
- The measure is an `Int`; there are no composite measures.
- A measure guarantees that a loop terminates, not that it terminates quickly: a huge initial measure allows many iterations. A slow recursion (`fib(40)`) still has no time limit.

## 0.4.0 — Examples and `nex test`

Third step in the main line: a function can include concrete cases of what it should return, and `nex test` checks them without writing `main`. It implements [decision 0008](docs/decisions/0008-ejemplos-y-nex-test.md) and [decision 0009](docs/decisions/0009-memoria-agotada.md).

### Added

- **Examples in functions**: `example double(2) == 4, "Two doubled"`, a clause at the start of the body alongside `requires` and `ensures`. It is a `Bool` expression that has to call its own function (`E2020` if it does not) and does not see parameters or `result`. The analyzer never evaluates it.
- **`nex test`**: evaluates examples, each in a fresh interpreter, checking contracts of everything executed. It does not require `main` and does not run it. Options `--format text|json` and `--function FUNCTION`. Each example ends in `passed`, `failed` (`E4004`, new category `test`), or `error` (the original diagnostic, with a note identifying the example).
- Exit code `6`: some example did not pass, or there were no examples to evaluate.
- Format `nexora.test/1` and `nexora.api.test_source`, which returns the same document.
- `nex inspect`: node `Example` and `examples` field at the end of `Function` (still `nexora.inspect/2`). `nex context`: `examples` field and `examples` in `features`.
- Example `examples/checked_examples.nex`.
- **`E3007` (Out of memory)**: a program that runs out of memory while executing receives a runtime diagnostic, with the call chain, instead of an internal error. In `nex test`, the example ends as `error` and the following ones are evaluated. `nexora.api.run_source` still responds with `memory_limit`, with the same message, and now includes `E3007` in `diagnostics`.

### Fixed

- **The npm and server tests were not run under Node 18 and 20.** `node --test` only expands patterns such as `"test/*.test.js"` from Node 21, so under the versions declared by the packages it found no files. The scripts now name each file explicitly, and a test checks that none are missing. CI tests npm on Node 18, 20, and 22, and the server on Node 20.6 and 22.

### Incompatible changes

- `example` moves from reserved word to keyword. No valid program could use it as a name.
- **`nex run` with a program that runs out of memory exits with `3`, not `70`**, and the error output shows `runtime error[E3007]` instead of `internal error`. With `--format json` it writes document `nexora.diagnostics/1`. Code `70` again means only an internal defect of NEXORA. A script that treats `70` as “out of memory” must check for code `E3007`.

### Limitations

- `nex test` has no per-example time or memory limit.
- `E3007` only appears if Python actually runs out of memory. On Linux, the OS may kill the process before any message appears.
- Out-of-memory outside execution (while analyzing the program or building a report) still ends with `70`.

## 0.3.1 — Review of refined types

Result of trying to break the guarantees of 0.3.0. The main guarantee held: no path allows a value to reach a refined type without satisfying its condition, and the static check and runtime execution agree on edge cases (`-0.0`, rounding of `Float`, division by zero avoided with `and`, overflow). These attacks are now part of the tests. The review found four defects around that guarantee, fixed here.

### Fixed

- **`nex check` could take too long with refined types.** Each constant evaluates the conditions of the entire type chain, so the work grew with types × conditions × constants: a valid 60 KB program took 2.5 s and exhausted the playground time limit (2 s). Now the work is capped at 100,000 condition nodes evaluated; above that, the program is rejected with the new code `E2019` instead of being partially validated. The same program is now rejected in 0.18 s, and a normal program checks in hundredths of a second.
- **A malformed type condition produced false errors on each use of the type** (`Cannot apply '+' to Bad and Int`, `Expected Bad, found Int`). Conditions are now checked before signatures, and a type with an incorrect condition is rejected without further errors.
- **A runtime error inside a condition did not say where the check was requested.** If `Huge(n)` overflowed inside the condition of `Huge`, the diagnostic pointed only to the type declaration. It now adds the note `While checking that a value is a valid Huge, at line …`.
- **An explanation with `
` broke the text format of the diagnostic.** An explanation is now a single line: a `
` in it is error `E1101`.

### Documentation

- The specification (section 10.1), the MCP server guide, and the description of `analysis_executes_code` said the analysis “does not execute anything.” They now say precisely what it does: it does not run the program, but it evaluates refined-type conditions on constants, without calling program functions and with work capped.
- New limit in the capabilities document (`get_capabilities()` in Python and in the MCP server): `max_refinement_steps`.

## 0.3.0 — Contracts and refined types

This consolidates the feature that distinguishes NEXORA: requirements are part of the program and are verifiable ([decision 0006](docs/decisions/0006-requisitos-verificables.md)). Contracts stop being experimental, each rule may include its explanation, and refined types arrive. The reasons for each choice are in [decision 0007](docs/decisions/0007-contratos-estables-y-tipos-refinados.md).

This version also includes everything done after 0.2.0 that did not reach publication under another number: documentation, tests, playground, and analysis tools.

### Added

- **Refined types:** `type Percent = Int where value >= 0 and value <= 100`. Every value of a refined type satisfies its condition:
  - A constant used as a value of the type is checked **without executing** (`E2017`).
  - Any other value is checked explicitly with `Percent(x)` at runtime (`E4003`, category `contract`, exit code `5`).
  - A refined value is accepted where its base is expected; an operation with it produces a base value.
  - A type may refine another (`type Pass = Percent where value >= 50`); both conditions are checked, starting from the base.
  - The condition may only use `value`, literals, operators, and built-in conversions (`E2018`).
- **Explanation of rules:** `requires amount <= balance, "An account cannot go below zero"`.
  It works in `requires`, `ensures`, and `where`, and appears in the diagnostic as `Reason: ...` when the rule is violated.
- New codes: `E2016` (invalid type declaration), `E2017` (constant outside a refined type), `E2018` (invalid refinement condition), and `E4003` (refinement violated).
- `nex context` lists refined types (field `types`) and the explanation of each contract (field `message`). New feature: `refined_types`.
- Examples `refined_types.nex`, `invalid/refinement_errors.nex`, and `failing/refinement_violation.nex`.
- **MIT license** (`LICENSE`).
- **npm package** (`npm/`, name `nexora-lang`): installs the `nex` command with a launcher that runs the bundled interpreter using the machine’s Python 3.11+. Prepared and tested locally; **not published**.
- **`nex context`**: summary of a program (signatures, contracts, variables, calls between functions, features used, diagnostics), in text or JSON. Does not execute the program.
- **`nex symbols`**: functions, parameters, and variables with their type, scope, declaration, and each use, with filters `--name` and `--function`. Does not execute the program.
- **`nexora.tooling`**: Python API with the same outputs (`check_source`, `inspect_source`, `get_symbols`, `get_context`, `get_language_spec`, `get_capabilities`). **Experimental.**
- **Optional MCP server** (`nex-mcp`, `pip install -e ".[mcp]"`): seven analysis tools for compatible assistants. It does not execute code or open files indicated by the caller. Tested automatically with the official SDK client (version 2.3.0) and manually in a Claude Code 2.1.296 session on Windows. Not tested with other assistants.
- Formats `nexora.symbols/1`, `nexora.context/1`, `nexora.spec/1`, and `nexora.capabilities/1`.
- JSON Schema for all formats in `docs/schemas/`, generated from code and used by tests to validate real output.
- `nexora_version` field in `nexora.diagnostics/1` and `nexora.inspect/1` documents. This is an added field; the format version does not change.
- Reference tasks for analysis tools (`tests/tooling_tasks.py`).
- **Partial analysis with syntax errors.** `nex inspect`, `nex symbols`, and `nex context` (and their Python and MCP equivalents) describe the code they were able to analyze, with the new `complete` field set to `false`. Statements with errors and functions whose declaration contains one are omitted. A program with syntax errors still does not run.
- **Playground**: web page that checks and runs code with the real interpreter (`docs/playground.md`). Prepared for local use; the containerized isolation for a public service is configured but **not tested**.
- `nexora.api`: `check_source` and `run_source`, for checking or running code in memory with optional output and text-length limits. Result schema `nexora.result/1`.
- `python -m nexora.worker`: single-use process that handles one JSON request.
- Diagnostic `E3006` (text too long), which only appears where the environment sets a limit.
- Exit code `130` when execution is interrupted with Ctrl+C, instead of a Python traceback.
- Limit of 100 errors per stage and file; the command summary indicates when this limit is reached.
- Examples `arithmetic.nex` and `invalid/syntax_error.nex`.
- Tests: examples with recorded output, executable documentation, security, and robustness.
- Coverage measurement (`pytest-cov`) and static code analysis (`ruff`) as development dependencies.
- Configuration to generate an installable package with code, documentation, examples, and tests (`MANIFEST.in`).
- CI workflow for GitHub Actions. **Not yet executed.**

### Fixed

- An integer literal with more than 4300 digits caused an internal error. It is now diagnostic `E1004`.
- A file that was not NEXORA (for example, a binary) produced a character error without a limit.
- When the stack was exhausted by recursive calls inside deeply nested expressions, the message for `E3004` claimed that 1000 calls had been exceeded even when they had not. It now reports the actual number.
- If the output reader closed early (`nex run … | head -1`), an internal error was shown. It now exits silently.

### Incompatible changes

- **`type` and `where` are keywords** (previously reserved words). No valid 0.2 program could use them as names, so none stop working.
- **`nex inspect` becomes `nexora.inspect/2`.** The `type` field of an expression may now be the name of a refined type, not just `Int`, `Float`, `Bool`, `Text`, or `Void`. Added: `TypeDecl` node, `types` field in `Program`, and `message` field in `Contract`. How to update: accept any text in `type` and validate via schema.
- Contracts stop being experimental: their syntax does not change, but from now on it will only change according to incompatible-change rules.
- The Python package is renamed to `nexora-lang` (previously `nexora`) because `nexora` already exists on PyPI. The command (`nex`) and the module (`import nexora`) do not change. How to update a development installation: `python -m pip uninstall nexora` and `python -m pip install -e .`. Generated files are now named `nexora_lang-0.3.0…`, and the optional extra is installed with `nexora-lang[mcp]`.
- In the `nex inspect` document, with syntax errors, `program` is now a partial tree and no longer `null`. It remains `null` with lexical errors or if the file cannot be read. How to update: to know whether a program is valid, use `ok`; to know whether the tree covers the whole file, use `complete`. The format name (`nexora.inspect/1`) does not change; the reason is in `docs/json-protocol.md`.
- Intentionally invalid examples were moved: `examples/errors.nex` is now `examples/invalid/name_errors.nex`; `type_errors.nex` is in `examples/invalid/`; `runtime_error.nex` and `contract_violation.nex` are in `examples/failing/`.

### Removed

- The internal function `values.type_name`, which had not been used since 0.2.0.

### Documentation

- New guides: installation, getting started, types, functions, contracts, CLI, diagnostics, automatic tools and AI, architecture, testing, limitations, and roadmap.
- `CONTRIBUTING.md`, `SECURITY.md`, and `CODE_OF_CONDUCT.md`.
- All programs in the documentation are executed in tests and their output is compared to the real output.
- Specification 0.3: section 4.4 (refined types), stable contracts (section 9), and new codes. Expanded guides for types and contracts. Decisions 0006 and 0007.

### Limitations

- For refined types, `nex check` only checks constants; a calculated value is checked at runtime. There is no way to check it without stopping the program if it fails (there is no `Result`).
- There is no type alias without a condition.
- The project still has no public repository and no contact channel.
- It has only been tested on Windows 11 with Python 3.12.

## 0.2.0

Type system, functions, contracts (experimental), and structured outputs for tools.

### Added

- **Types**: annotations in `let` (`let age: Int = 25`), with inference when omitted.
- **Operators**: comparisons `== != < <= > >=` and logical `and`, `or`, `not`.
- **Explicit conversions**: `to_float`, `to_int`, `to_text`.
- **Functions** with typed parameters, return type, and `return`. Recursion with a maximum of 1000 nested calls.
- **`if` / `else if` / `else`** as statements.
- **Contracts (experimental)**: `requires` and `ensures`, with `result`.
- **Static analysis** of argument and return types, return paths (`E2014`), unreachable code (`E2015`), and unused return values.
- **`nex inspect`**: syntax tree in JSON, with types and positions (`nexora.inspect/1`).
- **`nex run --format json`**: errors in JSON on standard error.
- **Category** in each diagnostic (`file`, `lexical`, `syntax`, `semantic`, `type`, `runtime`, `contract`) and `schema` field in JSON documents (`nexora.diagnostics/1`).
- Call chain in runtime diagnostics.
- New codes: `E1106`, `E2012`–`E2015`, `E3004`, `E3005`, `E4001`, `E4002`.
- Exit code `5`: contract violation.

### Incompatible changes

- The text type is called **`Text`** (previously `String`). This only changes messages: in 0.1 it was not possible to write types.
- The header of text diagnostics includes the category:
  `type error[E2011]: …` instead of `error[E2011]: …`.
- `to_text`, `to_float`, and `to_int` can no longer be used as variable names.
- An unknown return type is now `E2012` (previously `E2004`).
- Requires Python 3.11 or later (previously 3.10).

### Removed

- `E1104` and `E2003`, which warned that parameters, annotations, and user functions did not exist.

### Compatibility

The four example programs from 0.1 still run unchanged and produce the same output.

## 0.1.0

First executable version: `main` function, immutable variables with `let`, types `Int`, `Float`, `Bool`, and `String`, arithmetic, blocks, comments, `print`, and the commands `nex run` and `nex check`.
