# Compatibility and versioning policy

This is the public policy for changes to NEXORA programs and releases. It complements the
[interface stability policy](interface-stability.md), which defines the exact guarantees for each
public tool and protocol.

## What is stable today

NEXORA is currently before 1.0. The language specification and programs written for it may change
incompatibly between minor `0.y` releases. The package version does not replace the independent
language specification version.

This does not cancel existing interface promises: the documented `nex` CLI, stable diagnostics and
versioned JSON schemas remain governed by the [interface stability policy](interface-stability.md),
including while the package is `0.x`. LSP, MCP and the Python tooling API are experimental; other
implementation modules are internal.

## Version numbers

### Before 1.0

- A `0.y.z` patch release fixes defects, security issues or documentation without an intentional
  incompatible change to language syntax or semantics or to a stable public interface. A correction
  that makes the implementation conform to specified behavior is a bug fix; its impact is explained
  in the release notes and covered by a regression test.
- A `0.(y+1).0` minor release may add language features and may make incompatible changes to
  language syntax or semantics and to interfaces explicitly marked experimental.
- An intentional incompatible language change gets a new language-specification version and is
  described in the release notes. Stable CLI and JSON contracts continue to follow
  [their separate compatibility guarantees](interface-stability.md).

### Starting with 1.0

Package releases follow Semantic Versioning:

- **Patch (`1.x.y`)** fixes defects without intentionally changing documented behavior or stable
  interfaces. A correction to behavior that contradicted the specification is a bug fix; its impact
  is called out in the release notes and pinned by a regression test.
- **Minor (`1.y.0`)** adds backward-compatible features. It may deprecate a stable feature under the
  process below.
- **Major (`x.0.0`)** may remove deprecated stable features or make other intentional incompatible
  changes.

The stable CLI, diagnostics and JSON rules in
[Public interfaces and stability](interface-stability.md) apply in every release. Experimental
interfaces may change incompatibly before they are declared stable; such changes are still listed in
the release notes.

## Deprecation and incompatible changes

Every intentional incompatible change must be announced before release and recorded in
`CHANGELOG.md` under **Incompatible changes**. The change must identify affected versions and
behavior, explain the reason, and provide a migration guide with before/after examples. A
`docs/decisions/` record is required when the language design or a stable contract changes.

For a stable feature in 1.x, the release that introduces deprecation must name its replacement and
provide migration guidance. The feature remains available through at least one later minor release;
removal is allowed only in a subsequent major release. Experimental features do not have a guaranteed
deprecation period, but their incompatible changes are announced in the release notes.

Provide an automated migration with `nex migrate` when the transformation is safe and deterministic.
When intent cannot be inferred safely, document the manual steps and make the migration tool report
what it cannot decide instead of guessing.

## Required compatibility tests

The change and its migration are not ready to release until the relevant checks pass:

- Add regression tests for the new rule and tests that prove the old syntax or behavior is rejected
  or translated as documented.
- For an automated migration, compare a representative old-version corpus with the migrated
  programs. Check syntax or structure, exit status and output, examples, and unchanged source bytes
  where applicable, as done by the equivalence checks for decision 0019.
- Keep the stable CLI command, option, exit-code, diagnostic and JSON-schema compatibility tests
  passing. A breaking JSON shape requires a new schema identifier and tests for both identifiers
  where the old one remains supported.
- Run the project test suite and the package-install checks required by CI before merging.

Each pull request declares whether it changes existing behavior and links the changelog entry,
migration guidance and tests when it does. The checklist is in
[the pull request template](../../.github/PULL_REQUEST_TEMPLATE.md).

## Support period

Only the latest published release of each component receives bug and security fixes. A new published
release replaces the previous one immediately; there is no overlapping support window, LTS branch or
backport commitment. This policy applies before and after 1.0 unless a future public policy says
otherwise. The current supported release numbers and vulnerability-reporting response targets are
listed in the repository-level [security policy](../../SECURITY.md).

