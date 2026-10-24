"""The front end of NEXORA 0.11, frozen: lexer, parser and checker as they were in 0.11.0.

Only `nex migrate` uses it, to check that a program is a valid 0.11 program before it
moves it to the syntax of 0.12 (decision 0019, section 8.2). It is a copy, not a shared
module: the 0.12 front end changes, and this one must keep reading exactly what 0.11 read.
The checker needs the interpreter of 0.11 to evaluate refined conditions on constants, so
that is copied too.

Do not edit it to follow the language. It goes away in 0.13.0, together with the
diagnostics E1107 and E1108 (decision 0019, section 13, detail 8).
"""
