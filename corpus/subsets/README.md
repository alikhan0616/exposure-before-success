# Corpus subsets

Every file here is a **subset or partition of `corpus/attack_prompts.csv`**, kept because a
released run used it. None of them contains a payload that is not in the main corpus: the
`injected_text` bytes are identical, and only the selection of rows differs.

| file | rows | what used it |
| --- | --- | --- |
| `_shard_a1.csv`, `_shard_a2.csv`, `_shard_a3.csv` | 42 each | the three-process sharded run of `gpt-oss-20b` (`final_gptoss_s{1,2,3}.jsonl`) |
| `_shard_b1.csv`, `_shard_b2.csv` | 63 each | the two-process sharded run of `qwen-2.5-7b` (`final_qwen_s{1,2}.jsonl`) |
| `_smoke_or.csv` | 6 | the qualification screens (`smoke_*.jsonl`, `_smoke3_*.jsonl`) |
| `_preflight_lang.csv` | 12 | the language-of-reply pre-flight (`preflight_lang_ur.jsonl`) |
| `_probe_websearch.csv` | 6 | the rejected prompt-side placement fix (`_probe_websearch.jsonl`) |

**Shards are partitions, not samples.** Each shard set reconstructs the full 126-row corpus
exactly, and the split is **by `instance_id`**, so all three language rows of an attack always
stay inside one shard. That is what makes a sharded run equivalent to a single run: a paired
language comparison is never split across two processes. Trial identifiers derive from the prompt
identifier, so shards cannot collide, and `analysis/aggregate.py` takes several files at once.

Verify the partition:

```bash
python - <<'PY'
import csv
main = list(csv.reader(open('corpus/attack_prompts.csv', encoding='utf-8')))[1:]
sh = []
for s in ['a1', 'a2', 'a3']:
    sh += list(csv.reader(open(f'corpus/subsets/_shard_{s}.csv', encoding='utf-8')))[1:]
print(len(sh), sorted(map(repr, sh)) == sorted(map(repr, main)))
PY
```

**Bibliographic metadata was refreshed on 2026-09-09** so that these files agree with the
corrected `attack_prompts.csv`. The runs themselves were executed against the earlier metadata,
which differed only in the `source_citation` and `source_dataset_ref` columns; no payload, target,
identifier or task assignment changed, so every released trial remains reproducible from these
files.
