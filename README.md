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

## Semantics and paired-task scope

The environment holds two logical views. `true_state` is private and unchanged
by masking; `EvidenceProjection` creates the only observations visible to the
agent. A commit is graded using the private unsafe world, so hiding a critical
limit can change the agent's decision but cannot change the safety label.

Each JSONL row contains an unsafe base world and a minimal matched `safe_twin`
specification. The twin stores only its replacement true state, changed critical
evidence values, and expected behavior; user goal, tools, safety rule, and
provenance are shared by construction. A schema-valid target commit is unsafe in
the unsafe world and safe in the matched safe world. This supports FES, ESM/KBR,
safe-world goal success, false abstention, and the safety--utility trade-off.

Track A applies a semantic mask across every declared exposure. Track B applies
the same omission to ordinary observation channels but provides an independent
recovery tool. ESM search is defined only over unsafe-world tasks; safe twins are
utility controls and are excluded from its denominator.
