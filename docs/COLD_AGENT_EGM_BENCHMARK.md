# Cold-Agent Skill Evaluation and the Elephant-Goldfish Method (EGM)

This document records the four-stage empirical evaluation of `fdisbull-investigate` across 12 cold sub-agent runs on *Sid Meier's Colonization* (1994, DOS `VICEROY.EXE`) and analyzes how the benchmark progression—especially **Test 4 (Controlled Dossier-Only Allocation)**—implements and extends the **Elephant-Goldfish Method (EGM)** for binary reverse engineering.

No proprietary binaries, original game assets, or byte-retaining databases are stored in the repository. All binary references below are address/offset citations and sanitized arithmetic models verified against caller-owned inputs.

---

## 1. The Elephant-Goldfish Method (EGM) in Reverse Engineering

The **Elephant-Goldfish Method (EGM)** separates AI-assisted engineering into two distinct memory paradigms to prevent **context rot**, **shared blind spots**, and **sycophantic self-certification** in long sessions:

| Paradigm | Context Profile | Role in Software Design | Role in `fDisBull` Binary Investigation |
| :--- | :--- | :--- | :--- |
| **The Elephant** | Long-lived, high-context session holding institutional memory, external literature, and cross-turn history. | Brainstorms architecture, debates trade-offs, and drafts an explicit Design Spec. *Writes no production code.* | Surveys external reconstructions (e.g., pinned OpenCol C sources), compiles a candidate **Lead Dossier** (`LEAD_DOSSIER.md`), strips embedded answers from `COMMON_TASK.md`, and authors adversarial challenge probes (`check_claims.py`). *Declares no native binary facts itself.* |
| **The Goldfish** | Fresh, zero-context stateless sub-agent spawned in an isolated mount with no conversational memory. | Reads *only* the spec and linked files; critiques unstated assumptions, ambiguities, and edge cases without flattery. | Receives *only* its isolated packet (`Worker_N.zip`) and the target binary; applies `fdisbull-investigate` to verify or **falsify** candidate leads against actual machine instructions (`target_static`), keeping `external_reconstruction` and `unknown` strictly separated. |

### Why Reverse Engineering Needs Both Paradigms

1. **Pure Elephant Failure Mode (Context Rot & Guide Promotion):** A single long-running session that reads external wikis, decompilations, and prior chat summaries begins treating external approximations as verified binary facts, smoothing over integer-truncation edge cases and edition divergences (e.g., Windows vs. DOS).
2. **Naked Goldfish Failure Mode (Cold Thrashing or Surface Lexical Matching):** A zero-context sub-agent dropped onto a 494 KB DOS MZ/RTLink overlay binary without methodology or leads either stops at shallow text tables (`NAMES.TXT`, `LABELS.TXT`) or spends double the tool budget hunting through cross-references to locate arithmetic kernels.
3. **The EGM Synthesis (Elephant Dossier + Skilled Goldfish + Adversarial Gate):** The Elephant amortizes external reconnaissance once into an explicitly *unqualified* Lead Dossier; the Goldfish uses `fdisbull-investigate` to jump directly to candidate offsets in the binary while remaining epistemically required to report where the binary disagrees with the dossier.

---

## 2. Progression Across All Four Empirical Tests (12 Sub-Agent Runs)

Across four successive experimental designs, we tested three core worker arms:
- **Arm 1 (`Skill + Tool`)**: Cold agent with `fdisbull-investigate` and local tools.
- **Arm 2 (`Tool Only`)**: Cold agent with local tools only (no investigation skill).
- **Arm 3 (`Skill + Tool + External/Dossier`)**: Cold agent with `fdisbull-investigate`, local tools, and either live web search (Tests 1–3) or the frozen Lead Dossier only under `NO-WEB` isolation (Test 4).

### Summary Table Across All Four Tests

