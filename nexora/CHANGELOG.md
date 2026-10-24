# Changes

Changelog for NEXORA, with the most recent version first.

All versions are prior to 1.0: the language may change incompatibly between versions. Each incompatible change is indicated here and explained in `docs/decisions/`.

This log starts with version 0.1.0, the first that could run. Version 0.9.0 is the first published version: it is tagged (`v0.9.0`) and the `nexora-lang` package is on PyPI and npm. Versions 0.10.0, with `Option` and `Result`, and 0.11.0, with modules and imports, are also tagged (`v0.10.0`, `v0.11.0`) and published in both registries. Earlier ones only identify code states: they were never tagged or published.

Each version groups its changes into these sections, when they contain content:

| Section | What it covers |
|---------|----------------|
| Added | New features |
| Fixed | Resolved defects |
| Incompatible changes | What may cause an existing program or script to stop working, and how to update it |
| Removed | What no longer exists |
| Documentation | Relevant documentation changes |
| Limitations | Known restrictions worth being aware of |

## Unreleased

Work of the branch of 0.12.0, phase 1 of [decision 0019](docs/decisions/0019-identidad-propia-del-lenguaje.md): a syntax that says what each clause is, and the evidence behind it. The version number stays 0.11.0 until it is published.

### Added

- **Header clauses.** The clauses of a function go between its signature and the `{` of its body, one per line: `needs` (was `requires`), `promises` (was `ensures`) and the new `trust`. Loops use `keeps` (was `invariant`) and `shrinks` (was `decreases`) the same way. Every clause can have a name, `needs fits: part <= 92233720368547758`; names are optional, unique within the function and its loops, and different from the parameters and `result` (new code `E2031`).
- **`gives T`** for the result type, instead of `-> T`. A function that gives nothing has no `gives`; `gives Void` is `E2012`, and `main` has no `gives` (`E2004`).
- **`trust`**: a condition the program relies on and the language does not check. It is type-checked as a `Bool` and never evaluated, and its explanation is required.
- **`Option.value`, `Option.value_or`, `Result.value` and `Result.value_or`**, the names of `unwrap` and `unwrap_or` from 0.12.
- **`nex migrate <file> [--write]`** rewrites a 0.11 program, with every module it imports, in the syntax of 0.12. Without `--write` it shows the edits and the migrated text; with it, it writes the files. It only edits the words and braces that change, keeps every other byte (comments, blank lines, line endings, a byte-order mark), checks the structure of every file before writing anything, and refuses, with the file and the position, what it cannot decide for the person ([CLI reference](docs/cli-reference.md#nex-migrate)).
- **`nex check --evidence`**: what backs every `needs`, `promises`, `trust`, `keeps` and `shrinks` of the program. This version computes only the enforcement: `checked` for a clause the language evaluates when the program runs, `trusted` for a `trust`. With `--format json`, the new format `nexora.evidence/1` ([JSON protocol](docs/json-protocol.md)). Nothing is run.
- **New diagnostics**: `E1107` (a clause word of 0.11), `E1108` (`->` before the result type), both with the hint `nex migrate`, and `E2031` (a clause name used twice, or equal to a parameter or `result`).
- **Equivalence tests**: the 86 programs of the corpus of the decision (8.9.1) give the same results after migration, compared with the published 0.11.0: the same syntax tree after the mapping of the decision (T1), the same exit code, output and diagnostics (T2), the same result of every example (T3), and the same bytes outside the edits (T4).

### Fixed

- **The formatter no longer removes comments.** It rebuilt the program from the tokens of the lexer, which has no comments, so formatting a document in the editor deleted every comment and every blank line, joined expressions written across lines inside parentheses, and turned `\r\n` and `\r` into `\n`. It now works line by line: every comment stays on its line after the code of that line, blank lines stay, every line keeps its own line ending, and a line that holds anything other than tokens and a comment leaves the program unformatted instead of losing it. An expression across lines inside parentheses or brackets keeps its lines, one step further in. One space is left before a comment at the end of a line.
- **Formatting a selection in the editor no longer writes lines from another place.** The language server cuts the formatted text by line number, and the formatter used to remove lines; the formatted text now has the same lines as the document.

### Incompatible changes

- **The syntax of 0.11 is no longer accepted.** `requires`, `ensures`, `invariant` and `decreases` are `E1107`, and `->` before the result type is `E1108`. Those four words stay reserved for this minor version and cannot be names. How to update: `nex migrate program.nex --write`. The front end of 0.11 that `nex migrate` uses, `E1107` and `E1108` are only in 0.12.x: they are removed in 0.13.0.
- **`needs`, `gives`, `promises`, `keeps`, `shrinks` and `trust` are keywords.** A program that used one of them as a name no longer compiles (`E1101`); `nex migrate` refuses it and says which name to change.
- **`Option.unwrap`, `Option.unwrap_or`, `Result.unwrap` and `Result.unwrap_or` are now called `value` and `value_or`**: the old names are `E2008`. `nex migrate` renames the calls.
- **`ai` and `tool` are no longer reserved**: they are ordinary names.
- **`nex inspect` moves to `nexora.inspect/3`.** `Function.header`, one ordered list of `Contract` and `Example`, replaces `contracts` and `examples`; `return_type` is `null` when the function has no `gives`; `Contract.clause` is `needs`, `promises` or `trust`, `LoopClause.clause` is `keeps` or `shrinks`, and both have a `name` field ([inspect schema](docs/inspect-schema.md)).
- **`nex context` moves to `nexora.context/2`** and **`nex symbols` to `nexora.symbols/2`**: the clauses take the new names, and the contracts of `nexora.context/2` and its loop clauses have a `name` field. How to update, for the three formats: read the new clause words, and in `nexora.inspect/3` read the clauses from `header`. `nexora.capabilities/1` keeps `requires` and `ensures` for the contracts of the built-in functions, so that its version does not change.
- **The specification is written in English, and `get_language_spec` moves to `nexora.spec/2`.** `language` is `"en"` (it was `"es"`), and the section ids come from the English headings (`7-functions` instead of `7-funciones`). How to update: read the ids again from the index the tool returns, or from `docs/language-spec.md`. The rest of the document does not change ([JSON protocol](docs/json-protocol.md)).

### Documentation

- The whole documentation is in English: the READMEs, `docs/` (guides, reference and `decisions/`), this changelog, `CONTRIBUTING.md`, `SECURITY.md` and `CODE_OF_CONDUCT.md`. Decision files keep their Spanish filenames.
- [LSP](docs/lsp.md) describes the language server that exists since the editor work (`nexora-lsp`), instead of calling it planned.
- The examples, the golden outputs and the programs of the documentation that the tests check (the blocks with a `nex:` marker) are written in the syntax of 0.12. The decisions are records: their programs keep the syntax of their time and are checked with the front end of 0.11.
- **Not yet updated:** the text of the specification (`docs/language-spec.md`, still version 0.11: its grammar, keywords and sections 9.x) and of the guides that explain the clauses (`contracts.md`, `diagnostics.md`, `getting-started.md` and others) still describe the syntax of 0.11 outside their checked programs.

### Limitations

- `nex check --evidence` computes only the enforcement of each clause. What the examples observe (`nex test --evidence`) and what is decided at the call sites without running are later phases of decision 0019; the document says so in each clause (`not_computed`, with its reason).
- `nex migrate` writes the files of a program one by one: replacing several files is not one atomic operation, and after a failed write the files already replaced stay replaced.
- The equivalence tests measure the corpus of the decision, and nothing broader. They need to reach PyPI the first time, to install the published 0.11.0 in an environment of their own.

## 0.11.0 — Modules and imports

This version is tagged (`v0.11.0`) and published: the `nexora-lang` package is on PyPI and npm. It implements
[decision 0018](docs/decisions/0018-modulos-e-importaciones.md): a program may be made of several files.

### Repository

- The server (`servidor/`), the web app (`web/`) and its deployment are no longer in this repository; the repository remains focused on the language itself: interpreter, npm package, VS Code extension, and documentation. They live in a separate private repository. The web is at <https://nexoralang.org>.

### Added

- **`import "path/file.nex"`**, at the beginning of the file. The path is resolved relative to the file doing the import, not relative to the directory from which the command is run.
- **A namespace per module**, with the file name without the extension:
  `models.area(p)`, `models.Point(x: 1, y: 2)`. Records in a module are nominal: a `Point` from one module is not the `Point` from another.
- **`pub`**: everything declared by a module is private unless marked with `pub`.
- **New diagnostics**: `E2027` (unknown module), `E2028` (private name), `E2029` (circular import), and `E2030` (two modules with the same name).
- **`nex symbols` and `nex context`** now include the names and functions of imported modules, with a new `file` field at the end of each object: the file that declares it, relative to the program and using `/`. `nex inspect` stays `nexora.inspect/2` and gains, as added fields, `imports`, `public`, and `qualifier` in `TypeRef` and `RecordConstruction`.
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
It implements [decision 0015](docs/decisions/0015-entrada-argumentos-archivos-y-permisos.md),
which describes a program's input, its arguments, and access to files with explicit
permissions. [0012](docs/decisions/0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) is not
rewritten: its input part (D11) and its effect system are still a proposal, and this
version decides another way of doing the same thing.

### Added

- **Program arguments**: `args() -> List[Text]` returns the arguments the program was
  run with, written after `--`: `nex run program.nex -- one two`. They require no declaration.
- **Standard input**: `input() -> Text` reads one line, without the line ending. When there is
  nothing left to read, the program stops with `E3009`. It requires no declaration.
- **Files**: `read_file(path)` and `write_file(path, text)`. A program declares what it
  needs with `uses read "path"` or `uses write "path"`, and whoever runs it has to allow it
  with `--allow-read=PATH` or `--allow-write=PATH`.
- **The permission model**: the effective capability is the intersection of what the program
  declares, what whoever runs it grants, and what the environment allows. Declaring does not grant,
  granting does not enable, and the environment has the last word. Paths are confined on the resolved path: a `..` or
  a symbolic link that leaves the granted scope is of no use.
- **Tools**: `nexora.context/1` adds the `capabilities` field, with what the program
  declares; `nexora.inspect/2` adds the `UsesDecl` node and the `uses` field in `Program`. The format
  numbers do not change.

### Changed

- Only in programs that were already invalid: `uses` goes from reserved word to keyword, and
  `read`, `write`, `args`, `input`, `read_file`, and `write_file` become predefined names.
- The repository version becomes `0.9.0` and the specification `0.9`. The JSON schemas do not
  change version: the new fields and nodes are additive.

### Documentation

- The [specification](docs/language-spec.md) moves to version 0.9 and documents input,
  arguments, and files (section 8.3), with the grammar, the permissions, and the paths.
- New [ADR 0015](docs/decisions/0015-entrada-argumentos-archivos-y-permisos.md).
- Updated `diagnostics.md`, `limitations.md`, `cli-reference.md`, `playground.md`,
  `architecture.md`, `roadmap.md`, `types.md`, `json-protocol.md`, `inspect-schema.md`, and `README.md`.

### Limitations

- Standard input cannot be read "until the end" without stopping: `input()` fails with `E3009`.
- Only text files are read and written: there are no directories, binaries, renaming, or
  deleting.
- There is no network, no external processes, and no environment variables.
- The playground and the MCP server do not allow files: the worker has no field in its
  protocol to grant them.

## 0.8.0 — Immutable nominal records

A repository state, not a published version: there is no tag and no package in any registry. This
version implements [decision 0014](docs/decisions/0014-registros-nominales-inmutables.md), which
accepts the D02 part (nominal versus structural records) of proposal
[0012](docs/decisions/0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) within the scope
actually implemented. The rest of 0012 is still a proposal and is not part of this
version.

### Added

- **Records**: a type the program declares, with immutable and required fields:
  `type Point = { x: Int, y: Int }`. They are built with the fields by name
  (`Point(x: 1, y: 2)`, in any order) and their fields are read with `p.x`, also chained
  (`p.x.y`). A record is **nominal**: its identity is that of its declaration, not that of its name
  nor of its fields, so two records with the same fields are different types (`E2011`) and
  two values of the same record are compared by value.
- **Nominal identity in the type model** (`types.py`): the `Nominal` variant and the opaque
  `RecordIdentity` token, which the checker creates once per declaration and which travels in the
  `CheckedProgram` to the interpreter. The interpreter does not rebuild it from the name.
- **Tools**: `nex inspect` adds the `RecordDecl`, `FieldDecl`, `RecordConstruction`,
  `FieldInitializer`, and `FieldAccess` nodes, the `FieldAssign` statement, and the `records` field at the end of
  `Program`; `type` can be the name of a record. `nex context` adds the `records` field
  (with `name`, `fields`, `valid`, `line`, and `reason`) and the value `records` in `features`. `types`
  is still only for refined types.
- **Diagnostics**: `E2023` (Invalid record construction, `type`), `E2024` (Invalid field access,
  `type`), and `E2025` (Cannot reassign a field, `semantic`).
- **Example** [`examples/records.nex`](examples/records.nex), with its output recorded in the
  tests.

### Changed

- Only in programs that were already invalid: `p.x`, where `p` is a variable that is not a type,
  goes from being `E1101` ("Expected '(' to call 'p.x'") to being a field access. The form of a
  qualified call does not change: `Text.length(s)` and `name.length()` are still diagnosed the same,
  and `Point.x` is still a qualified call, not reading a field.
- The repository version becomes `0.8.0` and the specification `0.8`. The JSON schemas do not
  change version: the new fields and nodes are additive.

### Documentation

- The [specification](docs/language-spec.md) moves to version 0.8 and documents records (4.6),
  their grammar, their nominal equality, how they are printed, the table of diagnostics, and the limitations.
- Updated `types.md`, `limitations.md`, `roadmap.md`, `architecture.md`, `index.md`,
  `diagnostics.md`, `inspect-schema.md`, `json-protocol.md`, and `README.md`.
- [Decision 0014](docs/decisions/0014-registros-nominales-inmutables.md) becomes accepted, with its
  implementation. [0012](docs/decisions/0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md)
  is not rewritten and is still a proposal for what is not implemented.

### Limitations

- A record has no methods, no functions of its own, no refinements, no recursion, and no type
  parameters. A refined type cannot be built on a record (`E2016`).
- A record cannot contain itself, neither directly nor through another record nor through
  a list (`E2016`).
- There is no `Option`, `Result`, enums, `match`, user generics, or data input.

## 0.7.0 — Lists and `for` over lists

A repository state, not a published version: there is no tag and no package in any registry. This
version implements [decision 0013](docs/decisions/0013-listas-y-for.md), which accepts, within the scope
actually implemented, parts D01 (type model), D08 (lists), and D09 (`for`) of proposal
[0012](docs/decisions/0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md). The rest of
0012 is still a proposal and is not part of this version.

### Added

- **Immutable lists `List[T]`**: literals `[1, 2, 3]` and `[]`, inference from the first element,
  homogeneity, nested lists, structural equality, and printing as `[1, 2, 3]`. An empty list
  needs an expected type (`E2011`). The arguments of `List` are invariant and `Void` cannot
  be an element.
- **Functions of `List`**: `List.length`, `List.get`, `List.append`, `List.concat`, and
  `List.contains`. `List.get` is partial and declares `requires 0 <= i and i < List.length(xs)`; an
  index out of range stops the program with `E4001`. `append` and `concat` build new lists.
- **`for` over lists**: `for x in xs { ... }`, with an immutable iterator of type `T`, a new
  environment per iteration, `invariant` checked before each iteration and once after the last one, and
  without `decreases` (`E2022`). The iterable is evaluated once and must be a `List[T]`. `break` and
  `continue` still do not exist.
- **Internal type model** (`types.py` and `type_adapter.py`): a structured representation of
  primitives, `List[T]`, refined types, and type variables; identity, compatibility, substitution,
  and unification. The canonical form of types is still text; the migration of the checker
  is partial and the rules not migrated keep their strings.
- **Tools**: `nex inspect` adds `arguments` to `TypeRef`, the `ListLiteral` node, and the
  `For` node; `type` can be `List[...]`. `nex context` tells `while` and `for` apart in `loops.kind`.
  `language_info()` includes `List` in `types`, so that an editor colors it like the other types.
- **Example** [`examples/lists.nex`](examples/lists.nex), with its output recorded in the tests.

### Changed

- Only in programs that were already invalid: `for` and `in` go from reserved words to
  keywords, and `[` and `]` become symbols. `List` and the names of its functions are not reserved: the
  functions are called qualified (`List.length`).
- The repository version becomes `0.7.0`. The JSON schemas do not change version: the new fields and
  nodes are additive.

### Documentation

- The [specification](docs/language-spec.md) moves to version 0.7 and documents lists (4.5), the
  functions of `List` (8.2), `for` (9.6), compatibility, conversions, diagnostics, and
  limitations.
- New [ADR 0013](docs/decisions/0013-listas-y-for.md). [0012](docs/decisions/0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md)
  is not rewritten and is still a proposal for what is not implemented.
- Updated `types.md`, `limitations.md`, `roadmap.md`, `architecture.md`, `index.md`,
  `diagnostics.md`, `inspect-schema.md`, and `README.md`.

### Limitations

- There is no syntactic indexing (`xs[i]`), element mutation, `List.set`, `map`, `filter`,
  sorting, or a total variant of `List.get`.
- All the elements of a list have the same type; `[]` and `for x in []` need an expected
  type. A list cannot be refined (`E2016`).
- A `for` does not count as a path that always returns: if it is the last statement of a function
  that returns a value, a `return` is needed after it.
- There is no `for` over ranges or `Text`, and no user generics.

## Unpublished — editor

An extension for Visual Studio Code, with its language server and its formatter, not yet
published on the Visual Studio Code marketplace. They do not change the language: they only give it an editor. The
extension is distributed separately, as a `.vsix`; the package published on PyPI and npm
does not change.

### Added

- **The VS Code extension** (`vscode-nexora/`): syntax highlighting for `.nex` files, with
  a grammar written over the real lexer, and automatic recognition of those files. It carries
  its icon (the same mark as the site) and what the marketplace asks for, so it can be published there.
- **The language server** (`nexora/src/nexora/lsp.py`): it speaks LSP over standard input and
  output and answers with the same analysis the command line uses. It offers diagnostics (those
  of `nex check`, with their code and their hint), completion, hover with the type of a value and the
  signature of a function, go to definition, references, rename, the symbols of the document, and
  signature help. It is run with `python -m nexora.lsp`, or the `nexora-lsp` command.
- **The language formatter** (`nexora/src/nexora/formatter.py`): rewrites a program in its
  canonical form, on the tokens of the lexer, so it does not change what it means. The editor uses it
  to format the document or a selection, and optionally on save.
- **The tests** (`tests/test_lsp.py`, `tests/test_formatter.py`, `tests/test_vscode_extension.py`):
  that the diagnostics of the server are those of the command line, that the formatter does not change the
  meaning of a program, and that the manifest and the grammar of the extension follow the lexer.

### Documentation

- New [ADR 0017](docs/decisions/0017-un-editor-la-extension-de-vs-code.md), which explains the
  decision and why the server and the formatter belong to the language itself.

## Unpublished — server and web

Changes to the web server (`servidor/`) and the website (`web/`) after the `v0.6.0` tag, still without a
version. They are not part of 0.9.0 or 0.10.0, nor of their packages: the language is documented
above, and the server and the website are deployed separately.

### Added

- **Anti-spam for sign-up and sign-in** (`servidor/src/captcha.js`): Google reCAPTCHA v3,
  a honeypot field and a strict per-client limit (5 sign-ups or 15 sign-ins per hour) for
  every request without a token that Google confirms. reCAPTCHA is only loaded in the browser if the
  person accepts it in the cookie panel; without it you can still get in, with that limit. The secret
  key goes in `RECAPTCHA_SECRET_KEY` and the site key in `web/js/consent-config.js`; at startup, the
  server warns if only one of the two is set.
- **Sign-in throttling per account** (`servidor/src/login-throttle.js`): after 5 failures from
  a client, that client waits longer each time, up to 15 minutes; after 20 failures against an account
  from any client, every attempt waits, at most one minute. It answers the same for an email
  with an account and one without, and it reserves each attempt before querying the database.
- **Per-client limits with IPv6** (`servidor/src/rate-limits.js`): all the limits count an IPv6
  address by its /56 block, and also each /48 network with four times the quota. The
  `RateLimit-*` headers describe the count that runs out first, and every rejection carries `Retry-After`.
- **Deletion of expired sessions** at startup and every hour, in batches, without two passes
  overlapping (`servidor/src/session-cleanup.js`).
- **Security headers on every response** (`servidor/src/security-headers.js`): the
  content security policy (CSP) without inline code that the playground and the guide had moves to every
  page, plus `X-Frame-Options`, `Cross-Origin-Opener-Policy`, `Permissions-Policy`,
  `Referrer-Policy` and, in production and only over HTTPS, HSTS. The API has a policy that loads
  nothing.
- `LISTEN_HOST`: the address the server listens on. With nginx on the same machine,
  `LISTEN_HOST=127.0.0.1` and `TRUST_PROXY=loopback`; at startup, the server warns if they do not match.
- Website: the fonts are served from the site itself (JetBrains Mono, with its OFL licence) instead
  of Google Fonts, and the whole site uses JetBrains Mono; a cookie consent manager with
  Google Consent Mode v2; the legal pages, still a draft (see Limitations); and broader web
  documentation: what NEXORA is, how it is tested and the recent changes.
- `GET /api/playground/status` says whether the playground is enabled (`{"enabled": true}` or `false`).
  It also answers with the playground disabled and does not start the worker. The page asks it
  first: when disabled, it does not request `/info` nor `/examples`.
- The legal pages carry `<meta name="robots" content="noindex, nofollow">` while they are a
  draft, and a test requires it. It only asks search engines not to index them: it does not prevent
  anyone with the link from opening them.
- `GET /api/health`: says whether the process is running and answering requests
  (`{"status":"ok","checks":{"http":"ok"}}`), and nothing else: it does not check MySQL, Google, GitHub,
  reCAPTCHA nor the playground, nor does it reveal the version or the configuration. During shutdown it answers 503.
- **Graceful shutdown** (`servidor/src/lifecycle.js`): on `SIGTERM` or `SIGINT`, the server stops
  accepting connections and answers with `Connection: close`, so that a persistent connection does not
  hold it back; it waits up to 10 s for the requests in progress and for the batch of session deletion that is
  in MySQL (it sends no more); it closes the MySQL pool (another 10 s at most) and exits with 0, or
  with 1 if it had to cut something. If the other signal arrives during the shutdown,
  it is not repeated; if the same one arrives again, Node ends the process on the spot, without waiting.
  The limit of each wait keeps the process alive until it expires: if the only thing pending has
  no resource behind it (a pool close that does not finish), the process no longer exits with 0 ahead of
  time without logging it, but waits for the limit, logs it and exits with 1. Tested with automated
  tests on Windows (Node 20.6.1, 22.23.3 and 24.21.0), without real signals: with systemd, not
  tested.
- **Integration tests with MySQL, prepared and never run** (`servidor/test/integration/`).
  `npm run test:integration` would run the real queries of the application against an isolated test
  database (`nexora_test`), with one account for the migrations and another for the application, which an
  administrator would have to create by hand with `setup-admin.sql` (a proposal pending review).
  They are not part of `npm test` nor of continuous integration. Before loading anything, some guards
  reject any other environment (`DB_*` variables, another server, a playground that can be enabled, or grants
  different from the expected ones), and a named lock (`GET_LOCK`) prevents two runs at once.
  The guards only accept Node 22 from 22.22.3 and Node 24 from 24.14.0 (`HOOK_MINIMUMS` in
  `servidor/test/integration/guard.js`): these are the minimums measured on Windows for the module hook of
  `preflight.js`, not those of `engines` in `servidor/package.json` (`^22.23.2 || ^24.18.1`), and a test
  of `npm test` checks that everything `engines` accepts is inside. The other branches (23, 25, 26 and
  later) and versions that are not exactly X.Y.Z are rejected until they are measured. In the
  measured versions below those minimums, the hook blocked mysql2 also in the legitimate order;
  the cause is not confirmed. On a Node the guards do not accept, `npm test` skips, with their reason, the 14 tests that launch
  `preflight.js`: that is what happened in the experimental Node 26 run of continuous integration
  on 21 October 2026. **None of this has been run against a real
  MySQL**: neither the administration SQL, nor the migrations with reduced grants, nor the lock.

### Incompatible changes

- **The server requires Node.js 22.23.2 or later on the 22 branch, or 24.18.1 or later on the 24
  branch** (`engines` in `servidor/package.json`: `^22.23.2 || ^24.18.1`; before, 20.6 or later). Node 20
  has had no support since 30 April 2026, and the minimums are the latest security releases
  of each branch in October 2026. Branches 23, 25 and 26 are left out. npm only warns (`EBADENGINE`)
  with another version, it does not prevent installing. Within the range, 22.23.3 and 24.21.0 have been tested locally, on Windows;
  the exact minimums have not. The continuous integration of the server now tests 22.23.2,
  24.18.1, the latest of branches 22 and 24 and, without blocking, Node 26; it ran for the first time on
  21 October 2026.
- **With `NODE_ENV=production`, `PLAYGROUND_ENABLED=true` requires the container command** in
  `PLAYGROUND_WORKER_COMMAND`. Without it (or with a process command), the server does not start: process
  mode runs the visitors' code with the permissions of the server. Outside production,
  process mode is still available for testing on your own machine. Configuring the container
  command does not prove that the isolation works: it is still unchecked with real Docker.

- **`NODE_ENV` only accepts `development`, `test` or `production`, in lower case.** Before, any
  value other than `production` (`Production`, `prod`, empty) left the server in development, without
  HTTPS-only cookies. Now those values prevent starting. Undefined still works as
  development, and the server warns about it at startup.
- **`TRUST_PROXY` only accepts `0`, `loopback` or an integer from 1 to 10 without leading zeros.**
  Before, it was read with `Number()`: `true` or `nginx` gave `NaN` without any warning. Now any other
  value prevents starting. With nginx on the same machine, `loopback` is recommended instead of `1`.
- `LISTEN_HOST` only accepts an IP address or being empty; a name, `localhost` included, prevents
  starting.
- With `NODE_ENV=production` and `RECAPTCHA_SECRET_KEY`, a missing `RECAPTCHA_HOSTNAMES` prevents starting.
  So does a `RECAPTCHA_MIN_SCORE` outside 0 to 1, or a `RECAPTCHA_HOSTNAMES` that is not a list of domains.
- **In production without `RECAPTCHA_SECRET_KEY`, every sign-up and sign-in goes through the
  strict limit** (5 sign-ups or 15 sign-ins per client and hour). In development nothing
  changes.
- The accounts API has new responses: `429` with `code: "login_throttled"` and `Retry-After`
  during sign-in throttling; `400` with `captcha_invalid` or `captcha_expired`; and `429`
  with `captcha_required` on the strict limit. A `website` field with content is rejected with `400`.

- **The playground is disabled unless it is enabled explicitly.** Before, it was enabled
  whenever `PLAYGROUND_ENABLED` was not exactly `false`: undefined, empty or with a typo
  (`False`, `0`), it was left open. Now only `PLAYGROUND_ENABLED=true` enables it; undefined,
  empty or `false`, the API answers 503 (`playground_disabled`) and no worker starts. A
  local installation that wants to use the playground has to add `PLAYGROUND_ENABLED=true` to its
  `servidor/.env`.
- Any other value of `PLAYGROUND_ENABLED` (`True`, `1`, `yes`…) prevents the server from starting,
  with a message that asks for `"true"` or `"false"`.
- **The only container command `PLAYGROUND_WORKER_COMMAND` accepts is the documented one.** It has
  to start with `"docker","run"`, carry exactly once each isolation and limit option
  of `servidor/.env.example` with its exact value, among them `"--init"`,
  `"--pull","never"` and `"--name","{container}"`, and end with the image. Any other container
  command prevents the server from starting, even if the playground is disabled, with a message that
  names what fails. That includes an option that is missing, repeated, has another value or is not in the
  list, such as the aliases `-m`, `-u`, `--net` or `--interactive`; the `--option=value` form; anything
  after the image; a path to the executable, `docker.exe`, `sudo`, Podman,
  `docker container run` or global Docker options. What goes after the image is not applied by
  Docker, but received by the program of the container. With the previous check, a
  `"--name","{container}"` written after the image was accepted (checked with the previous
  validator) and, according to the code, the server could take as removed a container that was still alive;
  it has not been observed with real Docker. To update an existing configuration, copy the command
  from `servidor/.env.example`. Changing a limit requires changing the server
  (`servidor/src/playground/config.js`), not just `servidor/.env`.
- **Only the local image `nexora-worker` is run, and Docker never downloads it.** The image
  has to be `nexora-worker` or `nexora-worker:<tag>`: no other name, path,
  registry nor digest is accepted. `"--pull","never"` makes the run fail, if the image is not on the machine,
  instead of downloading it. The image has to be built on the server before
  enabling the playground and on every update (see the
  [playground guide](docs/playground.md#3-worker-image)). `--pull` needs Docker 20.10 or
  later.
- The process mode commands are still not checked, except those that contain `{container}` or
  an executable called `docker` or `podman`: those are treated as container commands and are
  rejected if they are not the documented one.

### Fixed

- **A container that times out no longer keeps running with its slot released.** Before, the
  server killed the `docker run` client, which does not stop the container, and released the slot at that
  moment. According to the code, that allowed more live containers than
  `PLAYGROUND_MAX_CONCURRENT`; it has not been observed with real Docker, because container mode
  has not been tested yet. Now each
  container has a name generated by the server; if it does not end well, it is removed by that
  name and the slot is only released when it is confirmed that it no longer exists. The attempts to remove it
  are limited; if none confirms, the slot stays occupied.
- **The Run button of the playground is visible again on mobile.** At 390 px it was cut off and at 320 and 360 px
  it could not be seen; only the Ctrl+Enter shortcut was left. Below 440 px the four buttons now go in
  two rows.
- **With the playground disabled, the page no longer looks ready to run.** Before, it showed
  «Real interpreter» with a green dot and Run and Check enabled, and every load got two 503
  responses. Now it says «Disabled», Run and Check are disabled (their shortcuts too), the help and the footer
  do not say that the code runs, and it sends no run request. While it waits for the
  server's answer it says «Connecting…». If the server does not confirm whether it is enabled (it does not
  answer or answers something the page does not understand), it says «Status unknown» and does not let you run either:
  Run and Check are only enabled when the server confirms it. «Real interpreter» in green only
  appears if the interpreter answered as well; otherwise, «Unavailable». When enabled, it behaves as before.
- The sign-up form fits entirely, button included, on a 1366×768 screen. Sign-in
  already fitted and does not change.
- **Sign-up is atomic.** Before, the account was created and then, separately, its first session: if the
  session could not be saved, the account was left created, the person got an error and, when trying
  again, a 409. Now the account and the session are saved in a single transaction, the cookie is only
  sent after confirming it, and the password hash is computed before opening it, so as not to
  hold a pool connection during scrypt. If the `ROLLBACK` also fails, the original error is the one that counts
  (a duplicate email still answers 409) and that connection does not go back to the pool, because it could
  have been left with the transaction open: it is destroyed. The `ROLLBACK` failure is logged
  with its type and its code (`auth: sign-up rollback failed (Error ER_ERROR_DURING_ROLLBACK)`), without the
  message nor any data of the request. Tested with a simulated database; against real MySQL, the
  test is prepared and not run.
- Sign-in with Google or GitHub follows the same rule in its transaction: if the
  `ROLLBACK` fails, the original error is the one that counts (for example, `account_exists` is still `account_exists`), the
  connection is destroyed instead of going back to the pool (only once, never returned and destroyed) and a
  line `oauth: <provider>: rollback failed (…)` without data is left. Before, a failed `ROLLBACK` replaced the
  original error and the connection went back to the pool. Tested with a simulated database.
- **The server log no longer copies whole errors.** An internal error of the application or
  of sign-in with Google or GitHub wrote the complete object, which in a MySQL error
  includes the query and the message of the server (with the email, for example). Now only the
  type and a known code are written (`Error ER_DUP_ENTRY`, `ProviderError token_http_500`), never the message,
  the stack, the query, the token, the authorization code nor the secret. The route is written by its
  template (`/api/auth/:provider/callback`), never by the requested path nor its query string; without
  a matching route, `(no route)`. The deletion of expired sessions follows the same rule: before, it
  wrote the message of the error when it had no code.
- Google: an account is only created or linked if `email_verified` is exactly `true`; before,
  any value JavaScript takes as true was enough. A profile without an identifier, or a list
  of GitHub emails that is not a list, are now a provider failure with their own code.
- A password hash stored with extra fields (`…$extra`) is no longer accepted as valid: the
  format has to be exactly that of `hashPassword`.

### Documentation

- `servidor/.env.example` leaves the playground at `false`, and the [playground guide](docs/playground.md)
  keeps it disabled on a public server until the
  [isolation check](docs/playground.md#checking-the-isolation) is complete. The checks
  that need the playground enabled are done in a controlled environment, without public exposure.
- Linux checked ([Tests](docs/testing.md#linux)): on Ubuntu 24.04 under WSL 2 the
  automated tests of `nexora/` pass with Python 3.11, 3.12 and 3.13 (also the four POSIX ones, which
  had never been run) and those of `npm/` and `servidor/`, and the pip and npm packages install
  and work. No code had to change. Docker and the isolation of the playground are still
  unchecked.
- Deployment ([playground guide](docs/playground.md#deploying-on-your-own-server)): nginx with
  redirection from HTTP to HTTPS, `limit_req`, `server_tokens off` and the `http2 on` syntax of
  current versions; `TimeoutStopSec` in systemd; the health route; and MySQL backups and
  restore. **None of it has been tested** with real nginx, systemd or MySQL: the guide
  says so in each section.

### Limitations

- Container isolation is still **unchecked**: this change prevents enabling the playground by
  mistake, but it does not make it safer once enabled.
- None of this has been tested with real Docker. The tests of the command only analyse the list of
  arguments, without running any Docker; those of the life cycle (removing containers, occupied
  slot, missing image) use a fake Docker. If the server crashes, nobody removes the
  containers it had running.
- What a container command is is decided only by the documented names. A wrapper
  script, another tool (`nerdctl`…) or a Docker executable with another name are outside
  the detection: they are not a supported way of running containers, and the server would not validate
  their command nor remove their containers.
- Validating the command does not guarantee the effective configuration of the Docker daemon nor of its runtimes.
- The local tag (`nexora-worker` or `nexora-worker:<tag>`) is mutable: whoever has access
  to the Docker daemon can re-tag another image with that name, and the server would
  run it without noticing. That the Nexora image is the one that runs depends on the access control to the
  machine and to the Docker daemon.
- Docker in *rootless* mode is not supported: the command does not allow `-H` nor `--context`, and the
  server only passes `PATH` and `SystemRoot` to the commands it launches.
- The anti-spam, the sign-in throttling, the session deletion and the headers have been tested
  with the database, Google reCAPTCHA and the browser simulated: not against a real MySQL, with real
  reCAPTCHA keys, in a browser nor behind nginx. The automated tests of the server,
  with those same simulated services, give 811 passed and 0 failures with Node 24.21.0 (one run,
  on Windows 11, with the guards of the integration tests limited to the measured branches). Before
  that change they gave 810 passed and 0 failures with Node 24.21.0 (in each of
  three runs), 24.14.0, 22.23.3 and 22.22.3, and 796 passed, 14 skipped (those that need Node
  22.22.3 or later on the 22 branch, or 24.14.0 or later) and 0 failures with Node 20.6.1 and 22.15.0 (one
  run with each of those versions), on Windows 11. With the minimums of `engines` (22.23.2 and
  24.18.1) they have not been run. On Ubuntu 24.04 under WSL 2 they were run before the latest fixes of the website
  (567 passed, 0 failures, in each of three runs) ([Tests](docs/testing.md)).
- The counters of the limits and of the sign-in throttling are in memory: they are lost on
  restart and are not shared between several instances of the server.
- In sign-in with Google or GitHub, the session is created outside the transaction of the account and
  its link: if it fails, the account is left linked without a session until the next attempt. During
  shutdown, a second `SIGTERM` or `SIGINT` ends the process without completing the cleanup, and the 503 of
  `/api/health` only arrives over connections already open. The automated tests, on Windows and with the
  simulated database, cover the failure of the OAuth session and the retry, the 503 during
  shutdown and the rejection of new connections. They do not cover the second signal of the same type nor two
  simultaneous first sign-ins with the same identity, which are still untested. Still pending are
  tests against a real MySQL, with real operating system signals, with systemd and behind
  nginx ([Pending tasks and risks](docs/playground.md#pending-tasks-and-risks)).
- The legal pages are a draft without the details of the owner nor legal review: they must not be
  published like this. Risks and pending decisions (Analytics and its CSP, the `409` that reveals whether an email
  has an account, the cancellation of MySQL queries):
  [Pending tasks and risks](docs/playground.md#pending-tasks-and-risks).

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
