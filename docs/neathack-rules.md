# neatHack rules

Source: https://neatlogs.com/hackathon and the organisers' Luma messages, read on 9 October 2026.

Checked again against the live page on 11 October 2026, 9:17 PM IST: nothing below differs from it.

## The challenge

- One track only: **Build an Agent That Works (Literally)**.
- Build an AI agent, or a team of agents, that completes a substantial task from start to finish.
- Give it a goal, tools and an environment, and let each result guide its next action.
- All projects compete for the same prizes.
- The example tasks on the site are ideas, not separate tracks, and you don't have to build one of them.

### Focus areas

- Planning: break a goal into actionable steps.
- Tool use: choose tools, supply inputs and handle responses.
- State: retain state across steps, runs and failures.
- Context: bring in relevant information and leave out the rest.
- Execution: keep long tasks running to completion.
- Recovery: handle failures and unexpected results.
- Verification: check that results are correct.
- Iteration: use each result to choose the next step.

### Example tasks (optional)

- Fix a GitHub issue: investigate, write and test a fix, propose it.
- Answer a research question with sources, deciding which source to trust when they disagree.
- Watch a running system, find the cause of a problem and take an action to fix it.
- Several worker agents solve parts of a task and a coordinator combines the results.
- Work on a long task while the environment keeps changing.

## Mandatory requirements

- **Use neatlogs, Entire and cfo.ai.** The site: "Your project must use neatlogs, Entire and cfo.ai. Use neatlogs and Entire to build and improve your agent, and cfo.ai to plan its business."
  - neatlogs: trace every agent run (model and tool calls, state changes, retries, failures, latency, tokens, cost).
  - Entire: repository context for your coding agent (Checkpoints and entire-graph).
  - cfo.ai: plan the agent's pricing, costs, revenue and runway, and include the business plan in the submission. Signup at https://cfo.ai/neathacks needs a card; cancel the subscription straight after.
- **All code written during the hackathon**, between the start at 12:30 PM IST on Saturday 10 October and the deadline on 12 October. The site calls it a 48-hour hackathon.
- Finished or half-built projects cannot be brought in. Planning the idea in advance is allowed.
- **Public repository** with commits dated during the hackathon, so judges can verify.
- Use neatlogs throughout development, not just at the end.

## Teams

- Solo or a team of 1 to 4 people.
- Every member registers on Luma separately with the same team name.
- Each person can join only one team.
- Each team submits one project.
- Complete the web check-in to confirm your team: https://neatlogs.com/hackathon/check-in

## Submission

- **Window:** Monday 12 October 2026, 7:00 PM to 11:55 PM IST. The site calls the close "planned" and says the final cutoff is announced on Discord (checked 11 October).
- **Late submissions will not be judged.**
- Submit as a public **quote post of the official neatlogs submission post on X**.
- The post must include: team, name, project, public repository link, demo link.
- Announced by the organisers on X on 12 October: the quote post must include the demo video and tag @neatlogs, @EntireHQ and @arithecfo, which is how their systems detect a submission. **A second step is also required:** fill out the submission form, whose link the organisers share. The form alone does not count, and neither does the post alone.
- Bonus points for a demo video that clearly explains the problem and the solution.
- Keep the official post attached, then publish. Opening the draft alone does not count as submitting.
- **Demo video: three minutes or less.**
- The video must explain the agent and the use of neatlogs, Entire and cfo.ai.
- Include supporting evidence in the repository.
- neatlogs and cfo.ai will engage with the first 50 quote posts.

## Judging

| Category | Weight | What it means |
|---|---|---|
| The agent | 30% | How well it handles a substantial task from start to finish |
| Use of neatlogs, Entire and cfo.ai | 25% | How effectively all three were used to build, improve and plan a business around the agent |
| Demo video | 20% | How clearly it explains the agent and the use of neatlogs, Entire and cfo.ai |
| Building in public | 15% | How you shared the project while building it |
| Usefulness and originality | 10% | Whether it solves a real problem in a new way |

- Each category is scored out of 100, then weighted to a final score out of 100.
- The judges' decision is final.

### Evidence judges expect

| Claim | Evidence |
|---|---|
| The agent improved | A run before your change and a run after, e.g. two neatlogs traces, with the numbers compared |
| You used neatlogs | Links to neatlogs traces from the project, or screenshots |
| You used Entire | Checkpoints or entire-graph output from the repository |
| You used cfo.ai | A business plan covering the agent's pricing, costs, revenue and runway |
| The agent recovers from failures | A run where an action failed, showing what the agent did next |
| You built in public | Links to what you shared during the hackathon, tagged #neatHack |
| You wrote the code during the hackathon | A public repository with commits dated during the hackathon |

## Community Winner (separate award)

- Goes to the project with the strongest genuine community interest during the hackathon.
- Looks at product and demo quality, launch and content quality, shares, discussion and genuine engagement.
- Follower count does not decide it.
- The project must still use both neatlogs and Entire, but tool usage is not scored for this award.
- Can be won alongside a top-three placement.
- Bought likes or bot activity disqualifies the team.

## Conduct

- Be respectful in Discord and all event spaces.
- Harassment, spam or plagiarism results in removal.

## Schedule (IST)

| When | What |
|---|---|
| Sat 10 Oct, 9:00 AM | Kickoff call |
| Sat 10 Oct, 12:30 PM | Hackathon begins |
| Sat 10 and Sun 11 Oct | Workshops and office hours |
| Mon 12 Oct, 5:00 to 6:00 PM | Closing call |
| Mon 12 Oct, 7:00 to 11:55 PM | Submissions |
| Fri 16 Oct | Winners announced |

## Prizes

| Place | Cash | Dodo Payments credits |
|---|---|---|
| 1st | $2,000 | $5,000 |
| 2nd | $1,000 | $3,000 |
| 3rd | $500 | $1,000 |
| Community Winner | $500 | none |

- Each winner also gets 3 months of neatlogs Pro.

## Free credits

- AWS credits: one $25 allowance per team, first 350 teams to complete web check-in (the site said 200 on 9 October; 350 on 11 October). Bedrock is not included.
- LiteLLM: one shared $20 model budget per checked-in team (Nova and Claude through one OpenAI-compatible key), sent to the team leader's check-in email.
- Crustdata: 5,000 credits for everyone participating.

## Not published yet

- The official X post to quote for submission (still "Submissions opening soon" on 11 October, 9:17 PM IST).
- The full workshop schedule.
- How to redeem the AWS and Crustdata credits.

## Links

- Hackathon page: https://neatlogs.com/hackathon
- Web check-in: https://neatlogs.com/hackathon/check-in
- Discord: https://neatlogs.com/discord
- neatlogs docs: https://docs.neatlogs.com/docs
- Entire: https://entire.io
- Hackathon skill: https://neatlogs.com/hackathon/skill
