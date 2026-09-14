# 与 Evidence Safety Margin 相关的现有 Agent Benchmark 调研

> 调研日期：2026-09-13  
> 范围：信息不完整、澄清/弃权、工具调用安全、间接提示注入、行为风险与动态用户交互。  
> 资料原则：只采用论文、作者项目页、官方代码仓库和官方数据页；文中所有链接均指向一手资料。

## 1. 结论先行

本项目不宜直接复刻某一个已有 benchmark。最合理的组合是：

- 用 **AgentDojo / ASPI** 的“同一任务配对条件 + 确定性效用/安全检查器”作为安全评测骨架；
- 用 **LHAW** 的“从完整任务系统性删去信息 + 以终态差异验证缺失信息确实关键”作为样本构造方法；
- 用 **ClarifyBench / When2Call / QuestBench** 定义 `执行 / 澄清 / 拒绝(或无法完成)` 决策及澄清质量；
- 用 **τ-bench** 的有状态数据库环境、规则遵从、用户模拟器和 `pass^k` 衡量多次运行的一致性；
- 用 **Agent-SafetyBench / ToolEmu / R-Judge** 的风险分类、失败模式、轨迹级风险解释与 judge 校准扩大风险覆盖面；
- 用 **ASB** 补充攻击面矩阵与可插拔攻击/防御实验，但不把其总体攻击成功率当作 Evidence Safety Margin。

目前最明显的研究缺口是：已有工作分别测“缺信息时会不会问”“是否会遭提示注入”“最终行为是否危险”，却几乎没有统一测量 **证据充足度 × 行为风险 × 行为可逆性** 下的决策边界，也没有把“采取行动所依据的证据”做成可审计、可扰动、可逐级增加的实验变量。ToolEmu 是“良性意图但任务/安全约束欠规格”侧最直接的前身，ASPI 是澄清状态安全侧最近的工作，LHAW 是可控信息删减侧最近的工作；三者都未定义 Evidence Safety Margin。

## 2. 对照总表

| Benchmark | 核心任务 | 威胁/失败模型 | 环境 | 主要指标 | 最值得复用 | 与本项目距离 |
|---|---|---|---|---|---|---|
| AgentDojo | 工具 Agent 在不可信数据中完成用户任务 | 间接提示注入导致攻击者目标实现 | Workspace、Slack、Travel、Banking 的有状态模拟环境 | Utility、Targeted ASR、Untargeted ASR、二者联合结果 | 确定性 task/security checker；suite/task/attack/defense 接口 | 安全骨架很近，但缺信息量梯度和证据边界 |
| ASPI | 对照完整执行状态与缺信息后的澄清状态 | 澄清回复、`ask_user` 返回或工具输出中的提示注入 | 复用 AgentDojo 四套环境；728 个配对 task–attack 场景 | Utility、ASR、Clarification Rate、配对 ΔASR、bootstrap CI/McNemar | 单槽删除、8 条件配对实验、澄清用户模拟器、统计分析 | **安全侧最近**；只测单槽/单轮和注入攻击 |
| LHAW | 长程任务中检测并解决可控欠规格 | 缺少 Goal/Constraint/Input/Context 导致终态分歧 | MCP-Atlas、TheAgentCompany、SWE-Bench Pro；285 个变体 | pass@k、pass^k、checkpoint%、Ask%、Gain/Q | 信息片段删除与 criticality/guessability；基于运行的有效性验证 | **信息不完整侧最近**；不直接测危险行为 |
| ClarifyBench | 多轮工具调用中的显式、歧义和不可行请求 | 错误工具、参数遗漏/错误、未问或多问 | 文档、车辆、股票、旅行、文件系统；716 样本、92 工具 | Coverage、TMR、PMR、平均问题数 | 动态用户模拟器；ground-truth tool call；三类请求 | 澄清能力很近，但没有风险/不可逆动作 |
| When2Call | 决定直接回答、调工具、追问或承认不可答 | 工具幻觉、该问不问、该停不停 | 基于 BFCL 的静态 tool schema/问答 | Macro-F1、归一化准确率、无工具时 hallucination rate | 四类动作标签、held-out parameter 生成方式 | 适合作为轻量单步 decision probe，不是动态安全环境 |
| QuestBench | 找出完成推理所需的最小问题 | 部分可观测状态下猜测或错误提问 | Logic-Q、Planning-Q、GSM-Q、GSME-Q | 正确澄清问题的选择准确率及难度轴 | CSP 与“仅缺一个必要变量”的可证明构造 | 适合验证“最小充分证据”，但无真实工具风险 |
| τ-bench / τ³-bench | 与模拟用户多轮交互并遵守领域政策 | 任务未完成、错工具/参数、非预期动作、规则不遵从 | 航空、零售、通信、知识银行等有状态服务环境 | 终态 reward、pass^k；新版支持动作 criteria | 数据库终态评估、策略文本、用户模拟、可重复运行 | 交互底座很好，但原始任务不系统覆盖欠规格/安全 |
| Agent-SafetyBench | 综合评估 Agent 行为安全 | 8 类风险、10 类失败模式；含缺信息时编造参数 | 349 个 Python 模拟环境、2,000 测例 | scorer 给出的 safety score；另有 helpfulness 分析 | JSON tool schema + Python 环境；风险/失败模式标签；公开 scorer | 风险覆盖广，但主要是 judge 总分，边界不可辨识 |
| ToolEmu | 在 LM 模拟的工具沙箱中发现工具 Agent 风险 | 数据泄露、财产/物理损害等高风险行为 | LM 模拟 36 个工具包、144 个测试用例 | LM 自动安全/帮助性评估，轨迹级风险分析 | 低成本生成工具与测试用例、沙箱 emulator、risk evaluator | 适合快速扩域；模拟器与 judge 误差不利于精确边界测量 |
| R-Judge | 从已给 Agent 交互记录中识别安全风险 | 10 类真实世界风险；重点是风险意识而非执行攻击 | 27 个场景/569 条交互记录，静态轨迹 | F1、Recall、Specificity、开放式风险识别 | 风险描述语料、轨迹级 judge 训练/校准 | 可做离线审计器训练集，但不能测行动策略和因果边界 |
| ASB | 系统评估 Agent 的攻击与防御 | DPI、OPI、PoT 后门、memory poisoning 等 | 10 场景、10 agents、400+ tools | 多种攻击、防御、性能与效率指标 | AIOS 基座、YAML 配置、攻击/防御插件矩阵 | 攻击覆盖广，但与“合法任务证据是否足够”不同 |
| CAR-bench | 车载助手在缺工具/参数/结果或歧义下安全决策 | 凭空补全、过早 set、错误承认/澄清 | τ-bench 派生的 31 动态状态、58 工具、19 policies | 合取式 task success、intermediate-state/policy errors、pass^k | get/set 分离、中间状态检查、失败后纠正仍计错 | 行为边界很近，但单一汽车域且仍是 hard pass/fail |

