# Testing

How it is checked that NEXORA does what its documentation says, how to run those checks
and what they do **not** cover.

> Since 23 October 2026, the server (`servidor/`) and the website (`web/`) are in a separate private
> repository, with their own continuous integration. What this document says about them (the
> `npm test` tests in `servidor/`, the integration tests, the review of the website) is the record of
> the measurements made when they lived here.

## Running the checks

With the virtual environment activated and the development tools installed
(`python -m pip install -e ".[dev]"`), from the `nexora/` directory:

```bash
python -m ruff check src tests     # static analysis of the Python code
python -m pytest                   # all the tests
python -m pytest --cov             # tests with coverage measurement
python benchmarks/benchmark_interpreter.py  # execution-time and peak-memory baseline
```

Useful options:

```bash
python -m pytest tests/test_parser.py          # a single file
python -m pytest -k recursion                  # the tests whose name contains "recursion"
python -m pytest -x                            # stop at the first failure
python -m pytest --cov --cov-report=html       # browsable report in htmlcov/index.html
```

The full suite takes about three minutes. The tests need no internet connection.

## Benchmarks

`benchmarks/benchmark_interpreter.py` runs three small NEXORA programs: recursive `fib(20)`, a
100,000-iteration `while`, and building a 1,000-element list with `List.append`. By default it
reports the median of three end-to-end timing runs, without `tracemalloc`, and peak traced Python
allocation from a separate set of runs with `tracemalloc` enabled. Both include analysis and
execution through `nexora.api.run_source`. Run it from this directory; `--repeats N` changes the
sample count for each set. The baseline and its environment are recorded in
[Limitations](limitations.md#performance). These are measurements, not pass/fail performance tests.

## Latest measurement

Done on 21 October 2026, on Windows 11 with Python 3.12.10:

| Check | Result |
|-------|--------|
| `python -m ruff check src tests` | No errors |
| `python -m pytest` | 2285 tests passed, 9 skipped, 0 failures |
| Line and branch coverage (`--cov`) | 94.59 % |
| Configured threshold (`fail_under` in `pyproject.toml`) | 90 % |
| Tests of the web server (`node --test "test/*.test.js"`, in `servidor/`) | 821 passed, 0 failures |

The 821 server tests are those of this measurement. Before, the table had 112, the same as
`v0.6.0`. After the tag, the commit
`cb709ff` added `servidor/test/playground-config.test.js`: on `main`, at commit `7c87027`,
`npm test` in `servidor/` gives 130 passed and 0 failures (15 October 2026, Windows 11, Node
24.21.0). That run only repeated the server tests; the rest of the table was not measured
again. On the branch `fix/playground-container-lifecycle`, which adds
`servidor/test/playground-containers.test.js`, `npm test` gives 154 passed and 0 failures in each
of six runs at commit `d5585099`, and 325 passed and 0 failures in each of six
runs after adding the tests of the format of the container command and of the local
image (16 October 2026, Windows 11, Node 24.21.0). The format tests only analyze the
command; the life-cycle ones use a fake Docker. No real container was run.

Four of the skipped tests need POSIX functions that Windows does not have: one checks a
file without read permission (the same case is covered on Windows by simulating the error), and three
check the memory and CPU limits that the playground process asks the operating system for.
On Windows they are skipped; on Linux they run and pass (next section).

The other five are skipped in this measurement: two examples that need a *host* (the standard
input and files) are not compared with the API, and three tests of symbolic links are
skipped because on Windows privileges are needed to create them (the one of directory junctions
runs only when the system allows it).

### Linux

Done on 17 October 2026 on Ubuntu 24.04 on WSL 2 (kernel 6.18), with a user that
is not root (uid 1000), with Node.js 24.11.1. It was run on a copy, in the Linux file system
(not in `/mnt/c`), of the working tree of the branch `fix/playground-container-lifecycle` at
commit `237184b`. In `nexora/` and `npm/` that tree had no uncommitted changes; in `servidor/` and
`web/` it had work in progress, uncommitted (pages of the website, CAPTCHA and their tests), which is included in
the figure of `npm test` in `servidor/`:

| Check | Result |
|-------|--------|
| `python -m ruff check src tests` | No errors |
| `python -m pytest --cov`, Python 3.12.3 | 1604 tests passed, **0 skipped**, 0 failures; coverage of 94.48 % |
| `python -m pytest` (without `--cov`), Python 3.11.17 and 3.13.16 | 1604 passed, 0 skipped, 0 failures in each version |
| `npm test` in `npm/` | 12 passed, 0 failures |
| `npm test` in `servidor/`, with the working tree described above | 355 passed, 0 failures, in each of two runs |
| pip package: `python -m build`, installing the wheel with `--no-index` in a clean environment, `nex run` and `nex --version` | No errors |
| npm package: `npm pack`, installing from the file and `npx nex run` | No errors |

The four POSIX tests ran for the first time and passed: the file without read
permission gives `E0001`, and the memory, real-time and CPU limits end the program. Those
limits were tested with `tests/test_worker.py`, which starts the worker directly as a process, without
a container and without going through the server.

`ruff`, coverage, the tests of `npm/` and `servidor/` and the packages were only checked with
Python 3.12.3; with 3.11 and 3.13 only `pytest` was run. Python 3.11 and 3.13 were installed with `uv`;
Ubuntu only ships 3.12. The server tests need the environment of `nexora/.venv` (on Linux,
`nexora/.venv/bin/python`), as on Windows.

**Docker was not run**, nor any of the checks of the
[isolation of the playground](playground.md#checking-the-isolation), which are still pending.

Later, on 17 October 2026, on the branch `feature/server-hardening`, only
`npm test` in `servidor/` was run. The server (anti-spam, per-client limits, login throttling,
deletion of expired sessions, security headers and its own fonts) was already in the
commits `a8a956b`, `cda0ee9` and `a160829`; the website (consent manager, account forms,
draft legal pages and expanded documentation) and its tests were still uncommitted. An earlier
figure of that same day, 522 passed, only on Windows, corresponds to a previous state of the work.

| Tree | Windows 11, Node 24.21.0 | Ubuntu 24.04.5 on WSL 2, Node 24.11.1 |
|------|--------------------------|---------------------------------------|
| `a160829` without the uncommitted changes | 492 passed, 0 failures (one run) | Not run |
| `a160829` with the uncommitted changes (audit) | **565 passed**, 0 failures, 0 skipped, in each of three runs | **565 passed**, 0 failures, 0 skipped, in each of three runs |
| The same tree after the fixes of the audit | **567 passed**, 0 failures, 0 skipped, in each of three runs | **567 passed**, 0 failures, 0 skipped, in each of three runs |
| `dce6061` with the fixes of the visual review, uncommitted | **575 passed**, 0 failures, 0 skipped, in each of three runs | Not run |
| `75661aa` with phase 1 of the production audit, uncommitted | **643 passed**, 0 failures, 0 skipped, in each of three runs | Not run |
| The same tree with the fixes of the review of phase 1 | **658 passed**, 0 failures, 0 skipped, in each of three runs | Not run |
| The same tree with the test of the real startup | **659 passed**, 0 failures, 0 skipped, in each of three runs | Not run |
| The same tree with the guards of the integration tests | **701 passed**, 0 failures, 0 skipped, in each of three runs | Not run |
| The same tree with the atomic sign-up and the revised guards | **721 passed**, 0 failures, 0 skipped, in each of three runs | Not run |
| The same tree without `DROP`, with the escaped wildcard and the protected rollback | **741 passed**, 0 failures, 0 skipped, in each of three runs | Not run |
| The same tree with the fixes of the final audit (preflight, logged rollbacks) | **766 passed**, 0 failures, 0 skipped, in each of three runs | Not run |
| The same tree with the review of the preflight (allowed modules, migration process, playground, Node without `registerHooks`) | **784 passed**, 0 failures, 0 skipped, in one run | Not run |
| The same tree with the shutdown limit fixed | **797 passed**, 0 failures, 0 skipped, in one run | Not run |
| The same tree with the final review of the audit (tests without fixed waits, shutdown by steps) | **798 passed**, 0 failures, 0 skipped, in each of three runs | Not run |
| The same tree with the lock of the integration tests, the measured Node minimums and `captcha.test.js` without order dependence | **810 passed**, 0 failures, 0 skipped, in each of three runs | Not run |
| `5eae954` with the closed list of Node branches in the integration guards, uncommitted | **811 passed**, 0 failures, 0 skipped, in one run | Not run |
| `e4ec28f` (website and playground up to date with language 0.7) with `List` in the types of `language_info`, uncommitted | **818 passed**, 0 failures, 0 skipped, in one run, on 21 October 2026 | Not run |
| `6d61ea9` (nominal records, 0.8.0) with the website and the server up to date with language 0.8, uncommitted | **821 passed**, 0 failures, 0 skipped, in one run, on 21 October 2026 | Not run |

On Linux a fresh copy of the working tree was used, checked file by file with SHA-256, with
the dependencies installed with `npm ci` and the interpreter of `nexora/.venv` (Python 3.12.3). The row
of 567 was run on Linux before adding this section: that copy only differed from the tree in this
file.

The eight new tests of the last row cover `GET /api/playground/status` with the playground
enabled and disabled (without starting the worker); that the disabled page only asks `/status`,
sends nothing when Run or Check is pressed and keeps the saved code; that Run and Check send nothing
while the server has not confirmed that the playground is enabled (no answer, an answer
it does not understand or an error of the service); that on an older server without `/status` it decides from
`/info`, as before; that a connection lost later is still reported when Run is pressed; and that the
draft legal pages carry `noindex`.

The 68 new tests of the row of 643, all without network and without a real database:

- `playground-config.test.js` (11): in production, the playground enabled without the container command
  prevents starting (without a command and with a process command); with the container command, disabled or
  outside production, it starts. One of them launches `src/index.js` in a separate process, without
  `servidor/.env`, with port 0 and the database on a closed port: it ends with an error before
  listening and before deleting sessions.
- `passwords.test.js` (7): real scrypt; stored format, a different salt in every hash, wrong
  passwords, 10 and 200 characters, non-ASCII text, other parameters, invalid formats and impossible
  parameters (an error, not a wrong password).
- `oauth.test.js` (32): Google and GitHub simulated. `state` missing, different, repeated or of another
  length; cancellation; provider not configured; HTTP errors, answers that are not JSON or without the
  expected fields, timeout and network down; unverified emails; an account with a password that is not
  linked; database failures inside and outside the transaction; and that in no failure is
  an account confirmed (`commit`) or a session opened, nor does the log receive the secret, the token,
  the code or the email. That an account undone with `rollback` is not really stored can only
  be checked with a real MySQL.
- `health.test.js` (6), `lifecycle.test.js` (8) and `safe-log.test.js` (4): `/api/health`, the orderly
  shutdown with real HTTP servers on free ports, and the description of errors in the log.
  The signals themselves (`SIGTERM`, `SIGINT`) are not tested: on Windows, killing a process does not run its
  handlers. They are still pending on Linux.

The 15 tests of the row of 658 fix what the review of that phase found. Each one was
written before the fix and failed without it:

- `lifecycle.test.js` (4): a keep-alive connection (with `http.Agent` and with `fetch`) no longer holds the
  shutdown: the response carries `Connection: close` and exits with 0 in less than 1.5 s, where before it exhausted
  a limit of 3 s; the pool is closed only after the deletion batch in progress; if the deletion does not
  finish in time or fails, the pool is closed anyway and it exits with 1, without the message of the error.
- `session-cleanup.test.js` (5): `stop()` waits for the batch in progress, sends no other one even if there were
  sessions left and schedules no more passes; it ends at once if there is none in progress; it is never rejected;
  and an error without a code is logged by its type, never by its message.
- `health.test.js` (3) and `safe-log.test.js` (3 more; the one of `describePath` is replaced by four of
  `describeRoute`): the route is logged by its template, also the nested one
  (`/api/auth/:provider/callback`) and one written with other capitalization; without a matching route,
  `(no route)`; never the requested path, the query string, an email or an identifier.

In the row of 659, the test that read `src/index.js` with regular expressions is replaced by two
that start the real server in a separate process (free port, without `servidor/.env`, database
on a closed port, playground disabled) and send it `SIGTERM` or `SIGINT` through
`test/fixtures/signal-bridge.js`, which emits the event on `process`: it runs the same handlers as
a signal, but it is not a system signal. With `SIGTERM` it arrives while there is a sign-up in progress:
the response carries `Connection: close` and the process exits with 0. Both detect three faults
introduced on purpose in a copy of `src/index.js`: without a `SIGTERM` handler, the shutdown
created late and the tracking of responses started after the first request. The operating system
signal and systemd are still untested.

In the row of 797, the shutdown can no longer end before its limit. `within()`
(`servidor/src/lifecycle.js`), which limits every wait of the shutdown, set its timer with
`unref()`: if the only pending thing had no resource behind it (for example, a pool close that
never ends), the process had nothing left to keep it alive and exited with 0 in 1–2 ms, without
logging the limit or reaching `exit()`. Now the timer does not carry `unref()`: it keeps the
process alive until the wait ends or expires, and `clearTimeout` still clears it as soon as it ends.
With the current flow, the shutdown can take up to about twice the limit (`timeoutMs`, 10 s): the
requests in progress and the deletion of sessions are waited for at the same time, and the pool afterwards. The 13
new tests of `lifecycle.test.js`:

- 6 with simulated timers: no timer of the limit uses `unref()`; all of them are cleared after
  the close, the error and the expiry; a late close adds nothing to the log; and every order between
  the limit and the close of the pool has a fixed result (in the same turn, in any order, it counts
  as expiry; if the pool closes before the limit arrives, as a close).
- 7 in a process of their own (`test/fixtures/shutdown-child.js`, with a real `process.exit`, a simulated
  pool and an HTTP server on a free port of 127.0.0.1): a pool that does not close, with nothing else
  alive, waits for the limit, logs it and exits with 1 (before, with 0 in 1–2 ms); one that closes at once
  exits with 0 without waiting; one slower than the limit and one that rejects exit with 1 and a single line;
  without `process.exit`, the process ends as soon as the shutdown finishes, without any pending
  timer; and, with the same deadline as the limit, the timer set first wins (that of the
  limit or, if it was set before the shutdown started, that of the pool).

The two tests that already expected an expired limit (a pool or a session deletion that never end)
now expect it with nothing else keeping the process alive. Before the fix, on Node 20.6.1 and
22.23.3, 19 tests of `lifecycle.test.js` and `session-cleanup.test.js` were cancelled: seven waited for
a timer with `unref()` with nothing else alive, and the rest fell in a cascade after them (the test runner
of Node 24 does not cancel them). The five of `session-cleanup.test.js` now wait with the event
loop alive, as in the real server; the two of `lifecycle.test.js` no longer need it.

`npm test` with this row, on Windows 11, one run per version, on 18 October 2026 (Node
20.6.1 and 22.23.3 are the official portable distributions, with their SHA-256 checked; 24.21.0 is the
system one):

| Node | Tests | Passed | Skipped | Failures | Cancelled |
|------|-------|--------|---------|----------|-----------|
| 20.6.1 | 797 | 783 | 14 (those of `preflight.js`, without `registerHooks`) | 0 | 0 |
| 22.23.3 | 797 | 797 | 0 | 0 | 0 |
| 24.21.0 | 797 | 797 | 0 | 0 | 0 |

Still not shown: the case with a real MySQL (that the close of the pool stays pending without any
open socket), the real operating system signals (the tests use
`test/fixtures/signal-bridge.js`) and the `TimeoutStopSec` of systemd, which has to exceed those two
times the limit.

In the row of 798, the final review of the audit:

- `servidor/src/lifecycle.js`: marking the server as shutting down (`onDraining`, which puts
  `/api/health` in 503) and stopping the deletion of sessions (`stopCleanup`) are tried separately. Before
  they were in the same block: if the first one failed, the second one was never called. The new test
  is number 798.
- `lifecycle.test.js` no longer waits fixed times. The tests that needed a request in progress
  waited 100 ms and assumed it had arrived; now they wait for the server to receive it, and the
  slow response arrives when the test decides. The one of `SIGTERM` to the real server sent the signal
  while scrypt computed the hash (about 100 ms); now it sends the body in two parts, and the second one
  only when `test/fixtures/signal-bridge.js` confirms over IPC that it has emitted the signal. Besides, it uses a
  keep-alive client: with `agent: false` the client itself asked for `Connection: close`, and checking that
  header in the response showed nothing.
- `whileAlive()` (`session-cleanup.test.js`) has a limit of 5 s. Before, if a pass never
  ended, the test waited forever: `node:test` sets no limit by default.
- `auth-routes.test.js`: the test that a failed sign-up does not leave the account half done repeated the
  sign-up with a new simulated database, so it checked nothing; now it repeats it with the same one.
- The test of `stop()` with a batch in progress records its lines instead of writing them to the standard
  error.

Five faults introduced on purpose in copies of the tree (without `servidor/.env`) are detected by these
tests: the two steps of the shutdown together again, without the `SIGTERM` handler, without
`Connection: close`, the sign-up confirming (`COMMIT`) instead of undoing, and a pass deadline that
never expires (the five tests with `whileAlive()` fail after 5 s, instead of waiting forever).
Without `Connection: close`, the test of the real `SIGTERM` only detects it since it uses the
keep-alive client.

`npm test` with this row, on Windows 11, on 18 October 2026 (the same Node distributions
as in the row of 797, with their SHA-256 checked again):

| Node | Runs | Tests | Passed | Skipped | Failures | Cancelled |
|------|------|-------|--------|---------|----------|-----------|
| 20.6.1 | 1 | 798 | 784 | 14 (those of `preflight.js`, without `registerHooks`) | 0 | 0 |
| 22.23.3 | 1 | 798 | 798 | 0 | 0 | 0 |
| 24.21.0 | 3 | 798 | 798 | 0 | 0 | 0 |

After each run no Node process was left open. With Node 20.6.1, the test runner
warns `MaxListenersExceededWarning` once in `integration-guard.test.js`: according to the trace, it
is produced by its own way of applying the `timeout` of each test (`stopTest`), not by the code of the server.

With the tests of each file in random order (`node --test --test-randomize`, Node 24.21.0), in
six runs: in four the 798 pass; in two the same two tests of `captcha.test.js` fail
(committed in `cda0ee9` and `a160829`), because they share the strict limit of the same IP: the second one
assumes that the first one already used it up. With the normal order, `node:test` runs the tests of a
file in the order in which they are written, and `npm test` did not fail. They are fixed in the row of 810.

In the row of 810:

- **`captcha.test.js` without order dependence.** The two tests that use up the strict limit now use
  each one its own route, with the whole quota (`protectedRoute`), and they use up the quota themselves:
  a low score and a Google outage pass twice and then both are throttled. With the previous
  version, the seeds 2774676119 and 4 reproduce the failure (48 passed, 2 failures); with the new one, those
  two seeds and 100 more (1000–1099) pass the 50 tests of the file.
- **The integration tests have a run lock** (see below). 11 new tests in
  `integration-guard.test.js`, with simulated connections.
- **The Node minimum of the integration tests was wrong.** `module.registerHooks` exists since
  Node 22.15, but in the versions below, when importing a CommonJS module from ESM, the hook
  received in the measurements a second resolution with the absolute path and without `parentURL`: the hook of
  `preflight.js` cannot know who asks for it and blocks `mysql2` also in the legitimate order. It is an
  observation on Windows: the Node documentation does not describe that behaviour or its change, so
  its exact cause is not confirmed. It failed safely (it lets nothing through), but the integration
  tests could not run, and `npm test` failed in those versions (3 failures on Node 22.15.0)
  instead of skipping those tests. Measured with
  the "legit" case of `test/fixtures/preflight-probe.js` and the official distributions for Windows, with
  their SHA-256 checked: it is blocked by 22.15.0, 22.18.0, 22.19.0, 22.20.0, 22.21.0, 22.22.0, 22.22.1,
  22.22.2, 24.0.0, 24.11.1, 24.13.0 and 24.13.1; it is loaded by 22.22.3, 22.23.0, 22.23.3, 24.14.0, 24.14.1,
  24.15.0, 24.16.0, 24.21.0, 25.9.0 and 26.12.0. `checkHookSupport` (`guard.js`) now requires those
  versions and explains why; in the others, `npm test` skips the 14 tests that launch processes with
  `preflight.js`, each one with its reason. A new test pins the table of versions.

`npm test` with this row, on Windows 11, on 18 October 2026, one run per version except
24.21.0 (three). The figures come from the logs of each run:

| Node | Tests | Passed | Failures | Skipped | Cancelled | Exit code |
|------|-------|--------|----------|---------|-----------|-----------|
| 20.6.1 | 810 | 796 | 0 | 14 (without `registerHooks`) | 0 | 0 |
| 22.15.0 | 810 | 796 | 0 | 14 (a hook that does not see who loads each module) | 0 | 0 |
| 22.22.3 | 810 | 810 | 0 | 0 | 0 | 0 |
| 22.23.3 | 810 | 810 | 0 | 0 | 0 | 0 |
| 24.14.0 | 810 | 810 | 0 | 0 | 0 | 0 |
| 24.21.0 (×3) | 810 | 810 | 0 | 0 | 0 | 0 |

With random order, Node 24.21.0, seeds 2774676119, 1, 2, 3, 4 and 5: the 810 passed in each
of the six, exit code 0. After each run no Node process was left open.

**Intermittent failures, not fixed.** In an earlier run of this same round, with the same
server code, tests that start the real Python interpreter or
processes with a time limit failed by timeout: 1 on Node 20.6.1 (`playground-api.test.js`) and 4 on Node 22.23.3
(`playground-api`, `playground-containers`, `playground-frontend` and `web-guide`). They are tests
committed before this audit. They were not reproduced: those four files passed 3 times in a row
with each of the two versions (326 of 326), and in the table above. The most likely cause was
a momentary load on the machine while `node --test` runs several files at the same time, but it is not
shown.

In the row of 811 (`5eae954` with the uncommitted changes), the guards of the integration tests
only accept the branches of `HOOK_MINIMUMS` (Node 22 from 22.22.3 and Node 24 from 24.14.0) and reject
any other branch and the versions that are not exactly X.Y.Z. Before they accepted any version of
branches 25 and later, and incomplete versions such as `v24`. The rejection message says the reason
(unreadable version, a branch without a measured minimum or a version below the minimum) and no longer presents as a
fact the cause of the mysql2 block. The test of those versions is rewritten with each reason and with the
limit of each branch, and a new test checks that everything `engines` accepts in
`servidor/package.json` is inside that list. `npm test`, on Windows 11 with Node 24.21.0, one
run, on 18 October 2026: 813 passed, 0 failures, 0 skipped, exit code 0, in 26.3 s.
The previous run, with 811 passed, was that of the row this paragraph refers to. That
combination of Node has since been run on Linux, Windows and macOS by the continuous integration.

In the row of 818, the word lists of the playground, the guide and the documentation of the website are
brought up to date with language 0.7 (lists and `for`): before `e4ec28f`, three tests compared those
lists with the real interpreter and failed. `language_info()` also includes `List` in `types`, and a
highlighting test checks that `List` is marked as a type. Exit code 0, 29 s. That
combination of Node has since been run on Linux, Windows and macOS by the continuous integration.

In the row of 821, the website and the server are brought up to date with language 0.8 (records): the catalogue
of examples of the playground offers `records.nex`, the highlighting of the editor recognizes the types that
the program declares (a record is marked as a type, not as a function), the roadmap of the
documentation separates what is already there from what comes next, and the guide describes records with an
example that the tests run with the real interpreter. Exit code 0, 32 s. That combination of
Node has since been run on Linux, Windows and macOS by the continuous integration.

#### Integration tests with MySQL: run once

`servidor/test/integration/` contains tests against a real database (migrations and schema,
accounts and sessions, deletion of sessions and close of the pool with queries in progress and locks, OAuth
with persistence and concurrency, and SQL errors). They first need the `nexora_test` database, the schema
of the marker `nexora_test_guard` and two accounts, which are created with
`servidor/test/integration/setup-admin.sql`. That script **has been run**: on 18 October
2026 it created the database, the schema of the marker and the two accounts with their permissions. The migrations account
only has `CREATE`, `ALTER`, `INSERT` and `REFERENCES` on the three tables of the application, **without
`DROP`** and no permission on the whole database: it cannot delete tables, create others or delete the database.
The application one has `SELECT`, `INSERT` and `DELETE` on `` `nexora\_test`.* ``, with the `_`
escaped: unescaped, in a permission on a whole database `_` is a wildcard and would also give access to
`nexoraXtest`. Both can only read the marker. They are only launched with `npm run test:integration`,
never with `npm test`, and they load `servidor/.env.integration` (ignored by git), never `servidor/.env`.

**Measured result.** On 18 October 2026 `npm run test:integration` was run **only once**,
on the branch `feature/server-hardening` (HEAD `74f2a03`, with `test/integration/context.js`, `run.js`,
`guard.js` and `test/integration-guard.test.js` modified and uncommitted), inside an isolated auxiliary
container that shares the network namespace of a `nexora-mysql-test` container with MySQL 8.4.11,
published only on `127.0.0.1:3307` of the host: **30 passed, 0 failures, 0 skipped, exit
code 0**, in 20.36 s. Per suite: migrations 6/6, accounts 8/8, sessions 3/3, close of the pool with
queries in progress 2/2, OAuth 6/6 and SQL errors 5/5.

The migrations ran and finished correctly. The three checks that cover them passed:
creating the expected schema from a database without tables, repeating them without changing any table or
losing rows, and not repairing a schema drifted by hand; the last one undid its own `ALTER`. The
run ended on its own and emitted its summary.

It was **a single run**: it has not been repeated, so the figure says nothing about the result being
deterministic, nor about it being so on another operating system or with another version of Node. Here the process
was Node 24.21.0 inside a Linux container on MySQL 8.4.11, not on the Windows host
like the measurement of `npm test` above. The time limit when releasing the run lock
(10 s in `guard.js`) was never triggered: the run was fast and clean.

**The fresh schema test** only runs if none of the three tables exists, that is, with the
newly created database. If they exist, it is skipped and says so; if only some exist, it fails, because the database
was left half migrated. To repeat it, a person with administration permissions first runs, by
hand and on the test server, `servidor/test/integration/prepare-fresh-schema-admin.sql`, which deletes
only the three tables of the application (not the database, not the marker, not the accounts). The script **does not
guarantee on its own** that it is on the test server: it shows the marker, and checking it is the job of
whoever runs it. First of all the target has to be reviewed (server, port and account of the client);
then, use the MySQL or MariaDB client **without `--force`**, so that it stops at the first error
(if the marker does not exist, its query fails and the `DROP` statements do not run); and look at the result of the
query of the marker: it has to be exactly one row, `nexora-integration-tests-only`. With
anything else, stop. The safest thing is to run only that query first.

Since the run of 18 October 2026 created the three tables, that preparation is no longer needed
to launch the suite again on that same test server: while the tables exist, the
fresh schema test **is skipped and says so**. To exercise it again,
`prepare-fresh-schema-admin.sql` has to be run first, as the previous paragraph describes.

The drifted schema test undoes its change with `ALTER`, without deleting anything, also if the
migrations or a check fail (`undoAfter` in `guard.js`). If what fails is undoing it, it does not hide the
original error: it records it separately and asks for `prepare-fresh-schema-admin.sql`.

Before loading any test, `servidor/test/integration/preflight.js` (with `--import` in the script, and
also as the first import of `run.js`) rejects an unsafe environment: without `npm run test:integration`,
with any `DB_*` variable, with the playground able to be enabled (`PLAYGROUND_ENABLED` can only be missing or
be exactly `false`, and no other `PLAYGROUND_*` variable is accepted) or with a test configuration
that is not the authorized one. It also installs a Node module resolution hook: from
`servidor/src/` only the modules of the `APP_MODULES` list of `guard.js` can be loaded (those
the tests import and everything they import; `npm test` checks that the list is exactly
that), and only when an application connection has been verified and `useAppDatabase()` has prepared the
environment. `src/index.js` (it would listen on `PORT`, 3000 if there is no other, and would start the deletion of
sessions) and `src/migrate.js` (it connects and migrates when loaded) are never loaded in that process. `mysql2`
can only be loaded by `guard.js` (with the process already marked) or by those modules. This holds for any
way of loading them: static import, `import()` with a text, a variable or a template, `require` and
`createRequire`, and other ways of writing the same path (`SRC`, `%73rc`). `playground/worker.js`, which
is in the list because `app.js` imports it, creates its working folder in the temporary
directory when loaded, as in `npm test`.

**The integration tests only accept Node 22.22.3 or later on branch 22, or 24.14.0 or
later on branch 24** (`module.registerHooks`, and that its hook sees who loads each module; see the
rows of 810 and 811). They are minimums measured on Windows, with the official distributions: in the earlier
versions that were tested, the hook blocked mysql2 also in the legitimate order. The documentation
of Node does not describe that change, so its exact cause is not confirmed. The list is closed
(`HOOK_MINIMUMS` in `servidor/test/integration/guard.js`): any other branch (23, 25, 26, 27 or
later) is rejected until it is measured and added, even if some single version did not block mysql2 in the
measurement (25.9.0 and 26.12.0). Versions that are not exactly X.Y.Z are also rejected, such as those
with a suffix (`-pre`, `-rc`) or leading zeros.

The compatibility declared in `servidor/package.json` (`engines`) is stricter:
`^22.23.2 || ^24.18.1`, the latest security releases of each branch in October 2026. The code
of the server does not need those versions (`npm test` passed with Node 20.6.1), but Node 20 has had no
support since 30 April 2026 and the earlier versions of branches 22 and 24 have published security
fixes. Within that range 22.23.3 and 24.21.0 have been tested locally (Windows 11); the
exact minimums, 22.23.2 and 24.18.1, have not. The continuous integration tests those fixed minimums, the latest
version of branches 22 and 24 and, on Linux and non-blocking, Node 26, which stays outside `engines` until
it is validated; that experimental run has already been done, without blocking the workflow. The minimums of
`engines` and those of the guards are different
things: `engines` says where the server is supported, and the guards, where the
integration tests can run. A test of `integration-guard.test.js` checks that everything that
`engines` accepts is within what the guards accept. On any Node that the guards do not accept
(also in the experimental Node 26 run of the continuous integration):
- `preflight.js` refuses to run the integration tests and explains why;
- `npm test` can run everything else; of `integration-guard.test.js` the 14 tests that
  launch processes with `preflight.js` are skipped, each one with its reason, and the summary counts them as skipped
  (`skipped 14`), not as passed.

With real Node 20.6.1 and 22.15.0, on Windows 11, `npm test` skips exactly those 14, each one with its
reason (see the rows of 797, 798 and 810). That `preflight.js` refuses with `npm run test:integration` has not been run on Node
20.6: it has only been simulated on Node 24, removing `registerHooks` before loading `preflight.js` (`node
--import ./test/fixtures/without-register-hooks.js --test test/integration-guard.test.js`). The
continuous integration never validates the
integration tests either: it only runs `npm test`, without a database; that step passing says nothing about them.
The alternative that exists since Node 20.6, `module.register`, runs its hooks asynchronously in
another thread and on Node 20 does not see `require`; it would have to be completed with an internal function of Node, so
it is not used.

The migrations run in a separate process, through `servidor/test/integration/migrate-child.js`.
Its environment is exactly that of `migratorProcessEnv` (the migrations account, `127.0.0.1`,
`nexora_test`, `NODE_ENV=test`, `PATH` and `SystemRoot`; on Windows, also, the system variables that
Node adds to every child process, such as `TEMP` or `USERPROFILE`): any other one, such as `NODE_OPTIONS`, a
`TEST_*` one or the application account, stops it before connecting. With its own connection it verifies the
migrations account (identity, exact permissions and marker, only reads) before loading
`src/migrate.js` and again after migrating; if the first one fails, it does not migrate.

**Two runs do not change `nexora_test` at the same time.** Before opening any other connection, the
run takes a named lock, `GET_LOCK('nexora_test.integration_run', 0)`, with a connection of its
own verified like that of the application, and keeps it until the end (`holdRunLock` in `guard.js`).
It does not wait: if another run has it, it stops without opening anything else and without changing anything. Before
emptying the tables and before launching the migrations, it checks on the server that the lock is still
its own (`IS_USED_LOCK(…) = CONNECTION_ID()`); if it was lost (the connection was cut or
`wait_timeout` expired), it stops. At the end, `run.js` releases it (`RELEASE_LOCK`); if the process ends in
another way, also if it crashes, the server releases it when the connection closes, and its socket does not keep
the process alive. It needs no permission. **It is not a security barrier**: it is a lock of the whole
MySQL or MariaDB server that only orders these tests among themselves; it isolates nothing from production, and in
a cluster with several servers (Galera, replicas) each server has its own locks. Tested
only with simulated connections: that MySQL or MariaDB release it when the connection is cut, and the
behaviour with two real runs, unchecked.

**None of this is an absolute barrier**: it protects against mistakes, not against code written to get around it.
These limits remain:
- the migrations process does not have the hook (it runs `src/migrate.js` on purpose);
- **`src/migrate.js` opens a different connection from the one the migrations process verifies.** It uses
  the same configuration (the `DB_*` variables already checked) and runs between the two
  verifications, but what that connection does is not verified by itself: what is verified is the
  account and its configuration;
- a `Worker`, a child process of its own, `--preserve-symlinks` or a socket opened by hand do not go through the
  hook;
- if `run.js` were launched without `--import`, the environment is still checked before evaluating any
  test (`preflight.js` is its first import), but the hook would arrive after linking its
  static imports: a static import of `src/` would be evaluated. Without `DB_*` variables,
  `src/config.js` would stop when loaded. The text checks of `npm test` warn about it beforehand,
  but they do not guarantee it.

What does run with `npm test` are the 127 tests of `integration-guard.test.js`: the guards
that those tests have to pass before doing anything. They reject `DB_*` variables in the environment,
`NODE_ENV` other than `test`, another host, another database, another user, a template password, another
effective identity (`CURRENT_USER()`), any permission too many or too few (also global, on
another database, the database without the escaped `_` or with similar names such as `nexoraXtest`, `DROP` or
any permission on the whole database for the migrations account, writing to the marker, roles,
`PROXY` or `GRANT OPTION`, in the MySQL 8 format and in the MariaDB one) and the lack of the marker; the only
destructive operation (emptying the three tables) only accepts verified connections; no function
opens a connection if the process was not launched by `run.js` with `npm run test:integration` and a list of
files identical to that of the folder; no file of the folder reaches `src/` or `mysql2` through
static imports, neither directly nor indirectly; and `src/` is only imported with `import()`, inside
functions and after calling a guard. The tests of `preflight.js` launch separate processes
with `--import` (with fake connections and port 1, never a database server): an
unsafe environment stops before loading anything; eleven ways of loading `src/` or `mysql2` too early
(static import, `import()` with a text, a variable or a template, top-level `await`, `require`,
`createRequire`, `%73rc`, `SRC` on Windows, with the process only marked and `mysql2` from a test) are
stopped; and the legitimate order (verified connection, `useAppDatabase()`, `src/db.js` and `mysql2` through
it) still works. `src/index.js` and `src/migrate.js` are rejected before and after that moment, with
`import()` and with `require`, and the proof that they were not evaluated is that there is no
`SIGTERM` handler (`index.js` registers it when loaded) nor any trace that it listened or migrated; those tests give
`PORT=0` and `LISTEN_HOST=127.0.0.1`, so that a failure would never touch port 3000. `PLAYGROUND_ENABLED`
is accepted undefined or with `false`, and rejected with `true` or any other value, like
any other `PLAYGROUND_*`. Of the migrations process, the verification before and after is tested with fake connections
(and that without the first one it does not migrate, that a change of permissions during the
migration is detected afterwards and that the connection is always closed); and, with real processes that
stop before connecting, that the exact environment is accepted and a different one rejected. That test with
a real process found that on Windows Node adds system variables to every child process: without
accepting them, the migrations process would have refused to start on Windows. The text checks (`require`, `createRequire`, `process.env[…]`,
`DB_*` variables, `import()` without a fixed text, top-level `await` also after `export`) are
applied to all the files of the folder, not only to the tests; they are heuristics on the usual
format of the code, an early warning, not a syntactic analysis. The faults introduced on purpose
in copies of `guard.js`, `preflight.js`, `run.js`, `package.json`, `setup-admin.sql` and the integration
files are detected by them. Whether MySQL or MariaDB really behave that way (the wildcard, the table
permissions, the format of `SHOW GRANTS`) is still unchecked: no server has been connected to.

They are automated tests: the MySQL database, the answers of Google reCAPTCHA and the browser
are simulated (the consent manager and the forms run in a minimal DOM,
`servidor/test/fixtures/mini-dom.js`). **The real checks are still pending**: against a
real MySQL, with real reCAPTCHA keys, in a browser with those real services, behind
nginx and with the headers of the production server. Docker was not run either. The website was reviewed
by hand in the browser, without those services ([Visual review of the website](#visual-review-of-the-website)).

Coverage went down compared to the previous measurement (99.56 %) because two new modules are tested
by launching them as separate processes, which the measurement does not follow: `worker.py` and `mcp_server.py`.

These figures are a snapshot of that day. To know the current ones, run the commands.

### Visual review of the website

On 17 October 2026 the website was reviewed in Chrome (desktop, 1912×948) and in Microsoft Edge 155
headless, driven by CDP, at 320×640, 360×740, 390×844, 820×1180, 1366×768 and 1440×900. The
test server started without `servidor/.env` and with the database on a closed port, so that it
could not read from or write to MySQL (when it starts it deletes expired sessions), with the playground
disabled. After the fixes it was repeated at 320×640, 360×740, 390×844 and 1366×768: no
page overflows horizontally, the controls of the playground, the sign-up and the login
are fully visible when going through them with Tab, and the sign-up fits in 1366×768.

**Not checked**: the playground enabled in the browser (it is in the automated tests), the
real login and sign-up messages, which need the database, Firefox, Safari,
screen readers or reCAPTCHA with real keys.

### Coverage per component

| Module | Lines and branches covered |
|--------|----------------------------|
| `lexer.py` | 100 % |
| `parser.py` | 99 % |
| `checker.py` | 99 % |
| `interpreter.py` | 99 % |
| `diagnostics.py` | 98 % |
| `cli.py` | 92 % |
| `api.py` | 100 % |
| `tooling.py` | 96 % |
| `ast_nodes.py`, `pipeline.py`, `prelude.py`, `schemas.py`, `tokens.py`, `values.py` | 100 % |
| `mcp_server.py` | 30 % measured (see below) |
| `__main__.py`, `worker.py` | 0 % measured (see below) |

What is left uncovered, and why:

- **`worker.py` and `mcp_server.py`** are really tested, but as separate processes:
  `tests/test_worker.py` launches the process and sends it requests, and `tests/test_mcp.py` starts the
  server and talks to it through the MCP protocol. The measurement does not follow child processes, so
  their percentage does not reflect what runs.
- **`tooling.py`**: in the text output, the path of a program that was never analyzed, the
  refined types block of `nex context`, a loop clause written without an explanation, and
  the two messages of `nex symbols` when there are no symbols to show.
- **`__main__.py`** (two lines) runs in all the tests that launch `python -m nexora` in
  a separate process, but the measurement does not follow child processes.
- **`cli.py`**: the branch that runs if the terminal does not allow changing the encoding to UTF-8, and
  the one that redirects the output when the reader closes. The second one is tested with a real process,
  outside the measurement.
- **`diagnostics.py`**: asking for a line that does not exist in the file.
- The defensive branches of the interpreter that would only be reached with a defect of the checker are
  explicitly excluded from the measurement in `pyproject.toml`.

**High coverage does not prove that the program is correct.** It shows that almost all the code
runs in some test; not that all combinations of inputs have been tested.

## What each file checks

| File | Tests | What it checks |
|------|-------|----------------|
| `test_lexer.py` | 51 | Tokens, literals, comments, line endings, positions, invalid characters, unclosed texts |
| `test_parser.py` | 68 | Valid programs, precedence, shape of the tree, every syntax error with its position, recovery after an error, nesting limits |
| `test_checker.py` | 56 | `main`, variables, scopes, duplicate declarations, calls, order of the stages |
| `test_warnings.py` | 69 | The three warnings (`W2001`, `W2002`, `W2003`): what each reports, what it must not report, that they never stop a program, and that the examples have none |
| `test_types.py` | 140 | Inference, annotations, every operator with every combination of types, conversions, conditions |
| `test_refined_types.py` | 68 | Refined types (`type Name = Base where condition`): that constants are checked by the static analysis (`E2017`) and any other value only when checked with `Name(x)` while the program runs (`E4003`) |
| `test_functions.py` | 56 | Parameters, arguments, returns, return paths, `if` / `else`, functions that return nothing, recursion and its limit |
| `test_contracts.py` | 50 | `needs` and `promises` that hold and that fail, types of the conditions, `result`, content of the diagnostics |
| `test_example_clauses.py` | 43 | The `example` clause as the static analysis sees it: syntax, types, names, the own-call rule and the call graph. It evaluates no example ([decision 0008](decisions/0008-ejemplos-y-nex-test.md)) |
| `test_text_operations.py` | 184 | The functions of a type (`Text.length`, `Int.parse`…) and the ordering between texts: every case of the decision, their requirements and suggestions, huge texts, rounding and limits of `Float`, the syntax of the dot and its errors, that 0.5.1 programs do not change, and `inspect`, `symbols`, `context` and the capabilities ([decision 0011](decisions/0011-operaciones-sobre-textos.md)) |
| `test_loops.py` | 96 | `var`, assignments, loops with their measure and their invariants: analysis, every diagnostic with its iteration and its values, that no loop hangs (not in `nex test` either), and what `inspect`, `symbols` and `context` show ([decision 0010](decisions/0010-var-y-while.md)) |
| `test_interpreter.py` | 47 | Output of programs, integer and decimal arithmetic, overflow, division by zero |
| `test_out_of_memory.py` | 20 | A program that runs out of memory while it runs: the `E3007`. The `MemoryError` is caused on purpose, so no test exhausts the real memory ([decision 0009](decisions/0009-memoria-agotada.md)) |
| `test_diagnostics.py` | 16 | Text format, JSON format, and that the registry of codes matches the specification |
| `test_inspect.py` | 9 | The JSON schema of `nex inspect`: nodes, fields, types and positions |
| `test_cli.py` | 74 | Commands, options, exit codes and formats; also with the real command in a separate process, from other directories |
| `test_examples.py` | 80 | Every program of `examples/`: output, diagnostics and exit code, compared with the recorded ones |
| `test_nex_test.py` | 46 | The evaluation of examples: the engine, `nexora.api.test_source` and the `nex test` command, with the cases of the matrix of the decision ([decision 0008](decisions/0008-ejemplos-y-nex-test.md)) |
| `test_docs.py` | 178 | Every program of the documentation and its output; links; version; that the CLI reference and the list of codes are complete |
| `test_security.py` | 76 | That the interpreter does not evaluate Python code, what a program can do, which modules each file can import, that the analysis tools do not run |
| `test_records_syntax.py` | 25 | The grammar of records: declaration, construction, access, chains and the assignment to a field ([decision 0014](decisions/0014-registros-nominales-inmutables.md)) |
| `test_records_types.py` | 27 | The types of records, their nominal identity, forward references and cycles |
| `test_records_values.py` | 24 | What a record does when it runs: construction, reading, equality by value and immutability |
| `test_records_diagnostics.py` | 18 | The three codes of records: title, category, message, position and order |
| `test_records_tools.py` | 11 | The new nodes of the tree and the `records` field of the context |
| `test_input_arguments.py` | 11 | The arguments a program was run with: empty, multiple, with spaces and with Unicode ([decision 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)) |
| `test_input_stdin.py` | 14 | The standard input: several lines, an empty line and the end of the input (`E3009`) |
| `test_permissions_files.py` | 23 | Files and permissions: the three rules of the model, path confinement and the errors of the file system |
| `test_permissions_static.py` | 12 | What the static analysis detects of missing declarations (`E2026`) |
| `test_permissions_environments.py` | 8 | That the playground worker and the MCP server always reject access to files |
| `test_robustness.py` | 86 | Truncated, mutated, random, binary, huge or very nested inputs; regressions of real defects |
| `test_api.py` | 42 | Checking and running code in memory (`nexora.api`), with its output and text limits |
| `test_worker.py` | 23 | The single-use process of the playground: valid and invalid requests, limits, environment |
| `test_tooling.py` | 85 | The JSON Schemas and that the real output meets them; symbols, references and context; the partial analysis with syntax errors, including a program cut at every character; that the analysis neither runs nor opens files; that the CLI and the API return the same |
| `test_tooling_tasks.py` | 19 | The nine [reference tasks](ai-tooling.md#reference-tasks) against the real tools |
| `test_mcp.py` | 35 | The MCP server through its real protocol: startup, discovery of tools, calls, rejected arguments, that no tool runs code, shutdown |

`test_mcp.py` needs the MCP SDK, which is part of the development dependencies. If it is not
installed, its tests are skipped.

## How they are made

### Three levels

1. **Unit.** They call a stage (lexer, parser, checker, interpreter) and check its
   result: tokens, shape of the tree, error codes, output.
2. **Integration.** They call `cli.main` with a list of arguments and a temporary file, and
   check standard output, standard error and exit code.
3. **End to end.** They launch the real command (`python -m nexora`, and the installed `nex`
   executable) in a separate process, as a person would.

### Recorded outputs

`tests/golden/examples/` stores, for each example, what `nex run` and `nex check` write. The
tests compare character by character. That way a change that alters a message, a position or a
result does not go unnoticed.

### Executable documentation

The NEXORA code blocks of the Markdown files carry a marker comment
(`<!-- nex:run -->`, `<!-- nex:check-fails -->`…) that says how to check them. `test_docs.py`
runs each one and compares the output the documentation shows with the real one. A complete
program without a marker makes the tests fail. The markers are described at the beginning of
`tests/test_docs.py` and in [`CONTRIBUTING.md`](../CONTRIBUTING.md#programs-in-the-documentation).

### Lists that cannot drift apart

There are tests whose only purpose is to prevent two descriptions of the same thing from diverging:

| What | Where it is described | It is compared with |
|------|-----------------------|---------------------|
| Error codes, titles and categories | `docs/language-spec.md`, `docs/diagnostics.md` | The registry of `diagnostics.py` |
| Nodes and fields of the tree | `docs/inspect-schema.md` | The classes of `ast_nodes.py` |
| Commands, options and exit codes | `docs/cli-reference.md` | The argument parser of `cli.py` |
| Version | `README.md` and other pages | `version.py` and the installed package |
| Examples | `examples/README.md` | The files of `examples/` |
| Keywords and built-in functions | The valid examples | `tokens.py`, `checker.py` |

### Tests with generated inputs

`test_robustness.py` subjects the interpreter to inputs that nobody would write on purpose:

- Every valid example, cut at **every** character and with **every** element removed.
- 3000 random sequences of elements of the language and 1500 mutations of valid programs, with
  a fixed seed so that the result is reproducible.
- Files of random bytes through the command line.
- Huge programs and programs with extreme nesting.

The condition is always the same: the result has to be an accepted program or NEXORA
diagnostics. A Python exception is a failure of the test.

### Regressions

Every real defect found has a test that reproduces it, with the prefix `test_regression_`
in `test_robustness.py`:

| Defect | Test |
|--------|------|
| An integer literal of more than 4300 digits caused an internal error | `test_regression_very_long_integer_literal` |
| A binary file produced one error per character, without limit | `test_regression_a_binary_file_does_not_produce_one_error_per_byte` |
| The message of an exhausted stack claimed "more than 1000 calls" when that was not true | `test_regression_stack_exhaustion_is_not_described_as_a_thousand_calls` |
| In the JSON of `nex inspect`, a field of contracts replaced the node kind | `test_regression_contract_field_does_not_overwrite_the_node_kind` |

And, in `test_cli.py`, the early close of the reader of the output
(`test_process_reader_that_stops_early`), which used to be shown as an internal error.

## Packaging

It is not an automated test of the suite; it is checked by hand with these steps.

```bash
python -m pip install build
python -m build
```

It produces `dist/nexora_lang-0.6.0-py3-none-any.whl` (the interpreter and the `nex` command) and
`dist/nexora_lang-0.6.0.tar.gz` (in addition: documentation, examples and tests).

Checked on 15 October 2026 for 0.6.0, with both packages built from
commit `5324619` (that of `v0.6.0`), on Windows 11 with Python 3.12.10:

| Check | Result |
|-------|--------|
| Installing the `.whl` in a new virtual environment, without network access (`pip install --no-index`) | Correct; it installs no other dependency |
| `nex --version`, `nex run` and `python -m nexora check` from that environment | Correct |
| Extracting the `.tar.gz` into an empty folder, creating an environment, `pip install -e ".[dev]"` | Correct |
| `ruff` and the full test suite (`pytest --cov`) in that clean copy | No errors: 1600 tests passed and 4 skipped (the POSIX ones), coverage of 94.48 % |

Those figures are from the copy extracted from the `.tar.gz`. In the repository itself, the full suite was not
repeated on commit `5324619`.

The second check is equivalent to starting from a clean clone: it shows that the source code
package contains everything needed to install, test and document the project.

The package is published on PyPI as `nexora-lang` since version 0.9.0; the steps are in
[Installation](installation.md#publishing).

## Continuous integration

At the root of the repository, `.github/workflows/nexora-ci.yml` defines the same checks for
GitHub Actions: analysis of the code, tests with coverage and building the package, on Linux,
Windows and macOS with Python 3.11, 3.12 and 3.13.

**That workflow runs on every change to `main`.** The first real run, on 21 October
2026, found three macOS differences that had not been seen until then: the operating system
adds `__CF_USER_TEXT_ENCODING` to every child process, the disk is case-insensitive,
and the macOS kernel accepts the address space limit but does not apply it.
All three are fixed, and [Limitations](limitations.md) and [Playground](playground.md)
say which limits macOS does not enforce.

The `README` shows no status badge.

## What the tests do not cover

- **Other platforms.** They have been run on Windows 11 with Python 3.12 and on Linux (Ubuntu 24.04
  on WSL 2) with Python 3.11, 3.12 and 3.13, and on Linux, Windows and macOS by the continuous
  integration. Other distributions and Linux without WSL, no.
- **Performance guarantees.** The benchmark suite records a small local baseline; it does not
  enforce thresholds or compare platforms.
- **Unlimited time and memory.** A program can take time or use memory indefinitely; there
  are no tests about it because the interpreter does not prevent it.
- **Exhaustiveness.** The tests with generated inputs are a sample of a few thousand cases, not
  a proof.
- **Correctness of contracts.** It is tested that contracts are checked when they should be, not that
  they prove anything about a program.
- **Documentation blocks without `fn main` and without a marker** (fragments that illustrate a rule)
  are not run.
- **The MCP server inside a real assistant.** The automated tests use the SDK client.
  There is a single manual check with Claude Code, described in
  [MCP server](mcp.md#check-in-claude-code).
- **No AI model.** The reference tasks measure the deterministic tools.
- **The isolation of the playground with containers** has not been run. The POSIX limits of the worker,
  launched as a process without a container, have, on Linux.
- **The server against real services**: MySQL (sessions, accounts and OAuth are tested with
  a simulated database), Google and GitHub, reCAPTCHA, nginx, HTTPS, shutdown with `systemctl
  stop` and the MySQL backups.
- **The website of the project** (`web/`): the playground and the guide have tests in `servidor/test/`
  (logic of the editor, API, links); the visual appearance and the rest of the pages, no.
- **Installing the package in a clean environment** has not been repeated since the analysis
  tools were added. The package is built without errors and includes the schemas and the
  `nex-mcp` command, but the complete check of [Packaging](#packaging) is older.
