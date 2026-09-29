#!/usr/bin/env python3
"""Arm C: no LLM in the path. run → acceptance eval → close, one JSONL record per run."""
import json, re, subprocess, sys, time, os
P = os.path.join(os.path.dirname(__file__), '../../../plugins/chrome/skills/cdp-chrome/scripts/page.mjs')
TASKS = json.load(open(os.path.join(os.path.dirname(__file__), 'tasks.json')))
OUT = os.path.join(os.path.dirname(__file__), 'results.jsonl')

def sh(*args, timeout=300):
    r = subprocess.run([P, *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout + r.stderr

def score(trace, expected):
    """Walk the trace against the ordered expected patterns. Neutral: WAIT, DONE deferred, unsure, FAILED re-tries."""
    i, matched, wasted = 0, 0, 0
    for line in trace:
        body = re.sub(r'^\d+\. ', '', line)
        if re.match(r'(WAIT|DONE|BLOCKED|unsure|DONE deferred)', body) or '→ FAILED' in body: continue
        if i < len(expected) and re.search(expected[i], body): i += 1; matched += 1
        elif any(re.search(e, body) for e in expected[:i]): continue      # repeating a satisfied step (benign)
        else: wasted += 1
    return matched, wasted, len(expected) - i

def one(task, n):
    args = ['run', task['url'], task['goal'], '--max-steps', '30', '--text', '0']
    for k, v in task['values'].items(): args += ['--value', f'{k}={v}']
    t0 = time.time()
    code, out = sh(*args)
    secs = time.time() - t0
    status = re.search(r'^(DONE|UNSURE|BLOCKED|STUCK|NEEDS_CONFIRMATION|MAX_STEPS)', out, re.M)
    m = re.search(r'run: (\d+) steps in ([\d.]+)s, of which Jev ([\d.]+)s', out)
    tab = re.search(r'tab ([0-9A-F]{8})', out)
    trace = [l for l in out.splitlines() if re.match(r'^\d+\. ', l)]
    accept = None
    if tab:
        time.sleep(2)
        _, ev = sh('eval', tab.group(1), task['accept'])
        accept = ev.strip().splitlines()[0] == 'true' if ev.strip() else False
        sh('close', tab.group(1))
    matched, wasted, missing = score(trace, task['expected'])
    rec = {'arm': 'C', 'task': task['id'], 'run': n, 'status': status.group(1) if status else 'ERROR',
           'steps': int(m.group(1)) if m else None, 'secs': float(m.group(2)) if m else None, 'jev_secs': float(m.group(3)) if m else None,
           'wall': round(secs, 1), 'accept': accept, 'matched': matched, 'wasted': wasted, 'missing': missing,
           'confs': [float(x) for x in re.findall(r'\(op ([\d.]+)', out)], 'trace': trace, 'err': None if status else out[-300:]}
    if task.get('expect_status'): rec['stop_ok'] = rec['status'] == task['expect_status'] and accept
    open(OUT, 'a').write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(f"{task['id']:20} run{n} {rec['status']:18} steps={rec['steps']} secs={rec['secs']} accept={accept} match={matched}/{len(task['expected'])} wasted={wasted}", flush=True)

if __name__ == '__main__':
    ids = sys.argv[1].split(',') if len(sys.argv) > 1 and sys.argv[1] != 'all' else [t['id'] for t in TASKS]
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    for n in range(1, runs + 1):
        for t in TASKS:
            if t['id'] in ids:
                try: one(t, n)
                except Exception as e: print(t['id'], n, 'EXC', e, flush=True)
                time.sleep(3)
