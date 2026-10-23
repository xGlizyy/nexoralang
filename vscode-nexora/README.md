# NEXORA for Visual Studio Code

![The icon of the extension](images/icon.png)

Extension for the NEXORA programming language: highlighting, diagnostics, navigation and
formatter.

It does not reimplement the language. All the answers come from the same analyzer that the
command line uses (`nex check`), so what the editor says about a program is exactly
what `nex check` says, with the same codes and the same texts.

## What it gives

| | |
|---|---|
| Highlighting | TextMate grammar written over the real lexer: keywords, types, built-in functions, operators, texts, numbers and comments |
| Diagnostics | Lexical, syntax and semantic errors, in the *Problems* panel, with the code (`E2011`), the position and the suggestion |
| Completion | Keywords, built-in functions, the names that are in scope and the reserved words |
| Hover | The type of a value and the signature of a function |
| Go to definition, references and rename | On functions, parameters and variables |
| Document symbols | Functions and variables, with their type |
| Signature help | The parameters of the function being called |
| Formatter | Whole document or selection, with the canonical shape of the language |

## What it needs

- **Python 3.11 or newer** with the `nexora` package installed: the language server is a
  Python process.

  ```bash
  cd nexora
  python -m pip install -e .
  ```

- **Node.js 18 or newer** only to build the extension (the `.vsix` comes already built).

## Install

1. Build and package:

   ```bash
   cd vscode-nexora
   npm install
   npm run compile
   npm run package        # leaves nexora-0.10.0.vsix
   ```

2. Install it:

   ```bash
   code --install-extension vscode-nexora/nexora-0.10.0.vsix
   ```

   That path is **relative**: the command has to be run from the root of the repository, which
   is where the `vscode-nexora/` folder is. If the package is somewhere else, with the full
   path:

   ```bash
   code --install-extension C:\full\path\nexora-0.10.0.vsix
   ```

   Or from the editor: *Extensions* → *⋯* → *Install from VSIX…*, and choose the file.

   And once the extension is published on the marketplace, the short form, which works from
   anywhere, is:

   ```bash
   code --install-extension nexoralang.nexora
   ```

## Configure

| Setting | What it does | Default |
|---|---|---|
| `nexora.python.path` | The Python that starts the server. Empty = the `python` on the PATH. | `""` |
| `nexora.trace.server` | How much the server writes to the output panel: `off`, `messages`, `verbose`. | `off` |
| `nexora.format.enable` | Format documents with the formatter of the language. | `true` |
| `nexora.format.onSave` | Format every time the file is saved. | `false` |

If the Python on the PATH does not have the package installed, the extension looks for the environment of the
repository itself (`nexora/.venv`), which is the usual case when developing inside the project.

## Publishing on the Visual Studio Code marketplace

The extension is ready for the marketplace: it has the icon (128×128), the licence, the
banner, the description, the categories, the keywords and the link to report a
problem.

```bash
cd vscode-nexora
npm run compile
npm run package          # checks that the package is fine
npm run publish:marketplace -- --pat <THE_TOKEN>
```

Two things are needed that only whoever publishes can do:

1. **Owning the publisher** `nexoralang` on the marketplace (or changing `"publisher"` in
   `package.json` to the one you already have). With the publisher `nexoralang` and the name `nexora`, the
   extension is `nexoralang.nexora` on the marketplace.
2. **An access token** for the marketplace: it is created at <https://marketplace.visualstudio.com/manage/publishers>,
   with the scope *Manage extensions*. It is passed with `--pat` so that it does not stay in the
   shell history; `vsce publish` asks for it interactively if it is not given.

The first publication has to be done by the publisher account, which has to be verified
through a Microsoft account. None of this can be done by the repository: it is a
decision of whoever publishes.

Before publishing, a quick check that the package works (from the root of the
repository):

```bash
code --install-extension vscode-nexora/nexora-0.10.0.vsix
```

## Commands

- **NEXORA: Check the current file** — runs `nex check` on the open file and writes the
  result to an output panel.
- **NEXORA: Restart the language server** — restarts it.

## Develop

```bash
cd vscode-nexora
npm install
npm run compile      # compiles TypeScript into out/
npm run watch        # recompiles on save
```

To debug the language server:

```bash
cd nexora
python -m nexora.lsp
```

speaks the protocol over the standard input and output, so it can be tried without the editor.

## Tests

The server, the formatter and the extension are tested from the suite of the language itself:

```bash
cd nexora
python -m pytest tests/test_lsp.py tests/test_formatter.py tests/test_vscode_extension.py
```

There it is checked that the diagnostics of the server are those of `nex check`, that the formatter
does not change what a program means and that the manifest and the grammar of the extension
follow the lexer.

## Limitations

- The analyzer does not yet resolve the members of a record by type (`x.field` is checked
  against the type that `x` has, not against that of every possible record), so navigation and
  renaming do not reach the fields of a record.
- There are no type variables in the language: `Option[T]` and `Result[T, E]` are the only types with
  arguments, and the error type of an `Ok` is given by the context.
- There is no `match`: the variants are recognized with functions.
- The formatter does not rewrite the inside of a text, does not touch comments and does not join or split
  lines: only indentation and spacing.
