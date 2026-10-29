# Deploying NEXORA applications

This guide gives a reproducible baseline for running a NEXORA application on Windows, macOS,
Linux and Linux containers. It pins the interpreter distribution and Python patch release, keeps
configuration outside the source code, and uses only a virtual environment. NEXORA itself has no
third-party runtime dependencies.

## Recommended deployment model

Install the Python package from PyPI inside an application-specific virtual environment. Pin
`nexora-lang` to an exact release in `requirements.txt`, and pin Python in `.python-version`.
This is the shortest path to a repeatable install and works the same way with or without Node.js.

The npm package is a convenient launcher for people who already use npm, but it still needs a
separately installed Python. It does not bundle Python or install operating-system runtimes. For
deployed applications, installing the Python package directly avoids an extra launcher layer.

The reference application uses Python **3.13.18** and NEXORA **0.14.1**. The commands use uv to
provision that exact Python patch consistently on Windows, macOS and Linux; uv downloads managed
CPython distributions and the Python version is recorded in `.python-version`. Install uv using
its [official installation instructions](https://docs.astral.sh/uv/getting-started/installation/).
uv supplies managed CPython builds, so it can provide the pinned patch even when an OS vendor has
not packaged it yet. For a new deployment, select a security-patched Python patch in the
supported 3.11–3.13 range, pin it in `.python-version`, and update the pin promptly when Python
publishes a security release. Keep NEXORA pinned to the release the application was verified
against; upgrade it deliberately and rerun the application's checks before deployment.

## Reference application

The runnable example is in [`docs/examples/deployment/`](examples/deployment/). It contains the
application source, `.python-version`, an exact `requirements.txt`, external config examples,
cross-platform launchers and a Linux container recipe.

The program reads `config/app.conf` using NEXORA's explicit file capability. Keep secrets out of
the example and source control: provide a deployment-owned config file with restrictive file
permissions, or mount it from the platform's secret/configuration store. Do not put secrets in
command-line arguments because process listings and logs may expose them. NEXORA does not read
environment variables directly; a deployment wrapper can render environment or secret-store
values into the external config file before starting `nex`.

## Windows, macOS and Linux

From the example directory, install the Python patch pinned in `.python-version` and create an
isolated virtual environment. These commands are identical across Windows, macOS and Linux:

```console
uv python install 3.13.18
uv venv --python 3.13.18 .venv
```

Installation needs network access; execution does not. `requirements.txt` contains only the exact
NEXORA runtime release, with no optional or development dependencies:

```console
uv pip install --python .venv -r requirements.txt
cp config/app.conf.example config/app.conf
.venv/bin/nex check app.nex
.venv/bin/nex run app.nex --allow-read config/app.conf
```

PowerShell:

```powershell
uv pip install --python .venv -r requirements.txt
Copy-Item config\app.conf.example config\app.conf
.\.venv\Scripts\nex.exe check app.nex
.\.venv\Scripts\nex.exe run app.nex --allow-read config\app.conf
```

Use [`run.sh`](examples/deployment/run.sh) or [`run.ps1`](examples/deployment/run.ps1) to apply the
same capability grant and run command on each platform. They use the NEXORA installation in
`.venv` and do not resolve packages at startup.

Exclude `.venv/` from source control and deployment archives. Recreate the environment from the
pins instead of copying it between operating systems or machine paths.

## Linux container

The example includes a Dockerfile based on Python 3.13.18 with the multi-platform image pinned by
digest. Build and run it from its directory:

```bash
docker build --tag my-nexora-app:0.1.0 .
docker run --rm --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --mount type=bind,src="$PWD/config/app.conf",dst=/app/config/app.conf,readonly \
  my-nexora-app:0.1.0
```

Build separately for each target architecture. When updating the Python patch, deliberately update
both the tag and multi-platform digest in the Dockerfile. Keep writable data in an explicitly
mounted volume; this example needs none.
Run containers as a non-root user, keep the filesystem read-only where practical, and apply CPU,
memory, process and network limits using the container runtime or orchestrator. Containers reduce
packaging differences; they are not a complete security boundary.

## Reproducibility limits

- The application pins the NEXORA release exactly; NEXORA has no third-party runtime dependencies.
- `.python-version` pins the exact Python patch expected by the example.
- uv, OS packages and the non-container base operating system are supplied by the deployment
  environment. The container base image is pinned by digest; update it deliberately with the
  Python patch and record the image identity with the application release.
- NEXORA runs with the operating-system permissions of the `nex` process. Its file capabilities
  still require both a source declaration and a path grant on the command line. Add execution
  limits such as `--timeout` and `--max-memory` where the host OS supports them; see the
  [CLI reference](cli-reference.md#nex-run).

The reference template is a reproducible install-and-run path, not a claim that every Python patch
or processor architecture has been manually exercised. CI covers Python 3.11, 3.12 and 3.13 on
Windows, macOS and Linux; see [installation support evidence](installation.md#what-has-been-checked).