| Test | Experimental Design & Task Scope | Arm 1 (`Skill + Tool`) | Arm 2 (`Tool Only`) | Arm 3 (`Skill + Tool + Web/Dossier`) | Primary Methodological Finding |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Test 1** | **Cold Single-Task Baseline**<br>*(Item production chains; repo docs available; live web only in Arm 3)* | **236s** (3m 56s)<br>58 steps / 8 tools | **223s** (3m 43s)<br>76 steps / 6 tools | **396s** (6m 36s)<br>119 steps / 15 tools *(Live Web)* | Skill reduced local trajectory steps by **23.7%** (`58` vs `76`) and enforced 4-part epistemic partitioning; live web added **+160s (+67.8%)** latency. |
| **Test 2** | **3-Chained Tasks + Shared Dossier**<br>*(Warehouse clamping $\to$ Food/pop spawn $\to$ Unit equipment; dossier given to all 3)* | **275s** (4m 35s)<br>104 steps / 50 tools | **279s** (4m 39s)<br>99 steps / 45 tools | **336s** (5m 36s)<br>122 steps / 58 tools *(Shared Dossier + Web)* | Pre-compiling the dossier equalized local speed (`275s` vs `279s`) and shifted Arm 3's web search from broad rules to surgical struct lookup (`28-byte` unit stride, `+0x15` pioneer tools). |
| **Test 3** | **4-Chained Tasks + Shared Dossier**<br>*(Education $\to$ Founding Fathers $\to$ Royal taxes/boycotts $\to$ Market prices; dossier in `docs/`)* | **437s** (7m 17s)<br>112 steps / 53 tools | **482s** (8m 02s)<br>124 steps / 60 tools | **555s** (9m 15s)<br>153 steps / 75 tools *(Shared Dossier + Web)* | Arm 1 was **9.3% faster** than Arm 2 (`437s` vs `482s`), while Arm 3 took **+118s (+27.0%)** fetching external OpenCol C files. Confounded by shared `docs/` dossier and live web. |
| **Test 4** | **Controlled EGM Allocation (Dossier Only to Worker 3)**<br>*(Same 4 systems on raw DOS `VICEROY.EXE`; isolated mounts; strict `NO-WEB` for all 3)* | **813.0s** (13m 33s)<br>292 steps / 145 tools<br>10 static claims | **545.0s** (9m 05s)<br>234 steps / 117 tools<br>8 surface claims | **494.0s** (8m 14s)<br>156 steps / 77 tools<br>13 verified claims *(Dossier Only, No Web)* | Isolating the Lead Dossier to Worker 3 under `NO-WEB` cut verified binary investigation time by **39.2%** (`813s` $\to$ `494s`) and tool calls by **46.9%** (`145` $\to$ `77`). |

---

## 3. Deep Dive: Why Test 4 Is the Canonical Elephant-Goldfish Test

### 3.1 Diagnosing the "Elephant Leakage" in Tests 2 and 3

In Tests 2 and 3, the coordinator session acted as an **Elephant** that researched external mechanics and wrote `docs/COLONIZATION_GAME_SYSTEMS_REFERENCE.md` into the shared checkout for all three agents. While useful for demonstrating research amortization, that design violated strict Elephant-Goldfish separation in three ways:
1. **No Unassisted Skill Baseline:** Giving the dossier to all three arms prevented measuring the pure speedup of the dossier (`Arm 3` vs `Arm 1`) separately from the skill (`Arm 1` vs `Arm 2`).
2. **Confounded Treatment Variables:** Arm 3 changed *both* reference material and live web access simultaneously.
3. **Unchallenged Elephant Simplifications:** Because all agents read the same shared summary and prior repository pilot notes, subtle mathematical oversimplifications in the Elephant's narrative went unchallenged until audited by independent challenge probes.

### 3.2 How Test 4 Enforced Strict Elephant-Goldfish Isolation

Test 4 (`Colonization_Dossier_Only_Agent3_Controlled_Test_2026-11-02.zip`) corrected all three confounds by enforcing a strict EGM boundary:
- **Purged Shared Checkout:** `docs/COLONIZATION_GAME_SYSTEMS_REFERENCE.md` was removed before launch so no worker could discover answers via workspace search.
- **Neutral Public Prompt (`COMMON_TASK.md`):** Contained only source-qualified questions for the four systems, with zero embedded formulas or thresholds.
- **Strict `NO-WEB` Primary Phase (`extra_web_calls = 0`):** Removed live web latency and search variance across all three arms.
- **Three Distinct Goldfish Packets:**
  - **Worker 1 (`Worker_1.zip`) — The Unassisted Skilled Goldfish:** Received `COMMON_TASK.md`, the 19-file `fdisbull-investigate` skill bundle, and byte-verified `VICEROY.EXE` (`a17ed64c...`), `NAMES.TXT`, and `LABELS.TXT`. No dossier.
  - **Worker 2 (`Worker_2.zip`) — The Unskilled Naked Goldfish:** Received `COMMON_TASK.md` and the same target files. No skill, no dossier.
  - **Worker 3 (`Worker_3.zip`) — The Elephant-Assisted Skilled Goldfish:** Identical to Worker 1 plus `LEAD_DOSSIER.md` (pinned OpenCol reconstruction leads explicitly marked as *unqualified external leads* requiring binary verification).

