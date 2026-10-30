"""Keep the public compatibility and incompatible-change process explicit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent
POLICY = ROOT / "docs" / "compatibility.md"


def test_policy_covers_pre_1_and_1_x_release_rules():
    text = POLICY.read_text(encoding="utf-8")

    for required in (
        "Before 1.0",
        "0.y.z",
        "0.(y+1).0",
        "Starting with 1.0",
        "Patch (`1.x.y`)",
        "Minor (`1.y.0`)",
        "Major (`x.0.0`)",
        "stable CLI",
        "versioned JSON schemas",
    ):
        assert required in text


def test_incompatible_change_process_requires_notice_migration_and_tests():
    policy = POLICY.read_text(encoding="utf-8")
    template = (REPOSITORY / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")

    for required in (
        "announced before release",
        "CHANGELOG.md",
        "affected versions",
        "migration guide",
        "before/after examples",
        "regression tests",
        "nex migrate",
        "at least one later minor release",
        "subsequent major release",
    ):
        assert required in policy

    for required in (
        "Does this change behavior",
        "Incompatible changes",
        "migration guidance",
        "regression, compatibility",
    ):
        assert required in template


def test_support_window_matches_the_public_security_policy():
    text = " ".join(POLICY.read_text(encoding="utf-8").split())
    security_policy = " ".join((REPOSITORY / "SECURITY.md").read_text(encoding="utf-8").split())

    assert "Only the latest published release of each component" in text
    assert "no overlapping support window, LTS branch or backport commitment" in text
    assert "Only the most recent published release of each component receives security fixes" in security_policy


def test_compatibility_policy_is_listed_in_public_documentation():
    index = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "[Compatibility and versioning](compatibility.md)" in index
    assert "[compatibility and versioning policy](docs/compatibility.md)" in contributing
    assert "## Unreleased" in changelog
    assert "### Incompatible changes" in changelog
