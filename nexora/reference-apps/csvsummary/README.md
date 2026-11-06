# csvsummary

Reads a CSV file, summarizes every column after the first one (the label) and writes the summary to a file. It is made of
three files: `main.nex` (the program), `csv.nex` (reads the text of a CSV into a table) and `stats.nex` (the figures of one
column).

```bash
mkdir -p out
nex run main.nex --allow-read data --allow-write out -- data/sales.csv out/summary.txt
nex test main.nex
```

With `data/sales.csv` the summary, which is printed and written to `out/summary.txt`, is:

```
units: count 4, sum 42, low 3, high 20
revenue: count 4, sum 1255, low 95, high 610
```

- The program declares `uses read "data"` and `uses write "out"`. Whoever runs it has to grant both. It cannot read or
  write anywhere else, and a grant for `.` is of no use for a path the program did not declare: it stops with `E3008`.
- The first line of the file is the header. Every other non-empty line is a row with as many fields as the header. Cells
  after the first column must be whole numbers.
- A bad file is reported with `error: ...` and nothing is written: `data/bad_cell.csv` (a cell that is not a number),
  `data/short_row.csv` (a row with a missing field) and `data/empty.csv`. `data/crlf.csv` is written with Windows line
  breaks and is read the same.
- `write_file` does not create folders: `out/` has to exist.
- `nex test main.nex` evaluates the `example` clauses of the three files.
