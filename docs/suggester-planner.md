# Suggester planner — mini factory CAM agent

**Team:** Attention Heads  
**Event:** neatHack (Build an Agent That Works)  
**Status:** Planning only — code starts after hackathon kickoff (12:30 PM IST, 10 Oct 2026).

This document uses **one vocabulary** for the whole project. Stick to these words in the demo, devlog, README, and video.

---

## Words we use (glossary)

| Word | Meaning in our project |
|---|---|
| **Part spec** | What the customer wants made: numbers and/or a simple **2D profile** file (we support **JSON spec** and/or **DXF** — pick one for day 1). |
| **Upload** | User (or demo script) puts the part spec into the agent run. |
| **G-code** | Machine instructions our agent produces for a **small CNC turning** sim. |
| **Program gate** | Phase 1: no manufacturing until the program passes checks. |
| **Validator** | Automatic rules: safe moves, inside stock, no crash — pass or fail. |
| **Simulator** | Software **CNC turning** that “cuts” using the G-code (not real metal). |
| **Viewer** | **2D** picture: target profile + toolpath / result (optional simple **3D** later). |
| **Precision** | Sim measured size/shape is within **tolerance** (e.g. ±0.1 mm in sim units). |
| **Agent loop** | Agent tries → validator/simulator/measures → if fail, adjust → try again. |
| **Approved program** | G-code (and params) that passed precision; locked for phase 2. |
| **Manufacturing loop** | Phase 2: sim **lathe runs** the approved program. |
| **Robotic arm** | **Secondary**: load blank, unload finished part — **sim only**, after program is approved. |
| **Green** | Verifier says success: program gate passed, or line run completed. |
| **Recovery** | One fail on purpose (bad cut or fault), then agent fixes or replans — visible in a trace. |
| **Improved** | Same part run twice; second run is better (fewer loops, fewer tool calls, or lower tokens) — two **neatlogs** traces compared. |
| **Trace** | One full agent run in **neatlogs** (one **workflow**). |
| **Job shop** | Small factory customer we describe in **cfo.ai** (not a software dev team). |

**Words we avoid in the pitch (v1):** real CNC, real robot, any 3D part upload, Mixamo, VRoid, Trellis, “AI fixes the motor,” full factory with four machines.

---

## One-line pitch

**An agent that turns an uploaded part spec into G-code, runs a CNC turning sim and 2D viewer until precision passes the program gate, then starts the manufacturing loop with a robotic arm for load and unload — every attempt recorded in neatlogs.**

---

## What we are building (short)

A **simulated mini factory** for a **small job shop**:

1. **Program gate (main):** upload → agent writes/adjusts **G-code** → **validator** → **simulator** → **viewer** → **precision** check → loop until **green** → **approved program**.
2. **Manufacturing loop (secondary):** **approved program** runs on the sim lathe; **robotic arm** loads and unloads; optional injected fault (e.g. arm stop) → agent **recovery** without throwing away the approved G-code.

All of this lives in **our public repo**, built during the hackathon window.

---

## Detailed explanation

### Who it is for

A **job shop** owner with one or two small lathes. They get a drawing or spec from a customer. They need a **safe program** and proof it meets size before they trust the machine — we simulate that proof.

### Phase 1 — Program gate (hero of the demo)

1. **Upload** a **part spec** (JSON numbers or DXF profile).
2. The **agent** generates or edits **G-code** (templates + parameters the agent can change).
3. **Validator** runs first (fast fail: unsafe G-code never hits the sim).
4. **Simulator** runs the **CNC turning** cut in software.
5. **Viewer** shows target vs result (2D).
6. **Precision** module compares result to spec within **tolerance**.
7. If not **green**, the **agent loop** reads the failure reason and tries again (deeper cut, extra pass, different feed, etc.).
8. When **green**, we store an **approved program** and move to phase 2.

This phase is the **substantial task** judges care about: clear input, tool use, verification, iteration, recovery.

### Phase 2 — Manufacturing loop (supporting story)

1. Only runs if **approved program** exists.
2. Sim **lathe** executes that G-code (time-step or instant “cycle done”).
3. **Robotic arm** (sim): pick blank → at machine → unload part → bin.
4. Optional: inject **fault** (over-temp, comm loss) on the arm → agent **recovery** (replan to other arm, pause, clear sim fault) while keeping the same **approved program**.

Robotic arm is **addition**, not the main loop.

### What “agent” means here

Not a chatbot. A **loop** driven by **claude-sonnet-5-5** with **tools**, for example:

- `read_part_spec`
- `write_or_patch_gcode`
- `run_validator`
- `run_simulator`
- `measure_precision`
- `render_viewer` (or viewer auto-updates after sim)
- Phase 2: `get_line_state`, `get_alarms`, `reassign_arm`, `start_cycle`

The model chooses the next tool until **green** or max steps.

### What we prove to judges

| Evidence | How |
|---|---|
| Agent completes a task | Upload → **approved program** → manufacturing **green** |
| Recovers from failure | Bad G-code or arm fault → trace shows retry → success |
| Agent improved | Two traces on same demo part; numbers compared |
| neatlogs | Link(s) to workflows in devlog |
| Entire | Checkpoints on commits; short entire-graph clip optional |
| cfo.ai | Business plan: job shop pricing, token COGS, runway |
| Built in public | #neatHack posts with viewer screenshots and trace metrics |

---

## Sponsor tech — role of each (everyone)

### neatlogs

**Role:** Trust and debug layer for the **agent loop** — not the UI we sell.

