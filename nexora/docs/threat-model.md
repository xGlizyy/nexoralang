# Threat model of the local CLI

What the local `nex` command (`run`, `check`, `inspect`, `test`, and the tools built on the same analyzer) is meant to
withstand, what it is not, and which test backs each claim. It is the document that the capability security gate of
[decision 0021](decisions/0021-alcance-nexora-1-0.md) asks for. It describes the **local CLI only**: the hosted
Playground has its own service and its own gate. [SECURITY.md](../../SECURITY.md) is the policy for reporting and for
supported releases; this page is the reasoning behind its list of what is in scope.

Written on 2026-11-07 from the code and the tests of the repository. Nobody but its author has reviewed it: the gate
stays *partial* until the maintainer's review is recorded at the end of this page.

## What is protected

**Assets**: the files of the user running `nex`, the network the machine can reach, the other programs the user can
start, and the memory and the time of the machine.

**Who is trusted**: the person who types the `nex` command and chooses its options. They are the only one who can
grant a capability.

**Who is not trusted**: the author of the `.nex` program, and of any module it imports. Running a program somebody
else wrote is the case the design is for. Its source text, its text values and its input are all hostile data.

**Entry points** an attacker controls: the `.nex` source and the imported modules; the standard input and the
arguments given to the program; the files the program is allowed to read; the answer of an allowed network origin;
the output of an allowed process.

## The rule that carries the model

A program does nothing outside its own memory unless three things agree: the program **declares** it (`uses read`,
`uses write`, `uses network`, `uses process`), the user **grants** it on the command line (`--allow-read`,
`--allow-write`, `--allow-network`, `--allow-process`), and the host **enables** it. Remove one of the three and the
operation fails with a diagnostic. The declaration is what a reader or a tool sees before running; the grant is what
only the user can give.

## Threats, what stops them, and the evidence

| # | Threat | What stops it | Test |
|---|--------|---------------|------|
| T1 | A program reads or writes a file without permission | Declaration, grant and host are all required; reading does not give writing | `tests/test_permissions_files.py`: `test_declaring_is_not_granting`, `test_granting_is_not_declaring`, `test_reading_is_not_writing`, `test_writing_is_not_reading`, `test_without_a_host_no_file_is_ever_read` |
| T2 | A program leaves the granted folder with `..`, an absolute path, a similar prefix, a symbolic link or a junction | The path is resolved with `realpath` and compared with the declared and the granted scope, both | `test_a_dot_dot_that_leaves_the_scope_is_denied`, `test_a_path_that_starts_the_same_is_not_inside`, `test_an_absolute_path_outside_the_scope_is_denied`, `test_a_symbolic_link_that_leaves_the_scope_is_denied`, `test_a_directory_junction_that_leaves_the_scope_is_denied` |
| T3 | A program reaches a network origin it did not declare, or plain HTTP | Only HTTPS to an origin that is declared and granted; the URL is checked before a client is built | `tests/test_network_process.py`: `test_https_requires_both_a_matching_grant_and_an_allowed_environment`, `test_network_capability_only_allows_the_declared_origin`, `test_https_rejects_non_https_urls_before_opening_a_connection` |
| T4 | An allowed origin sends the program somewhere else, a proxy variable of the environment does, or a huge answer exhausts memory | Redirects are refused, proxies are ignored, the answer is limited to 1 MiB and 5 seconds | `tests/test_threat_model.py`: `test_the_network_client_ignores_the_proxy_variables_of_the_environment`, `test_the_network_client_refuses_to_follow_a_redirect`, `test_a_network_answer_over_one_mebibyte_is_an_error` |
| T5 | A program starts an executable it did not declare, or a shell | The command is declared and granted exactly, and started without a shell and without standard input | `test_process_requires_a_static_declaration`, `test_process_runs_only_when_declared_granted_and_allowed`, `test_process_fails_without_grant_or_environment_permission` |
| T6 | A process runs forever, fills memory, or leaves descendants behind | Five seconds, 1 MiB for each output stream; on POSIX the process group is cleaned up | `test_process_timeout_is_bounded`, `test_process_output_is_bounded`; `tests/test_cli.py`: `test_process_run_cleans_up_descendants_after_command_returns` |
| T7 | Text of the program is interpreted as code (Python, shell) | The interpreter walks its own syntax tree; no module calls `eval`, `exec` or `compile` | `tests/test_security.py`: `test_no_module_evaluates_python_code_or_opens_files_by_itself`, `test_text_is_data_and_is_never_interpreted`, `test_python_and_shell_constructs_are_rejected_before_anything_runs` |
| T8 | A command-line argument is taken as code | `nex` only takes paths; there is no option that carries source | `tests/test_cli.py`: `test_an_argument_is_never_treated_as_source_code`, `test_there_is_no_option_to_pass_code_on_the_command_line` |
| T9 | Analysing a program runs it | `check`, `inspect`, `context` and `symbols` end before the execution stage | `test_check_never_calls_the_interpreter`, `test_inspect_does_not_run_the_program`, `tests/test_security.py`: `test_static_commands_do_not_run_the_program` |
| T10 | The core of the language touches the system | Only `host.py` and the entry points import system, network or process APIs | `test_modules_only_import_the_standard_library_modules_on_the_list`, `test_only_entrypoints_touch_the_operating_system` |
| T11 | A program escapes through the interpreter's own variables or Python's built-ins | Names resolve in the program's scopes; the built-ins are exactly the documented ones | `test_a_program_cannot_reach_the_variables_of_the_interpreter`, `test_the_built_in_functions_are_exactly_the_documented_ones` |
| T12 | A hostile file crashes or stalls the tools | Limits on nesting and on errors; a loop that does not shrink stops; budgets for time, output, input, text, source and memory | `tests/test_robustness.py`; `tests/test_loops.py`; `tests/test_cli.py` (`--max-*`, `--timeout`); `tests/test_out_of_memory.py` |
| T13 | A dependency is compromised | The package has no runtime dependencies | `test_the_package_has_no_runtime_dependencies` |

