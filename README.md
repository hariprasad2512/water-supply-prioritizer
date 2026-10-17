# Water Supply Prioritizer

Score TypeSafe's **Jev** on water-supply triage reports: every case is a state (the resident or
maintenance report), a shared set of questions, and the answers your team expects. One run tells you
how many Jev got right, how sure it was, how long it took and what it cost.

Zero dependencies — Python 3.10+ standard library only.

![Jev deciding the brown-water ticket: urgency, scope, cause, priority and escalation, each with a
probability bar and a "matches expected" mark](docs/jev-output.png)

## 1. Requirements

- Python **3.10 or newer** (`python3 --version`)
- A TypeSafe API key (`apikey_...`), from <https://typesafe.ai>
- Nothing else: no `pip install`, no virtualenv, no build step

## 2. Get the code

```bash
git clone https://github.com/hariprasad2512/water-supply-prioritizer.git
cd water-supply-prioritizer
```

## 3. Add your key

The runner reads `TYPESAFE_API_KEY` from the environment first, otherwise from a `.env` file next to
`run_jev.py`:

```bash
printf 'TYPESAFE_API_KEY=apikey_your_real_key\n' > .env
chmod 600 .env
```

`.env` is listed in `.gitignore` and is never committed; the key is only ever printed masked
(`apikey_...97f2`).

## 4. Check the key (free)

```bash
python3 run_jev.py --check
```

```
model: jev-latest   endpoint: https://api.typesafe.ai   key: apikey...97f2
check: key accepted; models: jev-latest, jev-preview
```

`GET /v1/models` costs nothing — fix the key before spending a real request.

## 5. Run the benchmark

```bash
python3 run_jev.py                    # every case in examples.json against jev-latest
python3 run_jev.py --json results.json   # also write the full request/response/score log
```

### Jev output

The screenshot at the top of this file is this run in the playground: same ticket, same five
questions, each with a probability bar, the action gate, and a green `matches expected` mark.

Same run as terminal output:

```
model: jev-latest   endpoint: https://api.typesafe.ai   key: apikey...97f2

Brown water, single apartment   [jev-1.13.0 | 735.9 ms | 819 tok]
  question        type    pick                    expected                conf   result
  is_urgent       noul    yes                     yes                     0.89   ok
  affected_scope  choice  single_apartment        single_apartment        0.30   ok
  likely_cause    choice  corrosion               corrosion               0.87   ok
  priority        score   2                       2                       0.86   ok
  escalate_to     choice  building_maintenance    onsite_plumber          0.56   MISS

------------------------------------------------------------------------------
cases: 1 answered, 0 failed
score: 4/5 expected answers right (80%)
  is_urgent         1/1
  affected_scope    1/1
  likely_cause      1/1
  priority          1/1
  escalate_to       0/1
tokens: 819 input, cost: $0.000034   (Jev: $0.042 per million input tokens)
wrote results.json
```

**4/5 expected answers right** — Jev agreed on urgency, scope, cause and priority, and disagreed on
who should attend first (`building_maintenance` vs the expected `onsite_plumber`). That single MISS is
the point of the harness: it surfaces where the model's judgement and your policy differ.

Reading a row: `pick` is Jev's headline answer, `expected` is the answer seeded in `examples.json`,
`conf` is its confidence (for `noul`, `p(yes)`), and `ok` / `MISS` compares the two.

## 6. Useful flags

| flag | what it does |
|---|---|
| `--check` | validate the key only (`GET /v1/models`, free) |
| `--json out.json` | write every request, response and score to a file |
| `--model jev-preview` | run another Jev version (`jev-latest` default) |
| `--group "Water supply"` | only groups whose name contains this text |
| `--item "Brown water"` | only cases whose name contains this text |
| `--base-url http://127.0.0.1:8770 --model s1ced` | score the same file against a local model |
| `--timeout 60` | per-request timeout in seconds |

## Files

| file | what it is |
|---|---|
| `examples.json` | the cases, in the s1ced playground's scenario format |
| `run_jev.py` | the runner: request, score, table, summary |
| `docs/jev-output.png` | screenshot of Jev answering the brown-water ticket in the playground |
| `.env` | your TypeSafe key (git-ignored) |
| `results*.json` | written by `--json` (git-ignored) |

## Add a case

Append to `groups[0].items` in `examples.json`:

```json
{"name": "No water, whole block",
 "state": "TICKET #WS-4490 ... describe what was reported ...",
 "expected": {"is_urgent": "yes", "affected_scope": "single_block", "priority": 3}}
```

`questions` are shared by every item in the group, so a new case only needs a state and expected
answers. Every id in `expected` must exist in `questions` and hold a legal value for its type — the
runner warns before spending a request:

- `noul` — `"yes"` or `"no"` (Jev's `p(yes) >= 0.5` is `yes`)
- `choice` — a key of that question's `criteria`
- `score` — an integer level index; may also be a list of accepted levels

**The expected answers are policy, not fact.** The seeded answers for the brown-water case are a
reasonable default; edit them to match what your team would actually decide, or the score measures
Jev against someone else's guess instead of yours.

## Free local baseline

Score the same file against a local model — free, and useful as a baseline:

```bash
uv run --project ~/Desktop/s1ced-playground s1ced-playground --no-browser   # in another terminal
python3 run_jev.py --base-url http://127.0.0.1:8770 --model s1ced
```

## Same cases in the playground

```bash
cd ~/Desktop/s1ced-playground
uv run s1ced-playground --examples ~/Desktop/water-supply-prioritizer/examples.json
```

The header shows `n/N expected` for whichever model you run — the same rule as `run_jev.py` — with
probability bars, action gates and a needs-review signal next to each answer (the screenshot above).

## Notes

- The starter questions are worded to fit the tightest model as well as Jev: S1-CED allows 91 tokens
  for the instructions plus every option description, and 8 options per question (Vega: 32 tokens per
  option; Jev: 64k context and 255 options). One file therefore runs unchanged on `s1ced`, `vega-0.8b`
  and `jev-*`.
- Requests follow TypeSafe's System One contract: `{"model", "state", "questions"}` in, `answers`
  with probabilities, confidence and `usage` out.
- Jev is billed at $0.042 per million input tokens; output is free. A whole run of small cases costs
  well under a cent.
- Rotate the key in `.env` if this folder is ever shared.
