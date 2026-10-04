# model-arena

Run local or hosted LLMs through [opencode](https://opencode.ai) on graded
agentic tasks and get a pass/fail scorecard per model.

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
 ┌────────────────┐  HTTP proxy   ┌─────────────────────────────────────┐
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
  endpoint is the host-side HTTP proxy (`runner/ollama_proxy.py`) on the
  bridge gateway. It forwards only `GET /v1/models`,
  `POST /v1/chat/completions` and `POST /v1/completions` to Ollama;
  administrative endpoints such as model pull/delete are blocked. The
  agent runs as UID 1000 with a read-only container filesystem, writable
  home and `/tmp` tmpfs mounts, no capabilities, and resource limits.
- **Tamper detection**: `meta.json` lists protected paths (the spec, visible
  tests). If the model modifies or deletes one of them, the run is failed
  automatically without grading.
- **Grading**: each task ships `grader/grade.py`, a hidden test suite that
  runs against the finished workspace read-only. The grader and its result
  live in root-only directories; every submitted program is dropped to UID
  1000 and cannot read either. Case permissions do not follow submission
  symlinks or expose private reference-output directories. Graders compare
  against reference implementations or drive the CLI through unseen cases.
  A submission snapshot is saved after the run for later inspection.
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
- **Hidden grading with fixed cases.** Graders run fixed cases with no
  network and no timing thresholds (except `cronlog`, whose subject *is*
  timing). Fixed inputs make results reproducible; an unlocked `cronlog`
  starter can still vary because of process scheduling. Graders use reference
  implementations or explicit expected outputs to check unseen inputs.
- **The starter is the floor.** Visible tests pass on the buggy starter and
  cover only a slice of the spec. A model that does nothing scores the
  baseline floor for that task (e.g. 0.545 on `tasklog`). Canonical floors
  are recorded in `tasks/baselines.json` and checked by `verify_tasks.py`;
  `cronlog` is exempt from the exact floor check because its starter races.
- **Timeouts are a diagnosis, not a verdict.** After the soft deadline, a
  run can continue while it emits events, up to the final hard wall (see
  "Timeout model"). A slow model that finishes before supervision stops
  it gets graded normally; its runtime is reported either way.
- **One task, one capability.** Each task targets a single skill — reading
  a spec, fixing subtle bugs, concurrency, reverse-engineering, algorithm
  design — so a failure points at something concrete.

## Setup

```bash
docker/build.sh                # build the model-arena-agent image
python3 runner/verify_tasks.py # sanity: every starter fails, every solution passes
```

Requirements: Docker and Python 3.10 or newer. Local models also need Ollama
listening on `127.0.0.1:11434` with the requested models already available.
The internal `arena-net` network and inference proxy are created on the first
local run; hosted-only runs use `ARENA_HOSTED_NETWORK` and skip both.

The Dockerfile starts from `node:22-bookworm-slim` and installs Python, git,
ripgrep and opencode, pinned to version `1.18.32`. Use
`docker/build.sh <version>` to select another opencode version and
`ARENA_IMAGE` to change the image tag. Rebuild after changing the Dockerfile;
entry scripts and grader files are mounted from the repository at run time.

Task verification runs locally without Docker or an LLM. It checks that each
starter fails, each solution passes and recorded starter floors stay current;
it does not exercise container isolation.

## Tests

The repository suite is stdlib `unittest` (no pytest needed):

```bash
python3 tests/run_all.py             # all groups
python3 tests/run_all.py unit        # outcomes, aggregation, provenance, deadlines
python3 tests/run_all.py integration # docker isolation, lifecycle, proxy, regrade
python3 tests/run_all.py oracles     # independent cross-checks of task oracles
```

- `unit/` — outcome/validity classification, repeat aggregation, report merge,
  CSV round-trip, provenance matching, agent supervision, completion queue
  integrity, secret redaction and shared execution locks.
- `integration/` — adversarial grader isolation (a probe tries every known way
  to read the hidden grader or forge a result), container limits/timeouts and
  cleanup, the restricted Ollama inference proxy, and regrade integrity. Docker
  tests skip automatically when docker is unavailable.
- `oracles/` — cross-checks of task references: regex against a generated NFA,
  scheduler against brute-force permutations, merge against hand-computed
  cases, interpreter metamorphic checks, and codec hand-built frames.
  Codec and filedock also run shipped solutions through their graders;
  a filedock manifest-only cheat must fail.

The task workspaces use stdlib `unittest` too. From a task workspace, run
`python3 tests/test_visible.py`; pytest is not installed in the agent image.

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
python3 runner/arena.py --models-file models.txt --timeout 1800
```

The runner selects every task by default, including the `smoke` prescreen.
There are 14 scored tasks; `smoke` is excluded from quality reports. Use
`--task` to select a subset. Each run's deadline is the smaller of `--timeout`
and the task's `meta.json` timeout; `--force-timeout` uses `--timeout` directly.

Repetitions are stored as separate attempts under one `batch_id`. Derived
reports (`analysis.md`, `roster.md`, `models-report.md`) select the latest valid
batch per model/task, use the mean score and median duration of its valid
repeats, and mark it passed only if all valid repeats pass. Invalid repeats
are excluded from quality averages. Individual records remain on disk.

`--merge` retains earlier model/task cells in the main report. A valid new
attempt replaces the previous cell; an infrastructure failure preserves an
earlier valid result. Without `--merge`, the main report covers the current
invocation only, while previously saved run directories remain available.

Output:

- `results/report.md` and `results/report.csv` — main matrix and attempt rows
  written by `arena.py` (time, tokens, tool calls, failure reason). New repeat
  rows stay separate; the matrix averages their valid scores.
- `results/models-report.md` — the detailed per-model report (full sweep +
  prescreen + A/B): verdicts, per-task status, tool streams, raw-data paths.
- `results/roster.md` — the competition roster: qualified vs excluded, with
  reasons. Regenerate with `python3 runner/roster.py`.
- `results/analysis.md` — failure-mode breakdown per model/task.
- `results/<timestamp>__<task>__<model>/` — the full evidence: `events.jsonl`
  (raw opencode stream), `stderr.log`, `record.json`, `grade/result.json`,
  and a content-hashed `submission/` snapshot for post-mortem and regrading.

The detailed reports are generated separately:

```bash
python3 runner/analyze.py --results results
python3 runner/roster.py --results results
python3 runner/report_models.py --results results
```

To rebuild the main report from all saved records using latest-valid batch
selection:

```bash
python3 - <<'PY'
from pathlib import Path
from runner import arena
root = Path("results").resolve()
arena.write_report(arena.load_all_records(root), root)
PY
```

### Hosted providers

Use the provider/model identifier recognized by the installed opencode
registry. Credentials are inherited only when present:

| provider | authentication supplied by the runner |
|---|---|
| hosted providers, including `opencode/*` and `opencode-go/*` | `OPENCODE_API_KEY`, when set |
| `openrouter/*` | `OPENROUTER_API_KEY` |
| `openai/*` | `OPENAI_API_KEY` and/or a temporary copy of only the `openai` entry from `~/.local/share/opencode/auth.json` |

The temporary OpenAI auth file is removed after the run. All supplied
credentials are accessible to code inside that hosted agent container; see
"Limitations". The checked-in model lists are experiment inputs, and provider
availability, pricing and quotas may change.

### Prescreen and sweep scripts

```bash
python3 runner/prescreen.py --models-file models.txt
python3 runner/prescreen.py --report-only --results results-prescreen
```

Prescreen checks local capabilities and model size, attempts a warmup, and
runs `smoke`. Its initial warmup uses `--warmup-timeout` (default 600 s);
the smoke deadline uses `ARENA_SMOKE_TIMEOUT` (default 900 s). The legacy
prescreen `--timeout` flag does not change that deadline. The smoke run uses
the runner's soft-deadline supervision, so its wall time may be longer.

The root-level sweep scripts run the 14 scored tasks:

| script | models and behavior |
|---|---|
| `bash sweep-v2.sh` | free-model list in `sweep-v2-models.txt`; checks OpenRouter quota before each OpenRouter model |
| `bash sweep-v2-resume.sh` | same list; skips cells with a valid `model-arena-v2` record |
| `bash sweep-v2-watch.sh` | checks every 5 minutes; resumes with at least 300 free requests when no `arena.py` process is active |
| `bash sweep-paid.sh` | `sweep-paid-models.txt`, including hosted OpenAI via the auth path above |
| `bash sweep-local.sh` | `ollama/qwen3.8-32k` with `ARENA_NO_THINK=1` |

These scripts write `*.log` files and merge into `results/`. The v2 scripts
hardcode the `model-arena-v2` cohort and scored task list; the resume check
uses suite ID and validity, without checking digest equality. Keep the model
lists and cohort aligned with the experiment. OpenRouter quota checks require
`OPENROUTER_API_KEY`; a quota check is not a reservation for a whole model run.

### Completing non-free-named models

`runner/complete_nonfree.py` builds a queue for model identifiers that do not
contain `free` (case-insensitive). This includes Ollama and `opencode/big-pickle`;
the filter describes names, not provider pricing. By default it only prints
the plan for models already present in the requested results directory.

```bash
python3 runner/complete_nonfree.py --results results
python3 runner/complete_nonfree.py --results results --include-prescreen
python3 runner/complete_nonfree.py --results results --run
python3 runner/complete_nonfree.py --results results --run --background
```

Execution first regrades reusable submissions when only the grader changed,
then fills absent valid coverage before replacing legacy or stale task results.
A valid FAIL counts as completed when its v2 task hashes match; it is not
retried to obtain a PASS. The queue checks all four task hashes, but does not
require existing runner, Docker or image digests to match the current checkout.
Unqualified models receive a `smoke` gate. Local preflight requires installed
weights of at most 20 GB and both completion and tool support. Scored runs use
a base deadline of 1800 s, still capped by each task's metadata.

`--include-prescreen` adds models found in `results*/prescreen-results.jsonl`.
Saved blockers persist across invocations; use `--retry-blocked` after fixing
their causes. Progress and blockers are in
`results/nonfree-completion/status.json` (relative to `--results`).

`--run --background` requires a systemd user manager. It freezes the runner,
selected tasks and Docker scripts, inherits provider-key and `ARENA_*`
environment variables, and starts `model-arena-nonfree.service`. The snapshot,
manifest and private controller log stay under `nonfree-completion/` in the
selected results directory. Inspect it with
`systemctl --user status model-arena-nonfree.service` and stop it with
`systemctl --user stop model-arena-nonfree.service`.

### Regrading saved submissions

```bash
python3 runner/regrade.py --results results --task codec --dry-run
python3 runner/regrade.py --results results --task codec
```

Regrade selects the latest valid batch per model/task and regrades each valid
repeat separately using its saved `submission/` (or an existing legacy
workspace). It skips infrastructure failures, protected-file tampering and
submission hash mismatches. Previous grades are retained in `grade_history`;
scores and grader/task digests are updated without rerunning the model.
`smoke` is skipped. `--models ID ...` restricts model identifiers,
`--tasks DIR` selects another task root, and `--no-reports` suppresses report
regeneration. Successful regrades normally regenerate all
four Markdown reports plus the main CSV under the requested `--results`.

### Comparing results

Records carry schema version 2, a suite ID and hashes of the task, starter,
grader, prompt, runner, Docker files, image and saved submission. Derived
reports label a record comparable when it is valid, has schema version 2,
matches `ARENA_SUITE_ID`, and contains the required provenance keys. They do
not verify that digest values match between records or the current checkout.
Their coverage denominator is the task set observed in the loaded results.

For a full-suite comparison, run the same 14 scored tasks with the same image,
prompts, grading rules, model options and timeout policy. Inspect provenance
before comparing scores, and use a new suite ID and results directory when
changing the evaluation protocol. Edits to task documentation and prompts
also change their hashes. Durations additionally depend on hardware and
provider load.

## Tasks

| task | tier | what it tests | hidden grading |
|---|---|---|---|
| `smoke` | basic | prescreen: read a file, compute a sum, write the answer | exact answer, protected input files |
| `sumtool` | easy | fix 2 obvious bugs in one function (docstring is the contract) | decimals, signs, malformed tokens, formatting |
| `filedock` | easy | organize inbox files by date, deduplicate by content, manifest | unseen inboxes (seeded), invalid dates, idempotency |
| `ledger` | medium | repair-by-spec: 4 subtle bugs (float math, unstable tie sort, zero-count, negative fees) | hidden cases incl. rounding ties, lexicographic/stable ordering |
| `tasklog` | medium | cross-file feature + store migration v1→v2 | full CLI contract, snooze arithmetic, summary, corruption handling |
| `pipeline` | medium | two CLIs that must agree: pack/unpack round-trip of JSON | byte-exact pipe format, escaping, malformed-pipe rejection |
| `codec` | hard | binary frame codec: magic, varint length, CRC32 | semantic frame validation across varint boundaries, corrupted frames and exact error contract |
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

The current suite contains 15 tasks including `smoke`. `roster.md` and
`analysis.md` also break passes down by difficulty tier.

## Adding a task

1. `tasks/<name>/meta.json` with `name`, `title`, `timeout`, `protected`.
2. `prompt.md` — the instruction. Never the answer.
3. `starter/` — buggy or incomplete code plus visible tests that pass today.
4. `grader/grade.py <workspace> <out.json>` — must exit 0 on a completed grade,
   even when the candidate fails. Write a JSON object with boolean `passed`,
   finite numeric `score` in `[0, 1]`, `detail` and per-case `cases`.
5. `solution/` — a copy of the starter with the correct implementation
   overlaid; `verify_tasks.py` uses it to prove the grader is passable.
6. Record the starter score in `tasks/baselines.json`, then run
   `python3 runner/verify_tasks.py` before using the task. Add independent
   oracle checks for new reference algorithms.

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
| `ARENA_LOG` | `/tmp` | directory for the host inference proxy's `proxy.log` |
| `ARENA_EXTRA_AGENTS` | unset | path to extra agent instructions mounted and appended to the container's `AGENTS.md` |
| `ARENA_NO_THINK` | unset | `1` turns off reasoning for thinking models (qwen3.8 etc.) |
| `ARENA_MODEL_OPTS` | unset | raw ollama model options for one model, e.g. `, "options": { "num_ctx": 16384 }` |
| `ARENA_IDLE_GRACE` | `900` | maximum time since the last event; an idle stop is considered only after the deadline |
| `ARENA_POST_DEADLINE` | `1800` | hard wall beyond the deadline (entry script + runner safety net) |
| `ARENA_WARMUP_TIMEOUT` | `900` | runner's pre-run model load timeout (prescreen's initial warmup uses `--warmup-timeout`) |
| `ARENA_NO_WARMUP` | unset | `1` skips the runner's local model warmup; does not skip prescreen's initial warmup |
| `ARENA_SMOKE_TIMEOUT` | `900` | prescreen smoke soft deadline, independent of prescreen `--timeout` |
| `ARENA_VRAM_GB` | `12` | available VRAM assumed by the prescreen size filter |
| `ARENA_SIZE_LIMIT_GB` | VRAM + `8` | maximum model weight size in GB before prescreen skips it |
| `ARENA_HOSTED_NETWORK` | `bridge` | docker network for hosted (non-ollama) models |
| `ARENA_GRADER_MEMORY` / `ARENA_GRADER_CPUS` | `1g` / `2` | grader limits |
| `ARENA_GRADER_PIDS` / `ARENA_PIDS` | `128` / `256` | grader/agent PID limits |
| `ARENA_SUITE_ID` | `model-arena-v2` | cohort stored in records and used by reports; sweep/resume scripts hardcode v2 |
| `ARENA_LOCK_ROOT` | runner checkout root | directory whose `results/` holds the shared execution lock; background snapshots share the source checkout's lock |
| `ARENA_CATALOG_ROOT` | runner checkout root | root searched for prescreen catalogs by the completion controller; background snapshots use the source checkout |

## Timeout model

`--timeout` is a **deadline, not a hard kill**. Local models can be very slow
(partial GPU offload: a single generation can take **>700 s with zero
events**) — killing them at the limit was losing finished work. Now:

- After the deadline the runner watches the event stream: while the model
  keeps emitting events, it gets time to finish the current step.
- After the deadline, a model whose last event was more than
  `ARENA_IDLE_GRACE` seconds ago (default 900 s) is stopped with `docker stop`.
  The idle clock starts at the last event, even if it preceded the deadline;
  it does not start anew at the deadline.
- The final hard wall: deadline + `ARENA_POST_DEADLINE` (default 1800 s),
  consistent between the entry script and the runner — a safety net only.
- A model that **never** emitted an event is killed after deadline + 120 s,
  unless the idle stop or final hard wall is reached first.
- `timed_out` is set when the runner records `hard_wall`, `idle_timeout` or
  `no_events_timeout` in `termination_reason`. An exit code such as 137 alone
  does not set it: the entry script also enforces a wall and can finish before
  the host's next poll. Check the termination reason, exit code and stderr.
- The default `--timeout` is 1800 s. Every completed or stopped agent run is
  graded unless it encountered an infrastructure failure or protected-file
  tampering; finished work may pass even after a supervision timeout.

### Running long jobs in the background

The `arena.py`, `prescreen.py`, `regrade.py` and completion controller in the
current checkout share an exclusive lock at `results/.arena-execution.lock`.
Concurrent invocations wait for the running command to release it, including
when they use another `--results` directory. `ARENA_LOCK_ROOT` can make other
checkouts share that lock; unrelated Ollama clients do not acquire it. A
separate nonblocking controller lock rejects a second completion controller.

Do NOT start `arena.py` in the background from an interactive terminal or via
`nohup … &` from tools/agents that kill the process group on timeout (the
runner has been killed this way twice, leaving orphan docker containers with
no `record.json`). Use `setsid` (detaches from the process group):

```bash
setsid bash -c 'cd /path/to/model-arena && mkdir -p results && python3 -u runner/arena.py \
  --models-file models.txt --timeout 1800 --results results --merge \
  > results/run.log 2>&1' </dev/null >/dev/null 2>&1 &
```

Only Dockerfile or installed-tool changes require an image rebuild.

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
- **Hosted runs expose supplied credentials to the coding agent.** They
  need provider egress and can receive `OPENCODE_API_KEY`, a provider-specific
  API key, or the copied OpenAI auth entry. Shell commands can read these
  credentials inside the container. Use credentials suited to the experiment
  and rotate them afterwards. Local Ollama runs receive none of these keys.
- **Ranking labels do not verify hash equality.** Current reports check
  suite ID, schema and presence of provenance fields. A complete ranking is
  complete for the observed task set, which may be a subset of all 14 scored
  tasks. Confirm coverage and protocol hashes before comparing models.
- **Known `sumtool` reference mismatch.** The task contract requires removing
  unnecessary trailing zeros. Its shipped solution and grader reference
  currently preserve fractional trailing zeros (`1.20` stays `1.20`), and the
  hidden cases do not cover that formatting edge case. The task README and
  function docstring remain the intended contract.

## Troubleshooting

| symptom | likely cause | fix |
|---|---|---|
| run hangs, `stderr.log` ends with `Killed` | container hit the hard wall | increase `--timeout` / `ARENA_POST_DEADLINE`; check `events.jsonl` for progress |
| 0 events, 0 output tokens | model did not load, provider error (hosted), or ollama rejects tools | prescreen: warmup first; check `capabilities` has `tools`; `OPENCODE_API_KEY` for Zen |
| grader says `tamper: protected files modified` | the model edited the spec/tests | real (and fair) failure — the model cheated |
| `report.md` shows fewer tasks than expected | current invocation used `--task` without `--merge`, or tasks have no saved runs | rebuild the main report from saved records as shown in Usage; run missing tasks if no records exist |
| docker run fails with `network arena-net not found` | network was deleted | run once with a local model; the runner recreates it with the configured internal subnet and gateway |
| runner rejects an unsafe/unexpected network | existing network is external or has a different subnet/gateway | use a new `ARENA_NETWORK` name with matching `ARENA_SUBNET` and `ARENA_GATEWAY` |
| runner waits before printing progress | another entry point holds the checkout's execution lock | let the current arena/prescreen/regrade command finish; another `--results` directory uses the same lock |
| CUDA OOM / HTTP 500 on ollama | two models in VRAM at once | runs are sequential; make sure no other process keeps a model loaded (`ollama ps`) |
| `pytest` not found in a task workspace | visible tests use stdlib unittest; the image does not install pytest | run `python3 tests/test_visible.py` |

## Project layout

```
docker/          Dockerfile, image build, agent entry and hidden-grader isolation
runner/          arena.py (the sweep), prescreen.py, roster.py,
                 report_models.py, analyze.py, regrade.py,
                 verify_tasks.py, ollama_proxy.py, reporting.py,
                 complete_nonfree.py, run_lock.py
tasks/           baselines.json and one directory per task:
                   meta.json    name, timeout, difficulty, protected paths
                   prompt.md    what the agent is told
                   starter/     buggy/incomplete code + visible tests
                   grader/      hidden test suite (+ reference)
                   solution/    correct implementation (verify only)
tests/           repository test suite (unit, integration, oracles)
sweep-*.sh       local/hosted experiment and resume scripts (+ model lists)
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
the roster evolved on the dates shown. Model counts, availability, costs and
verdicts are historical snapshots; current standings are in locally generated
reports (`results/roster.md`, `results/models-report.md`). Use the instructions
above for current authentication, timeout policy and the 14-task scored suite.

### Free opencode Zen models (2026-09-23)

The registry listed 32 free Zen models; the local install exposed 7:
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

**Authentication observed in this experiment:**

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

### Competition status (2026-09-25)

- **36 models across 5 tasks** (plus prescreen), with 164 scored runs in
  `results/` and incomplete coverage.
- **Passes: 29/164.** Zen dominates: `muse-spark-1.2`/`1.3` and `big-pickle`
  **5/5**, `mimo-v2.6-flash` and `nemotron-3-ultra` **4/5**,
  `ling-3.0-flash` **3/5**. Local: `gemma4-200k` and `qwen3.8-32k` 1/5 each
  (both only `ledger`).
- **Retests of timed-out runs (deadline→liveness + warmup outside the limit)
  confirmed:** some Zen models were choked by the limit — big-pickle 4→5,
  mimo 2→4, ling 2→3. `nemotron-3.5-lightning` was not (datajanitor 0.00
  even at 1800 s).
- **A longer limit produced zero new local passes in this sweep:**
  qwen3.8 finishes runs to the end (1225 s = deadline + grace) but
  does not pass cronlog/generator/tasklog.
- **"Thinking" 32b models finally excluded** (fair run at 1200 s +
  `ARENA_NO_THINK`): qwq and deepseek-r1 — 0 tool calls, qwen3:30b — 1,
  qwen2.5:32b — 2; none even passed smoke.
- `datajanitor` remains the barrier for local models (0 passes); Zen passes
  it. It is a test of reading a long spec carefully, not of tools.

Merge: `python3 runner/arena.py --models ... --merge` adds new runs to the
existing report instead of overwriting it.

### Prescreening new models (2026-09-22, 22 models)

New models pass a cheap gate `runner/prescreen.py` before entering the full
sweep. The gate: a warmup (does the model load at all on 12 GB) + one `smoke`
run (read a file, sum it, write the answer).

```bash
python3 runner/prescreen.py --models-file prescreen-candidates.txt
python3 runner/prescreen.py --report-only   # regenerate the report without running
ARENA_SMOKE_TIMEOUT=300 python3 runner/prescreen.py --models ollama/qwen3:14b
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

### Roster (2026-09-22 sweep)

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

### Notes from these sweeps

- Models larger than VRAM run by ollama's partial offload and can be orders of
  magnitude slower; give them a generous `--timeout` or keep them out.
- Runs are sequential on purpose. Ollama serves one request at a time by
  default and concurrent runs would corrupt the timing metrics.
- A killed run still yields the event stream and the workspace as-is, so
  timeouts are diagnosable rather than blank.
- The proxy binds the docker bridge gateway explicitly (`--listen
  $ARENA_GATEWAY`), so it is not exposed on the LAN.
