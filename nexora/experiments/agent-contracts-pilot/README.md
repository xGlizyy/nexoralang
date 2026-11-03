# Local contract pilot

This optional research harness is separate from the NEXORA runtime and never runs as part of the
language tools. It calls a local Ollama model, asks for one function edit per fresh request, then
checks the answer with the reference interpreter and hidden cases.

The fixed 12-task set is in `tasks.py`. `case-rationales.md` documents why each hidden case exists.
The recorded v2 outputs are in `results.jsonl`; v1 is retained but excluded in
`results-v1-excluded.jsonl` because its prompt leaked contract syntax. In that file the temporary
directory of the machine that ran the pilot, which appeared in the recorded compiler output, is
written as `<temp>`; nothing else was changed.

To run the full set with a new local Ollama model, start Ollama, make that model available locally,
then choose a new output file so the recorded results remain unchanged:

```powershell
python run_pilot.py --model gemma4:26b --results results-replication.jsonl
python summarize.py --results results-replication.jsonl
```

The runner records the model response, source, NEXORA check/run output, settings, seed, tool
versions, platform and task-file hash. It resumes an existing output file by skipping task/seed/
condition combinations already recorded. `summarize.py` reads the committed v2 file by default, or
the file passed with `--results`, and checks that all 72 unique runs are present.
