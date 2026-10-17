#!/usr/bin/env python3
"""Score TypeSafe's Jev on the cases in examples.json (the playground's scenario format).

  python3 run_jev.py                       # every case in examples.json against jev-latest
  python3 run_jev.py --check               # validate the key only (GET /v1/models, free)
  python3 run_jev.py --group "Water supply issues" --item "Brown water"
  python3 run_jev.py --model jev-preview --json results.json
  python3 run_jev.py --base-url http://127.0.0.1:8770 --model s1ced   # the same file, local model

The key comes from TYPESAFE_API_KEY in the environment, else from .env next to this script.
Scoring is the playground's rule: noul >= 0.5 is "yes", choice is the picked key, score is the
level with the highest probability; an expected value may be a list of accepted answers.
"""
import argparse, json, math, os, ssl, sys, time
from pathlib import Path
from urllib import request as urlreq, error as urlerr

HERE = Path(__file__).resolve().parent
DEFAULT_URL = 'https://api.typesafe.ai'
PRICE_IN = 0.042 / 1e6                     # USD per input token; Jev output is free


def load_env(path):
    """KEY=VALUE lines from .env; the real environment always wins."""
    if not path.exists(): return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k, _, v = line.partition('=')
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def ssl_context():
    """urllib verifies against the interpreter's own CA file, which some Python builds leave out."""
    ctx = ssl.create_default_context()
    p = ssl.get_default_verify_paths()
    try: have_ca = bool(p.cafile and os.path.isfile(p.cafile)) or bool(p.capath and os.listdir(p.capath))
    except OSError: have_ca = False
    if not have_ca:
        try: import certifi
        except ImportError: return ctx
        ctx.load_verify_locations(cafile=certifi.where())
    return ctx


CTX = ssl_context()


def mask(key):
    return f'{key[:6]}...{key[-4:]}' if key and len(key) > 12 else ('set' if key else None)


def call(url, body, key, timeout=60):
    """POST one contract request (or GET when body is None) and return the parsed JSON, or raise RuntimeError."""
    headers = {'Content-Type': 'application/json'}
    if key: headers['Authorization'] = f'Bearer {key}'
    data = json.dumps(body).encode() if body is not None else None
    r = urlreq.Request(url, data=data, headers=headers, method='POST' if body is not None else 'GET')
    try:
        with urlreq.urlopen(r, timeout=timeout, context=CTX) as resp: return json.loads(resp.read())
    except urlerr.HTTPError as e:
        raw = e.read().decode(errors='replace')[:1000]
        try: d = json.loads(raw).get('detail')
        except ValueError: d = None
        if isinstance(d, dict): raise RuntimeError(f'{e.code} {d.get("error_type", "error")}: {d.get("message", raw)}')
        raise RuntimeError(f'{e.code}: {raw or e.reason}')
    except (urlerr.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f'network: {e.reason if isinstance(e, urlerr.URLError) else type(e).__name__}')


def headline(a, qtype):
    """The model's single answer, exactly as the playground computes it."""
    if not isinstance(a, dict): return None
    if qtype == 'noul':
        v = a.get('noul')
        return ('yes' if v >= 0.5 else 'no') if isinstance(v, (int, float)) and math.isfinite(v) else None
    if qtype == 'choice': return a.get('choice')
    probs = {int(k): v for k, v in (a.get('probabilities') or {}).items()
             if str(k).isdigit() and isinstance(v, (int, float)) and math.isfinite(v)}
    return max(probs, key=probs.get) if probs else None


def exp_ok(pick, expected):
    return pick in expected if isinstance(expected, list) else pick == expected


def exp_label(expected):
    return ' or '.join(map(str, expected)) if isinstance(expected, list) else str(expected)


def check_expected(questions, expected, warnings, where):
    """Catch a typo in an expected answer before it costs a request."""
    for qid, exp in expected.items():
        q = questions.get(qid)
        if q is None: warnings.append(f'{where}: expected answer for unknown question {qid!r}'); continue
        values = exp if isinstance(exp, list) else [exp]
        if q['type'] == 'noul':
            bad = [v for v in values if v not in ('yes', 'no')]
        elif q['type'] == 'choice':
            bad = [v for v in values if v not in q['criteria']]
        else:
            bad = [v for v in values if not isinstance(v, int) or not 0 <= v < len(q['criteria'])]
        if bad: warnings.append(f'{where}: {qid} expects {bad}, which is not a valid {q["type"]} answer')


def confidence(a, qtype):
    if not isinstance(a, dict): return None
    if qtype == 'noul': return a.get('noul')
    return a.get('confidence')


def run_case(group, item, model, base_url, key, timeout):
    req = {'model': model, 'state': item['state'], 'questions': group['questions']}
    t0 = time.perf_counter()
    out = call(f'{base_url}/v1/systemone', req, key, timeout)
    wall = round((time.perf_counter() - t0) * 1000, 1)
    return out, wall


def score(group, item, out):
    rows = []
    for qid, q in group['questions'].items():
        expected = (item.get('expected') or {}).get(qid, '<none>')
        pick = headline((out.get('answers') or {}).get(qid), q['type'])
        rows.append({'id': qid, 'type': q['type'], 'pick': pick, 'expected': expected,
                     'ok': None if expected == '<none>' else exp_ok(pick, expected),
                     'confidence': confidence((out.get('answers') or {}).get(qid), q['type'])})
    return rows


