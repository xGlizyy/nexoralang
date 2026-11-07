# Migrating from NEXORA 0.x to 1.0

For someone who has programs, scripts or tools written for a version before 1.0. It says what to do to be on 1.0, in the
order to do it, and what each earlier version changed. The rules for changes after 1.0 are in the
[compatibility policy](compatibility.md); every incompatible change that was ever made is in
[`CHANGELOG.md`](../CHANGELOG.md) under **Incompatible changes**, and this page is built from it.

## In short

The language of 1.0 is the language of [specification 1.0](language-spec.md), which is the grammar and the semantics that the
reference implementation 0.15 already has (the syntax of 0.12, plus modules, enumerations with exhaustive `match`, and the `?`
operator). **Nothing in a program that compiles today with 0.12 or later has to change to run on 1.0.** What you have to do depends
on where you start:

| You have | You do |
|----------|--------|
| A program that passes `nex check` with 0.12 to 0.15 | Nothing. Install 1.0 and check again (step 4) |
| A program written for 0.11 (it uses `requires`, `ensures`, `invariant`, `decreases` or `->`) | Run `nex migrate` (step 2) |
| A program written for 0.10 or earlier | Update it to 0.11 by the table below, then `nex migrate` |
| A script or a tool that reads the output of `nex` | Read the schema identifier and move to the current one (step 3) |
| A tool that uses `nexora.tooling` or the language server or MCP protocols | They are experimental ([interface stability](interface-stability.md)): read the release notes of every version |

## Step by step

### 1. Know where you start

`nex --version` of the installation that the program was written for, or the first lines of its `CHANGELOG`. The tables below list
every incompatible change by version; you only need the rows after the version you start from.

### 2. Move the program to the syntax of 1.0

For a program of 0.11 (or a 0.10 program already updated to 0.11):

```bash
nex migrate program.nex            # shows the edits and the migrated text, and writes nothing
nex migrate program.nex --write    # replaces the files, only if every check passed
```

It works on the whole program: the file and every module that it imports.

`nex migrate` rewrites `requires`, `ensures`, `invariant` and `decreases` as `needs`, `promises`, `keeps` and `shrinks`, moves the
clauses from the body to the header, writes `gives` instead of `->` (and drops `-> Void`), and renames `Option.unwrap`, `Option.unwrap_or`,
`Result.unwrap` and `Result.unwrap_or` as `value` and `value_or`. It does not guess: a program that used one of the new
keywords (`needs`, `gives`, `promises`, `keeps`, `shrinks`, `trust`) as a name is refused, with its file, line and column, and
nothing is written. See the [CLI reference](cli-reference.md#nex-migrate).

Before and after, for one function:

```nex
// 0.11
fn withdraw(balance: Int, amount: Int) -> Int {
    requires amount > 0, "An amount is positive"
    ensures result >= 0
    return balance - amount
}

// 1.0
fn withdraw(balance: Int, amount: Int) gives Int
    needs amount > 0, "An amount is positive"
    promises result >= 0
{
    return balance - amount
}
```

### 3. Move what reads the output of `nex`

Every JSON document says its schema in `schema`; select behaviour by that field ([JSON protocol](json-protocol.md)). The
identifiers of 1.0 are `nexora.diagnostics/1`, `nexora.inspect/3`, `nexora.symbols/2`, `nexora.context/2`, `nexora.spec/2`,
`nexora.capabilities/1`, `nexora.evidence/1`, `nexora.result/1` and `nexora.test/1`. Each of them keeps its meaning for all of 1.x:
a change that breaks one gets a new identifier. The ones that moved on the way:

| From | To | What changed |
|------|----|--------------|
| `nexora.inspect/2` | `nexora.inspect/3` | `Function.header`, one ordered list of `Contract` and `Example`, replaces `contracts` and `examples`; `return_type` is `null` without `gives`; `Contract.clause` is `needs`, `promises` or `trust`; `LoopClause.clause` is `keeps` or `shrinks`; both have a `name` |
| `nexora.context/1` | `nexora.context/2` | The clauses take the new names; contracts and loop clauses have a `name` |
| `nexora.symbols/1` | `nexora.symbols/2` | The clauses take the new names |
| `nexora.spec/1` | `nexora.spec/2` | `language` is `"en"` and the section ids come from the English headings (`7-functions`, not `7-funciones`): read the ids again from the index |

The exit codes of `nex` are the ones in the [interface stability](interface-stability.md) policy (0, 1, 2, 3, 4, 5, 6, 70 and 130)
and are pinned by tests. If a script was written before 0.4.0 it may expect `70` for a program that runs out of memory: it is `3`
since 0.4.0, with the diagnostic `E3007`.

### 4. Check that the program is the same program

```bash
nex check program.nex                  # the static analysis: it has to pass
nex test program.nex                   # the examples of its functions: they have to pass
nex run program.nex -- ARGUMENTS       # and run it on an input whose output you know
```

For a program migrated with `nex migrate`, compare the output of the old and the new on the same inputs: the project does
that with a corpus of 0.11 programs ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md), the equivalence tests T1 to
T4), and the migration is deterministic, but a program of yours is the evidence that matters. Fix what `nex check` reports with its
diagnostic code: the [diagnostics reference](diagnostics.md) says what each code means and what to do.

