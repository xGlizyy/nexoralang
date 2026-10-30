;;; nexora-eglot.el --- NEXORA LSP setup for Emacs 29+ -*- lexical-binding: t; -*-

;; Load this file from your Emacs config. Eglot is built into Emacs 29+.

(require 'eglot)

;; Fall back to the decoded drive path if Windows Emacs cannot resolve a file URI.
(defun nexora-eglot--uri-to-path-fallback (original uri)
  "Use a decoded local Windows path if ORIGINAL cannot resolve URI."
  (let ((path (funcall original uri)))
    (if (and (eq system-type 'windows-nt)
             (or (null path) (equal path ""))
             (stringp uri)
             (string-prefix-p "file:///" uri))
        (let* ((url (url-generic-parse-url uri))
               (raw (decode-coding-string
                     (url-unhex-string (url-filename url)) 'utf-8-unix))
               (candidate (if (string-match "\\`/[[:alpha:]]:/" raw)
                              (substring raw 1)
                            raw)))
          (if (file-exists-p candidate) candidate path))
      path)))

(advice-add 'eglot-uri-to-path :around #'nexora-eglot--uri-to-path-fallback)

(defconst nexora--keywords
  '("fn" "let" "var" "return" "if" "else" "while" "for" "in"
    "needs" "gives" "promises" "trust" "example" "keeps" "shrinks"
    "uses" "type" "enum" "match" "where" "import" "pub" "and" "or" "not" "true" "false"))
(defconst nexora--reserved-words
  '("assert" "break" "const" "continue" "test" "try"
    "requires" "ensures" "invariant" "decreases"))
(defconst nexora--primitive-types '("Int" "Float" "Bool" "Text" "Void"))
(defconst nexora--compound-types '("List" "Option" "Result"))
(defconst nexora--constructors '("Some" "None" "Ok" "Err"))
(defconst nexora--builtin-functions
  '("print" "to_text" "to_float" "to_int" "args" "input" "read_file" "write_file"
    "Text.length" "Text.contains" "Text.starts_with" "Text.ends_with" "Text.slice"
    "Int.parse" "Int.can_parse" "Float.parse" "Float.can_parse"
    "List.length" "List.get" "List.append" "List.concat" "List.contains"
    "Option.is_some" "Option.is_none" "Option.value" "Option.value_or"
    "Result.is_ok" "Result.is_err" "Result.value" "Result.value_or" "Result.error"
    "Net.get" "Process.run"))
(defconst nexora--font-lock-keywords
  `((,(regexp-opt nexora--reserved-words 'symbols) . font-lock-warning-face)
    (,(regexp-opt nexora--keywords 'symbols) . font-lock-keyword-face)
    (,(regexp-opt nexora--primitive-types 'symbols) . font-lock-type-face)
    (,(regexp-opt nexora--compound-types 'symbols) . font-lock-type-face)
    (,(regexp-opt nexora--constructors 'symbols) . font-lock-constant-face)
    (,(regexp-opt nexora--builtin-functions 'symbols) . font-lock-builtin-face)
    ("\\_<[A-Z][A-Za-z0-9_]*\\_>" . font-lock-type-face)
    ("\\_<\\([A-Za-z_][A-Za-z0-9_]*\\)\\_>[ \t]*([^)]*)" 1 font-lock-function-name-face)))

(define-derived-mode nexora-mode prog-mode "NEXORA"
  "Major mode for NEXORA source files."
  (modify-syntax-entry ?/ ". 124b" nexora-mode-syntax-table)
  (modify-syntax-entry ?\n "> b" nexora-mode-syntax-table)
  (setq-local comment-start "// ")
  (setq-local comment-end "")
  (setq-local font-lock-defaults '(nexora--font-lock-keywords)))

(add-to-list 'auto-mode-alist '("\\.nex\\'" . nexora-mode))

(with-eval-after-load 'eglot
  (add-to-list 'eglot-server-programs
               '((nexora-mode :language-id "nexora") . ("nexora-lsp"))))

(add-hook 'nexora-mode-hook #'eglot-ensure)

(provide 'nexora-eglot)
;;; nexora-eglot.el ends here
