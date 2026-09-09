# Raw trial records — manifest

52 files, **4,671 trial records**, one JSON object per line. These are the primary data: every
number in `README.md`, in the aggregate CSVs and in the manuscript is derived from a file listed
here. Files whose runs were exploratory and are not cited by any finding were not released.

## Record schema

Each line is one trial. Fields, in the order the harness writes them:

| field | meaning |
| --- | --- |
| `run_id`, `trial_id` | run and trial identifiers; `trial_id` derives from `prompt_id`, so shards cannot collide |
| `is_clean_baseline` | true for an un-attacked trial used to measure benign completion |
| `prompt_id`, `instance_id` | corpus row, and the instance it belongs to (one attack in three languages) |
| `attack_pattern`, `environment`, `language`, `variant_num` | the corpus cell |
| `model`, `provider` | model identifier as served, and the gateway used |
| `run_index` | which repeat of this prompt |
| `user_task_id`, `user_task_text`, `user_task_frame` | the honest task the model was given, and whether it is a `read` or `action` frame |
| `benign_task_completed` | whether the honest task was completed in this trial |
| `injected_text` | the payload exactly as the model received it, byte for byte |
| `expected_malicious_action`, `attacker_target` | what the attack asked for, and against what |
| `success_score`, `success_label`, `checker_notes` | 1.0 / 0.5 / 0.0, its label, and the checker's own explanation |
| `tool_call_trace` | every tool call in order, with arguments |
| `final_assistant_message` | the model's answer to the user |
| `payload_seen` | **whether the injected text ever entered the model's context through its own tool calls** |
| `wall_clock_seconds`, `timestamp` | timing |
| `error` | populated only when the harness could not observe the trial; such rows are excluded from every denominator and never counted as zeros |
| `reached_step_limit` | whether the agent loop hit its step cap |

`payload_seen` is the field that distinguishes this dataset from a conventional attack-success
log. Read it before reading any success score.

No API keys, credentials, real email addresses, real people or real services appear in any record.
All environments are simulated and all fixture identities are invented.

## Files

`inj` is injection trials, `base` clean baseline trials, `err` error rows (already excluded from
every denominator).