## What is out of the model

These are not defects to report; they are what the CLI does not promise. SECURITY.md says the same of the first four.

1. **It is not a sandbox.** The interpreter is a Python program with the permissions of the user. A defect in it, or
   in the Python it runs on, removes every barrier above. There is no second layer (process isolation, system-call
   filter).
2. **A granted capability is trusted.** `--allow-process` runs an executable with the permissions of the user, and its
   arguments are not a boundary. `--allow-network` does not stop an origin that resolves to a private address.
   `--allow-read` and `--allow-write` trust everything under the folder, including what other programs put there.
3. **Resources are limited only if the user asks.** `--timeout` needs POSIX interval timers and `--max-memory` needs
   Linux. No limit covers `nex test`, analysis time, file writes, network use or every operating-system resource.
4. **Output is not filtered.** A program can print terminal control sequences.
5. **Side channels and timing** are not considered.
6. **A malicious toolchain** (the Python of the machine, the installer, the package index) is outside the model; the
   supply chain section of SECURITY.md says what the project does about its own artifacts.

For code that is not trusted, the answer stays the one in SECURITY.md: a container, a virtual machine or a job object
that enforces the deadline, the memory, the processes, the file system and the network.

## The native `nex`

[Decision 0027](decisions/0027-herramientas-nativas-por-defecto.md) makes the native `nex` the default way to use NEXORA, so the
rows above have to hold for it too. `tests/test_threat_model_rows.py` runs the scenarios of T1, T2, T3, T5, T6, T8, T9 and of the
modules through the real command of the Python implementation and, with `NEXORA_NEX` set, of the native one, and both have to give the
same exit status and the same diagnostic code. The job `commands` of `nexora-selfhost.yml` runs it on every change of the native tools.

Checked on 2026-11-07, native `nex` built from this tree: Linux x64 (Ubuntu 24.04, 66 tests, none skipped, symbolic links included)
and Windows x64 (Windows 11, 29 tests of the native `nex`; the file-symlink and `..`-after-a-link cases need privileges or POSIX
semantics and are the ones that Linux covers; the junction case runs). T4 (redirects, proxies, size) is read in the runtime rather than
run, because the native client verifies certificates and the test has no certificate that it trusts: `rt_https_get` reads no proxy
variable, accepts only status 200 (a redirect is a failure) and stops at one MiB (`RT_HOST_MAX_BYTES`).

**What this found.** Before 2026-11-07 the native `nex run` did not follow symbolic links when it compared a path with the folders that
the program declares and the user grants: a link inside an allowed folder that led outside it was read and written. The Python `nex`
denied it (`E3008`), the specification says it must, and `selfhost/README.md` listed it as a limit of the self-hosted interpreter, but
neither SECURITY.md nor this page did. `native-v0.15.0` and `native-v0.15.1` have the defect. It is fixed: `host_real` of
`selfhost/interpreter.nex` asks the C runtime (`rt_resolve`) where a path really leads, with every link and, on Windows, every junction
followed, a link that points nowhere resolved by its target, and a loop of links denied. The change is recorded in `CHANGELOG.md`.

## Gaps found while writing this page

Three of the four gaps found while writing it were closed with `tests/test_threat_model.py`: the network answer (T4), the rule that
modules do not inherit capabilities (`test_a_module_that_reads_a_file_must_declare_it_even_if_the_program_does`) and
the environment of a child process (`test_a_child_process_does_not_receive_the_environment_of_the_user`).


None is open. The native `nex` was the fourth gap and is closed in the next section.

## Review

2026-11-07, second pass by the author of this page, after writing the tests above: every row was re-read against the code that
implements it and against the tests it names (all 37 names exist and pass), and each of T1, T2, T3, T5, T6, T8 and T9 was also run
against the native `nex`, which is how the symbolic-link defect above was found. Nothing in the table is stated without a test or
without the line of code that is named. This is a review by the author, not an independent one.

The gate asks for a reviewed threat model. When the maintainer has read this page and the rows, the date and the outcome go below.

- Maintainer's review: _not recorded yet_.
