"""Parser: turns tokens into an AST, following the grammar in docs/language-spec.md.

Recursive descent for declarations and statements, precedence climbing for expressions.
A syntax error does not stop the parse: the parser reports it, skips to the next
statement (or the next function) and carries on, so one run can report several
independent mistakes, and what did parse is kept as a partial tree.
"""

from __future__ import annotations

from . import ast_nodes as ast
from .capabilities import CAPABILITIES
from .diagnostics import MAX_DIAGNOSTICS, Diagnostic, Span
from .tokens import Token, TokenType
from .values import VOID

# Limits that keep any accepted program well inside Python's recursion limit.
MAX_NESTING = 64      # parentheses, unary operators, blocks and 'else if' chains inside one another
MAX_EXPRESSION_DEPTH = 256   # depth of an expression tree, e.g. a + b + c + ... (256 terms)

# Binary operators and their precedence (higher binds tighter). All are left-associative.
_PRECEDENCE = {
    TokenType.OR: 1,
    TokenType.AND: 2,
    TokenType.EQUAL_EQUAL: 3,
    TokenType.NOT_EQUAL: 3,
    TokenType.LESS: 3,
    TokenType.LESS_EQUAL: 3,
    TokenType.GREATER: 3,
    TokenType.GREATER_EQUAL: 3,
    TokenType.PLUS: 4,
    TokenType.MINUS: 4,
    TokenType.STAR: 5,
    TokenType.SLASH: 5,
}
_COMPARISON = 3
_COMPARISON_OPERATORS = ("==", "!=", "<", "<=", ">", ">=")

_NAME_KEYWORDS = (
    TokenType.FN, TokenType.LET, TokenType.RETURN, TokenType.IF, TokenType.ELSE, TokenType.TRUE,
    TokenType.FALSE, TokenType.AND, TokenType.OR, TokenType.NOT, TokenType.REQUIRES, TokenType.ENSURES,
    TokenType.TYPE, TokenType.WHERE, TokenType.EXAMPLE, TokenType.VAR, TokenType.WHILE, TokenType.FOR,
    TokenType.IN, TokenType.INVARIANT, TokenType.DECREASES, TokenType.USES,
)
_DECLARATION_KEYWORDS = (TokenType.FN, TokenType.TYPE)
# The clauses that open a function body: the contracts and the examples.
_CONTRACT_KEYWORDS = (TokenType.REQUIRES, TokenType.ENSURES, TokenType.EXAMPLE)
# The clauses that open the body of a loop.
_LOOP_KEYWORDS = (TokenType.INVARIANT, TokenType.DECREASES)
# Hints for the reserved words a program is most likely to reach for.
_RESERVED_HINTS = {
    "break": "There is no 'break': a loop ends when its condition is false or its list is exhausted, or with 'return'.",
    "continue": "There is no 'continue': put the rest of the turn inside an 'if'.",
}
_STATEMENT_END = (TokenType.NEWLINE, TokenType.RBRACE, TokenType.EOF)

# The names of the built-in types. A name that is a type is never a value, so `Text.length`
# is a call to a function of a type and never the reading of a field.
_BUILTIN_TYPE_NAMES = frozenset({"Int", "Float", "Bool", "Text", "Void", "List", "Option", "Result"})

# How many type arguments each built-in type with arguments takes.
_TYPE_ARGUMENT_COUNTS = {"List": 1, "Option": 1, "Result": 2}

# How those numbers are written in a diagnostic.
_TYPE_ARGUMENT_NAMES = {1: "one", 2: "two"}


class ParseError(Exception):
    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.label)
        self.diagnostic = diagnostic


class _TooManyErrors(Exception):
    """Raised to abandon the parse when MAX_DIAGNOSTICS syntax errors have been collected."""