| file | records | inj | base | err | model | first run |
| --- | --- | --- | --- | --- | --- | --- |
| **Main runs — the three models at 3 repeats** |||||||
| `final_gptoss_s1.jsonl` | 132 | 126 | 6 | 0 | openai/gpt-oss-20b | 2026-09-04 |
| `final_gptoss_s2.jsonl` | 132 | 126 | 6 | 0 | openai/gpt-oss-20b | 2026-09-04 |
| `final_gptoss_s3.jsonl` | 132 | 126 | 6 | 0 | openai/gpt-oss-20b | 2026-09-04 |
| `final_gemma.jsonl` | 390 | 378 | 12 | 0 | google/gemma-4-31b-it | 2026-09-04 |
| `final_qwen_s1.jsonl` | 195 | 189 | 6 | 0 | qwen/qwen-2.5-7b-instruct | 2026-09-04 |
| `final_qwen_s2.jsonl` | 195 | 189 | 6 | 0 | qwen/qwen-2.5-7b-instruct | 2026-09-04 |
| **Read-frame arm — the F9 placement manipulation** |||||||
| `readframe_gptoss.jsonl` | 132 | 126 | 6 | 0 | openai/gpt-oss-20b | 2026-09-05 |
| `readframe_gemma.jsonl` | 132 | 126 | 6 | 0 | google/gemma-4-31b-it | 2026-09-05 |
| `readframe_qwen.jsonl` | 132 | 126 | 6 | 0 | qwen/qwen-2.5-7b-instruct | 2026-09-05 |
| `readframe_gptoss_r2.jsonl` | 132 | 126 | 6 | 0 | openai/gpt-oss-20b | 2026-09-05 |
| `readframe_gemma_r2.jsonl` | 132 | 126 | 6 | 0 | google/gemma-4-31b-it | 2026-09-05 |
| `readframe_qwen_r2.jsonl` | 132 | 126 | 6 | 0 | qwen/qwen-2.5-7b-instruct | 2026-09-05 |
| **Four-model expansion, action frame, 1 repeat — exposure and tool use only** |||||||
| `full_gptoss120_s1.jsonl` | 48 | 42 | 6 | 0 | openai/gpt-oss-120b | 2026-09-05 |
| `full_gptoss120_s2.jsonl` | 48 | 42 | 6 | 0 | openai/gpt-oss-120b | 2026-09-05 |
| `full_gptoss120_s3.jsonl` | 48 | 42 | 6 | 0 | openai/gpt-oss-120b | 2026-09-05 |
| `full_mistralsmall_s1.jsonl` | 69 | 63 | 6 | 0 | mistralai/mistral-small-3.2-24b-instruct | 2026-09-05 |
| `full_mistralsmall_s2.jsonl` | 69 | 63 | 6 | 0 | mistralai/mistral-small-3.2-24b-instruct | 2026-09-05 |
| `full_nemo.jsonl` | 132 | 126 | 6 | 0 | mistralai/mistral-nemo | 2026-09-05 |
| `full_nemo_r2.jsonl` | 132 | 126 | 6 | 0 | mistralai/mistral-nemo | 2026-09-05 |
| `full_qwen330.jsonl` | 132 | 126 | 6 | 0 | qwen/qwen3-30b-a3b-instruct-2507 | 2026-09-05 |
| **Four-model expansion, read frame, 1 repeat** |||||||
| `read_gptoss120.jsonl` | 48 | 42 | 6 | 0 | openai/gpt-oss-120b | 2026-09-05 |
| `read_mistralsmall.jsonl` | 48 | 42 | 6 | 2 | mistralai/mistral-small-3.2-24b-instruct | 2026-09-05 |
| `read_nemo.jsonl` | 48 | 42 | 6 | 1 | mistralai/mistral-nemo | 2026-09-05 |
| `read_qwen330.jsonl` | 48 | 42 | 6 | 0 | qwen/qwen3-30b-a3b-instruct-2507 | 2026-09-05 |
| **Control A — benign completion at 8 repeats per task, and the planted-page base rate** |||||||
| `control_a_gptoss.jsonl` | 48 | 0 | 48 | 0 | openai/gpt-oss-20b | 2026-09-04 |
| `control_a_gemma.jsonl` | 48 | 0 | 48 | 0 | google/gemma-4-31b-it | 2026-09-04 |
| `control_a_qwen.jsonl` | 48 | 0 | 48 | 0 | qwen/qwen-2.5-7b-instruct | 2026-09-07 |
| `control_a_llama.jsonl` | 48 | 0 | 48 | 8 | meta-llama/llama-3.3-70b-instruct | 2026-09-04 |
| `control_a_novalite.jsonl` | 48 | 0 | 48 | 0 | amazon/nova-lite-v1 | 2026-09-05 |
| `control_a_ministral8.jsonl` | 48 | 0 | 48 | 0 | mistralai/ministral-8b-2512 | 2026-09-05 |
| **Control B — benign instruction-following** |||||||
| `control_b_benign.jsonl` | 117 | 105 | 12 | 0 | openai/gpt-oss-20b | 2026-09-04 |
| `ctrlb_gptoss.jsonl` | 117 | 105 | 12 | 0 | openai/gpt-oss-20b | 2026-09-04 |
| `ctrlb_gemma.jsonl` | 117 | 105 | 12 | 0 | google/gemma-4-31b-it | 2026-09-04 |
| `ctrlb_qwen.jsonl` | 117 | 105 | 12 | 0 | qwen/qwen-2.5-7b-instruct | 2026-09-04 |
| **Earlier full runs — superseded, retained for the record** |||||||
| `v2_full_openrouter_20b.jsonl` | 390 | 378 | 12 | 0 | openai/gpt-oss-20b | 2026-09-04 |
| `full_run_openrouter_20b.jsonl` | 390 | 378 | 12 | 0 | openai/gpt-oss-20b | 2026-09-04 |
| **Qualification screens — 11 candidates, 12 trials each** |||||||
| `smoke_gptoss120.jsonl` | 12 | 6 | 6 | 0 | openai/gpt-oss-120b | 2026-09-05 |
| `smoke_mistralsmall.jsonl` | 12 | 6 | 6 | 0 | mistralai/mistral-small-3.2-24b-instruct | 2026-09-05 |
| `smoke_nemo.jsonl` | 12 | 6 | 6 | 0 | mistralai/mistral-nemo | 2026-09-05 |
| `smoke_qwen330.jsonl` | 12 | 6 | 6 | 0 | qwen/qwen3-30b-a3b-instruct-2507 | 2026-09-05 |
| `smoke_llama31.jsonl` | 12 | 6 | 6 | 0 | meta-llama/llama-3.1-8b-instruct | 2026-09-05 |
| `smoke_ministral8.jsonl` | 12 | 6 | 6 | 0 | mistralai/ministral-8b-2512 | 2026-09-05 |
| `smoke_novalite.jsonl` | 12 | 6 | 6 | 0 | amazon/nova-lite-v1 | 2026-09-05 |
| `_smoke3_gptoss.jsonl` | 12 | 6 | 6 | 0 | openai/gpt-oss-20b | 2026-09-04 |
| `_smoke3_gemma.jsonl` | 12 | 6 | 6 | 0 | google/gemma-4-31b-it | 2026-09-04 |
| `_smoke3_llama.jsonl` | 12 | 6 | 6 | 2 | meta-llama/llama-3.3-70b-instruct | 2026-09-04 |
| `_smoke_qwen7b.jsonl` | 18 | 6 | 12 | 0 | qwen/qwen-2.5-7b-instruct | 2026-09-04 |
| `_smoke_qwen32b.jsonl` | 3 | 0 | 3 | 0 | qwen/qwen3-32b | 2026-09-04 |
| `_smoke_or.jsonl` | 6 | 6 | 0 | 0 | openai/gpt-oss-20b | 2026-09-04 |
| **Evidence for specific claims** |||||||
| `preflight_lang_ur.jsonl` | 12 | 12 | 0 | 1 | openai/gpt-oss-20b | 2026-09-04 |
| `_probe_websearch.jsonl` | 6 | 6 | 0 | 0 | openai/gpt-oss-20b | 2026-09-04 |
| `_failed_qwen_r2_provider525.jsonl` | 132 | 126 | 6 | 132 | qwen/qwen-2.5-7b-instruct | 2026-09-05 |

