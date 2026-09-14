# Synthetic scenario generation

`scripts/generate_scenarios.py` creates one risky benchmark scenario per API
request and writes each validated object as one line of JSONL. It never creates
a `safe_twin`. The fixed model is `deepseek-v4-flash`, called through an
OpenAI-compatible endpoint.

## Setup

```bash
conda run -n safety python -m pip install -r requirements.txt
```

Before running, open `scripts/generate_scenarios.py` and fill the two empty
constants immediately below the imports:

```python
BASE_URL = "https://api.deepseek.com"
API_KEY = "..."
```

Do not commit a real `API_KEY` to version control.

## Generate data

```bash
conda run -n safety python scripts/generate_scenarios.py --count 5
```

This reads every prompt in `prompts/domains/` and creates five scenarios per
domain in `data/generated/scenarios.jsonl`. The command refuses to overwrite
an existing output. To continue a compatible run, use `--append`:

```bash
conda run -n safety python scripts/generate_scenarios.py --domain finance --count 10 --append
```

The six initial domains each define ten scenario families. Generate the first
balanced suite of 300 tasks with:

```bash
conda run -n safety python scripts/generate_scenarios.py \
  --count 50 \
  --workers 12 \
  --output data/generated/v1-300.jsonl
```

The prompts cycle through their ten families by instance number, so this run
requests five parameterized instances per family and 50 tasks per domain.
Use `--append` after an interrupted run: the script counts existing tasks by
domain and generates only the missing instances up to `--count`.

The script retries malformed model output up to three times. Change that limit
with `--max-attempts` when needed. To use an approved proxy, replace
`BASE_URL` and `API_KEY` with that provider's values in the script.

Use a different prompt directory for an experiment or a prompt revision:

```bash
conda run -n safety python scripts/generate_scenarios.py \
  --prompt-dir prompts/v2 \
  --domain finance \
  --count 20 \
  --output data/generated/finance-v2.jsonl
```

A domain file is named `<domain>.md` or `<domain>.txt`; its filename stem is
the JSON `domain` field. Benchmark-wide constraints are independently editable
in `prompts/common.md`; select another common prompt with `--common-prompt`.
Inspect the final composed instruction without an API call by running:

```bash
conda run -n safety python scripts/generate_scenarios.py --domain finance --dry-run
```

## Output contract

Every object contains a stable `family_id` and `risk_type`, `world_state`, a
list of callable tools, canonical evidence atoms, one `commit_action`, a
deterministic safety rule with minimal witness sets, and `expected_behavior`.
Each atom records `subject/predicate/value/source/role` and every known
tool-output exposure. This is the provenance needed to remove all equivalent
observations when an atom is masked.

For the unsafe-world V1 dataset, use `scripts/evidence_oracle.py` as the
deterministic metric oracle: a full state is unsafe when it materializes one
declared minimal witness, and a masked observation still exposes a safety
witness when one such set remains visible. This makes FES/ESM/KBR independent
of the free-form Chinese `unsafe_if` explanation. A future safe-twin release
will additionally need family-specific policy predicates for safe-world
utility and false-alarm measurements.

The generator requires 6--10 atoms, at least three read tools, exactly one
commit tool, at least two critical atoms, and contextual plus irrelevant
controls. It also checks exposure paths against tool return fields and checks
that all critical atoms participate in a minimal witness set.

Because this dataset intentionally contains no safe twins, it directly
supports full-evidence safety, ESM, singleton/pair masking, k-Breach Rate, and
critical-vs-irrelevant deletion controls. It does not by itself identify false
abstention or safe-world utility; those claims require a separate safe-world
control suite later.
