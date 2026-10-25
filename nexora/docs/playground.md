# NEXORA Playground

The playground lets you write, check and run NEXORA code from the browser. The code
is sent to the server, which hands it to the **same interpreter used by the `nex` command**, and the page
shows what the interpreter answers. There is no simulated execution nor a second
implementation of the language in JavaScript.

This page describes the architecture, the API, the limits, the real isolation that exists, how to
run it locally and how to deploy it on your own server.

> The code of the server (`servidor/`) and of the website (`web/`) cited here is, since 23
> October 2026, in a separate private repository. This page still describes its design and its
> isolation; the interpreter and the worker (`nexora.worker`) are still in this repository.

## Status

| Part | Status |
|-------|--------|
| Core interface (`nexora.api`) and worker process | Implemented and tested |
| Server API (`/api/playground`) | Implemented and tested |
| Page (`web/playground.html`) | Implemented. Logic tested automatically; the drawing, checked by hand in Chrome |
| Limits of time, size, output, concurrency and requests | Implemented and tested |
| Operating system memory and CPU limits | Implemented for Linux and macOS, but they are only enforced by the operating system where they exist: the CPU one on both, the memory one only on Linux (on macOS, the kernel accepts the address space limit and does not apply it). Tested on Linux (Ubuntu 24.04 on WSL 2) with `tests/test_worker.py`, which launches the worker as a process, without a container; on macOS, only the CPU one. On Windows they do not exist |
| Container isolation (Docker) | Configuration prepared. **Not tested**: there was no Docker on the development machine |
| Deployment on a public server | **Not done** |