class Parser:
    def __init__(self, tokens: list[Token], type_names: frozenset[str] = _BUILTIN_TYPE_NAMES,
                 record_names: frozenset[str] = frozenset()) -> None:
        self._tokens = tokens
        self._pos = 0
        self._nesting = 0
        self._depths: dict[int, int] = {}
        self._diagnostics: list[Diagnostic] = []
        # The names that declare a type, and the ones that declare a record.
        self._type_names = type_names
        self._record_names = record_names

    def parse(self) -> tuple[ast.Program, list[Diagnostic]]:
        """Returns the program and the syntax errors found.

        When the list is not empty the program is partial: it holds the functions and
        statements that parsed, without the statements that have an error and without the
        functions whose declaration has one. It is for tools; it is never run."""
        types: list[ast.TypeDecl] = []
        records: list[ast.RecordDecl] = []
        uses: list[ast.UsesDecl] = []
        functions: list[ast.Function] = []
        self._skip_newlines()
        try:
            while not self._check(TokenType.EOF):
                try:
                    if self._check(TokenType.TYPE):
                        declaration = self._type_declaration()
                        if isinstance(declaration, ast.RecordDecl):
                            records.append(declaration)
                        else:
                            types.append(declaration)
                    elif self._check(TokenType.USES):
                        uses.append(self._uses_declaration())
                    elif self._check(TokenType.FN):
                        functions.append(self._function())
                    else:
                        raise self._top_level_error()
                except ParseError as error:
                    self._record(error)
                    self._nesting = 0
                    self._synchronize_to_function()
                self._skip_newlines()
        except _TooManyErrors:
            pass

        end = self._peek().span
        start = self._tokens[0].span
        return ast.Program(start.to(end), tuple(types), tuple(functions), tuple(records), tuple(uses)), \
            self._diagnostics

    def _record(self, error: ParseError) -> None:
        """Keeps a syntax error. Stops the whole parse once the limit is reached."""
        self._diagnostics.append(error.diagnostic)
        if len(self._diagnostics) >= MAX_DIAGNOSTICS:
            raise _TooManyErrors

    # Token helpers

    def _peek(self, offset: int = 0) -> Token:
        index = min(self._pos + offset, len(self._tokens) - 1)
        return self._tokens[index]

    def _peek_significant(self, offset: int = 0) -> Token:
        """The next token that is not a line break, without consuming anything."""
        index = self._pos
        found = 0
        while index < len(self._tokens):
            token = self._tokens[index]
            if token.type is not TokenType.NEWLINE:
                if found == offset:
                    return token
                found += 1
            index += 1
        return self._tokens[-1]

    def _check(self, kind: TokenType) -> bool:
        return self._peek().type is kind

    def _advance(self) -> Token:
        token = self._peek()
        if token.type is not TokenType.EOF:
            self._pos += 1
        return token

    def _match(self, kind: TokenType) -> Token | None:
        return self._advance() if self._check(kind) else None

    def _skip_newlines(self) -> None:
        while self._check(TokenType.NEWLINE):
            self._advance()

    def _error(self, code: str, label: str, token: Token | None = None, *, span: Span | None = None,
               hint: str | None = None, notes: tuple[str, ...] = ()) -> ParseError:
        where = span or (token or self._peek()).span
        return ParseError(Diagnostic(code, label, where, hint, notes))

    def _expect(self, kind: TokenType, expected: str, *, hint: str | None = None,
                notes: tuple[str, ...] = ()) -> Token:
        if self._check(kind):
            return self._advance()
        raise self._error("E1101", f"Expected {expected}, found {self._peek().describe()}", hint=hint, notes=notes)

    def _expect_name(self, expected: str, *, hint: str | None = None) -> Token:
        """A name being declared. Keywords and reserved words get their own message."""
        token = self._peek()
        if token.type is TokenType.RESERVED:
            raise self._error(
                "E1103",
                f"'{token.lexeme}' is a reserved word and cannot be used as a name",
                hint="Choose a different name.",
            )
        if token.type in _NAME_KEYWORDS:
            raise self._error("E1101", f"Expected {expected}, but '{token.lexeme}' is a keyword")
        return self._expect(TokenType.IDENT, expected, hint=hint)

    def _type(self, expected: str, *, hint: str | None = None) -> ast.TypeRef:
        """`Name`, or `List[Type]`, `Option[Type]` or `Result[Type, Type]` with nested arguments (I2)."""
        name = self._expect(TokenType.IDENT, expected, hint=hint)
        if not self._check(TokenType.LBRACKET):
            return ast.TypeRef(name.span, name.lexeme)
        opening = self._advance()
        self._enter(opening)
        arguments: list[ast.TypeRef] = []
        if not self._check(TokenType.RBRACKET):
            arguments.append(self._type("a type argument"))
            while self._match(TokenType.COMMA):
                arguments.append(self._type("a type argument"))
        closing = self._expect(
            TokenType.RBRACKET,
            "']' to close the type arguments",
            notes=(self._opened_bracket_at(opening),),
        )
        self._nesting -= 1
        span = name.span.to(closing.span)
        arity = _TYPE_ARGUMENT_COUNTS.get(name.lexeme)
        if arity is None:
            raise self._error(
                "E1101",
                f"'{name.lexeme}' cannot take type arguments",
                span=span,
                hint="Only 'List', 'Option' and 'Result' take type arguments: "
                     "List[Int], Option[Text], Result[Int, Text].",
            )
        if len(arguments) == 0:
            raise self._error(
                "E1101",
                f"'{name.lexeme}' needs a type argument: write {name.lexeme}[Int]",
                span=span,
                hint="A type with arguments always states them.",
            )
        if len(arguments) != arity:
            raise self._error(
                "E1101",
                f"'{name.lexeme}' takes exactly {_TYPE_ARGUMENT_NAMES[arity]} type argument"
                f"{'' if arity == 1 else 's'}, but {len(arguments)} "
                f"{'was' if len(arguments) == 1 else 'were'} given",
                span=span,
                hint=f"Write {name.lexeme}[Int]" + (", Text]" if arity == 2 else "]"),
            )
        for argument in arguments:
            if argument.name == VOID:
                raise self._error(
                    "E1101",
                    f"Void cannot be an argument of '{name.lexeme}'",
                    span=argument.span,
                    hint="Void means 'no value'. Use a type that has values, such as Int or Text.",
                )
        return ast.TypeRef(span, name.lexeme, tuple(arguments))

    # Recovery

    def _synchronize_to_function(self) -> None:
        """Skips to the next `fn` or `type` that starts a line, where a new declaration can begin."""
        while not self._check(TokenType.EOF):
            if self._peek().type in _DECLARATION_KEYWORDS and self._starts_line():
                return
            self._advance()

    def _starts_line(self) -> bool:
        return self._pos == 0 or self._tokens[self._pos - 1].type in (TokenType.NEWLINE, TokenType.RBRACE)

    def _synchronize_statement(self) -> None:
        """Skips the rest of a broken statement: up to the end of its line, or to the `}`
        that closes the enclosing block. Blocks opened in between are skipped whole."""
        depth = 0
        while not self._check(TokenType.EOF):
            kind = self._peek().type
            if kind is TokenType.LBRACE:
                depth += 1
            elif kind is TokenType.RBRACE:
                if depth == 0:
                    return
                depth -= 1
            elif kind is TokenType.NEWLINE and depth == 0:
                self._skip_newlines()
                return
            self._advance()

    def _top_level_error(self) -> ParseError:
        token = self._peek()
        if token.type is TokenType.RBRACE:
            return self._error("E1101", "This '}' does not close any block")
        return self._error(
            "E1101",
            f"Expected a function declaration, found {token.describe()}",
            hint="At the top level there are only functions, types and capabilities. "
                 "All other code goes inside a function: fn main() -> Void { ... }",
        )

    # Declarations

    def _type_declaration(self) -> ast.TypeDecl | ast.RecordDecl:
        """`type Name = Base where condition` with an optional `, "explanation"`.

        A record is declared the same way but with its fields: `type Name = { x: Int }`.
        The two are told apart by what comes after the '='.
        """
        keyword = self._advance()
        name = self._expect_name("a type name after 'type'")
        self._expect(TokenType.EQUAL, f"'=' after the type name '{name.lexeme}'",
                     hint=f"A refined type is written: type {name.lexeme} = Int where value > 0")
        if self._peek_significant().type is TokenType.LBRACE:
            return self._record_declaration(keyword, name)
        base = self._type(f"the type that '{name.lexeme}' refines, after '='")
        self._expect(
            TokenType.WHERE,
            f"'where' and the condition that the values of '{name.lexeme}' satisfy",
            hint="A type without a condition would only be another name for the same type, and NEXORA "
                 f"does not have those. Write the rule: type {name.lexeme} = {base.name} where ...",
        )
        self._depths.clear()
        if self._peek().type in _STATEMENT_END:
            raise self._error("E1101", f"Expected a condition after 'where', found {self._peek().describe()}")
        condition = self._expression()
        message, end = self._explanation("where", condition.span)
        self._end_of_statement()
        return ast.TypeDecl(keyword.span.to(end), name.lexeme, name.span, base, condition, message)

    def _record_declaration(self, keyword: Token, name: Token) -> ast.RecordDecl:
        """`type Point = { x: Int, y: Int }`: a record type.

        The '{' goes on the same line as the '='. Inside the braces a line break is
        allowed between fields. A record has at least one field, and no field is left
        out after a comma (decision 0014, 2).
        """
        if self._peek().type is not TokenType.LBRACE:
            raise self._error(
                "E1101",
                f"The '{{' of the record '{name.lexeme}' must be on the same line as the '='",
                hint=f"Write it as: type {name.lexeme} = {{ x: Int }}",
            )
        opening = self._advance()
        self._enter(opening)
        fields: list[ast.FieldDecl] = []
        self._skip_newlines()
        if self._check(TokenType.RBRACE):
            raise self._error(
                "E1101",
                f"The record '{name.lexeme}' needs at least one field",
                opening,
                hint=f"Write the fields of {name.lexeme}: type {name.lexeme} = {{ x: Int }}",
            )
        while True:
            field = self._expect_name("a field name", hint=f"Write a field as: {name.lexeme}(x: 1)")
            self._expect(TokenType.COLON, f"':' and the type of the field '{field.lexeme}'",
                         hint=f"Write a field as: {field.lexeme}: Int")
            field_type = self._type(f"the type of the field '{field.lexeme}'")
            fields.append(ast.FieldDecl(field.span.to(field_type.span), field.lexeme, field.span, field_type))
            self._skip_newlines()
            if not self._match(TokenType.COMMA):
                break
            self._skip_newlines()
            if self._check(TokenType.RBRACE):
                raise self._error(
                    "E1101",
                    "A field cannot be left out after ','",
                    hint=f"Write the fields of {name.lexeme}: type {name.lexeme} = {{ x: Int, y: Int }}",
                )
        closing = self._expect(TokenType.RBRACE, "'}' to close the record declaration",
                               notes=(self._opened_at(opening),))
        self._nesting -= 1
        return ast.RecordDecl(keyword.span.to(closing.span), name.lexeme, name.span, tuple(fields))

    def _uses_declaration(self) -> ast.UsesDecl:
        """`uses read "ruta"`: the capability a program declares that it needs.

        The path is a text literal: a capability is written down, not computed, so that
        it can be read, reviewed and checked (decision 0015, 2).
        """
        keyword = self._advance()
        capability = self._peek()
        if capability.type is not TokenType.IDENT or capability.lexeme not in CAPABILITIES:
            raise self._error(
                "E1101",
                f"Expected 'read' or 'write' after 'uses', found {capability.describe()}",
                capability,
                hint='A program declares what it needs with: uses read "datos/entradas.txt"',
            )
        self._advance()
        path = self._peek()
        if path.type is not TokenType.STRING:
            raise self._error(
                "E1101",
                f"Expected the path of the capability after 'uses {capability.lexeme}'",
                path,
                hint='Write the path as a text: uses read "datos/entradas.txt"',
            )
        self._advance()
        if not path.value:
            raise self._error(
                "E1101",
                "The path of a capability cannot be empty",
                path,
                hint='Write the path of the file: uses read "datos/entradas.txt"',
            )
        return ast.UsesDecl(keyword.span.to(path.span), capability.lexeme, path.value, path.span)

    def _explanation(self, clause: str, end: Span) -> tuple[str | None, Span]:
        """The optional `, "explanation"` after a condition. Returns it and where the clause ends."""
        if not self._match(TokenType.COMMA):
            return None, end
        token = self._peek()
        if token.type is not TokenType.STRING:
            raise self._error(
                "E1101",
                f"Expected a text after ',' explaining the rule of '{clause}', found {token.describe()}",
                hint=f'The explanation is a text literal: {clause} ..., "Why this rule exists"',
            )
        self._advance()
        if not token.value.strip():
            raise self._error(
                "E1101",
                f"The explanation of '{clause}' is empty",
                token,
                hint="Write why the rule exists, or remove the ',' and the text.",
            )
        if "\n" in token.value:
            # Diagnostics show the explanation on one line, after "Reason:".
            raise self._error(
                "E1101",
                "An explanation is a single line: it cannot contain '\\n'",
                token,
                hint="Say it in one sentence.",
            )
        return token.value, token.span

    def _function(self) -> ast.Function:
        keyword = self._expect(TokenType.FN, "'fn'")
        name = self._expect_name("a function name after 'fn'")
        hint = None
        if self._check(TokenType.DOT):
            hint = "Only the language defines functions of a type, such as Text.length. Choose a name without '.'."
        opening = self._expect(TokenType.LPAREN, f"'(' after the function name '{name.lexeme}'", hint=hint)

        params: list[ast.Param] = []
        if not self._check(TokenType.RPAREN):
            params.append(self._param())
            while self._match(TokenType.COMMA):
                params.append(self._param())
        self._expect(TokenType.RPAREN, "')' to close the parameter list", notes=(self._opened_at(opening),))

        self._expect(
            TokenType.ARROW,
            "'->' and a return type",
            hint="The return type is always written. Use 'Void' for a function that returns nothing.",
        )
        return_type = self._type("a return type after '->'", hint="Use 'Void' for a function that returns nothing.")
        self._skip_newlines()

        brace = self._expect(TokenType.LBRACE, f"'{{' to start the body of '{name.lexeme}'")
        self._enter(brace)
        level = self._nesting
        self._skip_newlines()
        contracts, examples = self._clauses(level)
        body = self._block_rest(brace, level)
        return ast.Function(
            keyword.span.to(body.span), name.lexeme, name.span, tuple(params), return_type, tuple(contracts), body,
            tuple(examples),
        )

    def _param(self) -> ast.Param:
        name = self._expect_name("a parameter name")
        self._expect(
            TokenType.COLON,
            f"':' and a type for the parameter '{name.lexeme}'",
            hint=f"Every parameter states its type: {name.lexeme}: Int",
        )
        param_type = self._type(f"a type for the parameter '{name.lexeme}'")
        return ast.Param(name.span.to(param_type.span), name.lexeme, name.span, param_type)

    def _clauses(self, level: int) -> tuple[list[ast.Contract], list[ast.Example]]:
        """The `requires`, `ensures` and `example` clauses that open a function body, in any order.
        All three share one form: a condition and an optional explanation."""
        contracts: list[ast.Contract] = []
        examples: list[ast.Example] = []
        while self._peek().type in _CONTRACT_KEYWORDS:
            try:
                keyword = self._advance()
                self._depths.clear()
                if self._peek().type in _STATEMENT_END:
                    raise self._error(
                        "E1101",
                        f"Expected a condition after '{keyword.lexeme}', found {self._peek().describe()}",
                    )
                condition = self._expression()
                message, end = self._explanation(keyword.lexeme, condition.span)
                self._end_of_statement()
                if keyword.type is TokenType.EXAMPLE:
                    examples.append(ast.Example(keyword.span.to(end), condition, message))
                else:
                    contracts.append(ast.Contract(keyword.span.to(end), keyword.lexeme, condition, message))
            except ParseError as error:
                self._record(error)
                self._nesting = level
                self._synchronize_statement()
        return contracts, examples

    def _block(self, what: str = "a block") -> ast.Block:
        opening = self._expect(TokenType.LBRACE, f"'{{' to start {what}")
        self._enter(opening)
        level = self._nesting
        self._skip_newlines()
        return self._block_rest(opening, level)

    def _block_rest(self, opening: Token, level: int) -> ast.Block:
        """The statements of a block and its closing brace; the opening brace is already read."""
        statements: list[ast.Statement] = []
        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            try:
                statements.append(self._statement())
                self._end_of_statement()
            except ParseError as error:
                self._record(error)
                self._nesting = level
                self._synchronize_statement()

        if self._check(TokenType.EOF):
            # The block is kept with the statements read so far, so that tools can still see
            # the part of the program that was written.
            self._record(self._error(
                "E1102",
                "Expected '}' before the end of the file",
                notes=(f"The block opened at line {opening.span.line}, column {opening.span.column} is never closed.",),
            ))
            self._nesting -= 1
            return ast.Block(opening.span.to(self._peek().span), tuple(statements))
        closing = self._advance()
        self._nesting -= 1
        return ast.Block(opening.span.to(closing.span), tuple(statements))

    def _end_of_statement(self) -> None:
        if self._check(TokenType.NEWLINE):
            self._skip_newlines()
        elif not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            raise self._error(
                "E1101",
                f"Expected the end of the line after this statement, found {self._peek().describe()}",
                hint="Write one statement per line.",
            )

    # Statements

    def _statement(self) -> ast.Statement:
        token = self._peek()
        # Expression depth is counted per statement.
        self._depths.clear()

        if token.type in (TokenType.LET, TokenType.VAR):
            return self._let()
        if token.type is TokenType.RETURN:
            return self._return()
        if token.type is TokenType.IF:
            return self._if()
        if token.type is TokenType.WHILE:
            return self._while()
        if token.type is TokenType.FOR:
            return self._for()
        if token.type is TokenType.LBRACE:
            return self._block()
        if token.type is TokenType.IDENT and self._peek(1).type is TokenType.EQUAL:
            name = self._advance()
            self._advance()
            value = self._expression()
            return ast.Assign(name.span.to(value.span), name.lexeme, name.span, value)
        if token.type is TokenType.IDENT and self._peek(1).type is TokenType.DOT and self._assigns_a_field():
            return self._field_assignment(token)
        if token.type in _CONTRACT_KEYWORDS:
            raise self._error(
                "E1106",
                f"'{token.lexeme}' must come at the start of a function body, before any other statement",
                hint="Move this clause to the first lines of the function.",
            )
        if token.type in _LOOP_KEYWORDS:
            raise self._error(
                "E1106",
                f"'{token.lexeme}' must come at the start of the body of a loop, before any other statement",
                hint="Move this clause to the first lines of the loop body.",
            )
        if token.type is TokenType.ELSE:
            raise self._error(
                "E1101",
                "This 'else' does not follow an 'if'",
                hint="'else' goes on the same line as the '}' that closes the 'if' block: } else {",
            )
        if token.type is TokenType.RESERVED:
            raise self._error(
                "E1103",
                f"'{token.lexeme}' is reserved for a future version of NEXORA and is not implemented yet",
                hint=_RESERVED_HINTS.get(token.lexeme),
            )
        if token.type is TokenType.FN:
            raise self._error("E1101", "A function cannot be declared inside another function")
        if token.type is TokenType.TYPE:
            raise self._error(
                "E1101",
                "A type cannot be declared inside a function",
                hint="Declare it at the top level of the file, outside any function.",
            )
        if token.type is TokenType.USES:
            raise self._error(
                "E1101",
                "A capability cannot be declared inside a function",
                hint="Declare it at the top level of the file, outside any function.",
            )
        if token.type is TokenType.WHERE:
            raise self._error(
                "E1101",
                "'where' can only follow the base type in a type declaration",
                hint="type Percent = Int where value >= 0 and value <= 100",
            )

        expression = self._expression()
        return ast.ExprStatement(expression.span, expression)

    def _assigns_a_field(self) -> bool:
        """Whether the statement at the current position assigns to a field.

        It looks at the tokens ahead: `p.x = 1` assigns, `p.x` only reads.
        """
        index = 1
        while self._peek(index).type is TokenType.DOT and self._peek(index + 1).type is TokenType.IDENT:
            index += 2
        return self._peek(index).type is TokenType.EQUAL

    def _field_assignment(self, root: Token) -> ast.FieldAssign:
        """`p.x = value`: giving a new value to a field of a record.

        A record is immutable, so this is always an error; the checker says so
        (decision 0014, 2 and 5).
        """
        self._advance()
        steps = self._field_steps(root)
        name, name_span = steps[-1]
        target: ast.Expr = ast.Name(root.span, root.lexeme)
        span = root.span
        for field, field_span in steps[:-1]:
            span = span.to(field_span)
            target = ast.FieldAccess(span, target, field, field_span)
        self._expect(TokenType.EQUAL, f"'=' and the new value of the field '{name}'")
        value = self._expression()
        return ast.FieldAssign(root.span.to(value.span), target, name, name_span, value)

    def _let(self) -> ast.Let | ast.Var:
        """`let` and `var` share one form; only `var` can be assigned again later."""
        keyword = self._advance()
        name = self._expect_name(f"a variable name after '{keyword.lexeme}'")
        declared_type = None
        if self._match(TokenType.COLON):
            declared_type = self._type(f"a type for '{name.lexeme}' after ':'")
        self._expect(
            TokenType.EQUAL,
            f"'=' and a value for '{name.lexeme}'",
            hint="A variable must be given a value when it is declared.",
        )
        value = self._expression()
        node = ast.Var if keyword.type is TokenType.VAR else ast.Let
        return node(keyword.span.to(value.span), name.lexeme, name.span, declared_type, value)

    def _return(self) -> ast.Return:
        keyword = self._advance()
        if self._peek().type in _STATEMENT_END:
            return ast.Return(keyword.span, None)
        value = self._expression()
        return ast.Return(keyword.span.to(value.span), value)

    def _if(self) -> ast.If:
        keyword = self._advance()
        self._enter(keyword)
        if self._check(TokenType.LBRACE):
            raise self._error("E1101", "Expected a condition after 'if', found '{'")
        condition = self._expression()
        then_block = self._block("the body of 'if'")

        else_branch: ast.Block | ast.If | None = None
        if self._match(TokenType.ELSE):
            if self._check(TokenType.IF):
                else_branch = self._if()
            else:
                else_branch = self._block("the body of 'else'")
        self._nesting -= 1
        end = else_branch.span if else_branch is not None else then_block.span
        return ast.If(keyword.span.to(end), condition, then_block, else_branch)

    def _while(self) -> ast.While:
        """`while condition { clauses statements }`. The clauses come first in the body, like the
        contracts of a function; the checker requires exactly one `decreases` (decision 0010)."""
        keyword = self._advance()
        self._enter(keyword)
        if self._check(TokenType.LBRACE):
            raise self._error("E1101", "Expected a condition after 'while', found '{'")
        condition = self._expression()
        opening = self._expect(TokenType.LBRACE, "'{' to start the body of 'while'")
        self._enter(opening)
        level = self._nesting
        self._skip_newlines()
        clauses = self._loop_clauses(level)
        body = self._block_rest(opening, level)
        self._nesting -= 1
        return ast.While(keyword.span.to(body.span), condition, tuple(clauses), body)

    def _for(self) -> ast.For:
        """`for name in iterable { clauses statements }`. The iterator is declared by the loop and
        cannot be assigned; the loop body takes the same clauses as a `while` (decision 0012)."""
        keyword = self._advance()
        self._enter(keyword)
        name = self._expect_name("a name for the iterator after 'for'")
        self._expect(
            TokenType.IN,
            f"'in' after the iterator name '{name.lexeme}'",
            hint="Write for x in xs { ... }.",
        )
        if self._check(TokenType.LBRACE):
            raise self._error(
                "E1101",
                f"Expected a list after '{name.lexeme} in', found '{{'",
                hint="Write the list the loop walks over, for example 'for x in xs'.",
            )
        iterable = self._expression()
        opening = self._expect(TokenType.LBRACE, "'{' to start the body of 'for'")
        self._enter(opening)
        level = self._nesting
        self._skip_newlines()
        clauses = self._loop_clauses(level)
        body = self._block_rest(opening, level)
        self._nesting -= 1
        return ast.For(keyword.span.to(body.span), name.lexeme, name.span, iterable, tuple(clauses), body)

    def _loop_clauses(self, level: int) -> list[ast.LoopClause]:
        """The `invariant` and `decreases` clauses that open the body of a loop, in any order."""
        clauses: list[ast.LoopClause] = []
        while self._peek().type in _LOOP_KEYWORDS:
            try:
                keyword = self._advance()
                self._depths.clear()
                if self._peek().type in _STATEMENT_END:
                    what = "a condition" if keyword.type is TokenType.INVARIANT else "an Int measure"
                    raise self._error(
                        "E1101",
                        f"Expected {what} after '{keyword.lexeme}', found {self._peek().describe()}",
                    )
                condition = self._expression()
                message, end = self._explanation(keyword.lexeme, condition.span)
                self._end_of_statement()
                clauses.append(ast.LoopClause(keyword.span.to(end), keyword.lexeme, condition, message))
            except ParseError as error:
                self._record(error)
                self._nesting = level
                self._synchronize_statement()
        return clauses

    # Expressions

    def _expression(self, minimum: int = 1) -> ast.Expr:
        """Precedence climbing: parses operators whose precedence is at least `minimum`."""
        left = self._unary()
        while True:
            operator = self._peek()
            precedence = _PRECEDENCE.get(operator.type)
            if precedence is None or precedence < minimum:
                return left
            if precedence == _COMPARISON and isinstance(left, ast.Binary) and left.operator in _COMPARISON_OPERATORS:
                raise self._error(
                    "E1101",
                    "Comparisons cannot be chained",
                    hint="Join two comparisons with 'and': a < b and b < c",
                )
            self._advance()
            right = self._expression(precedence + 1)
            left = self._built(
                ast.Binary(left.span.to(right.span), operator.lexeme, operator.span, left, right),
                left, right,
            )

    def _unary(self) -> ast.Expr:
        if self._check(TokenType.MINUS) or self._check(TokenType.NOT):
            operator = self._advance()
            self._enter(operator)
            operand = self._unary()
            self._nesting -= 1
            return self._built(ast.Unary(operator.span.to(operand.span), operator.lexeme, operand), operand)
        return self._primary()

    def _primary(self) -> ast.Expr:
        token = self._peek()

        if token.type is TokenType.INT:
            return ast.IntLiteral(self._advance().span, token.value)
        if token.type is TokenType.FLOAT:
            return ast.FloatLiteral(self._advance().span, token.value)
        if token.type is TokenType.STRING:
            return ast.TextLiteral(self._advance().span, token.value)
        if token.type in (TokenType.TRUE, TokenType.FALSE):
            return ast.BoolLiteral(self._advance().span, token.type is TokenType.TRUE)
        if token.type is TokenType.IDENT:
            self._advance()
            if self._check(TokenType.DOT):
                # A name that declares a type is never a value: `Text.length` is a call
                # to a function of a type, never the reading of a field. A name that is
                # called is a call too, whatever it is: `name.length()` says that a
                # value has no functions of its own.
                if token.lexeme in self._type_names or self._peek(2).type is TokenType.LPAREN:
                    return self._qualified_call(token)
                return self._field_access(token)
            if self._check(TokenType.LPAREN):
                if token.lexeme in self._record_names:
                    return self._record_construction(token)
                return self._call(token)
            return ast.Name(token.span, token.lexeme)
        if token.type is TokenType.LPAREN:
            self._advance()
            self._enter(token)
            inner = self._expression()
            closing = self._expect(TokenType.RPAREN, "')'", notes=(self._opened_at(token),))
            self._nesting -= 1
            return self._built(ast.Group(token.span.to(closing.span), inner), inner)
        if token.type is TokenType.LBRACKET:
            return self._list_literal()
        if token.type is TokenType.RESERVED:
            raise self._error(
                "E1103",
                f"'{token.lexeme}' is reserved for a future version of NEXORA and cannot be used here",
            )
        raise self._error("E1101", f"Expected a value or an expression, found {token.describe()}")

    def _list_literal(self) -> ast.ListLiteral:
        """`[a, b]`, or `[]`. A comma is a separator: a trailing comma is not accepted."""
        opening = self._advance()
        self._enter(opening)
        elements: list[ast.Expr] = []
        if not self._check(TokenType.RBRACKET):
            elements.append(self._expression())
            while self._match(TokenType.COMMA):
                if self._check(TokenType.RBRACKET):
                    raise self._error("E1101", "Expected a value or an expression after ','")
                elements.append(self._expression())
        closing = self._expect(
            TokenType.RBRACKET,
            "']' to close the list",
            notes=(self._opened_bracket_at(opening),),
        )
        self._nesting -= 1
        return self._built(ast.ListLiteral(opening.span.to(closing.span), tuple(elements)), *elements)

    def _field_steps(self, root: Token) -> list[tuple[str, Span]]:
        """The fields read after a name: `p.x.y` gives [("x", ...), ("y", ...)].

        The root is always a name. A call, a construction, a group or a list cannot be
        the root of a field access (decision 0014, 2).
        """
        steps: list[tuple[str, Span]] = []
        while self._check(TokenType.DOT):
            dot = self._advance()
            name = self._peek()
            if name.type is not TokenType.IDENT:
                raise self._error("E1101", f"Expected the name of a field after '{root.lexeme}.'", dot)
            if not (_touches(root.span, dot.span) and _touches(dot.span, name.span)):
                raise self._error(
                    "E1101",
                    f"Write '{root.lexeme}.{name.lexeme}' without spaces around the '.'",
                    span=root.span.to(name.span),
                )
            self._advance()
            steps.append((name.lexeme, name.span))
            root = name
        return steps

    def _field_access(self, root: Token) -> ast.Expr:
        """`p.x` and `p.x.y`: reading the fields of a record value."""
        target: ast.Expr = ast.Name(root.span, root.lexeme)
        span = root.span
        for name, name_span in self._field_steps(root):
            span = span.to(name_span)
            target = ast.FieldAccess(span, target, name, name_span)
        return target

    def _record_construction(self, name: Token) -> ast.RecordConstruction:
        """`Point(x: 1, y: 2)`: building a record value.

        Every field is given by name, and every name is given once. The order of the
        text does not have to be the order of the declaration (decision 0014, 2).
        """
        opening = self._advance()
        self._enter(opening)
        fields: list[ast.FieldInitializer] = []
        if not self._check(TokenType.RPAREN):
            while True:
                field = self._expect_name(
                    "a field name",
                    hint=f"A record is built with named fields: {name.lexeme}(x: 1, y: 2)",
                )
                self._expect(TokenType.COLON, f"':' and the value of the field '{field.lexeme}'",
                             hint=f"A record is built with named fields: {name.lexeme}(x: 1, y: 2)")
                value = self._expression()
                fields.append(ast.FieldInitializer(field.span.to(value.span), field.lexeme, field.span, value))
                if not self._match(TokenType.COMMA):
                    break
                if self._check(TokenType.RPAREN):
                    raise self._error(
                        "E1101",
                        "A field cannot be left out after ','",
                        hint=f"A record is built with named fields: {name.lexeme}(x: 1, y: 2)",
                    )
        closing = self._expect(TokenType.RPAREN, "')' to close the construction",
                               notes=(self._opened_at(opening),))
        self._nesting -= 1
        return ast.RecordConstruction(name.span.to(closing.span), name.lexeme, name.span, tuple(fields))

    def _qualified_call(self, qualifier: Token) -> ast.Call:
        """`Name.function(...)`. Only the form is checked here: whether `Name` is a type that has
        `function` is decided by the checker (decision 0011, 3.4 and 9)."""
        dot = self._advance()
        name = self._peek()
        if name.type is not TokenType.IDENT:
            raise self._error("E1101", f"Expected the name of a function after '{qualifier.lexeme}.'", dot)
        full = f"{qualifier.lexeme}.{name.lexeme}"
        # The '.' touches both names. Inside parentheses a line break leaves no token, so the
        # positions are compared, not the tokens.
        if not (_touches(qualifier.span, dot.span) and _touches(dot.span, name.span)):
            raise self._error("E1101", f"Write '{full}' without spaces around the '.'",
                              span=qualifier.span.to(name.span))
        self._advance()
        if self._check(TokenType.DOT):
            raise self._error("E1101", f"Expected '(' after '{full}', found '.'",
                              notes=("A qualified name has one '.': Type.function",))
        if not self._check(TokenType.LPAREN):
            raise self._error("E1101", f"Expected '(' to call '{full}'",
                              hint=f"A function is not a value: call it, as in {full}(...).")
        return self._call(qualifier, name=full, name_span=qualifier.span.to(name.span), qualifier=qualifier.lexeme)

    def _call(self, callee: Token, *, name: str | None = None, name_span: Span | None = None,
              qualifier: str | None = None) -> ast.Call:
        opening = self._advance()
        self._enter(opening)
        arguments: list[ast.Expr] = []
        if not self._check(TokenType.RPAREN):
            arguments.append(self._expression())
            while self._match(TokenType.COMMA):
                arguments.append(self._expression())
        closing = self._expect(TokenType.RPAREN, "')' to close the call", notes=(self._opened_at(opening),))
        self._nesting -= 1
        return self._built(
            ast.Call(callee.span.to(closing.span), name or callee.lexeme, name_span or callee.span,
                     tuple(arguments), qualifier),
            *arguments,
        )

    @staticmethod
    def _opened_at(token: Token) -> str:
        return f"The '(' was opened at line {token.span.line}, column {token.span.column}."

    @staticmethod
    def _opened_bracket_at(token: Token) -> str:
        return f"The '[' was opened at line {token.span.line}, column {token.span.column}."

    # Size limits

    def _enter(self, token: Token) -> None:
        self._nesting += 1
        if self._nesting > MAX_NESTING:
            self._nesting -= 1
            raise self._error(
                "E1105",
                f"Code is nested more than {MAX_NESTING} levels deep",
                token,
                hint="Split the code into smaller pieces: more 'let' declarations or more functions.",
            )

    def _built(self, node: ast.Expr, *children: ast.Expr) -> ast.Expr:
        """Records the depth of a new expression node and rejects trees that are too deep."""
        depth = 1 + max((self._depths.get(id(child), 1) for child in children), default=0)
        if depth > MAX_EXPRESSION_DEPTH:
            raise self._error(
                "E1105",
                f"This expression chains more than {MAX_EXPRESSION_DEPTH} operations",
                span=node.span,
                hint="Split the expression into several 'let' declarations.",
            )
        self._depths[id(node)] = depth
        return node


