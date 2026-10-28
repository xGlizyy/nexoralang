"""Keep the native editor highlighters aligned with the NEXORA language catalog."""

import json
import re
from pathlib import Path

import pytest

from nexora.checker import BUILTINS
from nexora.tokens import KEYWORDS, OLD_CLAUSE_WORDS, RESERVED_WORDS
from helpers import in_continuous_integration

ROOT = Path(__file__).resolve().parents[2]
INTEGRATIONS = ROOT / "editor-integrations"
HELIX_GRAMMAR = INTEGRATIONS / "helix" / "tree-sitter-nexora" / "grammar.js"

if not HELIX_GRAMMAR.is_file():
    if in_continuous_integration():
        pytest.fail(f"editor integrations are missing ({INTEGRATIONS})", pytrace=False)
    pytest.skip("editor integrations are included in the source repository, not source distributions",
                allow_module_level=True)


def _grammar_words(name: str) -> set[str]:
    source = HELIX_GRAMMAR.read_text(encoding="utf-8")
    match = re.search(rf"const {name} = \[([\s\S]*?)\];", source)
    assert match, f"missing {name} catalog in the Helix grammar"
    return set(re.findall(r'"([^"\\]+)"', match.group(1)))


def test_helix_grammar_tracks_the_lexer_keywords_and_reserved_words():
    assert _grammar_words("keywords") == set(KEYWORDS) - {"true", "false"}
    assert _grammar_words("reserved") == set(RESERVED_WORDS) | set(OLD_CLAUSE_WORDS)


def test_helix_grammar_tracks_builtin_functions_and_constructors():
    constructors = {"Some", "None", "Ok", "Err"}
    assert _grammar_words("builtins") == set(BUILTINS) - constructors
    assert _grammar_words("constructors") == constructors


def test_helix_grammar_tracks_the_language_types():
    grammar = HELIX_GRAMMAR.read_text(encoding="utf-8")
    primitive = re.search(r"primitive_type:.*?choice\(([^)]*)\)", grammar, re.DOTALL)
    compound = re.search(r"compound_type:.*?choice\(([^)]*)\)", grammar, re.DOTALL)
    assert primitive and compound
    assert set(re.findall(r'"([^"\\]+)"', primitive.group(1))) == {
        "Int", "Float", "Bool", "Text", "Void",
    }
    assert set(re.findall(r'"([^"\\]+)"', compound.group(1))) == {"List", "Option", "Result"}


def test_neovim_and_emacs_catalogs_track_language_tokens():
    neovim = (INTEGRATIONS / "neovim" / "syntax" / "nexora.vim").read_text(encoding="utf-8")
    emacs = (INTEGRATIONS / "emacs" / "nexora-eglot.el").read_text(encoding="utf-8")

    def vim_words(group: str) -> set[str]:
        match = re.search(rf"^syntax keyword nexora{group} (.+)$", neovim, re.MULTILINE)
        assert match, f"missing Neovim {group} catalog"
        return set(match.group(1).split())

    def emacs_words(variable: str) -> set[str]:
        match = re.search(rf"\(defconst nexora--{variable}\s+'\(([^)]*)\)\)", emacs)
        assert match, f"missing Emacs {variable} catalog"
        return set(re.findall(r'"([^"\\]+)"', match.group(1)))

    assert vim_words("Keyword") | vim_words("Boolean") | vim_words("Operator") == set(KEYWORDS)
    assert vim_words("Reserved") == set(RESERVED_WORDS) | set(OLD_CLAUSE_WORDS)
    assert vim_words("Constructor") == {"Some", "None", "Ok", "Err"}
    assert vim_words("Type") == {"Int", "Float", "Bool", "Text", "Void", "List", "Option", "Result"}
    assert emacs_words("keywords") == set(KEYWORDS)
    assert emacs_words("reserved-words") == set(RESERVED_WORDS) | set(OLD_CLAUSE_WORDS)
    assert emacs_words("builtin-functions") == set(BUILTINS) - {"Some", "Ok", "Err"}
    assert emacs_words("constructors") == {"Some", "None", "Ok", "Err"}
    assert emacs_words("primitive-types") | emacs_words("compound-types") == {
        "Int", "Float", "Bool", "Text", "Void", "List", "Option", "Result",
    }


def test_editor_configs_recognize_only_nexora_source_files():
    helix = (INTEGRATIONS / "helix" / "languages.toml").read_text(encoding="utf-8")
    neovim = (INTEGRATIONS / "neovim" / "ftdetect" / "nexora.vim").read_text(encoding="utf-8")
    emacs = (INTEGRATIONS / "emacs" / "nexora-eglot.el").read_text(encoding="utf-8")
    assert 'file-types = ["nex"]' in helix
    assert re.search(r"\*\.nex", neovim)
    assert r"\.nex\\'" in emacs


def test_helix_highlights_are_lexical_and_never_run_programs():
    grammar = HELIX_GRAMMAR.read_text(encoding="utf-8")
    query = (HELIX_GRAMMAR.parent / "queries" / "highlights.scm").read_text(encoding="utf-8")
    assert "LSP, not this recovery-friendly" in grammar
    assert "@keyword" in query and "@type.builtin" in query
    assert "@error" in query
    assert "interpreter" not in grammar.lower()

    generated_nodes = {
        node["type"]
        for node in json.loads((HELIX_GRAMMAR.parent / "src" / "node-types.json").read_text(encoding="utf-8"))
    }
    query_nodes = set(re.findall(r"^\(([^()\s]+)\)", query, re.MULTILINE))
    assert query_nodes <= generated_nodes
