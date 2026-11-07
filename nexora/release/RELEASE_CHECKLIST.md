# Release checklist

Every release of `nexora-lang` goes through these steps, in this order, and this file is attached to the GitHub release of
each tag `vX.Y.Z` by `nexora-release.yml`. The reasons and the commands are in
[the release process](../docs/release-process.md); what to do when a published artifact is bad is in
[the yank policy](../docs/yanking.md). A step that was skipped is written down in the release notes with its reason: a
release is not announced with a step silently missing.

## Before the tag

- [ ] The release has its version in one place, `nexora/src/nexora/version.py`, and every reference that has to follow it
      (READMEs, installation file names, the first lines of the language specification, `npm/package.json`, the supported
      releases table of `SECURITY.md`) says the same. Historical references are not touched.
- [ ] `nexora/CHANGELOG.md` has a section for the version, with the date, and **Incompatible changes** lists everything that
      can stop an existing program or script, each with its migration. Nothing is left under "Unreleased".
- [ ] A change of the language or of a stable contract has its decision in `nexora/docs/decisions/`, and the compatibility
      tests of [the compatibility policy](../docs/compatibility.md) pass.
- [ ] No open issue labelled P0 or P1 (`gh issue list --label P0,P1 --state open`); each one that is closed says how.
- [ ] `ruff check src tests` and the whole `pytest` suite pass on the release commit, and so do `npm test` in `npm/` and the
      jobs of `nexora-ci.yml` (Linux, Windows and macOS; every Python of the support target).
- [ ] The jobs of `nexora-selfhost.yml` pass: the seed is the fixed point of the sources, and the native tools give the same
      output as the Python ones.
- [ ] The release commit is on `main` by a fast-forward or a rebase (no merge commit), reviewed in its pull request.

## The tag

- [ ] The tag `vX.Y.Z` is annotated and points at the tip that `main` has, with the subject of the release commit as its
      message. A tag is never moved or reused: a bad release gets a new version.
- [ ] `nexora-release.yml` passes for the tag: the wheel, the source distribution and the npm package agree on name, version,
      licence and the bytes of every module; the source distribution installs in a clean environment; `SHA256SUMS` is
      written and verified.
- [ ] If the release changes the native tools, the tag `native-vX.Y.Z` is made too, and `nexora-native-release.yml` publishes
      the five packages, each with the one-line `.sha256` of its archive.

## Publishing

- [ ] The three files that are published to PyPI and npm are the ones attached to the GitHub release, byte for byte
      (`sha256sum -c SHA256SUMS` over the downloaded files); nothing is rebuilt on a laptop.
- [ ] `twine upload` of the wheel and the source distribution, and `npm publish` of the `.tgz`.
- [ ] A clean install from each registry gives the same hashes as `SHA256SUMS` (`pip download nexora-lang==X.Y.Z --no-deps`,
      `npm pack nexora-lang@X.Y.Z`) and runs `nex --version` and a program.

## After

- [ ] The supported releases table of `SECURITY.md` names the new release.
- [ ] A defect found after the tag is a new patch release; if it is a security or integrity problem, follow
      [the yank policy](../docs/yanking.md).
- [ ] `nexora/docs/1-0-readiness.md` and the roadmap are updated if the release changes the status of a gate.
