// A lexical tree-sitter grammar for editor highlighting. The LSP, not this recovery-friendly
// lexer grammar, is authoritative for syntax and type errors.
const keywords = [
  "fn", "let", "var", "return", "if", "else", "while", "for", "in", "needs", "gives",
  "promises", "trust", "example", "keeps", "shrinks", "uses", "type", "enum", "match", "where", "import",
  "pub", "and", "or", "not",
];

const reserved = [
  "assert", "break", "const", "continue", "test", "try", "requires",
  "ensures", "invariant", "decreases",
];

const constructors = ["Some", "None", "Ok", "Err"];

const builtins = [
  "print", "to_text", "to_float", "to_int", "args", "input", "read_file", "write_file",
  "Net.get", "Process.run", "Text.length", "Text.slice", "Text.contains", "Text.starts_with",
  "Text.ends_with", "Int.can_parse", "Int.parse", "Float.can_parse", "Float.parse",
  "List.length", "List.get", "List.append", "List.concat", "List.contains",
  "Option.is_some", "Option.is_none", "Option.value_or", "Option.value",
  "Result.is_ok", "Result.is_err", "Result.value_or", "Result.value", "Result.error",
];

module.exports = grammar({
  name: "nexora",
  word: ($) => $.identifier,
  extras: () => [/\s/, /\uFEFF/],

  rules: {
    source_file: ($) => repeat(choice(
      $.comment,
      $.string,
      $.number,
      $.boolean,
      $.keyword,
      $.reserved_word,
      $.primitive_type,
      $.compound_type,
      $.builtin_constructor,
      $.builtin_function,
      $.invalid_arrow,
      $.operator,
      $.punctuation,
      $.identifier,
    )),

    comment: () => token(seq("//", /[^\r\n]*/)),
    string: ($) => seq(
      "\"",
      repeat(choice($.escape_sequence, $.invalid_escape, token.immediate(/[^"\\\r\n]/))),
      token.immediate("\""),
    ),
    escape_sequence: () => token.immediate(seq("\\", /[nt"\\{]/)),
    invalid_escape: () => token.immediate(seq("\\", /[^nt"\\{\r\n]/)),
    number: () => token(choice(/[0-9][0-9_]*\.[0-9][0-9_]*/, /[0-9][0-9_]*/)),
    boolean: () => token(choice("true", "false")),
    keyword: () => token(prec(1, choice(...keywords))),
    reserved_word: () => token(prec(1, choice(...reserved))),
    primitive_type: () => token(prec(1, choice("Int", "Float", "Bool", "Text", "Void"))),
    compound_type: () => token(prec(1, choice("List", "Option", "Result"))),
    builtin_constructor: () => token(prec(1, choice(...constructors))),
    builtin_function: () => token(prec(2, choice(...builtins))),
    invalid_arrow: () => token("->"),
    operator: () => token(choice("=>", "==", "!=", "<=", ">=", "=", "+", "-", "*", "/", "<", ">")),
    punctuation: () => token(choice("(", ")", "{", "}", "[", "]", ",", ":", ".")),
    identifier: () => /[A-Za-z_][A-Za-z0-9_]*/,
  },
});
