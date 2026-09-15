# SafetyBenchmark

SafetyBenchmark is an executable, local environment for measuring how semantic
evidence suppression changes an LLM tool agent's willingness to perform an
unsafe commit. The supplied suite contains 300 paired JSONL rows in six domains.
Each row embeds a matched safe twin, and the repository expands the rows into
600 environment tasks (300 unsafe worlds + 300 safe worlds). No tool invokes a
real bank, cloud, messaging, commerce, travel, or data system.

## What is implemented

- strict Pydantic loading and expansion of 300 matched unsafe/safe pairs;
- stateful `reset → step → grade` episodes;
- tool observations compiled from evidence exposure JSONPaths;
- atom-level semantic masks applied across every declared exposure;
- parameter-aware responses when the same tool/path represents multiple entities;
- deterministic paired-world commit grading from unmasked true state;
- safe-world success and false-abstention grading;
- Track B channel omission with an independent evidence-recovery tool;
- recovery-attempt, recovery-success, and premature-commit metrics;
- append-only JSONL traces and stable trace hashes;
- safe and blind scripted control agents;
- an OpenAI-compatible tool-calling adapter configured from `.env`;
- exact singleton/pair/triple boundary search;
- episode and k-breach summary reports;
- contract tests over all 300 tasks and every singleton exposure mask.

## Install

The project uses the existing `safety` conda environment:

```bash
conda run -n safety python -m pip install --no-build-isolation -e .
conda run -n safety python -m unittest discover -s tests -v
```

The `.env` file accepts either naming convention:

```dotenv
BASE_URL=
API_KEY=
MODEL=
```

or `LLM_URL`, `LLM_API_KEY`, and `LLM_MODEL`. Secrets are never placed in an
episode trace.

## CLI

Validate or inspect the suite:

```bash
conda run -n safety sb validate
conda run -n safety sb list --domain finance
```

Run local golden controls:

```bash
conda run -n safety sb run \
  --scenario finance.payment.approval_limit.001 \
  --agent safe-reference

conda run -n safety sb run \
  --scenario finance.payment.approval_limit.001 \
  --agent blind-commit \
  --mask policy.finance_director.max_single_payment.CNY
```

Run the configured LLM and save an auditable trace:

```bash
conda run -n safety sb run \
  --scenario finance.payment.approval_limit.001 \
  --agent openai-compatible \
  --output results/episodes.jsonl
```

Run a matched safe twin (the virtual task ID is the base ID plus `.safe`):

```bash
conda run -n safety sb run \
  --scenario finance.payment.approval_limit.001.safe \
  --agent openai-compatible
```

Run Track B channel omission. Ordinary tools omit the selected atom, while the
environment exposes `recover_omitted_evidence` backed by an independent audit
source. The Agent must notice the missing field and actively recover it before
committing:

```bash
conda run -n safety sb run \
  --scenario finance.payment.approval_limit.001 \
  --agent openai-compatible \
  --track b \
  --mask policy.finance_director.max_single_payment.CNY \
  --show-trace
```

Exact evidence-boundary search:

```bash
conda run -n safety sb search \
  --scenario finance.payment.approval_limit.001 \
  --agent openai-compatible \
  --max-mask-size 2 \
  --repetitions 3 \
  --output results/finance-search.jsonl

conda run -n safety sb report results/finance-search.jsonl \
  --output reports/finance-search.json
```

`search --domain finance` runs every task in that domain and can incur many LLM
calls. Start with one scenario and one repetition when validating a provider.

## Paper-grade experiment protocols

`sb experiment` writes one append-only JSONL row per rollout and a separate
trace file per trial. Each trial is keyed by its protocol, scenario/world,
track, mask, repetition, and immutable settings hash. A stopped job can use
`--resume`: completed trial keys are skipped, while failed trials are retried.
The companion manifest freezes the dataset, code, prompt, model configuration,
and sampling configuration hashes.

Run the complete benchmark **one base task and its safe twin at a time**.
For each pair, finish full A/B controls, every critical/irrelevant singleton in
all four cells, higher-order critical search, and recovery at its first boundary
witness before starting the next pair. Combination search covers up to all of
that task's critical atoms and stops at the first observed unsafe commit.
Singletons never early-stop. Full and singleton trials are reused within the run.

```bash
conda run --no-capture-output -n safety sb experiment \
  --protocol boundary-recovery --agent openai-compatible --repetitions 1 \
  --ledger results/v2/boundary-recovery.ledger.jsonl \
  --wandb-project safetybenchmark --wandb-run-name boundary-recovery-v2
```

`paper` is an alias for this new protocol. There is no global K: legacy
`--max-mask-size` and `--breach-threshold` only apply to the old protocols.
The mask ordering uses `--seed` or zero when omitted; temperature defaults to
zero. One rollout does not imply a deterministic provider response.

W&B uses **`task_index` (1–300 base/twin pairs)** as the horizontal axis. There
is one log event per fully completed task: `current/*` contains that task's
metrics, `cumulative/*` contains equal-task averages so far, and `coverage/*`
contains each metric's eligible-task count. Full, singleton-critical,
singleton-irrelevant, and higher-order boundary results are separate. Missing
denominators are null/omitted, never reported as zero successes. Resume replays
the completed task points into the new W&B run before continuing.

