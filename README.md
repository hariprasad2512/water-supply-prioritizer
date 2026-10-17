# Water supply issue prioritizer

Scores TypeSafe's **Jev** on water-supply reports: every case in `examples.json` is a state, a shared
set of questions, and the answers you expect. One run prints how many Jev got right, how sure it was,
how long it took and what it cost.

No install: Python 3.10+ standard library only (`certifi` is used if it happens to be installed, which
it is on this machine).

## Run

```bash
cd ~/Desktop/water-supply-prioritizer
python3 run_jev.py --check      # key check only: GET /v1/models, free
python3 run_jev.py              # score every case
python3 run_jev.py --json results.json
```

The key is read from `TYPESAFE_API_KEY` in the environment, else from `.env` next to the script
(mode 600, listed in `.gitignore`). It is never printed beyond a masked `apikey_...fb12`.

## Files

| file | what it is |
|---|---|
| `examples.json` | the cases, in the s1ced playground's scenario format |
| `run_jev.py` | the runner: request, score, table, summary |
| `.env` | your TypeSafe key |
| `results*.json` | written by `--json`; ignored by git |

## Add a case

Append to `groups[0].items` in `examples.json`:

```json
{"name": "No water, whole block",
 "state": "TICKET #WS-4490 ... describe what was reported ...",
 "expected": {"is_urgent": "yes", "affected_scope": "single_block", "priority": 3}}
```

`questions` are shared by every item in the group, so a new case only needs a state and expected
answers. Every id in `expected` must exist in `questions` and hold a legal value for its type - the
runner warns before spending a request:

- `noul` - `"yes"` or `"no"` (Jev's `p(yes) >= 0.5` is `yes`)
- `choice` - a key of that question's `criteria`
- `score` - an integer level index; may also be a list of accepted levels

**The expected answers are policy, not fact.** The seeded answers for the brown-water case are a
reasonable default; edit them to match what your team would actually decide, or the score measures
Jev against my guess instead of yours.

## What one run prints

Per question: the pick, the expected answer, the model's confidence, `ok` / `MISS`, and latency.
Per run: answered vs failed cases, `n/N expected answers right`, per-question accuracy, average
latency, input tokens and total cost (Jev is $0.042 per million input tokens, output is free - a
whole run of small cases costs well under a cent).

`run_jev.py --model jev-preview` runs another Jev version. To score the same file against a local
model instead - free, and useful as a baseline - start the playground and point the runner at it:

```bash
uv run --project ~/Desktop/s1ced-playground s1ced-playground --no-browser   # in another terminal
python3 run_jev.py --base-url http://127.0.0.1:8770 --model s1ced
```

## Look at the same cases in the playground

```bash
cd ~/Desktop/s1ced-playground
uv run s1ced-playground --examples ~/Desktop/water-supply-prioritizer/examples.json
```

The header shows `n/N expected` for whichever model you run, the same rule as `run_jev.py`, and the
bars, gates and needs-review signal next to each answer.

## Notes

- The starter questions are worded to fit the tightest model as well as Jev: S1-CED allows 91 tokens
  for the instructions plus every option description, and 8 options per question (Vega: 32 tokens per
  option; Jev: 64k context and 255 options). One file therefore runs unchanged on `s1ced`, `vega-0.8b`
  and `jev-*`.
- Requests follow TypeSafe's System One contract (`docs/CONTRACT.md` in the playground repo):
  `{"model", "state", "questions"}` in, `answers` with probabilities, confidence and `usage` out.
- Rotate the key in `.env` if this folder is ever shared or committed.
