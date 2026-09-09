"""Build corpus/readframe_web.csv: the 42 web_search rows re-pointed at the
read-frame task. Same injected_text byte-for-byte; only ids and user_task_id move.
Pre-registered 2026-09-05; see docs/PROTOCOL.md."""
import csv, io, os

# Paths are derived from this file, which sits in harness/scripts/.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, 'corpus', 'attack_prompts.csv')
DST = os.path.join(REPO, 'corpus', 'readframe_web.csv')

with io.open(SRC, newline='', encoding='utf-8') as fh:
    reader = csv.DictReader(fh)
    fields = list(reader.fieldnames)
    rows = list(reader)

out = []
for r in rows:
    if r['environment'] != 'web_search':
        continue
    r = dict(r)
    assert r['user_task_id'] == 'websearch_shortlist_action', r['user_task_id']
    lang = r['language']
    base = r['instance_id']
    r['instance_id'] = base + '_rd'
    r['id'] = base + '_rd_' + lang
    r['user_task_id'] = 'websearch_recommend_read'
    out.append(r)

assert len(out) == 42, len(out)
assert len({r['id'] for r in out}) == 42
assert len({r['instance_id'] for r in out}) == 14

with io.open(DST, 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=fields, lineterminator='\n')
    w.writeheader()
    w.writerows(out)

raw = io.open(DST, 'rb').read()
print('wrote', DST, len(raw), 'bytes')
print('BOM      :', raw[:3] == b'\xef\xbb\xbf')
print('CR bytes :', raw.count(b'\r'))
print('rows     :', len(out), '| instances:', len({r["instance_id"] for r in out}))

# payload text must be untouched
src_by = {(r['instance_id'], r['language']): r['injected_text']
          for r in rows if r['environment'] == 'web_search'}
bad = [r['id'] for r in out
       if r['injected_text'] != src_by[(r['instance_id'][:-3], r['language'])]]
print('payloads changed:', bad or 'none')
