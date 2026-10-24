"""The VS Code extension: that it follows the language and that it is coherent.

The extension is not JavaScript the language can check on its own, so what is
checked here is what ties it to the language: the grammar names the words the
lexer knows, the manifest points at the files that exist, and the language
configuration agrees with the comments the lexer reads.
"""

import json
import re
from pathlib import Path

from nexora.checker import BUILTINS
from nexora.tokens import KEYWORDS, OLD_CLAUSE_WORDS, RESERVED_WORDS

EXTENSION = Path(__file__).resolve().parents[2] / "vscode-nexora"


def _manifest() -> dict:
    return json.loads((EXTENSION / "package.json").read_text(encoding="utf-8"))


def _grammar() -> dict:
    return json.loads((EXTENSION / "syntaxes" / "nexora.tmLanguage.json").read_text(encoding="utf-8"))


def _configuration() -> dict:
    return json.loads((EXTENSION / "language-configuration.json").read_text(encoding="utf-8"))


def test_the_manifest_declares_the_language_of_the_project():
    manifest = _manifest()
    languages = manifest["contributes"]["languages"]
    assert [language["id"] for language in languages] == ["nexora"]
    assert ".nex" in languages[0]["extensions"]
    assert (EXTENSION / languages[0]["configuration"]).is_file()


def test_the_manifest_points_at_the_grammar_that_exists():
    manifest = _manifest()
    grammar = manifest["contributes"]["grammars"][0]
    assert grammar["language"] == "nexora"
    assert (EXTENSION / grammar["path"]).is_file()
    assert grammar["scopeName"] == _grammar()["scopeName"]


def test_the_manifest_declares_the_commands_and_the_settings():
    manifest = _manifest()
    commands = {command["command"] for command in manifest["contributes"]["commands"]}
    assert {"nexora.check", "nexora.restartServer"} <= commands
    properties = manifest["contributes"]["configuration"]["properties"]
    assert {"nexora.python.path", "nexora.trace.server", "nexora.format.enable", "nexora.format.onSave"} <= set(properties)


def test_the_grammar_names_every_keyword_of_the_language():
    grammar = _grammar()
    keywords = grammar["repository"]["keywords"]["patterns"]
    named = " ".join(pattern["match"] for pattern in keywords)
    for word in KEYWORDS:
        assert word in named, word


def test_the_grammar_names_every_reserved_word_of_the_language():
    grammar = _grammar()
    reserved = grammar["repository"]["reserved"]["patterns"][0]["match"]
    for word in RESERVED_WORDS:
        assert word in reserved, word


def _words_of(patterns: list[dict]) -> set[str]:
    """The alternatives of every `\\b(a|b|c)\\b` pattern, as whole words."""
    return {word for pattern in patterns for group in re.findall(r"\\b\(([^)]*)\)\\b", pattern["match"])
            for word in group.split("|")}


def test_the_clause_words_of_0_11_are_reserved_and_not_keywords():
    # Decision 0019, 9: they stay reserved for one minor version, so they are not highlighted as
    # keywords, and 'ai' and 'tool' are ordinary names.
    grammar = _grammar()["repository"]
    keywords, reserved = _words_of(grammar["keywords"]["patterns"]), _words_of(grammar["reserved"]["patterns"])
    assert set(OLD_CLAUSE_WORDS) <= reserved
    assert not set(OLD_CLAUSE_WORDS) & keywords
    assert not {"ai", "tool"} & (keywords | reserved)
    assert keywords >= set(KEYWORDS)


def test_the_grammar_names_every_built_in_function_of_the_language():
    grammar = _grammar()
    patterns = [pattern["match"] for pattern in grammar["repository"]["builtins"]["patterns"]]
    for name in BUILTINS:
        assert any(re.search(pattern, name) for pattern in patterns), name


def test_the_grammar_names_the_types_of_the_language():
    grammar = _grammar()
    types = " ".join(pattern["match"] for pattern in grammar["repository"]["types"]["patterns"])
    for name in ("Int", "Float", "Bool", "Text", "Void", "List", "Option", "Result"):
        assert name in types, name


def test_the_grammar_reads_the_files_of_the_language():
    grammar = _grammar()
    assert grammar["fileTypes"] == ["nex"]
    assert grammar["scopeName"] == "source.nexora"


def test_the_language_configuration_uses_the_comment_the_lexer_reads():
    configuration = _configuration()
    assert configuration["comments"]["lineComment"] == "//"


def test_the_extension_asks_for_the_language_it_serves():
    manifest = _manifest()
    assert "onLanguage:nexora" in manifest["activationEvents"]
    assert manifest["contributes"]["grammars"][0]["language"] == "nexora"


def test_the_extension_has_what_the_marketplace_asks_for():
    manifest = _manifest()
    # The icon, the licence and the banner.
    icon = manifest.get("icon")
    assert icon, "the marketplace needs an icon"
    assert (EXTENSION / icon).is_file()
    assert (EXTENSION / "LICENSE").is_file()
    assert manifest.get("galleryBanner")
    # And the rest of what a published extension carries.
    for field in ("publisher", "name", "displayName", "description", "version", "engines", "categories"):
        assert manifest.get(field), field
    assert manifest["engines"]["vscode"]
    assert manifest["repository"]["url"]


def test_the_documentation_names_the_publisher_that_the_manifest_declares():
    """The README tells which publisher is needed; it must be the real one."""
    manifest = _manifest()
    readme = (EXTENSION / "README.md").read_text(encoding="utf-8")
    assert f"`{manifest['publisher']}`" in readme
    # The full name of the extension in the marketplace is publisher.name.
    assert f"{manifest['publisher']}.{manifest['name']}" in readme