def _touches(left: Span, right: Span) -> bool:
    """Whether `right` starts exactly where `left` ends, on the same line."""
    return left.end_line == right.line and left.end_column == right.column


def _declared_type_names(tokens: list[Token]) -> tuple[frozenset[str], frozenset[str]]:
    """The type names the program declares, and the ones that declare a record.

    The parser needs both before it reads the program. A name that declares a type is
    never a value, so `Point.x` keeps the meaning of a qualified call; a name that
    declares a record can only be used to build one (decision 0014, 2).

    The scan is lexical: a `type` inside a function body is a syntax error anyway, and
    the checker is the one that decides whether a declaration is valid.
    """
    names: set[str] = set(_BUILTIN_TYPE_NAMES)
    records: set[str] = set()
    index = 0
    while index < len(tokens) - 1:
        if tokens[index].type is TokenType.TYPE and tokens[index + 1].type is TokenType.IDENT:
            name = tokens[index + 1].lexeme
            names.add(name)
            following = tokens[index + 2:index + 4]
            if (len(following) == 2 and following[0].type is TokenType.EQUAL
                    and following[1].type is TokenType.LBRACE):
                records.add(name)
            index += 2
        index += 1
    return frozenset(names), frozenset(records)


def parse(tokens: list[Token]) -> tuple[ast.Program, list[Diagnostic]]:
    type_names, record_names = _declared_type_names(tokens)
    return Parser(tokens, type_names, record_names).parse()


def parse_expression(tokens: list[Token]) -> ast.Expr:
    """A single expression and nothing else. For the conditions the language declares itself
    (prelude.py), which are fixed text: any syntax error there is a defect, raised as ValueError."""
    parser = Parser(tokens)
    try:
        expression = parser._expression()
    except ParseError as error:
        raise ValueError(error.diagnostic.label) from None
    if not parser._check(TokenType.EOF):
        raise ValueError(f"unexpected {parser._peek().describe()} after the expression")
    return expression
