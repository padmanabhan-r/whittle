# For the judges

One row per judging criterion, each pointing at something you can open.

| Criterion | Where to look |
|---|---|
| The agent | Whittle's own agent scans a repository, works out how to run it, then fixes waste one patch at a time: patch, rerun, score, keep or revert. On the sample research agent, job `job_3e1b3cc39865`: $0.0300 a run down to $0.0095, 68.2% lower, five fixes kept, answer score 1.00 on both sides. Recovery on real runs: a fix reverted because its rerun was not cheaper (`job_1a5e1ef6b80e`), and a scan whose first entry point failed in the sandbox, was read, rewritten and run again (`job_2f4aac670180`). See [Real runs](../README.md#real-runs) and the [devlog's evidence table](../devlog.md#evidence). |
| neatlogs, Entire, cfo.ai | **neatlogs:** every run is one trace; [the before and after pair for one task](evidence/neatlogs.md), with screenshots and numbers. **Entire:** [checkpoints and real code graph output](evidence/entire.md); the graph is called at runtime to find the line to fix. **cfo.ai:** [the business plan](../business/plan.md), built from the cost per job we measured. |
| Demo video | [youtu.be/WZTi2TRm-IY](https://youtu.be/WZTi2TRm-IY), 2:57. neatlogs at 1:47, Entire at 2:19, cfo.ai at 2:32. |
| Building in public | Seven posts tagged #neatHack: [1](https://x.com/limb404/status/2109143046889898043), [2](https://x.com/limb404/status/2109159510082482614), [3](https://x.com/limb404/status/2109201036741423288), [4](https://x.com/limb404/status/2109224759393468849), [5](https://x.com/limb404/status/2109304204611461438), [6](https://x.com/limb404/status/2109603952513921380), [7](https://x.com/limb404/status/2109609814318023118). [The devlog](../devlog.md) records every session, including what failed. |
| Usefulness and originality | Try it with no setup: paste a public repository at [whittleai.site](https://whittleai.site), or run `npx whittle-ai` on your own machine. |
