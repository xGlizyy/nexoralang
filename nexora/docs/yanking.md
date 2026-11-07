# Yank policy

What the project does when a published release turns out to be bad, and when a release is withdrawn from the places where people
get it. It applies to `nexora-lang` on PyPI and npm, to the GitHub release of `vX.Y.Z`, and to the native packages of
`native-vX.Y.Z`. It extends the [security policy](../../SECURITY.md) (how to report, response targets, supported releases)
and the [release process](release-process.md).

## Words

- **Yank** (PyPI) and **deprecate** (npm) mean that the version stays downloadable by whoever asks for it exactly, but package
  managers stop choosing it for an open version range, and installing it prints a reason. Nothing is deleted.
- **Withdraw** a GitHub release means marking it as a pre-release and putting the reason at the top of its notes, so that
  "latest" is the fixed release. Its files stay, with their hashes.
- A version number, a tag and a published file are **never reused, moved or deleted**. The fix is always a new version.
  The only exception is a file that has to be removed by law or because it contains a secret; the release notes then say
  that it was removed and why.

## When a release is yanked

A release is yanked when staying available to a range install does harm that a new release cannot undo by itself:

| Reason | Example | Yank? |
|--------|---------|-------|
| **Security**: a way to break what the security policy lists as in scope, or what the [threat model](threat-model.md) says is protected | A program reads a file outside the folders it was granted | Yes, from the confirmation of the report |
| **Integrity**: an artifact is not what the release says | The three artifacts disagree, a published hash is wrong, a file was tampered with, a token was used by someone else | Yes, at once |
| **Does not install or run**: a clean install fails, or `nex` cannot run the example of the README, on a platform of the support target | A wheel that lacks a module | Yes |
| **Wrong data**: a defect that makes a checked program give a wrong answer or a stable output wrong | A contract that is not checked | Yes, if no workaround is simple |
| **Licence or legal** | A file with the wrong licence | Yes |
| **Any other defect** | An error message with a typo, a slow command, a limit that is too low | No: a patch release |

When in doubt about a defect that is not about security or integrity, the project does not yank: a yanked version still
installs by exact pin, but range installs skip it, and that surprises people.

## What is done, and how fast

The targets count from the moment the maintainer **confirms** the problem (the security policy has the targets from the
report to that point):

1. **Within 2 business days**: the release is yanked or deprecated on PyPI and npm with the reason in one sentence and the
   fixed version, and the GitHub release is marked as a pre-release with the same text.
2. **Within 2 business days**: `CHANGELOG.md` and the supported releases table of `SECURITY.md` say which versions are
   affected, what to do (update, or a workaround while there is no fix), and the version that fixes it. For a security
   problem, a note under "Known issue" in `SECURITY.md` and, when the report came through a private advisory, the advisory.
3. **As soon as it is safe**: the fixed release, as a new patch version, through the whole [checklist](../release/RELEASE_CHECKLIST.md).
   A fix that cannot wait for the whole checklist still goes through the check of the artifacts and the tests that pin the
   defect; what was skipped is written in the release notes.
4. **After the fix**: a regression test that fails on the old behaviour is part of the fix.

The native tools are handled the same way with their own tag: the affected `native-vX.Y.Z` is marked as a pre-release with
the reason, and `native-vX.Y.(Z+1)` replaces it.

## A compromised artifact or credential

If an artifact, a registry token or the workflow's permissions may have been used by someone who is not the maintainer:

1. Revoke the tokens and rotate the credentials first, then yank.
2. Yank every version published since the earliest moment the compromise could have happened, not only the one found.
3. Publish the hashes of the good files (`SHA256SUMS` of each release) and say which published hashes are not in them.
4. Publish the fixed version from a clean checkout through the workflow, and say in the advisory how a user can tell.
5. Write down what happened, what was affected and what changed to prevent it, in `CHANGELOG.md` and in the advisory.

## What a yanked version looks like afterwards

It keeps its tag, its release, its files and its entry in the changelog, where the entry now starts with the word **Yanked**,
the date and the reason. The supported releases table names only the fixed release. The version is listed in the changelog
forever: someone who finds it in an old lock file has to be able to see why it was withdrawn.

## What a user does

- A security notice in `SECURITY.md` or in the release notes of a version you use: update to the version it names. If you cannot
  update, follow the workaround in the notice.
- A yank warning during an install: it is a reason to read the note before going on. Installing a yanked version by exact pin
  still works, on purpose.
- To check that what you have is a good file, compare its hash with the `SHA256SUMS` of the fixed release (see the
  [release process](release-process.md)).