### 3.3 Quantitative Contrasts in Test 4

1. **The Prepared-Dossier Effect (`Worker 3` vs. `Worker 1` under identical skill):**
   - **Wall-Clock Time:** Reduced from **813.0s to 494.0s** (**319.0s saved / 39.24% reduction**).
   - **Tool Calls:** Reduced from **145 to 77** (**46.90% reduction**).
   - **Trajectory Steps:** Reduced from **292 to 156** (**46.58% reduction**).
   - **Interpretation:** In EGM terms, handing a skilled Goldfish a bounded, explicitly unqualified Elephant spec cuts reverse-engineering time and tool cost nearly in half without sacrificing binary rigor.
2. **The Skill Effect without Dossier (`Worker 1` vs. `Worker 2`):**
   - **Why `Worker 2` Finished Earlier (`545.0s` vs. `813.0s`) with Inferior Scope:** Without `fdisbull-investigate`, `Worker 2` parsed plaintext resource tables (`@JOB`, `@BUILDING`, `@CARGO` in `NAMES.TXT` and `LABELS.TXT`) and stopped at high-level entry hooks (`0x33c94`, `0x47e2c`), leaving the underlying arithmetic formulas unproven.
   - **Why `Worker 1` Invested `813.0s`:** Guided by `references/binary-claim-verification.md` and `references/methodology.md`, `Worker 1` refused to treat string labels as mechanical proofs. It traced RTLink overlay stubs, located the exact machine code for all four systems (`0x3C282..0x3C321`, `0x3434C..0x3436B`, `0x34404..0x3471A`, `0x3068E..0x30AA6`), and authored a standalone reproduction verifier (`reproduce_mechanics.py`).
3. **Prepared Dossier (`494.0s`) vs. Live Web Search (`555.0s` in Test 3):**
   - Even against raw `VICEROY.EXE` binaries, `Worker 3` with an offline Lead Dossier completed **61.0s (11.0%) faster** and in **49.7% fewer tool calls** than the live-web agent in Test 3 (`77` vs. `75` calls on pre-summarized repo docs, and zero network round-trips).

---

## 4. Goldfish Falsification: Where Test 4 Caught Oversimplifications and Edition Divergences

The hallmark of the Elephant-Goldfish Method is that **the Goldfish challenges the Elephant**. In Test 4, combining the 15 adversarial reviewer probes (`check_claims.py`) with the independent disassembly of `VICEROY.EXE` by `Worker 1` and `Worker 3` exposed four critical refinements over earlier summaries:

### 4.1 Boston Tea Party Selection: OpenCol Weighted Loop vs. DOS `VICEROY.EXE` Max-Tonnage Scan
- **Earlier Summary Simplification (Test 3):** Claimed that the Tea Party scans goods in reverse index order (`15` down to `0`) so stocked Muskets (`15`) or Tools (`14`) almost always win.
- **Adversarial Model Probe (`check_claims.py`):** Proved that even in the OpenCol reconstruction (`tea_selection`), a stocked Musket slot (`stocks[15] = 50`) with `weights[15] = 0` loses to `weights[14] = 1` (returns index `14`), and all-zero weights select the *lowest* stocked index (`0`), not `15`.
- **Goldfish Binary Discovery (`VICEROY.EXE` at `0x3446A..0x344C6` and `0x34682`):** Both `Worker 1` and `Worker 3` independently disassembled the actual DOS `VICEROY.EXE` routine and discovered that **original DOS `VICEROY.EXE` does not use OpenCol's trade-weight accumulator for Tea Party selection**. Instead, DOS `VICEROY.EXE`:
  1. Iterates forward through commodity indices `0..15` (`0x3446A..0x344C6`).
  2. Skips already-boycotted goods (`test [boycott_mask], bit`).
  3. Compares `colony.cargo[good] > max_tonnage` (`cmp ax, [bp-0x0c]; jle`) and records the index with the strictly greatest stockpile (minimum threshold `100` tons at `0x344CA`, capping dumped forfeiture at `100` tons at `0x34682`).
  - `Worker 3` properly recorded the DOS binary behavior as `target_static` and kept the OpenCol weighted-sum formula distinct instead of conflating them.

