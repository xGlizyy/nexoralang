if exists("b:current_syntax")
  finish
endif

syntax case match

syntax keyword nexoraKeyword fn let var return if else while for in needs gives promises trust example keeps shrinks uses type where import pub
syntax keyword nexoraOperator and or not
syntax keyword nexoraBoolean true false
syntax keyword nexoraType Int Float Bool Text Void List Option Result
syntax keyword nexoraConstructor Some None Ok Err
syntax keyword nexoraBuiltin print to_text to_float to_int args input read_file write_file
syntax keyword nexoraReserved assert break const continue enum match test try requires ensures invariant decreases

syntax match nexoraBuiltin "\<\(Text\|Int\|Float\|List\|Option\|Result\|Net\|Process\)\.[a-z_][A-Za-z0-9_]*\>"
syntax match nexoraFunction "\<[A-Z][A-Za-z0-9_]*\>\ze\s*("
syntax match nexoraNumber "\<\d\%(_\=\d\)*\%(\.\d\%(_\=\d\)*\)\?\>"
syntax match nexoraNumber "\<\d\%(_\=\d\)*\>"
syntax match nexoraInvalidArrow "->"

syntax region nexoraString start=+"+ skip=+\\\|\\"+ end=+"+ contains=nexoraEscape,nexoraInvalidEscape
syntax match nexoraEscape +\\[nt"\\{]+ contained
syntax match nexoraInvalidEscape +\\[^nt"\\{]+ contained
syntax match nexoraComment "//.*$" contains=@Spell

highlight default link nexoraKeyword Keyword
highlight default link nexoraOperator Operator
highlight default link nexoraBoolean Boolean
highlight default link nexoraType Type
highlight default link nexoraConstructor Constant
highlight default link nexoraBuiltin Function
highlight default link nexoraFunction Function
highlight default link nexoraNumber Number
highlight default link nexoraString String
highlight default link nexoraEscape SpecialChar
highlight default link nexoraInvalidEscape Error
highlight default link nexoraReserved WarningMsg
highlight default link nexoraInvalidArrow Error
highlight default link nexoraComment Comment

let b:current_syntax = "nexora"
