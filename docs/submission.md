# Submission checklist

neatHack, 10 to 12 October 2026. Team Attention Heads (Padmanabhan and
Sethuraman). Project Whittle AI. Tick a box only when the thing is done and
checked; the devlog's evidence table must agree with this file.

Times are IST. The rules are in `neathack-rules.md`; the live site wins when
the two disagree.

## Deadlines

- [ ] **Code freeze: Monday 12 October, 12:30 PM.** The site calls it a
      48-hour build on 10 and 11 October, so no product code after this. Docs,
      the video and the posts may continue.
- [ ] **Submission window: Monday 12 October, 7:00 PM to 11:55 PM.** The close
      is "planned"; the final cutoff is announced on Discord. Late entries are
      not judged. Aim to post by 8:00 PM.
- [ ] **Watch Discord on Monday** for the official neatlogs post to quote and
      for the cutoff time. The page still says "Submissions opening soon".

## Before Monday

Padmanabhan:

- [x] Watch `video/demo/final/whittle-ai-demo-paddy.mp4` once, end to end,
      with sound and headphones. Only a person can judge the music, the sound
      effects (are the pops and ticks audible, does the typing read as typing)
      and the end card in motion. It is 2:57, under the three-minute limit, and
      has a section each on neatlogs, Entire and cfo.ai.
- [x] Uploaded 12 Oct, public: https://youtu.be/WZTi2TRm-IY (2:57, with the neatlogs section rebuilt around the before and after traces; title, description, chapters and thumbnail set; subtitles not added). It replaces the 11 Oct upload, which is now private. Upload the video to YouTube, public or unlisted. X cuts standard
      accounts off at 2:20 for native video, so the post links to YouTube.
      Put the link in the devlog header (`Demo`) and the README.
- [x] neatlogs trace links: format confirmed (`https://app.neatlogs.com/traces/<id>`),
      a before and an after link in the devlog evidence table (11 Oct).
- [x] Entire evidence: `docs/evidence/entire.md` with real checkpoint, search,
      impact and stats output (11 Oct).
- [ ] One or two more build posts tagged #neatHack. Candidates: the agent
      building its own entry point and recovering from a failed run
      (`job_2f4aac670180`), and the launch on whittleai.site. Log each in the
      devlog under **Shared:**.
- [x] Devlog, evidence files, README evidence section, license: committed 11 Oct.
- [ ] Run `/devlog` again after the posts and the deployment, commit, push.

Sethuraman:

- [x] Deploy on **whittleai.site** with HTTPS, per `deploy.md` (the same
      steps are in the PDF): Elastic IP, GoDaddy A records, Caddy, the UI
      built with `VITE_API_URL=""`, the API on localhost only.
- [x] Check `https://whittleai.site/health` answers, the padlock shows, and a
      scan of a public repository streams its events.
- [x] Tell Padmanabhan when it is up, so the README screenshot and the devlog
      header (`Live app`, `Hosting`, `Status`) can be updated.

Either:

- [ ] Retake the README terminal screenshot (`assets/screens/cli-fix.jpg`)
      against the live site, so the report link shows the real address.
- [ ] Decide whether the CLI defaults point at whittleai.site. If yes, bump
      `cli/package.json`, `npm publish` from an interactive terminal (2FA),
      and note the version in the devlog. If no, leave 0.1.0 as it is. Either
      way the copy on the registry says UNLICENSED and ships no license file,
      which grants nothing; the next publish carries the FSL text.
- [x] License: Functional Source License 1.1 (FSL-1.1-MIT) for everything,
      the command-line tool included (`LICENSE.md`, `cli/LICENSE.md`). Both names
      as holders (11 Oct).
- [x] Sethuraman confirms the license, as co-owner, before the repository is public (11 Oct).
- [x] A longer-lived model key for the live site, minted by Padmanabhan and handed to Sethuraman (11 Oct). Still to do: he installs it and restarts; it must last past 16 October, when winners are announced.