**Practical conclusion:** the playground is ready to be used locally and in a trusted environment.
Before opening it on the Internet you have to build the worker image, enable container mode and
complete the [isolation checklist](#checking-the-isolation). Until then, on
a public server it must stay disabled (`PLAYGROUND_ENABLED=false`).

## Architecture

```text
  Browser                            Web server (Node, Express)                 Worker (Python)
  ---------                          ----------------------------               ---------------
  web/playground.html
  web/js/playground/
    view.js        editor and panels
    controller.js  state             POST /api/playground/run
    client.js  ───────────────────►  servidor/src/playground/
                                       router.js   validates the request,
                                                   limits, origin, quota
                                       limiter.js  concurrency and queue
                                       worker.js   launches a process ─────────►  python -I -m nexora.worker
                                                   per request,                    nexora/worker.py
                                                   kills it if slow                  operating system limits
                                                                                   nexora/api.py
                                                                                     check_source / run_source
                                                                                   pipeline.analyze   (lexer, parser, checker)
                                                                                   interpreter.run
                   ◄───────────────────  JSON response  ◄──────────────────────  JSON result
```

Key points:

- **A single core.** `nexora.api` calls `pipeline.analyze` and `interpreter.run`, the same
  functions that `nex` uses. A test runs each example through the command line and through the API and
  compares output and diagnostics.
- **The visitor's code is never run inside the web server.** Each request starts a
  new process, which serves that request and ends. If it takes too long, the server kills it.
- **The server only does transport.** It does not know the grammar nor decide whether a program is valid.
- **The browser only presents.** Syntax highlighting is colouring, not analysis; the lists of
  keywords are requested from the core itself.

### Editor

The editor is deliberately simple: a `<textarea>` over a highlighted copy of the same text,
with a column of line numbers. Neither CodeMirror nor any other library is used, because the website
has no build step nor JavaScript dependencies, and we wanted to keep it that way.

What it offers: the browser's normal editing, selection and undo, highlighting of the real syntax,
automatic indentation, marking of the lines with errors and jumping to the position of a diagnostic.

What it does **not** offer: autocompletion, bracket matching, multiple cursors, code folding nor
its own search.

## API

All the routes are under `/api/playground`. Responses are always JSON.

| Route | Method | Function |
|------|--------|---------|
| `/check` | `POST` | Analyses the program **without running it** |
| `/run` | `POST` | Analyses the program and, if it has no errors, runs it |
| `/status` | `GET` | Whether the playground is enabled (`{"enabled": true}` or `false`). It always answers, also when disabled, and does not start the worker |
| `/info` | `GET` | Language version, words of the language and limits of the service |
| `/examples` | `GET` | The example programs |

The page asks `/status` first. With the playground disabled it does not request `/info` nor `/examples`:
it shows «Disabled» and leaves Run and Check disabled.

### Request

`Content-Type: application/json`.

```json
{
  "code": "fn main() {\n    print(\"Hello from NEXORA\")\n}",
  "filename": "playground.nex"
}
```

| Field | Required | Rule |
|-------|-------------|-------|
| `code` | Yes | Text. At most 64 KiB in UTF-8 |
| `filename` | No | **Virtual** name: it only appears in the diagnostics. Letters, digits, `_` and `-`, ending in `.nex`, up to 64 characters. It is never used as a path and no file is opened |

### Response for a program (HTTP 200)

Schema `nexora.result/1`. It is returned whenever the interpreter could give an answer,
whether the program has errors or not.

```json
{
  "schema": "nexora.result/1",
  "action": "run",
  "status": "success",
  "output": "Hello from NEXORA\n",
  "diagnostics": [],
  "message": null,
  "duration_ms": 104,
  "version": "0.12.0"
}
```

| Field | Meaning |
|-------|-------------|
| `schema` | Name and version of the format |
| `action` | `"check"` or `"run"` |
| `status` | See the following table |
| `output` | What the program wrote. Empty in `check` and when the program did not get to start |
| `diagnostics` | The diagnostics of the interpreter, in the `nexora.diagnostics/1` format ([specification, section 11.4](language-spec.md#114-json-format)): category, code, message, file, line, column and suggestion |
| `message` | Explanation when the state is not a diagnostic (a limit reached). `null` otherwise |
| `duration_ms` | Time measured by the server, including the start of the worker |
| `version` | Version of NEXORA that answered |

| `status` | Meaning | `output` |
|----------|-------------|----------|
| `success` | `check`: no errors. `run`: the program finished | Full output |
| `invalid` | Lexical, syntax, semantic or type errors. **The program was not started** | Empty |
| `runtime_error` | The program failed while running | What was written until the failure |
| `contract_violation` | A `needs` or `promises` condition was false | What was written until the failure |
| `timeout` | It exceeded the maximum time and was stopped | Empty: the process was killed |
| `output_limit` | It wrote more than allowed and was stopped | The first bytes, up to the limit |
| `memory_limit` | It needed more memory than allowed (only where the operating system limits it). If memory ran out while the program was running, `diagnostics` contains the `E3007` | What was written until then |

A program with errors is **not** an HTTP error: the request was served correctly.

### Error response (HTTP 4xx and 5xx)

When the request is not valid or the service cannot serve it:

```json
{
  "schema": "nexora.result/1",
  "status": "error",
  "error": { "code": "code_too_large", "message": "The program is larger than the limit of 65536 bytes." }
}
```

| HTTP | `error.code` | When |
|------|--------------|--------|
| 400 | `invalid_json` | The body is not valid JSON |
| 400 | `invalid_request` | The body is not a JSON object |
| 400 | `missing_code` | The `code` field is missing |
| 400 | `invalid_code_type` | `code` is not a text |
| 400 | `invalid_filename` | `filename` is not a simple name ending in `.nex` |
| 403 | `origin_not_allowed` | The request comes from another website |
| 404 | `not_found` | Non-existent route or method |
| 413 | `code_too_large` | The program exceeds the maximum size |
| 415 | `unsupported_media_type` | The request is not `application/json` |
| 429 | `rate_limited` | Too many requests from the same client |
| 503 | `busy` | All the workers are busy and the queue is full. Includes `Retry-After` |
| 503 | `runtime_unavailable` | The worker did not start or did not give a valid answer |
| 503 | `playground_disabled` | The playground is disabled on this server |
| 500 | `internal_error` | Unexpected failure of the service |

Error responses never contain traces, server paths nor the code sent.

The page tells three situations apart and presents them differently: **the program** has a
problem (diagnostics), **the service** rejects or cannot serve the request (the message of
`error`), or **there is no connection** with the server ("Unable to reach the NEXORA runtime. Your code is
still available in the editor.").

## Limits

They are all configured in `servidor/.env` (see `servidor/.env.example`). Changing them requires restarting
the server.

| Limit | Initial value | Variable | What happens when exceeded |
|--------|---------------|----------|-------------------------|
| Program size | 64 KiB | `PLAYGROUND_MAX_CODE_BYTES` | HTTP 413 |
| Execution time | 2 s | `PLAYGROUND_TIMEOUT_MS` | The process is killed; state `timeout` |
| Output | 64 KiB | `PLAYGROUND_MAX_OUTPUT_BYTES` | The program is stopped; state `output_limit` |
| Length of a text | 262 144 characters | `PLAYGROUND_MAX_TEXT_CHARS` | Runtime error `E3006` |
| Worker memory | 512 MiB | `PLAYGROUND_MEMORY_MB` | State `memory_limit`. **Only on Linux**: on macOS, the operating system accepts the limit but does not apply it |
| Programs at once | 4 | `PLAYGROUND_MAX_CONCURRENT` | The following ones wait in the queue |
| Waiting requests | 8 | `PLAYGROUND_MAX_QUEUE` | HTTP 503 `busy` |
| Requests per client | 30 per minute | `PLAYGROUND_RATE_LIMIT`, `PLAYGROUND_RATE_WINDOW_MS` | HTTP 429 |
| Nested calls | 1000 | (of the language) | Runtime error `E3004` |

Time is measured from when the worker starts, so it includes the start of Python (in the order of
a tenth of a second) or of the container (slower: measure it on your server and adjust the limit).

## Security and isolation

The playground accepts code from any visitor. This is what protects it, by layers, and what
each layer does **not** cover.

### 1. The language

A NEXORA program can only compute and write text. There is no construct to use
the network, run other programs nor access environment variables, and the interpreter does not use `eval`
nor `exec`. It is checked by `tests/test_security.py`.

Files exist in the language, but **the playground does not allow them**: the worker has no
field in its protocol to grant them and the environment of the worker does not allow them, so a
program that uses them stops with `E3008` even if it declares the capability
([decision 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)). The same happens with
standard input and with arguments: the protocol does not carry them.

*Does not cover:* a defect of the interpreter, nor the consumption of time and memory.

### 2. The worker process

- A separate process per request, with an **empty environment**: it receives no variable from the server
  (neither database passwords nor OAuth secrets). On Windows the system adds on its own
  a few basic user variables; none comes from the server.
- It starts in an empty temporary directory, with Python in isolated mode (`-I`).
- The server kills it when it exceeds the maximum time and discards a response that is too large.
- The worker limits the output and the length of texts.
- On Linux and macOS it asks the operating system for limits on CPU, file creation and process
  creation, and a timer that ends the process even if the server does not. The memory
  limit (the address space of the process) is only requested and enforced on Linux: on macOS, the
  kernel accepts it and does not apply it.

*Does not cover:* **this is not a sandbox.** The worker runs with the same user and the same
permissions as the web server: if the interpreter had an exploitable defect, that process could
read whatever the server user can read. On Windows, moreover, there is no memory limit; on
macOS, the memory limit exists but the operating system does not enforce it: only the maximum
time and, in a container, its limits hold it back.

### 3. The container (required for a public service)

With `PLAYGROUND_WORKER_COMMAND`, each request runs in a single-use Docker container:
without network (`--network none`), with a read-only file system, without capabilities, unable to
gain privileges, as an unprivileged user, and with limits on memory, CPU and number of processes.
Only the local image `nexora-worker` is used, which Docker never downloads (`--pull never`).

*Does not cover:* a failure of Docker itself or of the system kernel. And **it is not tested yet**.

### 4. The service

- Only requests from the site itself are accepted (`Origin` header); no CORS headers are sent
  except for the origins of `PLAYGROUND_ALLOWED_ORIGINS`.
- Request quota per client, maximum request size, limited concurrency and queue.
- The output of a program is always treated as text: the API returns it inside a JSON and the
  page writes it with `textContent`. In addition, the playground page is served with a content
  security policy that prevents running scripts other than those of the site.
- **Nothing is stored.** The code is neither stored nor written to the server logs; the
  logs only record the type of failure. The code is kept in the browser tab
  (`sessionStorage`) while it is open. There is no analytics.

### Honest summary

| Exposure level | Is the current isolation adequate? |
|---------------------|-------------------------------------|
| On your machine, for development | Yes |
| On an internal network or with trusted users | Yes, on Linux, with process mode |
| Public on the Internet | **Only with container mode, and after checking it.** Process mode on its own is not enough |

## Running it locally

Requirements: Node.js 22.23.2 or later on the 22 branch, or 24.18.1 or later on the 24 branch; Python
3.11 or newer and, for the user accounts of the website, MySQL or MariaDB (the playground itself does not use
the database).

```bash
# 1. The interpreter
cd nexora
python -m venv .venv
.venv/bin/python -m pip install -e .          # Windows: .venv\Scripts\python.exe -m pip install -e .

# 2. The server
cd ../servidor
npm install
cp .env.example .env                          # fill in the database and set PLAYGROUND_ENABLED=true
npm run migrate
npm start
```

The playground is only enabled with `PLAYGROUND_ENABLED=true`. `.env.example` leaves it disabled
(`PLAYGROUND_ENABLED=false`), and it also stays disabled if the variable is not defined or is
empty: the API answers 503 (`playground_disabled`) on every route except `/status`. Any
other value (`True`, `1`…) prevents the server from starting. **A local installation that already has its `servidor/.env` and wants to use the
playground has to add `PLAYGROUND_ENABLED=true` explicitly**: before, it was enough not to
define it. Write it in your `servidor/.env` and restart the server. Use it only for controlled local
tests: the server listens on all the interfaces of the machine, so, if your firewall lets
connections in to port 3000, other machines on your network will also be able to use it.

Open <http://localhost:3000/playground>.

The server looks for the interpreter in `nexora/.venv`. If it is somewhere else, point to it with
`NEXORA_PYTHON`.

Quick check of the API, without a browser:

```bash
curl -s http://localhost:3000/api/playground/info
curl -s -X POST http://localhost:3000/api/playground/run \
  -H "Content-Type: application/json" \
  --data '{"code": "fn main() {\n    print(6 * 7)\n}"}'
```

The second command has to return `"status":"success"` and `"output":"42\n"`.

## Tests

```bash
cd nexora   && python -m pytest tests/test_api.py tests/test_worker.py
cd servidor && npm test
```

| File | What it checks |
|---------|---------------|
| `nexora/tests/test_api.py` | `check_source` and `run_source`; output and text limits; that the API and `nex` give the same result on every example |
| `nexora/tests/test_worker.py` | The worker process: protocol, malformed requests, isolated mode. The operating system limits run on Linux and macOS; the memory one, only on Linux |
| `servidor/test/playground-api.test.js` | The API over HTTP against the real interpreter: validation, HTTP codes, schema, limits, timeout, concurrency, worker failures, worker environment, origins, and parity with the command line |
| `servidor/test/playground-containers.test.js` | The life cycle of the containers with a fake Docker (`test/fixtures/fake-docker.js`), without Docker: a unique name per request, removal and confirmation after a timeout, an excessive response or an error, slot occupied until confirmed, limited attempts, no attempt if the tool does not start, and the [container command format](#container-command-format): the command documented in `.env.example`, this guide and the `Dockerfile`, options missing, repeated, with another value or unknown, and elements after the image |
| `servidor/test/playground-config.test.js` | Enabling with the real configuration: disabled without `PLAYGROUND_ENABLED`, empty or `false`; enabled only with `true`; error at startup with any other value; `/status` and 503 on the other routes without starting the worker, and a real program with `true`; in production, that the playground enabled without the container command prevents starting |
| `servidor/test/playground-frontend.test.js` | The logic of the page (client, state, highlighting) against a real server and with simulated failures |
| `servidor/test/web-guide.test.js` | The examples of the web guide and the links between pages |

### Checked by hand in the browser

The part of the page that draws and receives the keyboard (`view.js`) has no automatic tests: the
project does not include a test browser. It was checked in Chrome, on 14 October 2026:

| Check | Result |
|--------------|-----------|
| Initial load: example, version, list of examples, no errors in the console | Correct |
| Typing with the keyboard: automatic indentation, highlighting, line numbers | Correct |
| Run: button disabled and indicator while it runs; real output | Correct |
| Check with errors: diagnostics tab, counter, marked line, jump to the position | Correct |
| Shortcuts Ctrl+Enter and Ctrl+Shift+Enter | Correct |
| Output with HTML (`<img onerror=…>`): it is shown as text, not interpreted | Correct |
| Loading an example with unsaved changes: warning and Undo | Correct |
| Reset with and without changes | Correct |
| Copy | Correct |
| The code survives reloading the page | Correct |
| Without connection to the server: its own message, the code is kept | Correct |
| Mobile width (390 px): stacked panels, no overflow, all buttons visible | Correct |
| The page cannot be embedded in another site (`frame-ancestors` policy) | Correct |

It was not tested in Firefox nor in Safari, nor with screen readers.

## Deploying on your own server

These instructions **have not been run**: there was no access to the server. They describe a
deployment on a Linux VPS, with free software. Adapt paths and names.

### 1. Dependencies

- Node.js 22.23.2 or later on the 22 branch, or 24.18.1 or later on the 24 branch (`engines` in
  `servidor/package.json`). Install the latest version of the branch.
- Python 3.11 or newer.
- MySQL or MariaDB (for the accounts of the website).
- nginx as a reverse proxy, with a TLS certificate (for example, from Let's Encrypt).
- Docker, to isolate execution.

### 2. Installing

```bash
sudo useradd --system --create-home --home-dir /srv/nexora nexora
sudo -u nexora git clone <your-repository> /srv/nexora/app
cd /srv/nexora/app

# Interpreter (for process mode and for the checks)
python3 -m venv nexora/.venv
nexora/.venv/bin/python -m pip install ./nexora

# Server
cd servidor && npm ci --omit=dev
cp .env.example .env && chmod 600 .env        # fill in the database, PUBLIC_URL, etc.
npm run migrate
```

The secrets (database password, OAuth credentials) only go in `servidor/.env`,
which is not uploaded to the repository.

### 3. Worker image

The playground only runs the local image `nexora-worker`. The command carries `--pull never`, so
Docker never downloads it from a registry: the operator builds it on the server itself, from
the code being deployed.

```bash
cd /srv/nexora/app
docker build -f servidor/playground/Dockerfile -t nexora-worker .
docker image inspect nexora-worker --format '{{.Id}} {{.Created}}'   # it exists, and which one it is
```

- Build it before enabling the playground and build it again on every update (step 8):
  it contains its own copy of the interpreter. Each request creates a new container, so the
  next request already uses the rebuilt image.
- To pin a version, build it also with a tag (`-t nexora-worker:0.12.0`) and write that
  tag at the end of the command (`"nexora-worker:0.12.0"`). To go back to a previous version that
  you keep, change the tag of the command and restart the service. The tag is the only thing in the
  command that can be changed.
- If the image is not on the machine (it was not built, or it was deleted with `docker image rm` or
  `docker image prune -a`), every execution fails without running anything. According to the Docker manual, with
  `--pull never` it answers `No such image` and does not create the container, and then the API returns 503
  `runtime_unavailable`. That path is tested with a fake Docker that rejects the command with
  code 125, not with real Docker.
- `--pull` exists since Docker 20.10.0 (release notes of that version). The Docker manual writes it
  `--pull=never`; the Nexora command uses two elements (`"--pull","never"`), which according to the source
  code of the Docker client is equivalent, because `--pull` is a text option without an implicit default
  value. With a version earlier than 20.10, Docker should reject the option and not
  run anything. Neither of the two things has been checked with the installed version.
- Do not upload it to a registry to use it here: the server would not download it.
- **The tag is mutable.** `nexora-worker` and `nexora-worker:<tag>` are local names, not
  a fingerprint of their content. Whoever has access to the Docker daemon of that machine can re-tag
  another image with that name (`docker tag`, `docker build -t`), and the server would run it
  without noticing the change: it does not check which image is behind the name. That the Nexora
  image is the one that runs depends, therefore, on controlling who accesses the machine and the Docker daemon.

In `servidor/.env`:

```bash
NODE_ENV=production
TRUST_PROXY=loopback
LISTEN_HOST=127.0.0.1
PUBLIC_URL=https://tu-dominio.example
PLAYGROUND_ENABLED=false
PLAYGROUND_WORKER_COMMAND=["docker","run","--rm","-i","--init","--pull","never","--name","{container}","--network","none","--read-only","--cap-drop","ALL","--security-opt","no-new-privileges","--pids-limit","32","--memory","256m","--memory-swap","256m","--cpus","0.5","--user","65534:65534","--tmpfs","/tmp:rw,size=1m,noexec","nexora-worker"]
PLAYGROUND_TIMEOUT_MS=4000
```

**The playground stays disabled** until the
[isolation check](#checking-the-isolation) is complete. Only the exact value `true` enables it;
`false`, an empty value or not defining the variable leave it disabled, and any other value
(`True`, `1`…) prevents the server from starting. Do not define it in the environment of the service either
(`Environment=` in systemd or an exported variable): that value takes precedence over
`servidor/.env`, and a forgotten `PLAYGROUND_ENABLED=true` there would enable it.

Notes:

- The user that runs the server has to be able to use Docker. **Belonging to the `docker` group
  is equivalent to having administrator permissions on that machine.** It is the trade-off of this design: the
  visitor's code is locked in, in exchange for the web server being able to launch containers.
- **Docker in *rootless* mode is not supported for now.** To find its daemon, the `docker`
  command would need `DOCKER_HOST`, or the `-H` or `--context` options. But the accepted command does not
  allow global options, and the server only passes `PATH` and `SystemRoot` to the commands it launches,
  so the `docker` command uses the default daemon of the system. Supporting it would require changing the
  contract and the environment of the worker, and it is a pending decision.
- Starting a container per request is slower than starting a process. Measure how long it takes on your
  server and adjust `PLAYGROUND_TIMEOUT_MS`; the initial value of 2 s may not be enough.
- Killing the `docker run` command does not stop the container. That is why the command carries
  `"--name","{container}"`: the server puts a new name in the placeholder on every request
  (`nexora-pg-` and a UUID) and, if the container did not end well (timeout, response too
  large or unreadable, client error), it removes it with `docker rm -f` and checks with `docker ps`
  that it no longer exists. The worker slot is not released until that confirmation. It tries up to six
  times, separated by waits of 1, 2, 4, 8 and 16 s (31 s of waiting in total). Each attempt runs
  two commands, and each command is killed if it takes more than 10 s; if all of them reach that limit, up
  to 120 s more are added, without counting how long a command that was already killed takes to end. If no attempt
  confirms, the slot stays occupied until the server is restarted and the log records
  `container not confirmed stopped`.
- **If the server crashes** (a failure, a `kill`, a power cut of the machine), there is no guaranteed automatic
  cleanup of the containers it had running: the server only removes those of
  the requests it is serving, and at startup it does not look for those that were left. According to the code,
  moreover, those containers do not count towards `PLAYGROUND_MAX_CONCURRENT` after restarting the
  server. To see the ones that may be left:

  ```bash
  docker ps -a --filter name=nexora-pg- --format '{{.Names}}  {{.Status}}  {{.CreatedAt}}'
  ```

  That filter also lists containers of requests in progress, if the server is already running.
  Before removing one, check it: that the name is `nexora-pg-` followed by a UUID, that it is from
  the image `nexora-worker` and that it was created before the crash (`docker inspect -f '{{.Config.Image}}
  {{.Created}} {{.State.Status}}' <name>`). Only then remove it by hand with `docker rm -f
  <name>`. Neither this nor the crash have been checked with real Docker.
- `--init` makes process 1 of the container the Docker init and not Python, which as process
  1 would ignore signals without a handler, such as the one of the worker timer. **Not checked with
  real Docker yet.**
- `TRUST_PROXY=loopback` is required behind nginx so that the per-client quota uses the real
  address of the visitor and not that of the proxy. With `loopback`, `X-Forwarded-For` is only taken into account if
  the connection comes from the machine itself: a direct connection from another machine cannot
  make up its address. **But it trusts any process of the machine itself** that can connect
  to the server, not only nginx: on its own it does not protect against a malicious local process.
  `TRUST_PROXY=1` also works behind nginx, but it trusts any connection, wherever it
  comes from. The limits count IPv6 addresses per /56 block and, in addition, per /48 block.
- `LISTEN_HOST=127.0.0.1` makes the server listen only on the machine itself: even if the
  firewall left port 3000 open, it could not be reached from outside. Without it, it listens
  on all the interfaces, as in development. It only accepts an IP address: `localhost` stops the
  server at startup, because Node can resolve it to `::1` (that happens on Windows 11 with Node 24) and
  then it would not serve an nginx pointing to `127.0.0.1`. At startup, the server writes on which address
  it listens and warns if `TRUST_PROXY` and `LISTEN_HOST` do not match. **Not checked on a real VPS.**
- With `NODE_ENV=production`, the server sends HSTS only on the requests that arrive over HTTPS
  (nginx marks them with `X-Forwarded-Proto`, and `TRUST_PROXY` makes the server believe it).

#### Container command format

`PLAYGROUND_WORKER_COMMAND` accepts a single container command: the one above. The server
checks it at startup and, if it does not comply, it does not start and says what fails. The rules are:

1. It starts with `"docker","run"`: `docker` without a path and `run` right after.
2. Then come the options of the table, **each one exactly once and with that exact value**,
   in any order. An option with a value goes in two elements (`"--memory","256m"`).
3. The last element is the local image: `nexora-worker` or `nexora-worker:<tag>`. The
   tag follows the Docker grammar: letters, digits, `_`, `.` and `-`, not starting with `.` nor
   with `-`, and up to 128 characters. No other name, path, registry nor digest is accepted.
   The tag is the only thing that can be changed.

| Option | Value |
|--------|-------|
| `--rm` | — |
| `-i` | — |
| `--init` | — |
| `--read-only` | — |
| `--pull` | `never` |
| `--name` | `{container}` |
| `--network` | `none` |
| `--cap-drop` | `ALL` |
| `--security-opt` | `no-new-privileges` |
| `--pids-limit` | `32` |
| `--memory` | `256m` |
| `--memory-swap` | `256m` |
| `--cpus` | `0.5` |
| `--user` | `65534:65534` |
| `--tmpfs` | `/tmp:rw,size=1m,noexec` |

The options go before the image because the Docker client stops reading options when it reaches
it and passes what follows to the program of the container (`SetInterspersed(false)` in its source code).
According to that, a `"--name","{container}"` written after the image would leave the container with a
random name, and the server could not remove it. It has not been observed with real Docker: it is in
the [isolation check](#checking-the-isolation).

**Not accepted:**
- another `docker run` option, nor the aliases of those in the table (`-m`, `-u`, `--net`,
  `--interactive`…);
- the `--option=value` form, not even `--pull=never`, although it is the one shown in the Docker manual;
- combined flags (`-it`) nor `--`;
- anything after the image, nor another image;
- a path to the executable, `docker.exe`, `sudo`, Podman, `docker container run` nor global
  Docker options.

**What a container command is is decided only by names.** If any element contains
`{container}`, or is an executable called `docker` or `podman` (with a path or `.exe`, in upper or
lower case), the command is treated as a container command and has to be exactly the one above, even if
the playground is disabled. So a process command that meets that condition is rejected. The
other commands are process mode and are not checked. A wrapper script, another tool
(`nerdctl`, `docker.cmd`…) or a Docker executable with another name are outside that detection.
None of them is a supported way of running containers: the server would not validate their command nor
remove their containers.

The values of the table and the image are fixed on purpose: changing a limit, the isolation or the
image is a decision taken in the code (`CONTAINER_OPTIONS` and `CONTAINER_IMAGE` in
`servidor/src/playground/config.js`), with its tests, and not a variation of `servidor/.env`.

The tests of this check (`servidor/test/playground-containers.test.js`) only analyse the
list of arguments and do not run any Docker. Those of the life cycle in the same file use a
fake Docker. None uses real Docker.

Validating the command does not, on its own, guarantee effective isolation either, which also depends on the
configuration of the Docker daemon (`daemon.json`, the default runtime, user
namespaces) and on the installed version. The server checks none of that.

### 4. Service (systemd)

`/etc/systemd/system/nexora.service`:

```ini
[Unit]
Description=NEXORA web
After=network.target mariadb.service docker.service

[Service]
User=nexora
WorkingDirectory=/srv/nexora/app/servidor
ExecStart=/usr/bin/node --env-file=.env src/index.js
Restart=on-failure
# The server shuts itself down on SIGTERM: it waits up to 10 s for the requests in progress and another
# 10 s for the MySQL pool (about 20 s in the worst case). This margin should let it finish before
# systemd kills it with SIGKILL; it has not been tested with systemd.
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/tmp

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nexora
```

The server listens on the port of `PORT` (3000). **Do not expose it directly to the Internet**:
close it in the firewall and let only nginx reach it. The worker does not listen on any
port: it only communicates with the server through its standard input and output.

On `SIGTERM` (`systemctl stop` or `restart`), the server stops accepting connections and
`/api/health` starts answering 503 to the requests that arrive over connections that were already open.
A new connection does not get that 503: after `server.close()` the server no longer accepts it, and whoever
opens it sees the connection refused. The automated tests check it on Windows with a local server
(`ECONNREFUSED`); behind nginx the normal thing would be a 502, but it has not been tested with nginx nor with a
load balancer. From that moment every response carries `Connection: close`, so that a persistent
connection does not hold it back. It waits, at most 10 s, for the requests in progress and for the batch of session
deletion that is in MySQL (no more are sent); then it closes the MySQL pool, another 10 s
at most. If the deletion does not finish in time, the pool is closed anyway;
according to the code of mysql2 3.24.6, each connection is closed after its query in progress, without
cutting it (not yet checked against a real MySQL). It exits with code 0 if everything
finished in time and with 1 if it had to cut something; the log says what.

Each signal is handled only once (`process.once`). A second `SIGTERM`, or a second `SIGINT`,
during the shutdown is no longer received by the server: Node applies its default behaviour and ends the
process on the spot, without waiting for the requests in progress nor closing the MySQL pool. This is deduced from the
code and from the Node documentation; it has not been tested. A `SIGINT` after a `SIGTERM` (or the other way
round) does not interrupt it: it returns the same shutdown in progress (the tests check it by calling the
shutdown twice, without system signals). When `TimeoutStopSec` expires, systemd does not send another
`SIGTERM`, but `SIGKILL`, which does not allow cleaning anything up either.

**Tested only with automated tests on Windows**: the real signal, with systemd, is still untested.

### 5. Reverse proxy (nginx)

**Untested**: this configuration has not been used with a real nginx. It is a starting point that has
to be checked on a test server before publishing. The values of the limits are a
proposal, not a measurement.

```nginx
# In the http block (for example, /etc/nginx/conf.d/nexora-limits.conf): a per-client quota for
# the API, in addition to the limits of the server itself.
limit_req_zone $binary_remote_addr zone=nexora_api:10m rate=10r/s;

server {
    listen 80;
    listen [::]:80;
    server_name tu-dominio.example;
    return 301 https://tu-dominio.example$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name tu-dominio.example;

    ssl_certificate     /etc/letsencrypt/live/tu-dominio.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tu-dominio.example/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    server_tokens off;

    # The largest body the server accepts is that of the playground (about 385 KiB).
    client_max_body_size 512k;

    location /api/ {
        limit_req zone=nexora_api burst=20 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
}
```

- `http2 on;` is the form of nginx 1.25.1 and later. With an earlier version, remove that line and
  write `listen 443 ssl http2;` (and the same for `[::]:443`).
- `proxy_set_header Host $host` is required: the server compares the `Origin` header with `Host`
  to reject requests from other sites.
- `X-Forwarded-Proto` is what lets the server know that the request arrived over HTTPS (with
  `TRUST_PROXY=loopback`) and send HSTS. The server also sends the CSP and the other security
  headers: there is no need to repeat them in nginx.
- `limit_req` slows down a single client before it reaches the server. The limits of the server
  still act behind it (and they are in memory: they are lost on restart).
- The nginx error pages (502 if the server does not answer, 413 if the body is too
  large, 429 of the limit) say nothing about the server. Neither do those of the server: an internal error
  answers `{"error":"Internal server error."}` and leaves in the log only the type and a code.
- `/api/health` can stay open (it reveals nothing) or be restricted to the network of the monitor with
  `allow` and `deny` in a `location = /api/health` of its own.

The certificate can be obtained with Let's Encrypt (for example, `certbot --nginx`), which also
renews it. Then check the renewal with `certbot renew --dry-run`.

### 6. Logs

```bash
journalctl -u nexora -f
```

The server writes one line for each failure of the playground, with the type of failure
(`playground: worker failed`, `playground: worker unavailable`…). It never writes the code sent.

### 7. Verifying the deployment

First, that the process answers:

```bash
curl -s https://tu-dominio.example/api/health
```

It has to answer `{"status":"ok","checks":{"http":"ok"}}`. It only says that the process is running
and serving requests: **it does not check MySQL, Google, GitHub, reCAPTCHA nor the playground**. During a
shutdown it answers 503 with `{"status":"shutting_down"}`, but only over connections that were already open:
new ones are rejected ([Service](#4-service-systemd)). Also check that `http://` redirects to
`https://` (`curl -sI http://tu-dominio.example/` returns 301).

While the playground is disabled, check that it really is:

```bash
curl -s https://tu-dominio.example/api/playground/info
```

It has to answer with HTTP status 503 and the code `playground_disabled`.

The following checks, and those of the next section that use the page or the API, need
the playground enabled. **Do them in a controlled environment, without public exposure**: a test
server that cannot be reached from the Internet, or this same server before opening the site
(with the domain name unpublished or the proxy closed to the outside). In that environment use its own
address instead of `https://tu-dominio.example`.

```bash
curl -s https://tu-dominio.example/api/playground/info
```

It has to answer `"available": true` and the version. If it answers `"available": false`, the worker does not
start: review `PLAYGROUND_WORKER_COMMAND`, that the image exists and that the user can use Docker.

```bash
curl -s -X POST https://tu-dominio.example/api/playground/run \
  -H "Content-Type: application/json" \
  --data '{"code": "fn main() {\n    print(6 * 7)\n}"}'
```

It has to return `"output":"42\n"`. Then open `/playground` in the browser and run the
initial example.

### Checking the isolation

Before announcing the playground, check each point **on the real server**. None has been
checked yet. The rows that use the page or the API need the playground enabled: do them
in a controlled environment, without public exposure (see step 7). Only when all of them give the expected
result, change `PLAYGROUND_ENABLED` to `true` in `servidor/.env` of the public server and restart the
service.

| Check | How | Expected result |
|--------------|------|--------------------|
| The worker works in the container | The command of `PLAYGROUND_WORKER_COMMAND`, written by hand as in the comment of `servidor/playground/Dockerfile`, with a name of your own instead of `{container}` (for example `--name nexora-prueba`: only the server replaces the placeholder, and Docker does not accept it as a name), and with `{"action":"run","code":"fn main() {\n    print(1)\n}"}` on the standard input | A JSON with `"output":"1\n"` |
| No network | `docker run --rm --pull never --network none --entrypoint python nexora-worker -c "import socket; socket.create_connection(('1.1.1.1', 53), 2)"` | It fails |
| Read-only file system | Add `--read-only --entrypoint python … -c "open('/x','w')"` | It fails |
| Unprivileged user | `… --entrypoint id nexora-worker` | `uid=65534` |
| Time limit | Run a slow program from the page (for example `fib(40)`) | State `timeout`; with `docker ps` no container is left after a few seconds |
| Memory limit | A program that doubles a text many times | `E3006` or `memory_limit` (on Linux); the server keeps answering |
| The operating system tests | `python -m pytest tests/test_worker.py` on the server | The two tests marked as POSIX pass on Linux and macOS; the memory limit one, only on Linux |
| Concurrency | Several slow requests at once | Those that do not fit get 503 `busy`; there are never more containers than `PLAYGROUND_MAX_CONCURRENT` |
| *Pending:* the name identifies a single container | With a slow request running, take its name from `docker ps --filter name=nexora-pg-`. Run `docker ps -aq --filter name=^<name>$`, and the same with the name without its last character. Repeat the first one when the request has finished | The first one returns an identifier; the one with the cut name, nothing; the first one, repeated at the end, nothing |
| *Pending:* `--init` is active | With a slow request running, `docker inspect -f '{{.HostConfig.Init}}' <name>` and `docker top <name>` | `HostConfig.Init` is `true`, and the first process shown by `docker top` is `docker-init`. `docker top` shows the processes from outside the container: it indicates that `docker-init` is the first one, it does not prove it as process 1 inside the container. The row «Time limit» also checks that the internal timer of the worker ends the program |
| *Pending:* what goes after the image is not a Docker option | `docker run --rm --pull never --entrypoint python nexora-worker -c "import sys; print(sys.argv)" --name x` | It prints `['-c', '--name', 'x']`, and `docker ps -a --filter name=^x$` lists nothing |
| *Pending:* a name already in use | `docker run -d --rm --pull never --name nexora-prueba --entrypoint sleep nexora-worker 30`, twice in a row | The second one fails because of a name conflict and does not create another container |
| *Pending:* without the image nothing is downloaded | `docker run --rm --pull never nexora-worker:no-existe` | It fails with `No such image`, without downloading anything (`docker image ls` does not change) |

### 8. Updating

```bash
cd /srv/nexora/app && sudo -u nexora git pull
nexora/.venv/bin/python -m pip install ./nexora
docker build -f servidor/playground/Dockerfile -t nexora-worker .
cd servidor && npm ci --omit=dev && npm run migrate
sudo systemctl restart nexora
curl -s https://tu-dominio.example/api/playground/info     # enabled: the new version; disabled: 503
```

The worker image has to be rebuilt on every update of the language: it contains its own
copy of the interpreter. If the command uses a tag (`nexora-worker:0.12.0`), build the image with
the new tag, change it in `PLAYGROUND_WORKER_COMMAND` and restart the service; see
[Worker image](#3-worker-image).

### 9. MySQL backups

**Untested**: no step of this section has been run yet, neither the backup nor the restore.
Until a full restore has been checked on a test server, no backup should be taken
as good.

The database stores accounts (names, emails and password hashes), sessions and links with
Google and GitHub: every backup contains personal data. Store it encrypted, outside the server, with
restricted access, and delete it when the period set by the privacy policy has passed.

The credentials go in an options file, never on the command line (they would be visible in `ps`):

```ini
# /home/nexora-backup/.my.cnf  (chmod 600, owned by the user that makes the backup)
[client]
user=nexora_backup
password=...
```

The backup user only needs to read: `GRANT SELECT, SHOW VIEW, LOCK TABLES ON nexora.* TO
'nexora_backup'@'localhost';`. The backup, consistent without locking the tables (they are all InnoDB):

```bash
mysqldump --single-transaction --quick --default-character-set=utf8mb4 nexora \
  | gzip > nexora-$(date +%F).sql.gz
```

In MariaDB the command is also called `mariadb-dump`. To restore, **first into a different
database**, and check that the tables and the number of rows match:

```bash
mysql -e 'CREATE DATABASE nexora_restore CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'
gunzip -c nexora-AAAA-MM-DD.sql.gz | mysql nexora_restore
mysql -e 'SELECT COUNT(*) FROM nexora_restore.users; SELECT COUNT(*) FROM nexora_restore.oauth_accounts'
```

Only afterwards, with the service stopped (`systemctl stop nexora`), is it restored over the production
database. The sessions in the backup that have already expired are deleted on their own at startup.

### Without Docker

If you cannot use Docker, process mode (without `PLAYGROUND_WORKER_COMMAND`) works on your
machine, and on Linux it applies the operating system limits. **It is not a sandbox**: it runs the code
of the visitors with the permissions of the server. That is why, with `NODE_ENV=production`, the server does not
start with `PLAYGROUND_ENABLED=true` without the accepted container command: it says why and ends. That
the container command is configured does not prove that the isolation works either: you first have to
complete [Checking the isolation](#checking-the-isolation).

## Pending tasks and risks

- Build and test the worker image, and complete the isolation checklist.
- Test on a test server the nginx configuration (redirection to HTTPS, `limit_req`,
  certificate), the shutdown with `systemctl stop` and a MySQL backup restored from start to finish.
- In container mode, the web server user has to be able to use Docker, and that is equivalent to
  having administrator permissions on the machine: whoever compromised the web server would control the
  machine. Before enabling the playground in public it has to be decided how to separate them (for example,
  a separate service, with its own user, that is the only one launching containers).
- Check the operating system limits inside the container. On Linux they already pass with the worker
  launched as a process, without a container ([Tests](testing.md#linux)).
- Measure the start time of a container per request. If it is too much, the alternative is a
  pool of already started workers, which has not been implemented.
- The request quota and the sign-in throttle are kept in the memory of the server: they are
  lost on restart and are not shared between several instances.
- The deletion of expired sessions uses `DELETE … LIMIT`, which is unsafe with statement-based
  replication (`binlog_format=STATEMENT`). With `ROW` (the default value of MySQL 8) or `MIXED` there is no
  problem. If the production MySQL uses `STATEMENT`, it has to be changed to a deletion by primary
  key; it is pending until that server is known.
- The maximum time of each query of the session deletion is the client's (mysql2): the promise fails
  after 30 s, but the statement continues in MySQL and the connection does not go back to the pool until it ends. A
  blocked statement would hold a connection of the pool, the same one used by sign-up and sign-in.
  So as not to pile them up, a pass does not start while the queries of the previous one have not
  finished for mysql2: it is skipped and recorded in the log. A pass that exceeds its maximum time
  (5 minutes) stops sending new batches, but does not cancel the one in progress; the log says so,
  and records how many sessions that pass deleted in total or with what error it ended when it finally finishes. But mysql2 considers a query finished
  when its cap expires even if it continues in MySQL, so a statement that lasted longer than the interval (one
  hour) could add another connection in the next pass. Pending to test with a test MySQL
  a real cancellation (`KILL QUERY` from another connection, or destroying the connection when the time expires).
- The sign-in throttle reserves each attempt before querying the database, so
  simultaneous requests do not get around it. Its state is in memory: it is lost on restart and is not
  shared between several instances of the server.
- The playground has no CAPTCHA: its requests only have the quota per client and per IPv6 /48 network,
  which does not stop an abuse spread across many addresses. Sign-up and sign-in do
  have an antispam (`servidor/src/captcha.js`): Google reCAPTCHA v3, which is only loaded if the person
  accepts it, a honeypot field and a strict limit per client. **Not tested with real Google
  keys**: the tests simulate its responses.
- Sign-in with Google or GitHub (`servidor/src/oauth.js`): the account and its link with the
  provider are created in a transaction, but the session is created afterwards, outside it. If saving the
  session fails, the account is left created and linked without a session, and the person sees `oauth_failed`; according to the
  code, the next attempt finds the link and creates the session. The tests cover those two
  paths separately, with a simulated database, not against MySQL. **Untested**: two simultaneous first
  sign-ins with the same identity can collide (because of the primary key of the link or a
  MySQL deadlock), and one of them would get `oauth_failed`. Sign-up with a password, on the
  other hand, creates the account and its first session in a single transaction.
- Shutdown (`servidor/src/lifecycle.js`): a second `SIGTERM` or `SIGINT` ends the process on the spot,
  without completing the cleanup (untested); and the 503 of `/api/health` only arrives over connections already
  open, because new ones are rejected once `server.close()` has started. See
  [Service](#4-service-systemd). Not tested with real operating system signals, systemd nor
  nginx.
- Pending decision: sign-up answers 409 to an email that already has an account, and that reveals which
  emails are registered. Avoiding it requires confirming the email by mail, which the site does not send.
- Pending product and privacy decision: the consent manager (`web/js/consent.js`) knows how to
  load Google Analytics, Tag Manager and Ads after consent, but none is configured and the
  security policy of the pages (CSP, `servidor/src/security-headers.js`) only allows scripts and
  connections from the site itself: the browser would block them even with consent. The tests of the
  server fail while one is configured. If it is decided to use one, the proposal is that the
  server adds to the CSP only the domains of the configured service, as documented by Google at
  that moment, and only for external scripts: scripts written inside the page would still be
  forbidden. Before that, the cookie and privacy policies would have to be updated.
- The legal pages (`web/aviso-legal.html`, `privacidad.html`, `cookies.html` and `terminos.html`)
  are a draft: they lack the details of the owner and other data, marked in square brackets (such as
  `[NIF O CIF]` or `[DOMINIO]`), and they have no legal review. They must not be published like this. Those
  placeholders can only appear in the legal pages, which warn at the top that they are a draft
  (`servidor/test/web-guide.test.js` checks it). The notice of the sign-up form
  (`web/signup.html`) does not name the data controller: it refers to the privacy policy,
  where it is pending. The legal review must confirm whether that first layer of information is enough
  or whether the form has to name them.
- The page has not been tested in Firefox, in Safari nor with screen readers.
- A program cannot be shared through a link.