## Which finding rests on which file

| finding | files |
| --- | --- |
| **F1** exposure is model-dependent | `final_*.jsonl` |
| **F9** exposure is a placement property | `readframe_*.jsonl` against `final_*.jsonl`; extended by `full_*.jsonl` against `read_*.jsonl` |
| **F12** tool calls predict measurability | tool traces in `final_*.jsonl`, `full_*.jsonl` |
| **F13** what replicates | `readframe_*_r2.jsonl`, `full_nemo_r2.jsonl` against their run-1 files |
| **F14** rank inversion | all seven usable models' action-frame files |
| **F2** phantom successes | `final_qwen_s*.jsonl`, `full_nemo{,_r2}.jsonl`; the control uses `full_gptoss120_s*.jsonl`, `final_gptoss_s*.jsonl`, `final_gemma.jsonl` |
| **F3 / F3a** capability floor | `control_a_*.jsonl`, with `smoke_*.jsonl` and `_smoke3_*.jsonl` for the screen-versus-measurement comparison |
| **F4** planted-page base rate | `control_a_{gptoss,gemma,llama}.jsonl` |
| **F5** non-determinism | `v2_full_openrouter_20b.jsonl`, `readframe_*{,_r2}.jsonl`; the provider outage is `_failed_qwen_r2_provider525.jsonl` |
| **F6** language null across models | `final_*.jsonl`, inbox rows only |
| **F7** benign control instability | `control_b_benign.jsonl`, `ctrlb_*.jsonl` |
| **F8** calendar floored | `final_*.jsonl`, calendar rows only |
| **F10** failed replication | `readframe_gptoss{,_r2}.jsonl`, `readframe_gemma{,_r2}.jsonl` |
| Language-of-reply pre-flight | `preflight_lang_ur.jsonl` |
| Rejected prompt-side fix | `_probe_websearch.jsonl` |

## Notes on individual files

- **`_failed_qwen_r2_provider525.jsonl`** contains **no usable trials**. Every one of its 132
  records is an error row: the gateway routed the model to a failing upstream provider (HTTP 525)
  and no call succeeded. It is released because it is the direct evidence for F5's routing claim
  and for the recommendation to pin a back-end before any run whose numbers will be published.
- **`control_a_llama.jsonl`** carries 8 error rows, all on the calendar task, where the model
  emitted its tool calls as message text. Those rows are errors rather than zeros by design; see
  `docs/PROTOCOL.md`, Part 2.
- **`_smoke_qwen32b.jsonl`** stops after 3 trials. The candidate was excluded on latency, at about
  88 seconds per trial, which would have made one full run take about 9.6 hours.
- **`full_run_openrouter_20b.jsonl`** is superseded by `v2_full_openrouter_20b.jsonl` for every
  web_search number, because the payload placement changed between them. Its inbox and calendar
  rows remain valid. It is released so the superseded figures can be checked rather than taken on
  trust.
- **Sharded runs** (`_s1`, `_s2`, `_s3`) are one run split by `instance_id` so that a language
  triplet always stays whole inside one shard. Aggregate them together, never separately:
  `python analysis/aggregate.py results/raw_trials/final_gptoss_s*.jsonl --out <dir>`.
- **Files beginning with an underscore** are screening and diagnostic runs from before the naming
  convention settled. The names are kept exactly as they appear in the reports under `results/` so
  that every citation resolves.