## Monday, before posting

- [x] **Make the repository public** (done 11 Oct, 9:45 PM; fork pull request workflows need approval, because the deploy runner is the production server):
      `gh repo edit padmanabhan-r/whittle --visibility public`.
      Then open https://github.com/padmanabhan-r/whittle logged out and check
      the README renders, the banner shows, and the first commit reads
      10 October 12:37 IST.
- [x] Check nothing secret is in the repository (pushed history and all Actions logs scanned, 11 Oct): `.env.local` is ignored,
      `.env.example` carries no values, no key in `devlog.md` or the docs.
- [ ] Final devlog update: `Repo` public, `Live app`, `Demo`, `Status`
      `deployed`, every evidence row with a link, the submission table below
      marked done.
- [ ] Last commit and push before 12:30 PM for code; docs may follow.

## The post

A public quote post, from Padmanabhan's X account, of the official neatlogs
submission post. Keep the quoted post attached; opening the draft is not
submitting. One post per team.

It must contain, in this order or any other:

- [ ] Team: **Attention Heads**
- [ ] Names: Padmanabhan and Sethuraman (handles if they fit)
- [ ] Project: **Whittle AI**, one line on what it does: cuts what an AI
      agent wastes and proves the saving with before and after traces
- [ ] Public repository: https://github.com/padmanabhan-r/whittle
- [ ] Demo: the YouTube link, and the live app https://whittleai.site
- [ ] #neatHack, and the three tools named: @neatlogs, Entire, cfo.ai
- [ ] One measured number, from the devlog: the sample agent's cost per run
      fell 68.2%, answers unchanged

After posting:

- [ ] Copy the post's link into `devlog.md` under `## Submission` and push.
- [ ] Reply to the post with the four build posts, so the thread shows the
      work in public.
- [ ] Keep an eye on replies: neatlogs and cfo.ai engage with the first 50
      quote posts.

## Evidence the judges expect, and where ours is

| Claim | Where | State |
|---|---|---|
| The agent improved | `devlog.md` evidence table: $0.0300 to $0.0095 per run, 68.2% lower, answers 1.00 on both sides (`job_3e1b3cc39865`) | have |
| Used neatlogs | trace links in `devlog.md`; screenshots in the README and `docs/evidence/` | have |
| Used Entire | `docs/evidence/entire.md`: checkpoint list, search, impact, stats. The checkpoints themselves stay on the build machine (they are full session transcripts); show one on request | have |
| Used cfo.ai | `business/plan.md` and `business/cfo-ai-plan.jpg`, shown in the README | have |
| Recovers from failures | fixes reverted when not cheaper (`job_1a5e1ef6b80e`); scan entry point failed, rewritten, verified (`job_2f4aac670180`) | have |
| Built in public | five posts tagged #neatHack, links in `devlog.md` | have, add more |
| Written during the hackathon | first commit 10 Oct 12:37 IST, seven minutes after the start; the repository is public | have |

## Submission table

| Item | Status |
|---|---|
| Team registered on Luma, both under Attention Heads | done |
| Web check-in | done |
| cfo.ai signup, subscription cancelled after | done |
| Public repository link | done: https://github.com/padmanabhan-r/whittle, public since 11 Oct, 9:45 PM |
| Live app | done: https://whittleai.site, live with a Let's Encrypt certificate since 11 Oct, 7:30 PM; a full scan run through it on 11 Oct (`job_5ff5ad24dcf3`, verified) |
| Demo video under three minutes, all three tools | done: https://youtu.be/WZTi2TRm-IY, 2:57, public, uploaded 12 Oct |
| Business plan in the repository | done |
| Quote post on X | done: https://x.com/limb404/status/2109643103309287745, 12 Oct, 7:21 PM IST |
| Submission form | done: submitted 12 Oct, about 7:45 PM IST |
