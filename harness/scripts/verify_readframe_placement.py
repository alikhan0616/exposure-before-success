"""Does the read-frame payload actually reach the model via search_web alone?

Verifies the mechanism pre-registered on 2026-09-05 (docs/PROTOCOL.md, Part 4)
offline, before any trial is run: the read placement must put the payload inside
the search snippet on every row, and the action placement must put it outside on
every row. Run from anywhere:  python harness/scripts/verify_readframe_placement.py
"""
import sys, io, os
sys.stdout.reconfigure(encoding='utf-8')

# Paths are derived from this file, which sits in harness/scripts/.
HARNESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(HARNESS)
sys.path.insert(0, HARNESS)

from src.corpus_loader import load_corpus
from src.task_types import get_user_task, fixture_anchors
from src.environments.web_search import SearchIndex, SNIPPET_CHARS
from src.injection_points import PLACEMENTS
from src.tools import web_search_tools

tasks, _ = load_corpus(os.path.join(REPO, 'corpus', 'readframe_web.csv'))
ut = get_user_task('websearch_recommend_read')
anchors = fixture_anchors(ut.fixture_path)

print(f'SNIPPET_CHARS = {SNIPPET_CHARS}   user_prompt = {ut.user_prompt!r}\n')

ok_snip = ok_deep = 0
for t in tasks:
    # ---- read frame (new) ----
    env = SearchIndex.from_fixture(ut.fixture_path)
    PLACEMENTS['websearch_recommend_read'](env, t.injected_text, anchors)
    results = web_search_tools.search_web(env, ut.user_prompt)
    blob = ' '.join(str(r.get('snippet', '')) for r in results)
    probe = t.injected_text.strip()[:40]
    seen_read = probe in blob

    # ---- action frame (existing), same payload, for contrast ----
    env2 = SearchIndex.from_fixture(ut.fixture_path)
    PLACEMENTS['websearch_shortlist_action'](env2, t.injected_text, anchors)
    blob2 = ' '.join(str(r.get('snippet', '')) for r in
                     web_search_tools.search_web(env2, ut.user_prompt))
    seen_act = probe in blob2

    ok_snip += seen_read
    ok_deep += seen_act
    if not seen_read:
        print('  MISS(read):', t.prompt_id, '|', probe[:60])

print(f'read frame  — payload visible in search_web snippet: {ok_snip}/42')
print(f'action frame— payload visible in search_web snippet: {ok_deep}/42  (expected 0)')

# does the action-frame payload need fetch_page?
env3 = SearchIndex.from_fixture(ut.fixture_path)
t0 = tasks[0]
PLACEMENTS['websearch_shortlist_action'](env3, t0.injected_text, anchors)
page = web_search_tools.fetch_page(env3, anchors['top_result_url'])
print('action frame— payload reachable via fetch_page:',
      t0.injected_text.strip()[:40] in str(page))
