# Self-hosted NEXORA

The NEXORA implementation written in NEXORA, following
[decision 0024](../nexora/docs/decisions/0024-interprete-autoalojado.md). The Python interpreter
runs it for now; it is the bootstrap, not the goal.

| Part | File | State |
|------|------|-------|
| Lexer | [`lexer.nex`](lexer.nex) | Done. Same tokens and lexical errors as `lexer.py` on every program of the repository and on the cases in [`lexer_cases/`](lexer_cases/), with the gaps below |
| Parser | [`parser.nex`](parser.nex) | Done. Same tree and same syntax errors as `parser.py` on every program of the repository and on the cases in [`parser_cases/`](parser_cases/), including error recovery, the limit of 100 errors and the nesting and depth limits |
| Checker | | Not started |
| Interpreter | | Not started |

## Checking a part against the Python implementation

```bash
PYTHONPATH=nexora/src python selfhost/compare_lexer.py FILE.nex [FILE.nex ...]
```

Both lexers run on the same text, and tokens (kind, lexeme, span, decoded text literals) and
lexical errors (code, message, hint, span) are compared. A difference is a bug in the self-hosted
code unless it is listed under "Language gaps".

For the parser:

```bash
PYTHONPATH=nexora/src python selfhost/compare_parser.py selfhost/parser_cases/*.txt
```

Each line of a cases file is an expression; both parsers read it and the tree (as JSON) or the first
syntax error is compared. For whole programs, including the syntax errors a program can have:

```bash
PYTHONPATH=nexora/src python selfhost/compare_programs.py FILE.nex [FILE.nex ...]
```

`parser_cases/programs/` holds malformed programs that exercise recovery, headers, declarations, the
old 0.11 syntax and the size limits. A file with lexical errors is skipped: the lexer is checked on
its own.

## Stage 1 measurement: call depth

[`measure/depth.nex`](measure/depth.nex) builds and evaluates a nested expression with a recursive
`enum`, one NEXORA call per tree level.

| Nesting | Result |
|---------|--------|
| 499 | Works (about 0.3 s) |
| 500 | `E3004`, too many nested calls |

Each level costs two calls (`build` and `eval_expr`), so the limit of 1,000 calls is reached at
exactly 500. Plain recursion is cheap; the limit is the only obstacle.

What this means for the plan:

- **Parser and checker.** The language already bounds source nesting: the Python parser refuses
  more than 64 levels of parentheses, unary operators and blocks (`MAX_NESTING`) and expression
  trees deeper than 256 (`MAX_EXPRESSION_DEPTH`). Bounded recursion is therefore feasible for them,
  at a few calls per level, if the self-hosted parser enforces the same limits. The deepest tree in
  the repository's `.nex` files is 11 nodes.
- **Interpreter.** This is the real problem. An interpreted program may nest 1,000 calls, and each
  one costs several calls of a recursive evaluator, so a recursive evaluator tops out around 200 to
  250 interpreted calls. The evaluator has to keep its own stack of frames in a list, so that the
  depth of the interpreted program does not use the depth of the interpreter.

The stop condition of decision 0024, stage 1 is therefore **not** triggered: the bounded-recursion
option works.

## Language gaps found so far

Each one is a real limitation hit while writing the lexer. The decision 0024 rule applies: nothing
is added to the language except what the self-hosted code needs.

| Gap | Effect | Workaround used |
|-----|--------|-----------------|
| No `\r` escape and no character-from-code-point function | A carriage return cannot be written or recognised, so a CRLF file is not lexed like the Python lexer does | None. CRLF files differ |
| No code point of a character, no letter test | E1001 shows non-printable characters quoted instead of `U+XXXX`, and misses the "Names use the letters a-z" hint for non-ASCII letters | None. Only such characters differ |
| A line break continues an expression only inside `( )`, not inside `[ ]` | Long list literals do not fit on several lines | Wrap the list in parentheses |
| A field can only be read from a name, not from a call result | `List.get(tokens, i).kind` is rejected | Bind the call to a `let` first |
| `uses read` needs a literal path | Reading a file named by an argument needs `uses read "."` and `--allow-read .` | Declare the working directory |

Found while writing the parser, and fixed in the checker (not a language change): a record of an
imported module whose field type was another type of the same module was rejected with `E2012`
(`'Token' is not a type`), because the field types of every module's records were resolved with the
prefix of the module being checked. They are now resolved relative to the module that declares the
record (`tests/test_modules.py`). A genuine error inside an imported record is still reported
under the importing file's name, with the position of the imported one.

Differences the parser still has with `parser.py`, both from missing text functions: the explanation
of a clause counts as empty only if it is made of spaces, tabs and line breaks (Python's `strip()`
knows every Unicode space), and the lowercase check of a clause name is ASCII only, which is all a
name can be.

None of these blocks the lexer. The first two are the first candidates for stage 1 of the plan,
together with maps and `%`, which the lexer did not need.
