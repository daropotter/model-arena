# model-arena

Run local LLMs through [opencode](https://opencode.ai) on graded agentic
tasks, fully sandboxed, and get a pass/fail scorecard per model.

Every local run is isolated: the model sees only the task workspace, has no
internet access, and cannot touch the hidden grader. Hosted providers require
internet access and are therefore a separate, weaker trust boundary; see
"Limitations" below.

## Why

Running a local model through `ollama run` and chatting with it tells you
very little about whether it can *do work*. model-arena asks a different
question: put the model in a sandboxed workspace with the same tools a
developer has (read, edit, bash, tests), give it a specification, and see
whether it ships a solution that passes a hidden test suite it never saw.

This makes the evaluation:

- **Agentic** — the model must plan, read files, run commands and fix its
  own failures; a wrong one-off answer scores nothing.
- **Cheap and local** — anything `ollama` can serve fits the same harness,
  from 3B models on a laptop GPU to CPU-offloaded 30B models.
- **Honest** — grading is deterministic, hidden, and compares against
  reference implementations; there is no "vibes" score.

Typical use cases: picking a model for a local coding agent, comparing a
new release against the current roster, or screening candidate models
before letting them touch real code.

## How it works

```
       host                                 docker container (arena-net)
 ┌────────────────┐   TCP proxy   ┌─────────────────────────────────────┐
 │ ollama         │◄──────────────┤ opencode run -m ollama/...          │
 │ 127.0.0.1:11434│  172.22.0.1   │ /workspace  (task starter, rw)      │
 └────────────────┘   :11435       │ no internet, no host filesystem     │
                                   └─────────────────────────────────────┘
                                               │ after the agent exits
                                               ▼
                                    grader container (--network none)
                                    grader UID 0, submission UID 1000
                                    hidden tests/result inaccessible to code
```

- **Isolation**: the agent container is attached to an `--internal` docker
  network, so there is no internet and no route to the LAN. The only reachable
  endpoint is a small host-side TCP proxy (`runner/ollama_proxy.py`) that
  exposes `127.0.0.1:11434` (Ollama) on the bridge gateway.
- **Tamper detection**: `meta.json` lists protected paths (the spec, visible
  tests). If the model modifies or deletes one of them, the run is failed
  automatically without grading.
- **Grading**: each task ships `grader/grade.py`, a hidden test suite that
  runs against the finished workspace read-only. The grader and its result
  live in root-only directories; every submitted program is dropped to UID
  1000 and cannot read either. Graders compare against reference
  implementations or drive the CLI through cases the model never saw.
- **Metrics**: the runner parses opencode's `--format json` event stream and
  records tokens (in/out), steps, tool calls, tool errors, duration, timeouts
  and every file touched.
- **Result validity**: provider/API, runner and grader failures are recorded
  separately and excluded from quality averages. The latest valid attempt is
  preferred over a later failed retry.
- **Provenance**: schema-v2 records include suite ID, task/starter/grader,
  prompt, runner and Docker hashes, image ID, timeout policy and model options.

## Design principles

- **Trust nothing the model touches.** The prompt, the spec, the visible
  tests and the starter code are all *inside* the sandbox; the grader, the
  reference solution and the host are all *outside* it. A model that edits
  the spec or the tests to make itself pass is caught by the tamper check
  (protected paths in `meta.json`) and the run is failed without grading.
- **Hidden, deterministic grading.** Every grader runs fixed cases with no
  network and no timing thresholds (except `cronlog`, whose subject *is*
  timing). Two runs of the same workspace give the same score. Graders
  compare against reference implementations instead of hardcoded fixtures,
  so solutions are tested on inputs nobody has seen.
- **The starter is the floor.** Visible tests pass on the buggy starter and
  cover only a slice of the spec. A model that does nothing scores the
  baseline floor for that task (e.g. 0.55 on `tasklog`) — scores only make
  sense relative to that floor, not to 0.
- **Timeouts are a diagnosis, not a verdict.** The deadline is soft (see
  "Timeout model"): the runner kills a model only when it has actually
  stopped making progress. A slow model that finishes past the deadline
  gets graded normally; its runtime is reported either way.
- **One task, one capability.** Each task targets a single skill — reading
  a spec, fixing subtle bugs, concurrency, reverse-engineering, algorithm
  design — so a failure points at something concrete.

## Setup

```bash
docker/build.sh                # build the model-arena-agent image
python3 runner/verify_tasks.py # sanity: every starter fails, every solution passes
```

Requirements: docker, python3, and Ollama listening on `127.0.0.1:11434`.
The proxy and the `arena-net` network are created automatically on first run.

`docker/build.sh` expects a base image with node + opencode + git + ripgrep
available (the Dockerfile builds from `node:22-bookworm-slim` and installs
the rest). Override the tagged image with `ARENA_IMAGE` and edit
`docker/Dockerfile` if your base differs.

## Tests

The repository suite is stdlib `unittest` (no pytest needed):

```bash
python3 tests/run_all.py             # all groups
python3 tests/run_all.py unit        # outcomes, aggregation, provenance, deadlines
python3 tests/run_all.py integration # docker isolation, lifecycle, proxy, regrade
python3 tests/run_all.py oracles     # independent cross-checks of task oracles
```

- `unit/` — outcome/validity classification, repeat aggregation, report merge,
  CSV round-trip, provenance matching, and the agent supervision state machine.
- `integration/` — adversarial grader isolation (a probe tries every known way
  to read the hidden grader or forge a result), container limits/timeouts and
  cleanup, the restricted Ollama inference proxy, and regrade integrity. Docker
  tests skip automatically when docker is unavailable.
- `oracles/` — independent verification that does not import the shipped
  solutions: regex checked against a generated NFA, scheduler against
  brute-force permutations, merge against hand-computed cases, interpreter
  metamorphic tests, codec hand-built frames, and a filedock manifest-only
  cheat that must fail.

## Usage

```bash
# what is available
python3 runner/arena.py --list

# one model, all tasks
python3 runner/arena.py --models ollama/gemma4-128k:latest

# several models, a subset of tasks, 3 repetitions each
python3 runner/arena.py \
  --models ollama/gemma4-128k:latest ollama/qwen3.5-64k:latest \
  --task ledger tasklog cronlog --repeats 3

# models from a file, per-run deadline of 1800s (soft — see "Timeout model")
cat > models.txt <<EOF
ollama/gemma4:12b
ollama/gemma4:26b
ollama/qwen3.6:35b
EOF
python3 runner/arena.py --models-file models.txt --timeout 900
```

Repetitions are stored as separate attempts under one `batch_id`. Reports use
the batch mean score, all-repeats pass status and median duration while
retaining the individual scores for variance analysis.

Output:

- `results/report.md` and `results/report.csv` — pass/fail matrix plus
  per-run details (time, tokens, tool calls, failure reason).
- `results/models-report.md` — the detailed per-model report (full sweep +
  prescreen + A/B): verdicts, per-task status, tool streams, raw-data paths.
- `results/roster.md` — the competition roster: qualified vs excluded, with
  reasons. Regenerate with `python3 runner/roster.py`.
- `results/analysis.md` — failure-mode breakdown per model/task.
- `results/<timestamp>__<task>__<model>/` — the full evidence: `events.jsonl`
  (raw opencode stream), `stderr.log`, `record.json`, `grade/result.json`,
  and a content-hashed `submission/` snapshot for post-mortem and regrading.

## Tasks

| task | tier | what it tests | hidden grading |
|---|---|---|---|
| `smoke` | basic | prescreen: read a file, compute a sum, write the answer | exact answer, protected input files |
| `sumtool` | easy | fix 2 obvious bugs in one function (docstring is the contract) | decimals, signs, malformed tokens, formatting |
| `filedock` | easy | organize inbox files by date, deduplicate by content, manifest | unseen inboxes (seeded), invalid dates, idempotency |
| `ledger` | medium | repair-by-spec: 4 subtle bugs (float math, unstable tie sort, zero-count, negative fees) | hidden cases incl. rounding ties, lexicographic/stable ordering |
| `tasklog` | medium | cross-file feature + store migration v1→v2 | full CLI contract, snooze arithmetic, summary, corruption handling |
| `pipeline` | medium | two CLIs that must agree: pack/unpack round-trip of JSON | byte-exact pipe format, escaping, malformed-pipe rejection |
| `codec` | hard | binary frame codec: magic, varint length, CRC32 | byte-exact frames across varint boundaries, corrupted frames |
| `cronlog` | hard | concurrency: flock discipline, lock timeout, atomic replacement | grader holds real locks and spawns parallel writers |
| `datajanitor` | hard | messy CSV normalization: BOM, repeated headers, multi-format amounts/dates, duplicates, idempotency | unseen exports, byte-exact CSV + report comparison |
| `generator` | hard | reverse-engineering: recover an LCG + output permutation from samples | unseen seeds, offsets beyond samples, 500-step exactness |
| `scheduler` | hard | algorithm design: minimize late jobs with deadlines + dependencies | unseen instances incl. anti-greedy, cycles must be rejected |
| `interpreter` | hard | lexical scoping, closures and strict AST validation | capture/shadowing, malformed nodes and runtime type errors |
| `regex` | hard | parser plus greedy matching with full backtracking | alternatives/groups/stars, classes and malformed patterns |
| `merge` | hard | deterministic base-coordinate three-way line merge | insertions, deletions, repeated lines and conflict regions |
| `kvstore` | hard | crash-safe JSON key-value store: WAL records, atomic batches, recovery | WAL-only recovery, torn tails, corrupted records, null vs missing |

Each task directory:

```
tasks/<name>/
  meta.json      name, timeout, difficulty, protected paths
  prompt.md      what the agent is told (no solution leaked)
  starter/       initial workspace the agent sees
  grader/        hidden test suite (never mounted into the agent container)
  solution/      reference solution, used only by verify_tasks.py
```

New tasks added 2026-09-25 (review): `sumtool` + `filedock` (easy, to give
local models passable targets below `ledger`), `pipeline` (medium chain),
`codec` + `scheduler` (hard, to discriminate between the top Zen models
that all score 5/5 on the original five). `roster.md` and `analysis.md`
now break passes down per difficulty tier.

## Adding a task

1. `tasks/<name>/meta.json` with `name`, `title`, `timeout`, `protected`.
2. `prompt.md` — the instruction. Never the answer.
3. `starter/` — buggy or incomplete code plus visible tests that pass today.
4. `grader/grade.py <workspace> <out.json>` — must exit 0 and write
   `{"passed", "score", "detail", "cases"}`.
5. `solution/` — a copy of the starter with the correct implementation
   overlaid; `verify_tasks.py` uses it to prove the grader is passable.
6. Run `python3 runner/verify_tasks.py` before using the task.

Design rules that keep tasks discriminative:

- Visible tests must pass on the starter but cover only a slice of the spec.
- The spec must be unambiguous; every hidden failure should be a real
  mistake, not a coin flip.
- Prefer comparisons against a reference implementation over exact-output
  fixtures.
- Include an anti-shortcut case (hardcoded answers, sample-fitting) where
  relevant.
- Keep grading deterministic: use fixed seeds/cases, no network, no timing
  thresholds unless the task is about them.

## Environment knobs

| variable | default | meaning |
|---|---|---|
| `ARENA_IMAGE` | `model-arena-agent` | agent/grader image |
| `ARENA_NETWORK` | `arena-net` | docker network (created as `--internal`) |
| `ARENA_SUBNET` | `172.22.0.0/16` | verified subnet for the internal network |
| `ARENA_GATEWAY` | `172.22.0.1` | bridge gateway hosting the proxy |
| `ARENA_OLLAMA_PORT` | `11435` | proxy listen port |
| `ARENA_MEMORY` / `ARENA_CPUS` | `6g` / `8` | container limits |
| `ARENA_SCRATCH` | `/tmp/model-arena` | per-run workspace root |
| `ARENA_NO_THINK` | unset | `1` turns off reasoning for thinking models (qwen3.8 etc.) |
| `ARENA_MODEL_OPTS` | unset | raw ollama model options for one model, e.g. `, "options": { "num_ctx": 16384 }` |
| `ARENA_IDLE_GRACE` | `900` | seconds without new events after the deadline before a run is stopped |
| `ARENA_POST_DEADLINE` | `1800` | hard wall beyond the deadline (entry script + runner safety net) |
| `ARENA_WARMUP_TIMEOUT` | `900` | seconds allowed for the pre-run model load |
| `ARENA_SMOKE_TIMEOUT` | `900` | prescreen smoke limit, independent of `--timeout` |
| `ARENA_HOSTED_NETWORK` | `bridge` | docker network for hosted (non-ollama) models |
| `ARENA_GRADER_MEMORY` / `ARENA_GRADER_CPUS` | `1g` / `2` | grader limits |
| `ARENA_GRADER_PIDS` / `ARENA_PIDS` | `128` / `256` | grader/agent PID limits |
| `ARENA_SUITE_ID` | `model-arena-v2` | comparability cohort stored in records |

## Timeout model (updated 2026-09-25)

`--timeout` is a **deadline, not a hard kill**. Local models can be very slow
(partial GPU offload: a single generation can take **>700 s with zero
events**) — killing them at the limit was losing finished work. Now:

- After the deadline the runner watches the event stream: while the model
  keeps emitting events, it gets time to finish the current step.
- A model making no progress (`ARENA_IDLE_GRACE`, default 900 s with no event
  **after** the deadline) is stopped gently (`docker stop`) — opencode has
  time to flush the event stream.
- The final hard wall: deadline + `ARENA_POST_DEADLINE` (default 1800 s),
  consistent between the entry script and the runner — a safety net only.
- A model that **never** emitted an event (failed to load, provider error,
  no key) is killed at deadline + 120 s.
- `timed_out` in the record = the runner had to kill the container
  (rc 137/143). A model that finishes past the deadline is **slow, not
  "timed out"** — the runtime is still in `duration_s` and in the reports.
- The default `--timeout` is 1800 s (was 900). This does not skew grading:
  the run is graded normally after it stops; rescued work is work that was
  really done.

### Running long jobs in the background

Do NOT start `arena.py` in the background from an interactive terminal or via
`nohup … &` from tools/agents that kill the process group on timeout (the
runner has been killed this way twice, leaving orphan docker containers with
no `record.json`). Use `setsid` (detaches from the process group):

```bash
setsid bash -c 'cd /path/to/model-arena && python3 -u runner/arena.py \
  --models-file models.txt --timeout 1800 --results results --merge \
  > results/run.log 2>&1' </dev/null >/dev/null 2>&1 &
```

Rebuild the image after changes: `docker/build.sh`.

## Limitations

- **Local models run at local speed.** Models bigger than the GPU's VRAM
  run on partial CPU offload and can take tens of minutes per task; the
  harness gives them the time (soft deadline), but a full sweep of large
  models is an overnight job.
- **The harness is opencode-specific.** It wraps `opencode run` (any model
  opencode can talk to). Wiring in a different agent framework means
  adapting the event-stream parser and the entry script.
- **Grading measures the model-in-the-loop, not the raw model.** Prompt
  phrasing, tool descriptions and opencode's own scaffolding all influence
  the result. This is a property: the point is to measure the agent, not
  the weights.
- **Results are hardware-bound.** Token rates (and therefore any
  time-related observations) apply to the GPU they were measured on
  (12 GB VRAM in the published results). Scores and passes are comparable only
  within the same suite/protocol hashes; durations are not.
- **The free Zen models are rate-limited** (HTTP 429 without
  `OPENCODE_API_KEY`) and can be slow; a run with 0 output tokens usually
  means the provider refused, not that the model is dumb.
- **Hosted runs are not a secret-safe sandbox.** They need unrestricted
  provider egress and opencode receives `OPENCODE_API_KEY`. Because the coding
  agent can execute shell commands, do not run untrusted task content or an
  untrusted provider model with a long-lived valuable key. Use a scoped key
  and rotate it after experiments. Local Ollama runs do not receive this key.

## Troubleshooting

| symptom | likely cause | fix |
|---|---|---|
| run hangs, `stderr.log` ends with `Killed` | container hit the hard wall | increase `--timeout` / `ARENA_POST_DEADLINE`; check `events.jsonl` for progress |
| 0 events, 0 output tokens | model did not load, provider error (hosted), or ollama rejects tools | prescreen: warmup first; check `capabilities` has `tools`; `OPENCODE_API_KEY` for Zen |
| grader says `tamper: protected files modified` | the model edited the spec/tests | real (and fair) failure — the model cheated |
| `report.md` shows fewer tasks than expected | an earlier `--merge` with `--task` | regenerate reports: `report_models.py`, `roster.py`, `analyze.py` |
| docker run fails with `network arena-net not found` | network was deleted | run once with a local model (the runner recreates it), or `docker network create --internal arena-net` |
| CUDA OOM / HTTP 500 on ollama | two models in VRAM at once | runs are sequential; make sure no other process keeps a model loaded (`ollama ps`) |
| `pytest` not found in a task workspace | visible tests are plain unittest; pytest is optional | run `python3 tests/test_visible.py` instead |

## Project layout

```
docker/          agent entry script, Dockerfile, image build
runner/          arena.py (the sweep), prescreen.py, roster.py,
                 report_models.py, analyze.py, regrade.py,
                 verify_tasks.py, ollama_proxy.py
tasks/           one directory per task:
                   meta.json    name, timeout, difficulty, protected paths
                   prompt.md    what the agent is told
                   starter/     buggy/incomplete code + visible tests
                   grader/      hidden test suite (+ reference)
                   solution/    correct implementation (verify only)
tests/           repository test suite (unit, integration, oracles)
results/         run evidence + generated reports (git-ignored)
```

## Contributing

Contributions are welcome — especially new tasks. A good task is
discriminative: the visible tests pass on the buggy starter, the hidden
suite fails it, and the reference solution passes everything. The bar for
adding a task:

1. Follow "Adding a task" above and the design rules listed there.
2. Run `python3 runner/verify_tasks.py` — it must print `OK` for every
   task (starter fails, solution passes).
3. Keep grading deterministic: fixed seeds/cases, no network, no timing
   thresholds unless the task is about them.
4. Prefer comparing against a reference implementation over byte-exact
   fixtures, and include an anti-shortcut case where hardcoding is possible.

Please keep the docs in English (the code, README and generated reports
are all English).

## License

[MIT](LICENSE)

## Experiment log

Sections below are a running log of past sweeps. They document how
the roster evolved; current standings are always in the generated
reports (`results/roster.md`, `results/models-report.md`).

## Free opencode Zen models (added 2026-09-23)

Zen has 32 free models in the opencode registry; the local install exposes 7:
`muse-spark-1.2/1.3-contributor-free`, `big-pickle`, `ling-3.0-flash-fin-free`,
`nemotron-3-ultra-free`, `nemotron-3.5-lightning-free`, `mimo-v2.6-flash-free`
(plus the rejected `mimo-v2.5-free`). Full list of free models:

```bash
python3 - <<'EOF'
import json
d = json.load(open(__import__("pathlib").Path.home()/".cache/opencode/models.json"))
for mid, m in d["opencode"]["models"].items():
    c = m.get("cost") or {}
    if not (c.get("input") or 0) and not (c.get("output") or 0):
        print(mid)
EOF
```

**Run requirements:**
- internet (hosted models; local ollama models stay on the isolated network),
- `OPENCODE_API_KEY` in the environment — **without it the free tier returns
  HTTP 429 `FreeUsageLimitError`**. The key is inherited by the container and
  is visible to processes inside that hosted-run container; use a scoped key.
  The key from `auth.json` is not enough:
  `FreeTierError: can only be used from within OpenCode`.
- `bridge` instead of `arena-net` (the runner does this automatically for
  non-`ollama/*`).

**Results (155 scored runs, 31 models):** Zen beat the local models.
`muse-spark-1.2` and `1.3` have **5/5 passes (avg 1.00)** — all five tasks,
including `datajanitor`, which was 0/24 for local models. `big-pickle` 4/5
(0.91). After a retry with a longer limit, `nemotron-3-ultra-free` reached
4/5 (0.94) and `nemotron-3.5-lightning-free` 2/5 (was 1/5; needs ~1500 s).
The best local model (`gemma4-200k`) has 1/5 (0.38). Zen can be slow (free
tier, medians 2.5–7 min), so give `--timeout` generously.

## Competition status (2026-09-25)

- **36 models × 5 tasks** (plus prescreen) = 164 scored runs in `results/`.
- **Passes: 29/164.** Zen dominates: `muse-spark-1.2`/`1.3` and `big-pickle`
  **5/5**, `mimo-v2.6-flash` and `nemotron-3-ultra` **4/5**,
  `ling-3.0-flash` **3/5**. Local: `gemma4-200k` and `qwen3.8-32k` 1/5 each
  (both only `ledger`).
- **Retests of timed-out runs (deadline→liveness + warmup outside the limit)
  confirmed:** some Zen models were choked by the limit — big-pickle 4→5,
  mimo 2→4, ling 2→3. `nemotron-3.5-lightning` was not (datajanitor 0.00
  even at 1800 s).
- **Local models have hit their ceiling:** a longer limit produced zero new
  passes. qwen3.8 finishes runs to the end (1225 s = deadline + grace) but
  does not pass cronlog/generator/tasklog.
- **"Thinking" 32b models finally excluded** (fair run at 1200 s +
  `ARENA_NO_THINK`): qwq and deepseek-r1 — 0 tool calls, qwen3:30b — 1,
  qwen2.5:32b — 2; none even passed smoke.
- `datajanitor` remains the barrier for local models (0 passes); Zen passes
  it. It is a test of reading a long spec carefully, not of tools.

Merge: `python3 runner/arena.py --models ... --merge` adds new runs to the
existing report instead of overwriting it.

## Prescreening new models (2026-09-22, 22 models)

New models pass a cheap gate `runner/prescreen.py` before entering the full
sweep. The gate: a warmup (does the model load at all on 12 GB) + one `smoke`
run (read a file, sum it, write the answer).

```bash
python3 runner/prescreen.py --models-file prescreen-candidates.txt
python3 runner/prescreen.py --report-only   # regenerate the report without running
python3 runner/prescreen.py --models ollama/qwen3:14b --timeout 300
```

Pick candidates from ollama by filtering on `capabilities` (`tools` required):

```bash
curl -s http://127.0.0.1:11434/api/show -d '{"model":"qwen3:8b"}' | jq .capabilities
```

**Result for 22 new models:** 20 excluded, 2 BORDERLINE:

| exclusion reason | count | models |
|---|---|---|
| too big for 12 GB VRAM | 10 | nemotron-3-nano:30b, qwen3-next:80b, qwen2.5(-coder):32b, qwq:32b, deepseek-r1:32b, qwen3(-coder):30b, granite4.1/4.2:30b |
| hallucinate tool calls | 7 | qwen2.5-coder:7b/14b, granite4.1:3b, llama3.2:3b, phi4-mini:3.8b, mistral-nemo:12b, deepcoder:14b |
| "think" and do not act | 3 | qwen3:8b, qwen3:14b, qwen3-vl:8b |

**To the second round:** `cogito:14b` and `gpt-oss:20b` (BORDERLINE — they
tried a tool but got lost: cogito used the wrong parameter `file_path`
instead of `filePath` and gave up).

Methodological notes:
- The prescreen must wait for the warmup (loading can take 130-290 s while
  downloading in the background), otherwise you get false "too-slow".
- The size limit is VRAM+8 GB (20 GB), not VRAM+2: ollama splits a model
  between GPU and CPU, so 15-19 GB models can run — just slowly. Verify with
  a real warmup, not size alone. After raising the limit two more candidates
  appeared: granite4.1:30b and qwen3-coder:30b.
- The model must fit warmup + run in VRAM **separately**: two models at once
  give CUDA OOM (HTTP 500). The prescreen runs sequentially.
- `command-r:35b` answers simple questions but gives 0 events as an opencode
  agent — incompatible even though ollama reports `tools`.
- The report merges with `prescreen-results.jsonl`; an executed test
  (record.json) always beats an old log entry.

## Roster (2026-09-22 sweep)

Full sweep: 18 models × 5 tasks, then an A/B test on the tool-hallucinating
models (same runs with an explicit tool-use section appended to AGENTS.md).
Results in `results/roster.md`.

**Qualified (8):** gemma4:200k/128k/64k/12b/latest, qwen3.5-32k, qwen3.5-64k,
qwen2.5. All of them actually called tools; only gemma4-200k passed a task
(`ledger`).

**Excluded (10):**

| reason | models | evidence |
|---|---|---|
| no tool support | gemma3 | ollama returns HTTP 400 `does not support tools` |
| bigger than VRAM | gemma4:26b, gemma4:31b, ornith:35b, qwen3.6:35b | every run timed out with 0 output tokens; llama-server took >300s to load |
| too slow at any size | gemma4-256k | 4/5 timeouts at the 420s cap (long-context KV cache) |
| tool hallucination | llama3.1, mistral, ornith:9b, qwen3.5 | 0 real tool calls in 5/5 runs: prose-only or fake tool calls printed as text |

**A/B verdict on the hallucinators:** tool-use instructions appended to
`AGENTS.md` did not fix them — 8/10 runs identical, 1 worse (timeout), 1
marginal improvement (qwen2.5 tasklog: 2→7 tool calls, still fail). They stay
excluded. The instruction file lives in `docker/agents_extra_tool_use.md` and
is enabled with `ARENA_EXTRA_AGENTS=<path>`.

## Notes

- Models larger than VRAM run by ollama's partial offload and can be orders of
  magnitude slower; give them a generous `--timeout` or keep them out.
- Runs are sequential on purpose. Ollama serves one request at a time by
  default and concurrent runs would corrupt the timing metrics.
- A killed run still yields the event stream and the workspace as-is, so
  timeouts are diagnosable rather than blank.
- The proxy binds the docker bridge gateway explicitly (`--listen
  $ARENA_GATEWAY`), so it is not exposed on the LAN.