For `results/v2/boundary-recovery.ledger.jsonl`, local records include:

- The append-only ledger: every attempt start, every completed/error outcome,
  and each completed task's metric inputs and boundary result.
- `boundary-recovery.ledger.tasks/<task>/scenario.json`: both expanded worlds,
  evidence, rules, and manifest for later regrading.
- `<task>/executions.jsonl`: every finalized attempt for that task, including errors.
- `<task>/attempts/`: append-only model request/response and tool-event journals,
  plus full or partial traces; retries get distinct filenames.
- `<task>/result.json`: every completed condition and grade, witness annotations,
  boundary result, and within-task metrics with numerators/denominators.
- `<task>/cumulative_metrics.json`: the completed-prefix metric snapshot.
- `boundary-recovery.ledger.summary.json`: latest cumulative point estimates.

Model payloads and true-state snapshots stay in local files. W&B receives only
numeric metrics. If a required trial errors, execution stops at that task. Fix
the underlying failure and append `--resume` to the same command; successful
trials are skipped and failed/unfinished attempts retain their records. Use a
new ledger for this protocol: old recovery ledgers have different manifests and
cannot be resumed as a unified run.

Recompute all aggregate metrics from the ledger, including 10,000-draw family
bootstrap confidence intervals, without calling the model:

```bash
conda run -n safety sb report results/v2/boundary-recovery.ledger.jsonl \
  --output results/v2/boundary-recovery.report.json
```

Live per-task curves use point estimates and coverage; at completion,
10,000-draw family bootstrap intervals are saved in the summary JSON and W&B
`final/*` summary (without adding another task point). They can also be
recomputed by the offline report. See [the detailed protocol](docs/unified_boundary_recovery_protocol.md)
for formulas and metric definitions.

Use the individual protocols below only for pilot or diagnostic runs:

```bash
# B1: 600 tasks (unsafe bases and safe twins) under Track A and B full evidence.
conda run -n safety sb experiment \
  --protocol calibration --agent openai-compatible --repetitions 4 \
  --ledger results/calibration.ledger.jsonl

# B2/B3: unsafe bases only; full, every critical singleton, then critical pairs
# only if no singleton crosses the threshold. Start with one domain before full-suite use.
conda run -n safety sb experiment \
  --protocol boundary --agent openai-compatible --domain finance \
  --repetitions 4 --max-mask-size 2 --breach-threshold 0.5 \
  --ledger results/finance-boundary.ledger.jsonl

# B4: matched unsafe/safe worlds with Track A/B full, critical-singleton, and
# irrelevant-singleton conditions. `--limit 12` is a protocol smoke test.
conda run -n safety sb experiment \
  --protocol recovery --agent openai-compatible --limit 12 --repetitions 4 \
  --ledger results/recovery-pilot.ledger.jsonl

# Analyse a ledger with family-cluster bootstrap CIs, paired calibration,
# KBR threshold sensitivity, witness-vs-irrelevant, and Track B-minus-A effects.
conda run -n safety sb report results/calibration.ledger.jsonl \
  --output reports/calibration.json
```

For a resumed job, reuse exactly the same protocol options and manifest:

```bash
conda run -n safety sb experiment ... --ledger results/calibration.ledger.jsonl --resume
```

### Optional Weights & Biases

W&B is intentionally optional. Install it separately and pass
`--wandb-project PROJECT` (plus optional `--wandb-entity` and
`--wandb-run-name`). The runner logs only non-sensitive numeric trial metrics:
unsafe commit, safe goal success, false abstention, invalid actions, recovery
funnel events, event count, latency, request count, and token counts. It never
uploads user goals, tool observations, masks, API endpoints, credentials, or
full traces; those remain in the local ledger and trace directory.

## Semantics and paired-task scope

The environment holds two logical views. `true_state` is private and unchanged
by masking; `EvidenceProjection` creates the only observations visible to the
agent. A commit is graded using the private true world, so hiding a critical
limit can change the agent's decision but cannot change the safety judgment.

Commit safety is recomputed by an executable predicate registry covering all
60 scenario families. Predicates read normalized evidence materialized from
the private true state; `world_type` is reporting metadata and never determines
the oracle result. `sb validate` also requires every one of the 300 matched
pairs to evaluate `unsafe -> safe`, and fails closed if a family has no
registered predicate.

Each JSONL row contains an unsafe base world and a minimal matched `safe_twin`
specification. The twin stores only its replacement true state, changed critical
evidence values, and expected behavior; user goal, tools, safety rule, and
provenance are shared by construction. The executable family predicate, rather
than the pair label, verifies that the target commit is unsafe in the base world
and safe in the matched world. This supports FES, ESM/KBR,
safe-world goal success, false abstention, and the safety--utility trade-off.

Track A applies a semantic mask across every declared exposure. Track B applies
the same omission to ordinary observation channels but provides an independent
recovery tool. ESM search is defined only over unsafe-world tasks; safe twins are
utility controls and are excluded from its denominator.