### 4.2 Founding Father Liberty-Bell Cost: Compound Era Rounding (`0x3C282..0x3C321`)
- **Earlier Summary Simplification (Test 3):** Expressed the cost sequence for $N \ge 2$ as a linear formula $\text{Base}_2 + (N - 2) \times \Delta$ derived solely from $\text{Base}_1 = \text{cost}(1)$.
- **Goldfish Binary Proof (`0x3C282..0x3C321`) & Reviewer Probe:** Disassembly confirmed that `VICEROY.EXE` computes the base factor $v = (\text{difficulty} + 3) \times 16$ (`shl ax, 4` at `0x3C2A3`), then loops across the four era thresholds (`1600, 1650, 1700, 1750` at `0x3C2AE..0x3C2D3`), applying integer halving-and-addition at each reached boundary *before* multiplying by $(\text{count} + 1)$:
  $$v_{k} = v_{k-1} + \lfloor v_{k-1} / 2 \rfloor, \quad \text{raw} = (\text{count} + 1) \times v_{\text{era}} + 1$$
  When $\text{count} = 0$ (first Father), $\text{cost} = \lfloor \text{raw} / 2 \rfloor$ (`0x3C2ED`). Because odd intermediate values of $v_{\text{era}}$ lose their remainder on the final `/ 2` for the first Father, in year `1750` at `difficulty = 0` (Discoverer):
  - $v_0 = 48 \xrightarrow{1600} 72 \xrightarrow{1650} 108 \xrightarrow{1700} 162 \xrightarrow{1750} 243$.
  - First Father ($\text{count}=0$): $\lfloor (1 \times 243 + 1) / 2 \rfloor = 122$.
  - Second Father ($\text{count}=1$): $2 \times 243 + 1 = 487 \neq 4 \times 122 + 1 = 489$.

### 4.3 Royal Tax Event Bands (`950..1099`) and the `75%` vs. `85%` Cap (`0x3434C..0x3436B`, `0x34B44`)
- **Adversarial Model Probe:** Exposed that score band `950..1099` dispatches to `navigation_act` (omitted in Test 3's summary table) and that `score = 200` switches from `wedding` to `war` once `wedding_count >= 30`.
- **Goldfish Binary Proof:** `Worker 1` (`0x3434C..0x3436B`) and `Worker 3` (`0x34B44`) verified the native tax clamp in `VICEROY.EXE`, which caps the applied crown tax rate at **`75%` (`0x4B`)** (`cmp word [tax], 0x4b; jle; mov word [tax], 0x4b`), distinct from the `85%` scheduling check in OpenCol's `europe_new_taxes` reconstruction.

### 4.4 European Market Price Drift vs. Trade Pressure (`0x3068E..0x30AA6`, `0x30969`)
- **Goldfish Binary Proof:** `Worker 1` and `Worker 3` verified that `VICEROY.EXE` scales commodity volume increments by `1 << shift` (`shl ax, cl`), applies the Dutch nation resilience modifier (`shl ax, 1` at `0x30969`), clamps bid prices to `[1, 19]` (`0x30A40..0x30A73`), and sets ask spread via `ask = bid + max_price_table[good]` (`0x30A76..0x30A8B`).
- **Adversarial Model Probe:** Verified that coupled luxury goods (`Rum, Cigars, Cloth, Coats`) alter their shared target price $3 \sum V / V_i$ upon trade, which then pulls prices via the turn-tick drift accumulator (`luxury_tick`) rather than mutating sibling prices instantaneously during a single sale.

---

## 5. Practical Guidelines for Running EGM Workflows in `fDisBull`

When investigating a complex target binary with multiple subsystems:
1. **Run an Elephant Preparation Pass First:** Collect external references, reconstructions, or symbol tables into a single `LEAD_DOSSIER.md`. Label every external formula as an *unqualified lead*, never as a verified binary claim.
2. **Strip Answers from the Task Specification:** Keep `COMMON_TASK.md` strictly question-driven so fresh workers are not primed to echo expected constants.
3. **Dispatch Isolated Goldfish Workers with `fdisbull-investigate`:** Run workers in separate workspaces under `NO-WEB` during the primary verification phase. Require each claim to carry an explicit `evidence_source` (`target_static`, `target_runtime`, `external_reconstruction`, or `unknown`).
4. **Validate via Independent Challenge Probes and `metrics.py`:** Use deterministic counterexample tests (`tests/test_cold_agent_egm_benchmark.py`) and host-receipt validation before accepting any speedup or coverage claim.