| When | What we trace |
|---|---|
| Every **agent loop** run | One **workflow** root (e.g. `cam-program-gate` or `line-run`) |
| Each tool call | Span: validator, simulator, measure, gcode patch, arm replan |
| Failures | Failed validator/sim/precision visible before retry |
| Improvement | Baseline trace vs improved trace (tool count, latency, tokens, cache read) |

**Demo line:** “Every CAM retry and every recovery step is one trace — here is before and after we taught the agent to read measure output first.”

### Entire

**Role:** How **Attention Heads** builds and maintains the repo — linked to commits.

| When | What we use |
|---|---|
| While coding | **Checkpoints** on each commit (`Entire-Checkpoint` trailer) |
| While navigating | **entire-graph** to find validator, sim, agent tools, G-code templates |
| Evidence | Screenshot or quote of graph query in repo / devlog |

**Demo line:** “Entire links our coding sessions to fixes in the CAM pipeline and agent tools.”

### cfo.ai

**Role:** Business plan for the **job shop product** — not the agent’s runtime.

| Topic | Our story |
|---|---|
| **Customer** | Small **job shop** (1–3 machines) |
| **Product** | Agent-assisted **program gate** + optional line sim |
| **Pricing** | e.g. per part program, or monthly per machine |
| **COGS** | Model API (from trace **usage**), hosting, support |
| **Revenue / runway** | From cfo.ai plan — included in submission |

**Demo line:** “Shops pay to reduce scrap and reprogramming time; our COGS scale with agent runs we can measure in neatlogs.”

---

## Our end state (what “done” looks like)

At submission we have:

1. **CLI or single command** to run the demo part end to end (upload → program gate → manufacturing loop).
2. **One golden part spec** in the repo that always demos reliably.
3. **2D viewer** output (image or HTML) judges can see in the video.
4. **At least two neatlogs trace URLs** (improvement + recovery optional third).
5. **devlog.md** evidence table filled where possible.
6. **cfo.ai** plan exported or linked per hackathon instructions.
7. **Video ≤ 3 min:** problem → program gate loop → approved → line + arm → neatlogs → Entire → cfo.ai.

We do **not** need real hardware or a public web app for v1.

---

## One full example (walkthrough)

**Demo part name:** `shaft-50` (fictional customer job).

### Part spec (JSON example — words only)

- Type: simple **turning** job  
- Target outer diameter: **50.0** mm  
- Length: **80.0** mm  
- Tolerance: **±0.1** mm  
- Stock: bar already within range for sim  

(User **uploads** `shaft-50.json` or we pass it as the run goal.)

### Run 1 — Program gate (failure → recovery)

| Step | What happens |
|---|---|
| 1 | Agent reads **part spec**. |
| 2 | Agent writes **G-code** (rough turn only — too aggressive). |
| 3 | **Validator** → **green**. |
| 4 | **Simulator** runs **CNC turning**. |
| 5 | **Viewer** shows profile; **precision** → **fail** (diameter **49.6** mm, outside **tolerance**). |
| 6 | Agent adds finishing pass / adjusts offset. |
| 7 | **Simulator** again; **precision** → **green** (e.g. **49.95** mm). |
| 8 | System saves **approved program** `shaft-50.nc`. |

**neatlogs:** one **workflow** `cam-program-gate` with spans for each tool call; step 5–7 show **recovery** inside the CAM loop.

### Run 2 — Manufacturing loop

| Step | What happens |
|---|---|
| 1 | Agent (or orchestrator) checks **approved program** exists. |
| 2 | **Manufacturing loop** starts: sim lathe runs `shaft-50.nc`. |
| 3 | **Robotic arm** sim: load blank → wait for cycle → unload to bin. |
| 4 | Line state → **green** (“job complete”). |

Optional beat: inject **arm fault** before unload → agent reads **alarms** → replans (second arm or retry) → still **green** without deleting **approved program**.

**neatlogs:** separate **workflow** `line-run` (or same root with phase tag).

### Run 3 — “Improved” (evidence for judges)

Same `shaft-50` spec again with a small agent change (e.g. always **measure** before editing G-code, or prompt caching on).

| Metric | Baseline trace | Improved trace |
|---|---|---|
| CAM iterations to **green** | e.g. 4 | e.g. 2 |
| Tool calls | e.g. 14 | e.g. 8 |
| Input tokens / cache read | logged in **usage** | compare in devlog |

Post the two trace links in **devlog** under **Evidence** and **Measured**.

### cfo.ai (same example)

- Shop charges customer **₹X / $Y** per program.  
- Our fee **₹Z / $W** per **approved program** or monthly.  
- COGS: estimated tokens from traces × runs per month.  
- Runway: from cfo.ai output.

---

## Build order (after kickoff)

1. Validator + simulator + precision + **viewer** (no AI) — must show pass/fail.  
2. Agent + **neatlogs** on program gate only.  
3. Golden **upload** demo + recovery in CAM loop.  
4. **Manufacturing loop** + **robotic arm** sim.  
5. Second trace for **improved**; **cfo.ai**; video script.

---

## Open choices (decide at kickoff, then update this file)

- [ ] Day 1 upload format: **JSON spec only** vs **DXF + JSON**.  
- [ ] Tolerance number for sim (e.g. **±0.1**).  
- [ ] Product name for submission (e.g. Program Gate, LineKeeper).  
- [ ] Inject arm fault in video: yes / no.

---

## Submission checklist (reminder)

- [ ] Public repo, commits in hackathon window  
- [ ] Demo video ≤ 3 min, all three sponsor tools explained  
- [ ] neatlogs trace links in repo  
- [ ] Entire checkpoints present on commits  
- [ ] cfo.ai business plan  
- [ ] #neatHack build-in-public links in devlog  
- [ ] X quote-post submission Monday 7:00–11:55 PM IST  