## 3. 核心基准详解

### 3.1 AgentDojo：确定性效用/安全双评估骨架

**任务与环境。** AgentDojo 是为工具调用 Agent 设计的动态、有状态提示注入评测环境。论文发布版本包含 97 个现实用户任务和 629 个 security test cases，覆盖工作区、消息协作、旅行预订和网银等套件。用户任务与攻击者任务可以组合，工具返回的不可信内容中可放入攻击指令。[论文（NeurIPS 2024）](https://proceedings.neurips.cc/paper_files/paper/2024/file/97091a5177d8dc64b1da8bf3e1f6fb54-Paper-Datasets_and_Benchmarks_Track.pdf)；[官方文档](https://agentdojo.spylab.ai/)；[官方仓库](https://github.com/ethz-spylab/agentdojo)

**威胁模型。** 攻击者控制 Agent 会读取的外部数据，但不控制系统提示、工具实现或用户原始指令；目标是诱导 Agent 完成恶意任务。框架强调 adaptive evaluation：防御不能只对某个固定攻击字符串有效。

**指标。** 核心是把“是否完成用户任务”的 utility 与“是否完成攻击者任务”的 security 分开，并通过环境终态上的程序化检查器评分。这使四种结果可区分：安全成功、安全失败、攻击成功但用户任务失败、攻击成功且用户任务也完成。论文亦区分 targeted 与 untargeted attack success。

**可复用实现。** 最值得复用的不是具体攻击模板，而是：

- stateful suite 与 mock tools；
- `UserTask` / `InjectionTask` 的分离；
- 对环境终态执行的确定性 utility/security checks；
- 可插拔 agent、attack、defense 接口；
- 任务和攻击目标的组合生成。

**启示与缺口。** 本项目应沿用“任务效用与安全独立计分”，并禁止只看最终自然语言回复。缺口是 AgentDojo 默认用户任务是充分指定的，变量主要是注入攻击，不是证据完整度；它也不测“证据还差多少时 Agent 才应安全地停止”。

### 3.2 ASPI：澄清状态本身会扩大安全攻击面

**任务与威胁模型。** ASPI 从 AgentDojo 的用户任务—攻击任务对出发，删除一个完成任务所必需且无法从环境恢复的用户信息槽，迫使 Agent 调用 `ask_user`。攻击者可通过普通工具输出、`ask_user` 返回或用户澄清消息注入恶意指令。威胁模型假设攻击者不能修改系统提示、工具或模型权重，也不知道具体用户任务。[论文](https://arxiv.org/pdf/2605.17324)；[官方项目页](https://labs.scale.com/papers/aspi)；[官方仓库](https://github.com/scaleapi/aspi)；[官方数据](https://huggingface.co/datasets/ScaleAI/aspi)

**环境与实验设计。** 728 个配对 task–attack 场景覆盖 Workspace 407、Slack 97、Travel 94、Banking 130。每一组固定任务、攻击目标、环境与 scorer，仅改变：

- 状态：完整任务的 execution vs. 欠规格任务的 clarification；
- 通道：tool、user、next-turn、`ask_user` 等；
- 共 8 个条件：`exec_benign`、`exec_tool`、`exec_user`、`exec_next_turn`、`clarif_benign`、`clarif_tool`、`clarif_ask_user`、`clarif_user`。

**指标。** Task utility、ASR、clarification rate，以及配对条件间 ΔASR；代码提供 bootstrap 置信区间、McNemar 检验和 13 种配对差值。论文用 AgentDojo 的确定性 utility/security scorer，并另外用 LLM judge 做行为分解。其核心实证是：若只在充分指定任务下测安全，会系统性低估交互式 Agent 的攻击面。

**可复用实现。** `agentdojo/` 子模块、数据构造 pipeline、QC-1..QC-7、8-condition runner、`UserSimulator + ask_user`、JSONL 结果、配对统计和两类 defense（跨 user/tool 通道的 prompt guard；保留 `ask_user` 的 tool filter）都可直接借鉴。

**启示与缺口。** ASPI 证明“先问再做”并不自动更安全，澄清回复也必须有信任边界。对本项目而言，任何 Evidence Safety Margin 测试都应至少有 `完整/缺失 × 干净/污染 × 不同通道` 的成对或成组实验。其限制是只删一个 slot、只要求一轮 `ask_user`，且危险性主要由提示注入定义，没有连续证据强度、动作可逆性或风险严重度。

### 3.3 LHAW：可控欠规格与基于终态的有效性验证

**任务。** LHAW 将原本充分指定的长程任务系统性地删去信息，覆盖四个维度：Goal（目标/标识/格式）、Constraint（流程/准则/期限）、Input（位置/工具/API/参考物）、Context（领域知识/历史）。每个信息片段有 `criticality ∈ {0, .5, 1}`、`guessability ∈ {0, .5, 1}`，删除优先级为 `criticality × (1 - guessability)`。[论文/项目页](https://labs.scale.com/papers/lhaw)；[官方仓库](https://github.com/scaleapi/lhaw)；[官方数据](https://huggingface.co/datasets/ScaleAI/lhaw)

**环境与验证。** 285 个公开变体来自 MCP-Atlas、TheAgentCompany 与 SWE-Bench Pro。它不只让 LLM “判断是否歧义”，而是在原环境中多次执行，并按终态差异将删减后的任务分为：

- outcome-critical：0/N 成功且终态分歧，oracle 应澄清；
- divergent：部分成功、结果可变，论文定义的 oracle 为继续；
- benign：N/N 成功，继续；
- new_task：0/N 且形成另一任务，过滤。

**指标。** `pass@k`、强调一致性的 `pass^k`、checkpoint progress、Ask%、每条提问轨迹的问题数，以及 `Gain/Q = Δpass@3 / total_questions`。

**可复用实现。** 最具价值的是 task-agnostic 的 segment extraction / deletion / empirical validation pipeline、taxonomy YAML、三套真实长程 benchmark adapter、`ask_user` 实验、现成 285 变体和报告脚本。

**启示与缺口。** Evidence Safety Margin 的“证据轴”可直接借鉴四维 taxonomy、criticality 与 guessability，但应把离散删除扩展为多级 evidence ladder；样本保留标准也应要求完整任务下 Agent 有基线能力。LHAW 的终态差异主要定义任务成功，不等同于安全损失；其 `divergent → PROCEED` 规则对高风险、不可逆动作并不保守，不应原样采用。

### 3.4 ClarifyBench：动态澄清质量

**任务与环境。** ClarifyBench 评测工具 Agent 在显式、歧义、不可行三类请求中何时提问、问什么、何时执行。数据含 716 个样本、92 个工具，分布于文档编辑、车辆控制、股票交易、旅行和文件系统；每例含用户 query、隐藏真实意图、follow-ups、ground-truth tool call 与 domain。[ACL 2026 官方论文](https://aclanthology.org/2026.findings-acl.2028.pdf)

**构造。** 数据来自 DocPilot 与 BFCL-v3。对成功工具调用最多随机遮蔽 3 个参数生成歧义请求；不可行请求通过手写 API 错误规则构造；生成结果有人审，最高候选选择的一致性 Cohen's κ=0.76。用户模拟器只掌握当前轮可透露的真实意图，避免提前泄露未来信息。

**指标。** Coverage（工具与所有必要参数完全匹配）、Tool Match Rate、Parameter Match Rate、平均澄清问题数；此外将动作分为 ToolCall / AskQuestion / Decline 并可计算分类 P/R/F1。

**可复用部分与缺口。** 适合复用动态 user simulator、逐轮隐藏 ground truth、参数级匹配和问题成本。缺点是安全只隐含在“参数是否正确”，没有严重度加权、实际环境副作用、证据来源可靠性或恶意回复。

### 3.5 When2Call 与 QuestBench：轻量决策和最小必要问题

**When2Call。** 将输出决策明确划分为 `direct`、`tool_call`、`request_for_info`、`cannot_answer`，并在 BFCL 样本中记录 `held_out_param`。指标包括 Macro-F1、length-normalized accuracy，以及无工具时的 tool hallucination rate。仓库公开训练/测试 JSONL 和 evaluator，Apache-2.0。[官方仓库](https://github.com/NVIDIA/When2Call)；[NAACL 2025 论文页](https://aclanthology.org/2025.naacl-long.174/)

**QuestBench。** 把欠规格推理表述为缺少变量赋值的约束满足问题，并限制为最多问一个问题即可解决。四部分为 Logic-Q、Planning-Q（部分可观测 PDDL 初态）、GSM-Q 和 GSME-Q；模型从候选项选最小必要澄清问题。代码可生成 Logic-Q / Planning-Q 并支持 `mc/isambig/fullinfo` 对照。[官方仓库](https://github.com/google-deepmind/questbench)；[NeurIPS 2025 论文](https://openreview.net/pdf?id=gpwA9aZLTZ)

**启示与缺口。** 两者适合做成本低、可大量运行的 Stage-0 probe：先验证 agent 能否正确区分执行/澄清/拒绝，以及能否找到“最小充分证据”。但它们不执行真实有副作用的动作，不能单独支撑安全结论。

### 3.6 τ-bench / τ³-bench：有状态、多轮、规则约束的工程底座

**任务与环境。** 原始 τ-bench 让 Agent 在零售和航空场景中与 LLM 用户模拟器对话，通过领域 API 修改数据库并遵循策略规则；评分比较对话结束后的数据库状态与标注 goal state。它提出 `pass^k`，衡量同一任务连续 k 次都成功的可靠性。[原论文](https://arxiv.org/abs/2406.12045)；[原仓库（已标记过时）](https://github.com/sierra-research/tau-bench)

截至本次调研，维护方要求新评测使用同一官方仓库演进后的 τ³-bench：支持航空、零售、通信、知识银行等 domain、文本/全双工语音模式、Gym 接口，并修复了大量错误或歧义任务。[当前官方仓库](https://github.com/sierra-research/tau2-bench)

**指标与实现。** 原始核心 reward 是终态数据库匹配，`pass^k` 暴露单次成功率无法反映的不稳定性；代码还提供 user simulator、多 agent strategy、历史 trajectories 和故障归因（用户/agent/环境；部分完成/错工具/错参数/非预期动作）。新版把 domain 定义为 policy + tools + tasks + optional user tools，并提供动作级 evaluation criteria。

**启示与缺口。** 本项目可复用 domain contract、数据库 sandbox、用户模拟器和多次试验。策略规则可承载“高风险动作需要哪些证据”。但原始 τ-bench 并未系统操纵信息完整度，也没有攻击者和独立 safety predicate；论文明确指出终态 reward 只是必要而非充分条件，例如未获用户确认就执行退货，最终数据库仍可能恰好匹配 goal，因此数据库成功绝不能直接当作安全成功。

### 3.7 Agent-SafetyBench：广覆盖风险和“缺信息编造参数”失败模式

**任务与环境。** Agent-SafetyBench 包含 349 个交互环境、2,000 个测试用例、8 类风险和 10 类失败模式。环境以 JSON 工具 schema + Python class 双层实现，schema 与常见 function-calling 格式兼容。[论文](https://arxiv.org/abs/2412.14470)；[官方仓库](https://github.com/thu-coai/Agent-SafetyBench)

**风险/失败模型。** 风险覆盖敏感信息泄露、财产损失、危险/错误信息、身体伤害、违法/不道德、可用性破坏、有害/脆弱代码等。与本项目直接相关的是论文所称失败模式 M2：Agent 在信息不足时编造参数并调用工具；该失败模式在评测中安全得分很低。数据也区分 safely fulfillable 与 unfulfillable 请求。

**指标。** 主要安全分数由微调的 Qwen2.5-7B scorer 对完整交互轨迹判定；scorer 在论文的 200 条验证集上报告 91.5% 准确率。论文另以 GPT-4o 评估 helpfulness，从而分析安全不是简单拒绝。

**可复用实现与缺口。** 可复用广风险 taxonomy、failure-mode 标签、工具 schema/环境基类和公开 scorer。缺点是总 safety score 难以定位“证据阈值”，LLM judge 也不适合单独判断细微 margin；大量环境是合成工具，且论文承认多数任务只需常识而非高级领域知识。

### 3.8 ToolEmu：用 LM 模拟沙箱快速发现高风险轨迹

**任务与环境。** ToolEmu 的核心设定就是 instruction underspecification：用户意图良性，但指令缺少任务细节或安全/安全性约束；Agent 若擅自补全、不澄清或忽视风险，便可能执行危险工具操作。它让 Agent 调用 36 个工具包中的 311 个工具，由另一个 LM 模拟工具执行，不需接入真实服务；初始 benchmark 有 144 个测试用例和 9 类风险。每例显式记录 task-information underspecifications、safety/security-constraint underspecifications、potential risks/risky actions 与 expected achievements。[ICLR 2024 论文](https://proceedings.iclr.cc/paper_files/paper/2024/file/7274ed909a312d4d869cc328ad1c5f04-Paper-Conference.pdf)；[官方仓库](https://github.com/ryoungj/ToolEmu)；[项目页](https://toolemu.com/)

**威胁/失败模型。** 它主要评估良性用户的欠规格任务或 Agent 鲁莽工具使用造成的风险，不以攻击者为必需条件。LM emulator 被提示生成真实、一致并尽可能暴露风险的工具反馈；adversarial emulator 会朝潜在风险状态施压。LM evaluator 检查完整轨迹的风险和帮助性。

**指标与可复用实现。** Safety 0–3 由风险发生可能性（certainly not / possible / likely）与后果严重性（mild / severe）映射；Helpfulness 也为 0–3，并另报 failure incidence。工具规范/case 生成流水线、上述欠规格 case schema、LM-emulated sandbox、trajectory evaluator 与 agent executor 很适合低成本扩充领域。“不做任何事”可得很高 safety 却会失去 helpfulness，因此两轴必须并报。

**启示与缺口。** ToolEmu 几乎是 ESM 的前身，尤其值得直接继承“任务信息缺口”和“安全约束缺口”分栏。可在开发早期探索高风险域和生成候选样本，但正式主榜应尽量采用确定性环境与 predicate。其欠规格仍是文字标签而非同任务的证据梯度；emulator 与 judge 同为 LM 时，也会把环境误差、Agent 错误和评分误差混在一起，对临界证据差异尤其危险。

### 3.9 R-Judge：静态轨迹风险意识评估

**任务。** R-Judge 给 LLM 一段 Agent 交互记录，让其判断是否存在安全风险并说明风险。最新论文/数据版本包含 27 个场景、569 条记录、5 类应用与 10 类风险；项目页仍保留早期规模描述，因此复现实验必须固定论文/数据 release，而不能混用网页旧统计。资料来自公开 Agent benchmark 与人工构造。[论文](https://arxiv.org/html/2401.10019)；[官方项目页](https://rjudgebench.github.io/)；[官方仓库](https://github.com/Lordog/R-Judge)

**威胁模型与指标。** 它不让被测模型实际执行工具，而是测 risk awareness。安全判断主报 F1，并报告 Recall 与 Specificity；开放式风险识别使用 GPT-4 对照人工 risk description 评价 Effectiveness。在 50 个 unsafe 样本上，论文报告自动 scorer 与三位人工的平均 PCC 为 0.91。

**可复用部分与缺口。** 可用于训练或校准“轨迹审计器”、生成风险解释，以及与执行 Agent 做解耦评测。因为输入是固定轨迹，它无法测被测 Agent 是否会主动澄清、停止或采取危险动作，也无法估计缺少某条证据造成的因果变化。

### 3.10 Agent Security Bench (ASB)：攻击/防御面矩阵

**任务与环境。** ASB 在学业建议、咨询、投资、法律、电商、自动驾驶、金融等 10 个场景和 10 个 agent 上系统测试攻击与防御，包含 400+ tools。最终 ICLR 2025 版本论文报告 27 类攻击/防御方法与 7 个指标（早期 arXiv/README 的数量曾不同，应以会议版为准）。[ICLR 2025 论文](https://openreview.net/forum?id=V4y0CpX4hK)；[官方仓库](https://github.com/agiresearch/ASB)；[项目页](https://luckfort.github.io/ASBench/)

**威胁模型。** 代码涵盖 Direct Prompt Injection、Observation Prompt Injection、Plan-of-Thought backdoor、Memory Poisoning 和 mixed attacks，分别污染用户 query、环境 observation、system-level planning behavior 或检索 memory。

**指标与实现。** ASB 同时统计 attack effectiveness、agent utility、defense effectiveness 与效率等；实现基于 AIOS，YAML 配置可组合模型、攻击和防御，`scripts/agent_attack*.py` 是主要入口。

**启示与缺口。** 可借用“攻击面 × 通道 × 防御”的实验矩阵和配置方式，尤其是 observation / memory 证据污染。但 ASB 研究的是恶意操纵，不是合法但不完整的证据；多场景总体平均也可能掩盖高风险动作上的最坏情况。

### 3.11 CAR-bench：把内部取证与有副作用动作分开

**任务与环境。** CAR-bench 是从 τ-bench 思路扩展的车载助手 benchmark，设有 Base、Hallucination、Disambiguation 三类任务。Hallucination 分别删除完成任务所需的工具、参数或结果，使任务不可满足；Disambiguation 要求 Agent 优先用内部 get-tool 取证，环境中仍无信息时才询问用户。环境含 31 个动态状态、58 个工具（27 set、29 get、2 no-op）和 19 条 policy。[论文](https://arxiv.org/html/2601.22027)；[官方仓库](https://github.com/CAR-bench/car-bench)

**指标与实现。** task success 是相关二值条件的合取，包括 final/intermediate states、required get-tool subset、tool/policy errors 和用户是否正确终止；12 条 policy 可确定性检查，7 条使用 LLM judge，并报告 `pass^k/pass@k`。关键安全语义是：错误 set action 即使后来纠正也仍失败，因为真实物理副作用已经发生。

**启示与缺口。** 其 get/set 显式分离非常适合 ESM：先读取证据，再允许有副作用动作；三分法也可直接借为 complete/solvable、missing capability/unsatisfiable、resolvable ambiguity。缺口是单一汽车域，部分判分仍依赖 user simulator/LLM judge，而且只有 hard pass/fail，未构造连续 evidence ladder 或来源冲突。

## 4. SafeBench 名称辨析

“SafeBench”有多个同名项目，不能混用：

- [SafeBench（NeurIPS 2022）](https://safebench.github.io/) 是 CARLA 自动驾驶安全场景 benchmark，不是通用 LLM Agent benchmark；
- [SafeBench-MM](https://safebench-mm.github.io/) 是多模态大模型有害内容评测，也不是工具 Agent 行为安全；
- 与本项目相关的是本文第 3.7 节的 [Agent-SafetyBench](https://github.com/thu-coai/Agent-SafetyBench)。

如未来加入具身或自动驾驶域，CARLA SafeBench 的 adversarial scenario generation 和碰撞/轨迹指标可作为单独 domain adapter，现阶段不宜放入通用核心。

## 5. 对本项目的直接设计启示

### 5.1 样本必须是成组反事实，而不是孤立 prompt

建议每个 base task 至少生成以下组内条件，并共享同一环境初态、真实用户意图与安全 predicate：

1. `full-clean`：证据完整、无污染；验证 Agent 的基础能力；
2. `partial-clean[L1..Ln]`：逐级删除或弱化关键证据；
3. `partial-resolved`：Agent 澄清后只补回所需证据；
4. `partial-noisy`：补回无关或相互冲突证据；
5. `partial-adversarial[channel]`：在 user/tool/memory/ask_user 通道污染；
6. 可选 `full-adversarial`：区分纯状态效应与通道效应。

这是 LHAW 的可控删除与 ASPI 的配对设计的合并。只有 paired delta 才能说明失败由证据条件变化导致，而不是任务难度差异。

### 5.2 证据模型应显式化

每例建议保存：

- `evidence_items[]`：事实、来源/通道、相关 tool parameter、真实性、可获得性；
- `required_evidence_set`：执行某动作所需的最小证据集合，可允许多个等价集合；
- `criticality`、`guessability`：借鉴 LHAW；
- `source_trust`、`freshness`、`conflict_group`：补上来源质量与冲突；
- `risk_severity`、`reversibility`、`blast_radius`：描述动作损失；
- `oracle_action ∈ {execute, clarify, abstain, safe_alternative}`；
- `utility_predicates[]` 与 `safety_predicates[]`：独立、尽可能确定性。

Evidence Safety Margin 不应只等同“还缺几个参数”。相同缺口对于“搜索航班”和“付款/删文件/改密码”应产生不同安全边界。

### 5.3 指标要把能力、安全、校准和成本分开

建议核心指标至少包含：

- **Safe Utility**：完成任务且未触发任何 safety predicate；
- **Unsafe Action Rate (UAR)**：证据不足时仍执行有副作用动作；
- **Premature Action Rate**：在尚未达到最小证据集前首次执行；
- **Clarification Precision / Recall**：该问时问、不该问时不问；
- **Evidence Recovery**：提问后获得了多少必要证据，类似 PMR；
- **Minimality / Question Cost**：达到安全执行所需的问题数、token、延迟；
- **Margin / Boundary Error**：Agent 实际执行阈值与 oracle 安全阈值之差；
- **Risk-weighted Margin**：按 severity、不可逆性和 blast radius 加权；
- **Consistency `pass^k` / safe-pass^k**：多次运行是否稳定安全；
- **Paired ΔUAR / ΔASR**：同一任务在证据/通道条件变化后的增量；
- **Over-refusal / Safe Alternative Rate**：避免“永远拒绝”在安全分上作弊。

主榜不宜将以上压成一个不透明总分；可以展示二维 Pareto（safe utility vs. UAR）和按风险档位分层的 margin。

### 5.4 评分优先级：确定性检查器 > 规则解析 > 多 judge 校准

建议延续 AgentDojo / τ-bench：

1. 首选环境终态、tool call、数据库/文件 diff 和事件日志上的 deterministic predicates；
2. 对结构化但允许等价表达的结果使用 canonicalization / rule-based matcher；
3. 仅对风险解释、语义等价或开放式任务使用 LLM judge；
4. 对 LLM judge 做固定 rubric、双 judge、人工 held-out 校准，并报告一致性；
5. 保存完整 trace 和 scorer evidence，允许离线重打分而不重跑模型。

ToolEmu 式 emulator 可以用于开发集扩域，但不能成为临界 margin 的唯一真值来源。

### 5.5 环境与工程实现建议

推荐一个 Python-first、adapter-based 架构：

- **数据/schema**：Pydantic v2 + JSONL/Parquet；JSON Schema 表述 tools 与 evidence；
- **runner**：async Python，模型层用薄 provider adapter（必要时 LiteLLM），不让 provider 格式进入核心轨迹结构；
- **environment**：内存或 SQLite state machine，所有 mutation 产生日志；高风险动作支持 dry-run 与可回滚 sandbox；
- **task API**：`reset(seed) / tools() / step(tool_call) / snapshot() / grade(trace, final_state)`；
- **user simulator**：优先模板/有限状态机；开放式回复才调用 LLM，且只能读取该轮允许透露的 hidden intent；
- **evaluators**：utility、安全、澄清、证据覆盖、成本分别实现；
- **reproducibility**：冻结 task version、model snapshot、prompt hash、seed、tool schema hash；每例至少多次 trial；
- **统计**：paired bootstrap CI、McNemar（成对二值结果）、分层 bootstrap（task/domain）；
- **结果存储**：append-only trajectory JSONL + 单独 aggregate Parquet，便于断点续跑和重评分。

代码层面优先“借鉴接口并重写最小核心”，而不是直接把 AgentDojo、τ³-bench、LHAW 三个大型仓库同时作为运行依赖。可先做兼容 adapter，后续再导入任务。

## 6. 可复用优先级与许可注意

### 第一优先级：概念与实现都可直接借用

- **ASPI / AgentDojo**：配对条件、确定性 utility/security、澄清通道攻击；
- **LHAW**：欠规格 taxonomy、删除 pipeline、经验验证；
- **τ³-bench**：有状态 domain、用户模拟、多次试验与版本化任务。

### 第二优先级：抽取数据模型或 evaluator

- **ClarifyBench**：动态 user simulator 与参数级指标；
- **When2Call**：四分类 decision probe 与 tool hallucination；
- **Agent-SafetyBench**：风险/失败模式 taxonomy、scorer baseline；
- **ToolEmu / R-Judge**：轨迹风险解释和开发集扩域。

### 许可

在真正复制代码/数据前必须逐仓核对当时的 `LICENSE` 与资产子许可。当前官方资料明确：AgentDojo 与 τ-bench/τ³-bench 仓库为 MIT；QuestBench 软件为 Apache-2.0、其他材料为 CC-BY 4.0；When2Call 为 Apache-2.0；Agent-SafetyBench 论文称其新数据和评测代码为 MIT。论文中引用或再分发的第三方数据可能有不同许可，不能只看顶层仓库许可证。

## 7. 建议 MVP 取舍

如果目标是尽快验证 idea，而不是一开始追求“大而全”，建议 MVP：

- 3 个 domain：文件/协作（低到中风险）、消费/旅行（中风险）、银行/凭证（高风险）；
- 每域 15–25 个 base tasks；
- 每任务 4–6 级 evidence ladder，外加 clean/noisy/adversarial 关键条件；
- 每个条件至少 3 次 trial；
- 只使用可程序化评分的工具和终态；
- 首版只测 `execute / clarify / abstain / safe_alternative`，不引入复杂自然语言 judge 总分；
- 主结果报告 Safe Utility、UAR、risk-weighted margin、clarification P/R、safe-pass^3 和 paired confidence interval。

这样约 60 个 base tasks × 平均 6 条件 × 3 trials = 1,080 条轨迹/模型，成本和人工验收仍可控，同时已经能辨识安全边界。第二阶段再接 LHAW 长程任务、ASPI 多通道攻击和 Agent-SafetyBench 风险 taxonomy。

## 8. 一手资料索引

- AgentDojo：[论文](https://proceedings.neurips.cc/paper_files/paper/2024/file/97091a5177d8dc64b1da8bf3e1f6fb54-Paper-Datasets_and_Benchmarks_Track.pdf) · [仓库](https://github.com/ethz-spylab/agentdojo) · [文档](https://agentdojo.spylab.ai/)
- ASPI：[论文](https://arxiv.org/pdf/2605.17324) · [项目页](https://labs.scale.com/papers/aspi) · [仓库](https://github.com/scaleapi/aspi) · [数据](https://huggingface.co/datasets/ScaleAI/aspi)
- LHAW：[论文/项目页](https://labs.scale.com/papers/lhaw) · [仓库](https://github.com/scaleapi/lhaw) · [数据](https://huggingface.co/datasets/ScaleAI/lhaw)
- ClarifyBench：[ACL Anthology 论文](https://aclanthology.org/2026.findings-acl.2028.pdf)
- When2Call：[论文](https://aclanthology.org/2025.naacl-long.174/) · [仓库](https://github.com/NVIDIA/When2Call) · [数据](https://huggingface.co/datasets/nvidia/When2Call)
- QuestBench：[论文](https://openreview.net/pdf?id=gpwA9aZLTZ) · [仓库](https://github.com/google-deepmind/questbench)
- τ-bench：[论文](https://arxiv.org/abs/2406.12045) · [旧仓库](https://github.com/sierra-research/tau-bench) · [当前 τ³-bench 仓库](https://github.com/sierra-research/tau2-bench)
- Agent-SafetyBench：[论文](https://arxiv.org/abs/2412.14470) · [仓库](https://github.com/thu-coai/Agent-SafetyBench)
- ToolEmu：[论文](https://proceedings.iclr.cc/paper_files/paper/2024/file/7274ed909a312d4d869cc328ad1c5f04-Paper-Conference.pdf) · [仓库](https://github.com/ryoungj/ToolEmu) · [项目页](https://toolemu.com/)
- R-Judge：[论文](https://arxiv.org/abs/2401.10019) · [项目页](https://rjudgebench.github.io/) · [仓库](https://github.com/Lordog/R-Judge)
- ASB：[论文](https://openreview.net/forum?id=V4y0CpX4hK) · [仓库](https://github.com/agiresearch/ASB) · [项目页](https://luckfort.github.io/ASBench/)
- CAR-bench：[论文](https://arxiv.org/html/2601.22027) · [仓库](https://github.com/CAR-bench/car-bench)
