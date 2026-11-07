# Release process

How a release of `nexora-lang` is made and how anyone can check that what they installed is what was released. The steps
are in the [release checklist](../release/RELEASE_CHECKLIST.md), which is attached to the GitHub release of every tag; this
page says why each part exists. For a bad release see the [yank policy](yanking.md), and for what may change between
versions the [compatibility policy](compatibility.md).

## What a release is

One version, three artifacts, and the hashes of the three:

| Artifact | File | Where it is published |
|----------|------|-----------------------|
| Wheel | `nexora_lang-X.Y.Z-py3-none-any.whl` | PyPI, GitHub release |
| Source distribution | `nexora_lang-X.Y.Z.tar.gz` | PyPI, GitHub release |
| npm package | `nexora-lang-X.Y.Z.tgz` | npm, GitHub release |
| Hashes | `SHA256SUMS` | GitHub release |

The three carry the same interpreter. The npm package is a launcher that includes a copy of the Python modules, so a defect
in the copy would be a defect in the release: the check below compares them.

The native tools (`nex`, `nexora-lsp`, `nex-mcp`, the formatter and the worker) have their own tag, `native-vX.Y.Z`, and their
own workflow ([decision 0027](decisions/0027-herramientas-nativas-por-defecto.md)). Each of their five packages is published
with a `.sha256` file that has one line: the hash of the archive.

## How the artifacts are checked

`nexora-release.yml` runs for every tag `vX.Y.Z`, for every change of the packaging files in a pull request, and by hand. It
builds the three artifacts once, and then runs [`release/check_artifacts.nex`](../release/check_artifacts.nex), a program
written in NEXORA that the workflow runs with a native `nex` built from the seed of the compiler (a C compiler and nothing
else). Python only builds the wheel and the source distribution, as a Python package needs. The check fails, naming every
difference, unless:

- the three have the name `nexora-lang` and the same version, the version that `nexora/version.py` ships is that one, it is
  the version of `src/nexora/version.py` and, for a tag, the tag is `v` plus the version;
- the wheel and the source distribution have the same licence and the same `Requires-Python`, and the npm package the same
  licence;
- **every Python module of the interpreter has the same SHA-256 in the wheel, in the source distribution and in the npm
  package**;
- each one carries the licence file, the source distribution has its `pyproject.toml`, the wheel declares the `nex` command
  and the launcher that the npm package names is one of its files.

The workflow also installs the source distribution in a clean environment and runs a program with it, and tests that the
check catches what it is for: a wrong tag, a wrong version, an npm package with one module changed, a missing artifact, two
wheels, a changed hash and a file that `SHA256SUMS` does not list. Each of them must fail with status 5. The examples of the
check itself run first (`nex test release/check_artifacts.nex`).

To run it by hand on a folder `dist/` with the three files, from the repository root, with a native `nex` (it needs `ls`,
`mkdir`, `tar`, `unzip` and `sha256sum`, so Linux, macOS, or Git Bash on Windows):

```bash
nex run --allow-read . --allow-write . --allow-process ls --allow-process mkdir --allow-process tar \
    --allow-process unzip --allow-process sha256sum \
    nexora/release/check_artifacts.nex -- sums dist work vX.Y.Z X.Y.Z
```

`sums` checks and then writes `dist/SHA256SUMS`; `check` only checks; `verify` compares the three files with an existing
`SHA256SUMS`. `-` instead of the tag or the version skips that comparison. A failure ends the program with status 5, which is
the status of a contract: NEXORA cannot yet choose an exit status ([readiness](1-0-readiness.md)).

## Publishing exactly what was checked

The files that are published to PyPI and npm are the ones attached to the GitHub release, not new builds:

```bash
gh release download vX.Y.Z --pattern '*.whl' --pattern '*.tar.gz' --pattern '*.tgz' --pattern SHA256SUMS
sha256sum -c SHA256SUMS
twine upload nexora_lang-X.Y.Z*
npm publish nexora-lang-X.Y.Z.tgz
```

That is what makes the hashes in the release the hashes of what people install.

## Checking what you installed

```bash
pip download nexora-lang==X.Y.Z --no-deps --dest check
npm pack nexora-lang@X.Y.Z --pack-destination check
gh release download vX.Y.Z --pattern SHA256SUMS --dir check
(cd check && sha256sum -c SHA256SUMS)
```

A file whose hash is not in `SHA256SUMS` did not come from the release. If PyPI or npm serve something that does not match,
that is a supply-chain problem: report it as a vulnerability ([SECURITY.md](../../SECURITY.md)).

## Who and when

The maintainer decides when a release is made and authorizes each step that is visible outside the repository: the merge, the
tag, and the publication to the registries. The workflow never publishes to PyPI or npm and uses no secret: it needs only the
token of the workflow, to attach files to the release of the tag.