def show(group, item, rows, out, wall):
    bits = [str(out.get('model') or '?'), f'{out.get("latency_ms", wall):.1f} ms']
    tok = (out.get('usage') or {}).get('input_tokens')
    if tok is not None: bits.append(f'{tok} tok')
    if isinstance(out.get('cost_usd'), (int, float)): bits.append(f'${out["cost_usd"]:.6f}')
    print(f'\n{item["name"]}   [{" | ".join(bits)}]')
    print(f'  {"question":<16}{"type":<8}{"pick":<24}{"expected":<24}{"conf":<7}{"result":<7}')
    for r in rows:
        conf = '-' if r['confidence'] is None else f'{r["confidence"]:.2f}'
        mark = '' if r['ok'] is None else ('ok' if r['ok'] else 'MISS')
        exp = '-' if r['expected'] == '<none>' else exp_label(r['expected'])
        print(f'  {r["id"]:<16}{r["type"]:<8}{str(r["pick"]):<24}{exp:<24}{conf:<7}{mark:<7}')
    for w in out.get('warnings') or []: print(f'  warning: {w}')


def main():
    ap = argparse.ArgumentParser(prog='run_jev', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--examples', type=Path, default=HERE / 'examples.json', help='scenario file (playground format)')
    ap.add_argument('--model', default='jev-latest', help='jev-latest, jev-preview, s1ced, vega-0.8b, ...')
    ap.add_argument('--base-url', default=DEFAULT_URL, help=f'default: {DEFAULT_URL}; local server: http://127.0.0.1:8770')
    ap.add_argument('--group', help='only groups whose name contains this text')
    ap.add_argument('--item', help='only items whose name contains this text')
    ap.add_argument('--check', action='store_true', help='only check the key against GET /v1/models, then exit')
    ap.add_argument('--json', type=Path, help='write every response and score to this file')
    ap.add_argument('--timeout', type=float, default=60)
    a = ap.parse_args()

    load_env(HERE / '.env')
    key = os.environ.get('TYPESAFE_API_KEY', '').strip()
    base = a.base_url.rstrip('/')
    if not key and base.startswith('https://ap'):   # a local server ignores the key, TypeSafe does not
        sys.exit('error: no API key. Set TYPESAFE_API_KEY, or put it in .env next to this script.')

    print(f'model: {a.model}   endpoint: {base}   key: {mask(key) or "none (local)"}')
    if a.check:
        try: models = [m.get('name') for m in call(f'{base}/v1/models', None, key).get('models', [])]
        except RuntimeError as e: sys.exit(f'check failed: {e}')
        print(f'check: key accepted; models: {", ".join(models) or "none"}')
        return 0

    doc = json.loads(a.examples.read_text(encoding='utf-8-sig'))
    groups = [g for g in doc.get('groups', []) if not a.group or a.group.lower() in g['name'].lower()]
    warnings = []
    for g in groups:
        for it in g['items']:
            check_expected(g['questions'], it.get('expected') or {}, warnings, f'{g["name"]}/{it["name"]}')
    items = [(g, it) for g in groups for it in g['items']
             if not a.item or a.item.lower() in it['name'].lower()]
    if warnings:
        for w in warnings: print(f'note: {w}')
    if not items: sys.exit('error: no cases matched; check --group / --item / the examples file.')

    results, answered, correct, total = [], 0, 0, 0
    per_question = {}
    for g, it in items:
        try:
            out, wall = run_case(g, it, a.model, base, key, a.timeout)
        except RuntimeError as e:
            print(f'\n{it["name"]}\n  FAILED: {e}')
            results.append({'group': g['name'], 'item': it['name'], 'error': str(e)})
            continue
        rows = score(g, it, out); show(g, it, rows, out, wall)
        answered += 1
        for r in rows:
            if r['ok'] is None: continue
            total += 1; correct += int(bool(r['ok']))
            per_question.setdefault(r['id'], [0, 0]); per_question[r['id']][1] += 1
            per_question[r['id']][0] += int(bool(r['ok']))
        results.append({'group': g['name'], 'item': it['name'], 'model': out.get('model'),
                        'state': it['state'], 'request_questions': g['questions'], 'expected': it.get('expected'),
                        'response': out, 'score': rows, 'wall_ms': wall})

    usages = [r['response'].get('usage') or {} for r in results if 'response' in r]
    tokens = sum(u.get('input_tokens') or 0 for u in usages)
    cost = sum(r['response'].get('cost_usd') or 0 for r in results if 'response' in r)
    if not cost and tokens and a.model.startswith('jev'): cost = tokens * PRICE_IN   # TypeSafe bills input only
    lat = [r['response'].get('latency_ms') for r in results if 'response' in r and r['response'].get('latency_ms')]
    failed = [r for r in results if 'error' in r]

    print(f'\n{"-" * 78}')
    print(f'cases: {answered} answered, {len(failed)} failed'
          + (f' ({", ".join(r["item"] for r in failed)})' if failed else ''))
    if total: print(f'score: {correct}/{total} expected answers right ({100 * correct / total:.0f}%)')
    for qid, (ok, n) in per_question.items(): print(f'  {qid:<18}{ok}/{n}')
    if lat: print(f'latency: avg {sum(lat) / len(lat):.0f} ms, slowest {max(lat):.0f} ms')
    if tokens:
        line = f'tokens: {tokens} input'
        if a.model.startswith('jev'):
            line += f', cost: ${cost:.6f}   (Jev: ${PRICE_IN * 1e6:.3f} per million input tokens)'
        print(line)

    if a.json:
        a.json.write_text(json.dumps({'model': a.model, 'endpoint': base, 'results': results}, indent=1))
        print(f'wrote {a.json}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
