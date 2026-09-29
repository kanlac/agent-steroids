import json,re,collections,statistics as st
T={t['id']:t for t in json.load(open('tasks.json'))}
def clean(tr): return [l for l in tr if '(op ' in l or 'deferred' in l or 'unsure' in l]
def score(trace, expected):
    acts=[re.sub(r'^\d+\. ','',l) for l in clean(trace) if re.search(r'^\d+\. (CLICK|TYPE|SELECT|PRESS_ENTER|SCROLL)',l) and '→ FAILED' not in l]
    hit=set(); wasted=[]
    for a in acts:
        m=[i for i,e in enumerate(expected) if re.search(e,a)]
        if m: hit.update(m)
        elif re.match(r'CLICK .*(combobox|option|Done|textbox "Departure")',a): pass   # opening/closing a widget on the way: benign
        else: wasted.append(a[:70])
    return len(hit),len(expected),wasted
if __name__=='__main__':
    R=[json.loads(l) for l in open('results.jsonl')]
    by=collections.defaultdict(list)
    for r in R: by[r['task']].append(r)
    print(f"{'task':20}{'accept':>7}{'steps':>7}{'secs':>6}{'jev s':>6}{'coverage':>9}{'wasted':>7}")
    W=collections.Counter()
    for t,rs in by.items():
        cov=[score(r['trace'],T[t]['expected']) for r in rs]
        for c in cov: W.update(c[2])
        print(f"{t:20}{sum(bool(r['accept']) for r in rs):>4}/{len(rs)}{st.mean(r['steps'] for r in rs):7.1f}{st.mean(r['secs'] for r in rs):6.1f}{st.mean(r['jev_secs'] for r in rs):6.1f}{sum(c[0] for c in cov)/sum(c[1] for c in cov):9.2f}{sum(len(c[2]) for c in cov)/len(rs):7.1f}")
    print('\nmost common wasted steps:'); [print(f'  {n}× {w}') for w,n in W.most_common(8)]
