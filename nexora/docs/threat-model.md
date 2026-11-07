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
| T4 | An allowed origin sends the program somewhere else, a proxy variable of the environment does, or a huge answer exhausts memory | Redirects are refused, proxies are ignored, the answer is limited to 1 MiB and 5 seconds | Implemented in `host.py` (`NoRedirect`, `ProxyHandler({})`, `_NETWORK_MAX_BYTES`). **No test pins it today: see the gaps** |
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

## Gaps found while writing this page

- **T4 has no test.** The refusal of redirects, ignoring the proxy variables and the size limit of the network
  answer are implemented and untested. A test that replaces the opener would pin them.
- **Capabilities are not inherited by modules** (language specification, section 7.6), and no test names the
  threat: a module that reads a file without declaring it itself must fail even when the program that imports it
  declares and is granted the same file.
- **The environment of the child process** is described in decision 0020 (only `PATH` and what Windows needs to
  start programs); no test reads the environment that the child receives.
- **The native `nex`** (decision 0027) is the default of the tools. This page rests on the tests of the Python
  reference implementation; whether the same rows hold for the native one, and which tests show it, has not been
  checked here.

## Review

Pending. The gate asks for a *reviewed* threat model: when the maintainer has read this page against
`tests/test_security.py` and the other tests it names, the date and the outcome go here.
