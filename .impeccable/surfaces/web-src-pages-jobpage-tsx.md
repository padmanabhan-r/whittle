---
version: 1
slug: "web-src-pages-jobpage-tsx"
primary_target: "web/src/pages/JobPage.tsx"
related_targets: ["web/src/pages/Start.tsx"]
---

# The app (`/app`, `/app/jobs/:id`)

Scope: the start screen and the job screen. Mode: Operate. Task: start a job, watch the baseline, choose findings, watch each fix checked, read the result and take the patch. One user decision: which findings to fix. States that matter: baseline running, awaiting selection, a fix reverted, done, failed, API unreachable, job lost after a restart.

Chosen structure: "The ledger" HTML sketch `.impeccable/mocks/decision/app-ledger.html` (user's pick from three; surface seed 6b87195d). Code-led.

## Direction contract

THESIS: A working ledger of every model call, in the receipt's voice. Refuses the hero-metric dashboard of equal cards.

OWN-WORLD: The landing page's palette and faces. Blue is the shell: a solid blue side rail. Tables are set in mono with tabular figures, dashed total rules and a highlighted total.

STORY: Know where the job is, see the money move, decide once, watch fixes pass or get reverted, leave with proof.

FIRST VIEWPORT: Blue rail (job sections with live dots) left; title, state and actions on top; four figures with cost per run leading; one table for the current section; an inspector on the right with Agent, Finding and Console tabs.

FORM: Standard web controls throughout. Signature move: a call removed by a kept fix is struck through in red with the finding named beside it, as on the receipt; the cost counts down like a meter.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Unresolved: only the mock backend exists; every figure is invented and each page shows a "mock data" tag.
