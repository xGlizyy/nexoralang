"""Parser: turns tokens into an AST, following the grammar in docs/language-spec.md.

Recursive descent for declarations and statements, precedence climbing for expressions.
A syntax error does not stop the parse: the parser reports it, skips to the next
statement (or the next function) and carries on, so one run can report several
independent mistakes, and what did parse is kept as a partial tree.
"""

from __future__ import annotations

from . import ast_nodes as ast
from .diagnostics import MAX_DIAGNOSTICS, Diagnostic, Span
from .tokens import Token, TokenType

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
    TokenType.TYPE, TokenType.WHERE,
)
_DECLARATION_KEYWORDS = (TokenType.FN, TokenType.TYPE)
_CONTRACT_KEYWORDS = (TokenType.REQUIRES, TokenType.ENSURES)
_STATEMENT_END = (TokenType.NEWLINE, TokenType.RBRACE, TokenType.EOF)


class ParseError(Exception):
    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.label)
        self.diagnostic = diagnostic


class _TooManyErrors(Exception):
    """Raised to abandon the parse when MAX_DIAGNOSTICS syntax errors have been collected."""


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._pos = 0
        self._nesting = 0
        self._depths: dict[int, int] = {}
        self._diagnostics: list[Diagnostic] = []

    def parse(self) -> tuple[ast.Program, list[Diagnostic]]:
        """Returns the program and the syntax errors found.

        When the list is not empty the program is partial: it holds the functions and
        statements that parsed, without the statements that have an error and without the
        functions whose declaration has one. It is for tools; it is never run."""
        types: list[ast.TypeDecl] = []
        functions: list[ast.Function] = []
        self._skip_newlines()
        try:
            while not self._check(TokenType.EOF):
                try:
                    if self._check(TokenType.TYPE):
                        types.append(self._type_declaration())
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
        return ast.Program(start.to(end), tuple(types), tuple(functions)), self._diagnostics

    def _record(self, error: ParseError) -> None:
        """Keeps a syntax error. Stops the whole parse once the limit is reached."""
        self._diagnostics.append(error.diagnostic)
        if len(self._diagnostics) >= MAX_DIAGNOSTICS:
            raise _TooManyErrors

    # Token helpers

    def _peek(self, offset: int = 0) -> Token:
        index = min(self._pos + offset, len(self._tokens) - 1)
        return self._tokens[index]

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

    def _expect_name(self, expected: str) -> Token:
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
        return self._expect(TokenType.IDENT, expected)

    def _type(self, expected: str, *, hint: str | None = None) -> ast.TypeRef:
        token = self._expect(TokenType.IDENT, expected, hint=hint)
        return ast.TypeRef(token.span, token.lexeme)

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
            hint="At the top level there are only functions and types. "
                 "All other code goes inside a function: fn main() -> Void { ... }",
        )

    # Declarations

    def _type_declaration(self) -> ast.TypeDecl:
        """`type Name = Base where condition` with an optional `, "explanation"`."""
        keyword = self._advance()
        name = self._expect_name("a type name after 'type'")
        self._expect(TokenType.EQUAL, f"'=' after the type name '{name.lexeme}'",
                     hint=f"A refined type is written: type {name.lexeme} = Int where value > 0")
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
        opening = self._expect(TokenType.LPAREN, f"'(' after the function name '{name.lexeme}'")

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
        contracts = self._contracts(level)
        body = self._block_rest(brace, level)
        return ast.Function(
            keyword.span.to(body.span), name.lexeme, name.span, tuple(params), return_type, tuple(contracts), body,
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

    def _contracts(self, level: int) -> list[ast.Contract]:
        """The `requires` and `ensures` clauses that open a function body."""
        contracts: list[ast.Contract] = []
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
                contracts.append(ast.Contract(keyword.span.to(end), keyword.lexeme, condition, message))
            except ParseError as error:
                self._record(error)
                self._nesting = level
                self._synchronize_statement()
        return contracts

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

        if token.type is TokenType.LET:
            return self._let()
        if token.type is TokenType.RETURN:
            return self._return()
        if token.type is TokenType.IF:
            return self._if()
        if token.type is TokenType.LBRACE:
            return self._block()
        if token.type is TokenType.IDENT and self._peek(1).type is TokenType.EQUAL:
            name = self._advance()
            self._advance()
            value = self._expression()
            return ast.Assign(name.span.to(value.span), name.lexeme, name.span, value)
        if token.type in _CONTRACT_KEYWORDS:
            raise self._error(
                "E1106",
                f"'{token.lexeme}' must come at the start of a function body, before any other statement",
                hint="Move this clause to the first lines of the function.",
            )
        if token.type is TokenType.ELSE:
            raise self._error(
                "E1101",
                "This 'else' does not follow an 'if'",
                hint="'else' goes on the same line as the '}' that closes the 'if' block: } else {",
            )
        if token.type is TokenType.RESERVED:
            hint = None
            if token.lexeme == "var":
                hint = "Variables cannot be reassigned in this version; declare a new one with 'let'."
            raise self._error(
                "E1103",
                f"'{token.lexeme}' is reserved for a future version of NEXORA and is not implemented yet",
                hint=hint,
            )
        if token.type is TokenType.FN:
            raise self._error("E1101", "A function cannot be declared inside another function")
        if token.type is TokenType.TYPE:
            raise self._error(
                "E1101",
                "A type cannot be declared inside a function",
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

    def _let(self) -> ast.Let:
        keyword = self._advance()
        name = self._expect_name("a variable name after 'let'")
        declared_type = None
        if self._match(TokenType.COLON):
            declared_type = self._type(f"a type for '{name.lexeme}' after ':'")
        self._expect(
            TokenType.EQUAL,
            f"'=' and a value for '{name.lexeme}'",
            hint="A variable must be given a value when it is declared.",
        )
        value = self._expression()
        return ast.Let(keyword.span.to(value.span), name.lexeme, name.span, declared_type, value)

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
            if self._check(TokenType.LPAREN):
                return self._call(token)
            return ast.Name(token.span, token.lexeme)
        if token.type is TokenType.LPAREN:
            self._advance()
            self._enter(token)
            inner = self._expression()
            closing = self._expect(TokenType.RPAREN, "')'", notes=(self._opened_at(token),))
            self._nesting -= 1
            return self._built(ast.Group(token.span.to(closing.span), inner), inner)
        if token.type is TokenType.RESERVED:
            raise self._error(
                "E1103",
                f"'{token.lexeme}' is reserved for a future version of NEXORA and cannot be used here",
            )
        raise self._error("E1101", f"Expected a value or an expression, found {token.describe()}")

    def _call(self, callee: Token) -> ast.Call:
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
            ast.Call(callee.span.to(closing.span), callee.lexeme, callee.span, tuple(arguments)),
            *arguments,
        )

    @staticmethod
    def _opened_at(token: Token) -> str:
        return f"The '(' was opened at line {token.span.line}, column {token.span.column}."

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


def parse(tokens: list[Token]) -> tuple[ast.Program, list[Diagnostic]]:
    return Parser(tokens).parse()
