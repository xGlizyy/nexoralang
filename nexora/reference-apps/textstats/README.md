# textstats

A pure command-line tool: it reads a text and reports its size, its words and the word that repeats the most. It declares
no capability, so it needs no `--allow-*` option.

```bash
nex run textstats.nex -- the quick brown fox jumps over the lazy dog the end
echo "to be or not to be" | nex run textstats.nex
nex test textstats.nex
```

The text is the arguments joined with a space or, with no arguments, one line of the standard input. The first command
prints:

```
characters: 51
words: 11
vowels: 13
longest: quick
most frequent: the (3)
```

- Words are the runs of characters between spaces. Case matters: `The` and `the` are two words.
- `longest` and `most frequent` are `-` when there are no words. When several words tie, the first one wins.
- With no arguments and an empty standard input the program stops with `E3009` (there is no line to read).
- `nex test` evaluates the 15 `example` clauses of its six functions.
