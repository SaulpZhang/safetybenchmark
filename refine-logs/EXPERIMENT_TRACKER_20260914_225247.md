# 实验追踪表：Paired Safe Twins 与 Track B

**冻结协议**：4 fresh rollouts/condition；主 `q=0.5`（2/4）；family 等权 + 10,000 次 family bootstrap；所有 run 保存 dataset/code/prompt/model/config hash 和完整 trial ledger。

| Run ID | 里程碑 | 目的 | 系统 / 条件 | 范围 | 核心指标 | 优先级 | 状态 | 通过条件 |
|---|---|---|---|---|---|---|---|---|
| R001 | M0 | 600-task loading/projection contract | `sb validate` + unit tests | 600 tasks | errors, tests | MUST | DONE | 600=300 unsafe+300 safe；全部测试通过 |
| R002 | M0 | 60 family twin rule-inversion audit | executable predicates + `sb validate` | 300 pairs | base unsafe / twin safe | MUST | DONE | 60 predicates；全 300 pair 自动重算通过；投稿前保留人工抽审 |
| R003 | M0 | 可重建 trial ledger 与 cluster report | runner/search/report extension | fixture + dry run | fields, resume, bootstrap | MUST | TODO | 任意 row 可重建配置、mask、grade、trace |
| R004 | M0 | Golden controls | safe-reference, blind-commit, recovery-aware scripted | 6 domains × representative pairs | unsafe, recovery, disposition | MUST | TODO | 与预期 trace 完全一致 |
| R005 | M1 | Provider smoke | Model A, paired A/B full + critical omission | 12 stratified pairs | tool validity, recovery trace | MUST | TODO | 不改 prompt 即可扩展 |
| R006 | M2 | Paired full calibration | Model A, A-full and B-full | 600 tasks × 4 × 2 tracks | safe success, FAR, unsafe, invalid | MUST | TODO | 记录 B tool-presence effect |
| R007 | M3 | Track A singleton boundary | Model A, unsafe Track A all singleton | eligible unsafe bases × all atoms × 4 | KBR1, roles, behavior | MUST | TODO | exact all-atom singleton coverage |
| R008 | M3 | Track A pair boundary | Model A, unsafe Track A exact pairs after no singleton breach | conditional eligible bases × pairs × 4 | KBR2, ESM censoring | MUST | TODO | exact conditional pair coverage |
| R009 | M3 | Semantic negative control | reuse R007 | bases with witness+irrelevant | paired delta, invalid delta | MUST | TODO | family paired bootstrap CI |
| R010 | M4 | Track B all-critical recovery | Model A, both worlds | 944 masks × 2 worlds × 4 | attempt, recovered, correct action, premature | MUST | TODO | recovery cascade complete |
| R011 | M4 | Track B irrelevant control | Model A, both worlds | 419 masks × 2 worlds × 4 | recovery specificity, cost | MUST | TODO | paired with R010 analysis |
| R012 | M4 | Track A safe-side matched baseline | Model A, safe twins | (944+419) masks × 4 | safe success/FAR uplift A→B | MUST | TODO | same mask IDs as R010/R011 |
| R013 | M5 | q and repeat robustness | Model A | 20 stratified families, key conditions to 8 repeats | q-grid, stability | MUST | TODO | strict and threshold analyses agree in direction |
| R014 | M5 | Trace/provenance audit | Model A | representative traces per domain | taxonomy, leaks | MUST | TODO | all audited traces reconstructable |
| R015 | M6 | Model B replication | frozen protocol | R006--R014 | all primary metrics | MUST | TODO | no model-specific protocol changes |
| R016 | M6 | Model C replication | frozen protocol | R006--R014 | all primary metrics | NICE | TODO | only after A/B complete |
| R017 | M7 | Paper artifact freeze | all completed runs | manifests + tables + figures | reproduction | MUST | TODO | clean checkout regenerates results |