### 5. Installation

The package is `nexora-lang` on PyPI and npm; the command is `nex`. The native tools are files of the `native-v*` releases, each
with a `.sha256` ([installation](installation.md), [release process](release-process.md)). Before 0.3.0 the package was called
`nexora`, a name that is not the project's: `python -m pip uninstall nexora` and `python -m pip install nexora-lang`. 1.0 needs
Python 3.11 or later for the reference interpreter; the native tools need no Python.

## What every version changed

Only the changes that can stop an existing program or script. Versions that are not listed made no incompatible change.

| Version | Change | What to do |
|---------|--------|------------|
| **0.12.0** | The syntax of 0.11 is rejected: `requires`, `ensures`, `invariant`, `decreases` are `E1107`, and `->` before the result type is `E1108`. Those four words are reserved and cannot be names | `nex migrate program.nex --write` |
| 0.12.0 | `needs`, `gives`, `promises`, `keeps`, `shrinks` and `trust` are keywords: a program that used one as a name is `E1101` | Rename the name; `nex migrate` refuses and says which |
| 0.12.0 | `Option.unwrap`, `Option.unwrap_or`, `Result.unwrap`, `Result.unwrap_or` are `value` and `value_or`; the old names are `E2008` | `nex migrate` renames the calls |
| 0.12.0 | `ai` and `tool` are no longer reserved | Nothing: they are ordinary names |
| 0.12.0 | `nex inspect`, `nex context`, `nex symbols` and `get_language_spec` move to `nexora.inspect/3`, `nexora.context/2`, `nexora.symbols/2` and `nexora.spec/2` | Step 3 |
| **0.11.0** | `import` and `pub` are keywords (before, reserved words: a program that used them as names already did not compile) | Nothing |
| **0.10.0** | `Option`, `Result`, `Some`, `Ok` and `Err` belong to the language: a function that has one of those names makes calls use the built-in one. (With `None` it is the other way round: a name that the program declares wins) | Rename a function that has one of those names |
| **0.5.0** | `invariant` and `decreases` are keywords (a program that used them as names is `E1101`; in 0.12 they were renamed again, see above) | Rename the name |
| **0.4.0** | `example` is a keyword. A program that ran out of memory exits with `3`, not `70` (`E3007`, not `internal error`) | Update the scripts that expect `70` |
| **0.3.0** | `type` and `where` are keywords. `nex inspect` is `nexora.inspect/2` (a refined type can be the `type` of an expression; `TypeDecl`, `types` and `message` added). With syntax errors, `program` of `nex inspect` is a partial tree, not `null`. The package is called `nexora-lang` | To know whether a program is valid read `ok`, not `program`; reinstall by step 5 |
| **0.2.0** | The text type is `Text` (before, `String`: in 0.1 types could not be written). The header of text diagnostics includes the category. `to_text`, `to_float` and `to_int` cannot be names. An unknown return type is `E2012`. Python 3.11 or later | Rename; read the category from `category` in JSON, not from the text |

## What 1.0 itself changes

Nothing that was valid and checked in 0.12 or later. What 1.0 does is **freeze** what is already there
([decision 0029](decisions/0029-congelacion-de-la-especificacion-1-0.md)): from 1.0 the syntax and the semantics of the
specification, the stable CLI, the diagnostic codes with their categories and the JSON schemas change only by the rules of the
[compatibility policy](compatibility.md) (backward-compatible additions in a minor release, removals only in a major release
after a deprecation). A program that is correct on 1.0 keeps being correct on every 1.x.

What 1.0 does **not** include is listed in [the limitations](limitations.md#what-10-does-not-include) and
[decision 0029](decisions/0029-congelacion-de-la-especificacion-1-0.md): a program cannot choose its exit status, `input()` cannot
test for the end of the input, `write_file` does not create folders, `Ok(...)` and `Err(...)` cannot be written in an `example`,
and list literals and expressions fit on one line. Each of those is an addition for a later 1.x, so none of them can break what
you write today.
