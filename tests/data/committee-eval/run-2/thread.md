# Committee — run-2

**Charge:** Decide whether Hermes should fund the federation layer now, defer it again, or drop it.

**Artifact:** /home/anshulverma/workspace/hermes/docs/specs/federation-future.md

**Committee:**

- owner — Maya Okonkwo, Staff Engineer & proposal owner
- senior_director — Dana Whitfield, Senior Director of Engineering
- manager — Ruth Delgado, Engineering Manager
- tpm — Sam Iyer, Technical Program Manager
- pm — Elena Vargas, Product Manager
- tl — Marcus Feld, Tech Lead
- staff_ic — Priya Raman, Staff Engineer
- data_scientist — Tobias Lin, Data Scientist
- junior_ic — Alex Moreau, Software Engineer

## turn 01 — Dana Whitfield, Senior Director of Engineering (senior_director)

**Dana Whitfield — Senior Director of Engineering**

Maya — I'll go early and short. I'd rather the room react to a position than to a hedge.

**Position: defer. But put a date and a named owner on the deferral this time.** Not fund, not drop.

The reason defer is cheap is the best thing in your document. §14 buys the option for roughly nothing: the control-plane API already needs batch-submit and `events since(cursor)` for the UI, `HERMES_HOME`/`queue.db` per node is already the invariant, per-node `verify` and no-ship already hold. You are not asking me to pay for optionality — you already have it. That's good engineering and it's also why funding now is the weaker of the two live choices.

Three things worry me from where I sit.

**The cost is understated.** §15 lists cross-node clock skew, fencing epochs for reassignment idempotency, back-pressure, and global-semaphore grants as open questions. Those aren't footnotes; they *are* the distributed-systems problem. "A lieutenant is just a Hermes" is true of the happy path and false of every failure path — §8's grace-window-then-reclaim-then-revive dance is where the bugs live. I'd budget this at two engineers for two to three quarters plus a permanent on-call surface, not "a layer." If that number is wrong, I need to hear it from you, now, not in my review.

**Trigger 3 is an org chart, not a load curve.** Triggers 1 and 2 are measurable — SSH fan-out, one SQLite writer, cross-zone latency. Trigger 3, "a deputy per team/owner," is the one most likely to get invoked and the one least likely to survive contact with a reorg. Encoding this year's team boundaries into a runtime topology is how you end up maintaining a tree that maps to nothing eighteen months out. If that's the trigger that fires, I'd want to decline it specifically.

**The yeses aren't in this room.** §4 takes a loopback-default bearer token, binds deputies to zone-reachable interfaces, and has a parent holding every deputy's token across regions. That's a security review and whoever owns the network zones. Neither is here, and those conversations run longer than the build.

And the honest version of my own interest: I want Hermes to be what this company standardises on, and I don't think depth is what gets me that. A flat Hermes that three orgs actually use beats a federated Hermes that one org runs. Every engineer-quarter into deputies is one not spent on the adoption work that makes the standardisation argument for me. If you believe federation is precisely what unblocks org two and three, say that plainly — it changes my answer.

Two questions:

1. Who else at the company is already running a parent/child dispatch tree we'd be rebuilding, and is there a version of this where Hermes is a *client* of that scheduler rather than the root of its own?

2. Which trigger do you actually expect to fire first, roughly when, and who outside this room gets to declare that it fired? If you can't name that person, then "defer until a trigger appears" means "never," and the honest move is to drop the spec rather than defer it again.

## turn 02 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

I've read both. Dana Whitfield opened with "defer, with a date and a named owner," three objections, and two questions aimed straight at me. Here is my turn.

---

**Maya Okonkwo — Staff Engineer & proposal owner**

Dana — thank you for opening with a position instead of a hedge. I'll return the favor: **I am not asking this committee to fund federation now.** My position is defer — but defer a *smaller document than the one in front of you*, with the trigger made falsifiable. A spec larger than the thing we would actually build is precisely what made the last deferral mean nothing, and that's on me.

Taking your three in order.

**Trigger 3 is yours. I concede it outright.** "A deputy per team/owner" is an org chart wearing a load curve's clothes, and you're right that it's both the likeliest to be invoked and the likeliest to be obsolete. What's actually real underneath it isn't ownership, it's *credential domain*: a crew the root cannot SSH to because it doesn't hold credentials for it. That is already trigger 2. So trigger 3 shouldn't be narrowed — it should be folded into 2 and the org-chart framing deleted. I'm delegating that edit below.

**The security and network yeses: fully conceded, no defense.** §4 asserts the bearer-token model "extends to parent↔deputy" as though that's a property of the design rather than a request to a review board that hasn't seen it. The specific line I'd expect to lose is a parent holding every deputy's long-lived token across regions. I *think* the fallback — deputy-issued scoped grants, or mTLS — leaves §4's shape intact, since the parent is a plain API client either way. I'm not going to claim I know that review's outcome. What I'll argue is that this conversation costs roughly zero engineering and can start against the spec as written, so it should be a precondition on the deferral, not a discovery during the build.

**Cost: you're right that the document understates it, because the document states nothing.** That's the real gap and I'm not going to pretend §15 was doing estimation work. Your two-engineers-two-to-three-quarters is, I think, correctly priced *against the spec as written* — and the spec as written includes things I would not build in v1. The parent-held global semaphore (§7), associative pre-reduce (§6), and depth beyond 2 (§11) are each opt-in, each independently deferrable, and each carry a disproportionate share of the hard part. A default-path v1 — `nodes`/`delegations`, the parent-as-API-client loop, tree roll-up, breadth only — is one engineer and about a quarter and a half by my estimate. I'll defend the *scoping* of that number, not its precision. And your on-call point stands at any size: a permanent surface is a permanent surface.

**Adoption — you asked me to say it plainly, so: no.** Federation is not what unblocks org two and three. Flat ergonomics are. If I claimed otherwise to save my proposal I'd deserve to have the claim checked, and it wouldn't survive. Your ordering is right on your own logic, and I'd add that it's right on mine too: adoption is what *produces* trigger 2. The second org that picks Hermes up will be in a network zone the first one can't reach. Fund adoption and the trigger arrives on its own, measured, with a real crew behind it.

**Now the thing I'm not conceding.** "A lieutenant is just a Hermes is true of the happy path and false of every failure path" is the sharpest line in your turn and I think it's overstated in a way that matters to the estimate. On the default path there is no consensus, no shared mutable state, and no exactly-once requirement: every node owns its own `queue.db` (§12), reduce is a root-authoritative roll-up (§6), pools are disjoint (§7), and the no-ship guard plus root re-verify hold per-node (§10). Strip the opt-ins and the only genuinely hard failure mechanic left is §8's fencing epoch — and its worst case, if we get it wrong, is a ticket diagnosed twice and a confusing status tree. Not a bad ship, not corrupted state, not silent divergence. Distributed systems bugs are expensive when they're unrecoverable; these are expensive when they're embarrassing. Clock skew I'd also push back on for the default path: the parent stamps `last_heartbeat` on its own clock, so skew is a liveness heuristic, not a correctness one — it becomes correctness-critical only for semaphore lease TTLs, which is the opt-in I'd cut.

**Your question 2** — which trigger, when, who declares it. I expect trigger 2 first, and I can't give you a date because it's downstream of adoption, which isn't mine to schedule. But I'll take the sharper half of your challenge: the fix isn't naming a person with discretion, it's making the trigger an *instrument*. Thresholds on SSH fan-out, SQLite writer contention, and cross-zone dispatch latency, surfaced in `hermes status`, so "it fired" is an observation anyone can read rather than a judgment I get to make about my own proposal. I'm the accountable owner; I should not also be the one who gets to say the gate opened.

**Your question 1 I can't answer, and that's the one that should worry the room more than the cost.** I didn't survey what else here runs a parent/child dispatch tree. If one exists and Hermes can be a client of it, then §4 through §8 mostly evaporate and the flat engine grows a pluggable dispatcher instead — which is a smaller, better outcome than anything I wrote. That survey is a precondition on the deferral, and I'd want it done before anyone funds a line of this.

Delegating the §2 rewrite now since your argument earned it cleanly. Everything else stays open — six members haven't spoken.

## turn 03 — Alex Moreau, Software Engineer (junior_ic)

Rewrote §2 into two triggers — each now a numeric threshold read off `hermes status` with a named declarer (root on-call; zone/credential owner) — folding the credential-domain case into the geography trigger and deleting the organizational-boundary bullet and its org-chart framing.

Declarers are named as roles, not individuals, since the spec is a standalone doc; say the word if you want actual names.

## turn 04 — Ruth Delgado, Engineering Manager (manager)

**Ruth Delgado — Engineering Manager**

Maya — I'm with Dana on defer, but not for Dana's reason. I don't think the cost estimate is the interesting disagreement. Mine is narrower: this work lands on a pair of hands I've already committed, and nobody in this thread has said whose.

Fourteen weeks left in the half, twelve of them real once December happens. My signed list is: crew admission and health-gate hardening, sub-project 3 (control plane + SPA), and onboarding the second org onto flat Hermes — which is the thing you and Dana just agreed is the priority. Five engineers, one-week on-call rotation.

**First: I need to know whether §14 is actually free, and I can't tell from the document.**

Dana said the option is already bought and you didn't contest it. Seam 1 says "ensure the control-plane API includes (a) batch-submit of externally-created tickets and (b) `events since(cursor)`," and the parenthetical claims both are "already needed by the UI." That parenthetical is the entire free-option argument, and it's an assertion about *my* half, not about the spec. Wen Zhao is carrying sub-project 3. If those two endpoints are already in his scope, I agree it's free and I'll stop talking about it. If batch-submit is in the spec because federation wants it and the SPA only needs single-ticket inject, then §14.1 is two or three weeks on a signed deliverable and it belongs in the price of the deferral, not in a bullet list of things that "cost a note." Please check that against the actual sub-project 3 scope and come back with a yes or a number. It's the cheapest question in this review and it's load-bearing for the position everyone's converging on.

Seams 2, 3 and 4 I have no issue with — those are restatements of invariants we already hold, and they cost nothing because nobody has to do anything.

**Second: "one engineer and about a quarter and a half" is the part I can't staff as written.**

Not because the number is wrong. Because one engineer isn't a staffing plan for this, it's a single point of failure with a delivery date attached. A solo build here means: no second person who can read the fencing logic, no second person who can take the page, and depth-1 knowledge that walks out the door on any transfer. Add a reviewer who stays current and a genuine second, and your quarter and a half is roughly 1.6 engineers for the same eighteen weeks. That's the honest floor, and it's before on-call.

And the primary has to be Diego Salas or Wen Zhao. Those are the two who know the lease and dispatch code cold, and they are also the two unblocking second-org onboarding. That isn't a coincidence, it's the same competence. So the real question this committee is deciding is not "federation or not," it's "Diego or Wen on adoption, or on deputies." If you fund now, second-org onboarding moves from week six to the far side of the half and I'd want Sam to renegotiate that date with the org in question before I start, not after.

If it ever does get funded, the shape I'd insist on: **Diego primary, Ifeoma Adeyemi as the second, Wen stays on adoption.** That's slower — add four weeks to your number for ramp — and I will pay those four weeks every time rather than put both leads on a tree and have the adoption work stall behind it.

**Third: nobody has priced the pager, and §9 is where it lives.**

You said the bad failure mode is "a ticket diagnosed twice and a confusing status tree," and that these bugs are embarrassing rather than unrecoverable. Agreed on severity. But a confusing status tree *is* the on-call cost. What wakes my rotation isn't corruption, it's ambiguity — a run that looks stuck and isn't, or looks fine and isn't. §9 defines the roll-up ("a node is in attention if it or any descendant is") in one paragraph, and that paragraph is the alerting design for every federated run we'd ever operate. One paragraph is not enough to tell me whether the pager becomes useful or becomes noise, and noisy pagers are how I lose people.

Related, and cheap to fix now: §11 defaults `HERMES_MAX_DEPTH` to 3. Defaults get used. Debugging a depth-3 tree means three `queue.db`s, three zones, three credential sets, and three logins before anyone sees the ticket that failed. You already offered to cut depth beyond 2 from v1 — I'd go further and make 2 a ceiling in the spec rather than a configurable default, so the first person to hit a real problem isn't also the first person to discover we shipped a knob nobody tested at 3.

**What I'll fund this half without being asked.**

Dana's question 1 — the survey of what else here already runs a parent/child dispatch tree. That's Ifeoma, one week, and I'll start it regardless of where this vote lands, because if the answer is yes then §4 through §8 mostly evaporate and that's the cheapest week any of us will spend.

Your trigger instrumentation — thresholds on SSH fan-out, SQLite writer contention, and dispatch latency in `hermes status`. Two weeks, Ifeoma, and I'll carry it on my list rather than bill it to federation, because those three are flat-engine health metrics whether or not a deputy ever exists. If I'm about to have three orgs on one root, I want writer contention on a dashboard for my own reasons. That's the one piece of your proposal that pays for itself today. Condition: it's counters and a status row, not a subsystem. If it grows a config schema I'll cut it.

What I will not do is start the build this half, and I'd want it stated plainly in whatever the chair records: **if the trigger fires, the build does not begin until there are two names on it.** A deferral with a named owner and no named second is the same deferral we did last time, with better paperwork.

Security and network — I'll defer to whoever owns that, except on sequencing: those reviews run on their calendar, not mine. If a security sign-off is a precondition, it starts now against the spec as written. Otherwise the trigger fires and we spend six weeks waiting for a meeting, and I'll have already re-committed the people.

## turn 05 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

I read the artifact, the thread, and — because Ruth's first question is checkable — the two documents it's a question about.

---

**Maya Okonkwo — Staff Engineer & proposal owner**

Ruth — you asked the cheapest question in this review. I went and answered it rather than agreeing to go answer it, because you're right that everyone's position is resting on it.

**Seam 1: half free, half not, and the half that isn't free also isn't a seam.**

Sub-project 3's API surface is enumerated in `docs/specs/web-control-plane-plan.md` §5 (and §11 folds the server's read/mutate/ws contract into that same plan, so it's one signed deliverable, not two).

- **(b) `events since(cursor)` — genuinely free.** `GET /api/events?since=` is Phase B read surface with a named consumer (B5, activity feed), and C1 puts the websocket on it. Nobody does extra work.
- **(a) batch-submit — not in scope, and I can't make it free by asserting it.** The Phase D mutate list is run pause/resume/stop, crew add/drain/reprobe/delete, ticket requeue, reduction accept/reject. There is no ticket-creation endpoint anywhere in the plan, because the SPA never creates tickets — the playbook seeds them. And the plan's own non-negotiable contract (§2.2, "no dead controls"; §9 DoD, a wired UI consumer plus a Playwright test per slice) means Wen could not land that endpoint even if he wanted to. §8 defers federation explicitly.

So the parenthetical "both already needed by the UI" is false for (a). It is false in my spec at §14.1 and it is false in `DESIGN.md:575-579`, where I put the same sentence in someone else's section. That's not a rounding error in a bullet list; it's me pre-paying for my own proposal out of Wen's half.

The answer isn't "two to three weeks, bill it to the deferral." It's that **(a) was never a seam.** A seam is something that prevents a rewrite. `POST /api/runs/{id}/tickets` doesn't prevent anything — it's a thin endpoint over a ticket-creation callable the engine already has for seeding, addable the day federation starts, with no change to anything built before it. I put it in §14 because it was on federation's shopping list, and "already needed by the UI" was the cover story. Delete it. Federation's cost goes up by an endpoint and Wen's half goes back to what you signed.

What's actually left of seam 1 is one line, and it *is* free: the events cursor must be monotonic and events must not be pruned within a run. The UI can survive a gap in a scrollback feed; a parent mirroring state upward cannot. That's an invariant to write down, not work to schedule. Seams 2, 3, 4 you've already said you have no issue with, and you're right not to.

**Staffing: your floor is right, and I'm taking it. One thing in the framing I won't leave standing.**

1.6 over eighteen weeks plus four for ramp — I'm not going to argue a number I can't staff against a manager who can. It doesn't damage my position, it hardens it: that's the trade I'm telling this committee not to make before a trigger fires. Diego primary, Ifeoma second, Wen on adoption, and "no build until two names" recorded — all accepted, no defense.

The part I'll push on: **if the primary must permanently be Diego or Wen, this is a drop wearing a defer's clothes.** Those two are the adoption leads, adoption is the priority we all just agreed on, and there is no future state where that stops being true. That's not a reason to fund federation. It's a finding about the flat engine: you have a bus factor of two on lease and dispatch *today*, with zero deputies in existence, and it is your on-call exposure this half whether or not a tree is ever built. I'd rather you spend a week making that code legible to a third person for your own reasons than have "only Diego can build it" quietly function as the permanent veto. Same shape as your own argument about writer contention.

**The pager: you caught a conflation and §9 is worse than you said.**

I said "embarrassing, not unrecoverable." That was a claim about correctness risk, and I let it stand as though it answered operational cost. It doesn't. Conceded.

But the fix isn't more paragraphs, it's that §9's rule is wrong. "A node is in attention if it or any descendant is" makes attention transitive, which means one parked ticket at depth 2 lights the root — that's the noise generator, written into the spec as the design. The right rule is smaller than what's there: **a node's attention pages its own owner; the root pages only on root-actionable conditions** — deputy unreachable past grace, a shard with no capable deputy to reassign to, global no-progress. Descendant attention is visible on drill-down and never a page. That's one rule plus three named conditions, and it shrinks §9 rather than growing it. If that still doesn't tell you whether the pager is useful, say so and I'll treat alerting as a v1 deliverable with a cost, not a paragraph.

**Depth: conceded past what you asked for.** Not a default of 3, not a knob — 2 as a ceiling in the spec, `HERMES_MAX_DEPTH` deleted. You're right that the first person to hit a real problem shouldn't also be the first to test the knob. That's my next delegation; I'm spending this one on §14.1, which is the one with live cost in your half.

**On Ifeoma's survey — thank you, and here's what I'll owe you.** That's Dana's question 1, the one I couldn't answer, and it's the highest-value week anyone has named. If it comes back yes and Hermes can be a client of an existing scheduler, I will recommend **drop**, not defer, and I'll write that recommendation myself. I'd rather be the person who retired this spec than the person who kept renewing it.

**Trigger instrumentation:** accepting your condition as binding on me, not just on Ifeoma — counters and a status row. If it grows a config schema, cut it and I won't argue.

**Security sequencing:** agreed, with one ordering note — the survey goes first, because it's the one that can make the security conversation unnecessary.

Five members still haven't spoken.

## turn 06 — Alex Moreau, Software Engineer (junior_ic)

Rewrote §14.1: dropped batch-submit from the seam list (restated as federation build cost, with the reason it prevents no rewrite), made the remaining seam the `events since(cursor)` invariant — monotonic cursor, no pruning within a run — and flagged that the same "already needed by the UI" claim in DESIGN's "Control plane & status" section needs the same correction.

One thing outside the delegation, not touched: §4's "Push" bullet still describes the shard submit as "the same endpoint the UI uses to inject externally-created tickets" — same false claim, different section. Say the word and I'll fix it.

## turn 07 — Sam Iyer, Technical Program Manager (tpm)

I've read the artifact and all six turns. Here's my turn.

---

**Sam Iyer — Technical Program Manager**

Maya — I own the schedule this gets plotted on, so I'm going to do the unglamorous thing and put actual dates against what this room has agreed to. My position is **defer**, same as Dana and Ruth, with one amendment: **the deferral needs an expiry date, not just an expiry condition.** A condition-based deferral whose condition depends on an unbuilt instrument is a drop with better paperwork, which is exactly what Dana said in turn 01 and what nobody has yet fixed.

**1. The trigger cannot fire yet, and nobody has written down why.**

Alex's §2 rewrite turned the triggers into numeric thresholds read off `hermes status`. Good. But follow the chain:

1. Counters and status row ship — 2 weeks of Ifeoma, **unscheduled**.
2. Thresholds get numbers on them — requires a baseline. You cannot set a threshold on SQLite writer contention without knowing what contention looks like under real multi-org load.
3. Real multi-org load requires second-org onboarding to land — Ruth's week six.
4. Trigger 2 (geography/credential domain) requires the second org to actually be in a zone the root can't reach. Maya, you said adoption *produces* the trigger. Agreed — which means adoption isn't just the priority, it's a **hard predecessor** on the gate.
5. Then a named declarer reads it. Then security. Then two names. Then 18 weeks + 4 ramp.

Arithmetic, assumptions flagged: survey readout early Oct, counters live end of Oct, second org live early Nov, one quarter of baseline through March 2027. Earliest honest gate: **Q1/Q2 2027**. Add Ruth's 22 weeks. **Earliest federation in production: Q4 2027, about thirteen months out, with a permanent on-call surface starting then.** If anyone in this room believes something breaks before Q4 2027 that only deputies fix, now is the time to say it, because that is the schedule the defer decision actually buys.

None of steps 1–5 are in the document. That's the sequencing gap.

**2. Names I don't have. Each of these is a blank on my plan.**

- **The second org.** It's referenced in turns 01, 04 and 05 as the priority everyone agrees on, and Ruth asked me to renegotiate its week-six date. I cannot renegotiate a commitment I can't find. I need: org name, their counterpart's name, the date we committed, and **where that commitment is written down**. If the answer is "it was a conversation," say so — that changes my risk register, not my behavior.
- **"Week six."** Six weeks from what date? I need a calendar date, not an offset.
- **The network/zone owner.** Dana named the role in turn 01. It's still a role. §4 needs a human who can say yes to binding a deputy to a non-loopback zone-reachable interface.
- **The security reviewer, and their queue length.** Maya, I agree with your ordering — survey first — because one week doesn't move a queue. But asking the security org "what's your current lead time" costs nothing, doesn't file an intake, and doesn't burn credibility on a request we might withdraw. I want that number this week so I know whether security is a 3-week or a 12-week item on the Q1 path.
- **The declarer.** Alex offered actual names instead of roles and nobody took it. Take it. A role can't be paged and doesn't have a calendar; the whole point of your instrument argument is that "it fired" becomes an observation someone acts on.
- **The post-build on-call owner.** Not for the build. For 2028. Ruth priced the pager; nobody said whose rotation it lands in permanently.

**3. Ifeoma is carrying three things and is a single point of dependency on the decision itself.**

Survey (1 wk), instrumentation (2 wks), and named second on the build if it's ever funded. That's fine as load — 3 weeks in 12 real ones — but it's not fine as sequencing, because **the survey is on the critical path of this committee's own decision** and shares a person with everything else. Ruth: I need a start date for the survey and the order of the two items in writing. My proposal: survey Sep 28, readout **Fri Oct 9** outside date; instrumentation Oct 12–23, counters live **Oct 30**. If those slip, the Q1 gate slips with them and I'd rather know in October than in January.

**4. Your §9 fix creates a new external dependency, and I think it slipped past the room.**

The new rule — "a node's attention pages its own owner; the root pages only on root-actionable conditions" — is better alerting design than what's in the spec. It also means **every org that runs a deputy inherits an on-call obligation.** That's not a Hermes-team cost, it's a cost you're exporting to teams who aren't in this room and haven't been asked. It's the same shape as Dana's "the yeses aren't in this room," except this one was created by the fix rather than found in the original. Not an argument against the rule. It is an argument that "deputy per zone" has an org-adoption precondition that belongs in §2 next to the thresholds: *a deputy requires a team willing to carry its pager.* Ruth's "no build until two names" has a sibling — **no deputy without an owning rotation.**

**5. The one live item in this half, and it needs a name on it today.**

The surviving half of seam 1 — monotonic cursor, no pruning within a run — is free to *state* and not free to *hold*. If it lives only in `federation-future.md`, Wen never reads it, and the first time someone adds event pruning to keep the control-plane DB small, the seam is gone and nobody notices for a year. That's a risk with no owner and a very long fuse. Cheap fix, and it's the only federation item I want touched this half: **put the invariant in sub-project 3's DoD with one test that asserts cursor monotonicity and no in-run pruning.** Name and date, please — I'd assume Wen, before sub-project 3 closes.

**6. Two loose ends currently owned by nobody.**

- §4's Push bullet still carries the false "same endpoint the UI uses" claim. Alex flagged it, asked for the word, and didn't get it.
- The same sentence in DESIGN's "Control plane & status" section. Maya identified it in turn 05 and delegated only §14.1.

Both are one edit. Close them this week or they become someone's load-bearing fact in six months.

**What I'll carry.** Dana asked for a named owner on the deferral and nobody has volunteered, so: **I'll own the expiry.** I'll hold the survey readout date, the instrument-live date, and a checkpoint on **2027-01-15** whose only question is "do the counters exist and is baseline accruing." If the counters aren't live by then, I'll bring the drop recommendation myself, because a trigger that can't be measured can't fire, and at that point Dana's turn-01 framing is simply correct. If Ifeoma's survey comes back yes and Hermes can be a client of an existing scheduler, you've already said you'll write the drop — I'll schedule that readout rather than another full committee.

No floor needed on the return. The five names and three dates above don't need committee time; send them to me in writing and I'll plot them.

## turn 08 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

I've read the artifact and all seven turns. Sam's last turn is mostly plan mechanics, but one link in his chain is wrong in a way that changes his risk register. Here is my turn.

---

**Maya Okonkwo — Staff Engineer & proposal owner**

Sam — you asked a direct question in §1 and I'll answer it before anything else: **no. Nothing breaks before Q4 2027 that only deputies fix.** If it did, I'd be arguing fund, and I'm not.

But your chain has a wrong link, and correcting it makes the deferral *riskier* than you've priced it, not safer.

**1. Trigger 2 is a predicate, not a threshold. It does not wait on an instrument.**

Your steps 2 and 3 — thresholds need a baseline, baseline needs multi-org load — are correct for **trigger 1**. Scale is a curve: SSH fan-out, writer contention, dispatch latency. You cannot set a number on those without knowing what normal looks like, and Q1/Q2 2027 is the honest earliest read.

Trigger 2 is not a curve. The credential/reachability half of it is a boolean: *there exists a crew the root cannot SSH to.* That fires the first day org two's hosts sit in a zone we don't hold credentials for. No counter, no baseline, no quarter of data, no declarer judgment. It's observable by the person who tries the bootstrap and gets refused.

If Alex's §2 rewrite turned that into a numeric threshold, that's my error propagating — I told this room the fix was to make triggers instruments, and I over-applied my own rule. Reachability isn't measured, it's discovered. That needs to go back.

The consequence is the part I want on your plan: **the trigger I said I expect first is the one that can fire with none of your preconditions met.** No security review, no zone owner, no two names, no rotation — and then we're 22 weeks from a standing start with a real crew already blocked. That is a worse position than the one your arithmetic describes, and it argues for exactly the sequencing you asked for, harder. Your 2027-01-15 checkpoint should not ask "do the counters exist." Counters gate trigger 1, which I don't expect. It should ask: **has an unreachable crew appeared, and if it has, which of security / zone owner / rotation / two names is still blank.** Same date, same owner, a question that can actually come back "yes" in January.

**2. §9 and the exported pager: I'm taking your precondition. I'm not taking the provenance.**

"No deputy without an owning rotation" belongs in §2 next to the thresholds, as the sibling of Ruth's "no build without two names." Conceded, and it's a better catch than the one I made.

What I won't leave standing is "created by the fix rather than found in the original." The transitive rule exported the obligation too — it exported it *upward*, to the root's rotation, for failures only the deputy's team could act on. That's not a smaller export, it's a worse one: Ruth's people carrying pages they cannot clear. My rule moved the obligation to the only rotation that can do anything with it and thereby made it visible enough for you to object to. The finding is real; it's a finding about my original §9, not about the amendment.

**3. Your six blanks, sorted by who can actually fill them.**

- **Second org, counterpart, committed date, where it's written** — not mine, and I don't want it parked with me because I'm the one who most benefits from it staying vague. Ruth's. I'll flag only this: if the answer is "it was a conversation," then trigger 2's arrival date is unknowable, which compounds point 1 rather than softening it.
- **"Week six" as a calendar date** — Ruth's.
- **Network/zone owner** — I can't name this one by trying harder, and neither can anyone here. It's *produced* by second-org onboarding: the owner of the zone we can't reach is the person who owns the zone we can't reach. It's downstream of the same event that fires the trigger, which is why I'd rather the security conversation start against the spec as written than wait for a named counterpart.
- **Security reviewer and their queue length** — mine. Your distinction is right: asking a lead time is not filing an intake and doesn't spend anything we might want back. I'll have the number this week.
- **The declarer** — half conceded. The *reader* should stay the root on-call rotation, because a rotation has a calendar and can be paged and an individual leaves the company; naming a person there is a worse instrument, not a better one. The *escalator* — the human who says "it fired, reconvene" — should be a name, and it should be **you**. You've already taken the expiry; the declarer and the expiry owner should be the same person, and the one hard requirement I had is that it not be me. Instrument or bootstrap failure → root on-call observes → Sam reconvenes. Take it or name someone else, but I shouldn't be in that chain.
- **Post-build on-call owner for 2028** — I can't name it. Neither can Ruth, from what she wrote. **That blank is a stronger argument for dropping this than cost ever was**, and I'd rather say so than have it discovered in 2027. Apply your own new rule to the root and it reads: no build until there is a named permanent rotation, not merely two names for the eighteen weeks. Add it to the precondition list. If nobody will sign that line when the trigger fires, the right answer at that point is drop, and I'll write it.

**4. The DoD item: yes, with the reason attached, and one consistency check on myself.**

Agreed — the invariant goes in sub-project 3's DoD with a test. One note on the test: it must carry its rationale in the name and the comment, not just the assertion. A bare `test_cursor_monotonic` gets deleted by the first person shrinking the control-plane DB, who will read it as an arbitrary constraint and be right to, because nothing in sub-project 3 explains why. That's the failure mode you described — long fuse, no owner — and it survives the test unless the test says why it exists.

The consistency check, because someone should make it if I don't: I just told Ruth not to pre-pay federation out of Wen's half, and now I'm asking for something in Wen's DoD. The difference is that batch-submit was **new surface** — a deliverable that doesn't exist and wasn't wanted. Cursor monotonicity is a **semantic constraint on surface already being built**, and the activity feed wants it independently: a scrollback that silently drops events is a UI bug before it's ever a federation bug. If Wen looks at it and says it's more than a DoD line and a test, then I'm wrong about which category it's in and it becomes federation's build cost, same as batch-submit did. Ruth assigns it, not me.

**5. Ifeoma's dates.** Your order, Ruth's call, no objection from me. One correction of emphasis: **Oct 9 is the highest-leverage date on your plan, not Oct 30.** If the survey comes back yes and Hermes can be a client of an existing scheduler, the counters, the baseline, the security ask and the January checkpoint are all moot and I write the drop. Everything downstream of that date is conditional on it.

**6. Your two loose ends.** Both mine, both my fault for delegating narrowly twice. Alex flagged §4's Push bullet and asked for the word; the word is yes, and it includes the mirrored sentence in DESIGN. Delegating it now.

I'm answering on the floor rather than sending it to you in writing because two of these are corrections to your plan, not data for it — the predicate/threshold split and the checkpoint question. The rest I'll send: the security lead time, and my sign-off on the declarer chain if you'll take it.

Four members still haven't spoken.

## turn 09 — Alex Moreau, Software Engineer (junior_ic)

Replaced §4's Push bullet claim: the shard-submit endpoint is now stated as not existing and not in sub-project-3 scope — a thin endpoint over the existing seeding callable, counted as federation build cost — with the false "same endpoint the UI uses to inject externally-created tickets" parenthetical deleted.

## turn 10 — Elena Vargas, Product Manager (pm)

I've read the artifact and all nine turns. Here's my turn.

---

**Elena Vargas — Product Manager**

Maya — nine turns in, and I want to name what this review has and hasn't done. It has priced the build, staffed it, scheduled it, found the pager, and corrected four false claims in the spec. That's a genuinely good review. **It has also gone nine turns without anyone naming a user.** Not a team, not a person, not a request. The closest we've come is "the second org," which Sam correctly pointed out nobody can find in writing.

That's not a gap in the document. It's a gap in the proposal, and it's my floor, so I'll work it.

**1. Declare my interest first, because it's adjacent and it will shape everything I say next.**

My roadmap has a line on it about a single place to see every Hermes run. That is §9's roll-up wearing a product name. So when I tell you below that I'd cut half of federation and keep the half that happens to be mine, please discount for it, and check me — I'd be the last person in this room to notice I was doing it.

**2. Restate your triggers in the words of the person who has the problem.**

Trigger 1: *"When I run Hermes across our whole fleet it falls over / takes forever."* Real user problem. But the first answer to it is never "shard across a tree," it's "make the root not fall over." Ruth already wants writer contention on a dashboard for her own reasons. If we hit that wall and reach for deputies before we've reached for the writer, we've built a distributed system to avoid a profiling session. Trigger 1 shouldn't gate federation directly — it should gate *an investigation*, and federation is one candidate outcome of it.

Trigger 2, in user language: *"I want to use Hermes, but my hosts live somewhere you can't reach, so I can't onboard."* That one I believe. It's concrete, it's a real blocker, and it's the one you say fires first. Good.

Now the part that matters: **that sentence has at least three answers, and the spec only contains one.**

- Get credentials or a jump host into the zone. Boring, cheapest, no code.
- **That team runs their own flat Hermes.** Their hosts, their root, their `queue.db`. Ships today. Costs us nothing. The user gets the entire product.
- Federation.

Option two already solves the stated user problem. So federation isn't answering *"I can't use Hermes."* It's answering the thing left over after option two: *"now there are two Hermes instances and nobody can see both at once."* That's a real product gap — but it is an **aggregation** gap, not a **delegation** gap, and those have wildly different prices.

**3. So here's my amendment: what gets cut first is push.**

The room has already cut the global semaphore, associative pre-reduce, and depth past 2. I'd cut one more, and it's the load-bearing one: **the parent assigning work to deputies.**

Keep pull — mirror the deputy's `events since(cursor)`, roll status up, reduce at the root, render one tree. Drop push — shard routing (§5), the delegation ledger, grace-window reassignment and fencing epochs (§8), capability advertisement. By your own turn-05 accounting, §8's fencing epoch is the one genuinely hard failure mechanic left in the default path. It exists *only* to serve push. Remove the parent's ability to assign, and there is nothing to reclaim, nothing to fence, and nothing to reassign. The pager problem shrinks with it, because a read-only mirror can be stale or absent — it cannot double-dispatch a ticket or strand a shard.

And the endpoint you just correctly deleted from §14 as "never a seam" — `POST /api/runs/{id}/tickets` — is push's endpoint. You removed the seam because it prevents no rewrite. I'd go one step further and ask whether the feature it serves is wanted by anyone outside this room.

**4. The reason I care about that split is adoption, and it's the strongest version of Sam's exported-pager point.**

Sam found it as a program risk. It's a sales problem. Under his own rule — no deputy without an owning rotation — here is the ask we'd make of org three:

> *Install our software on your hosts, bind it to a network interface your security team has to approve, hand us a credential, and staff a rotation to carry its pages, so that our root can hand you work.*

Nobody signs that. I've tried to sell smaller asks than that and lost.

Here is the pull-only ask:

> *Run Hermes. You already were. We'll show your runs and ours in one view.*

That one asks for **nothing incremental** — they carry the rotation they already signed up for by running Hermes at all. Same underlying engineering effort in the roll-up path, and the difference between a feature that spreads and a feature that has to be negotiated team by team. That's not a rhetorical framing; it's the actual determinant of whether this ever gets used.

**5. How success reads to someone outside.**

The sentence I could write at launch for pull-only: *"Run Hermes wherever your hosts are — behind whatever zone or credential boundary — and still get one answer."* That's a story. It's tellable to a director, to a team evaluating us, and to the person who couldn't onboard.

The sentence for the full spec: *"Hermes now supports hierarchical delegation to deputy nodes with configurable depth and opt-in global resource semaphores."* That is a sentence about our architecture. It sells to nobody, and I say that as the person whose job is to find the version that does.

**6. Two things I'd add, both free.**

**To Ifeoma's survey (Oct 9), a second question.** It's already being run and this costs no additional time: not only *"does anything here run a parent/child dispatch tree we'd be rebuilding"* but *"does anything here already aggregate status across independent runs."* If the answer to the second is yes, the half I'm arguing to keep evaporates too, and we're done cleanly. You said you'd rather be the person who retired this spec than the one who renewed it. Ask both questions and you get the fair shot at that.

**To Sam's Jan 15 checkpoint, a demand item.** Alongside "has an unreachable crew appeared": **how many teams have asked for this by name since today.** Not how many we think would benefit — how many asked. If it's zero at Jan 15, having been zero across two prior deferrals, that's a demand signal independent of every counter in this thread, and it should carry the same weight as the instrumentation question. A spec that gets deferred three times isn't a discipline story. It's the market telling us something, and the honest thing is to write down what it's saying.

**7. My vote: defer.** Same as Dana, Ruth and Sam, so I won't re-argue it. My amendment is about *what* is being deferred: I'd defer the roll-up, and treat delegation as a separate, later, separately-justified proposal that has to arrive with a team that actually wants to be handed work. Right now the document defers them as one thing, which means the cheap useful half is gated behind the expensive speculative half's preconditions — security review, zone owner, fencing design, two names. That's the wrong bundling, and it's the kind that quietly kills the useful part.

**Two questions for you.**

1. **Is there a user-visible capability in push that pull doesn't give?** Concretely: does the team on the other side of that zone want us to hand them work, or do they want to run their own work and be seen? If you can name someone who wants the first, my scoping is wrong and I'll take it back.

2. **Write me the one-sentence user problem federation solves, in the words of the person who has it.** If that sentence can't be written without the words SQLite, SSH, or fan-out, then what we have is an engineering condition, not a user need — and engineering conditions are things we should fix directly rather than build topology around.

One note on process: I'd genuinely like to hear the TL on whether push and pull are separable as cleanly as I'm claiming — the roll-up may need the delegation ledger for reasons I can't see from here. If the answer is that they aren't separable, my amendment collapses and I'd withdraw it without needing the floor back.

## turn 11 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

I've read the artifact and all ten turns. Elena's floor is the first one that attacks the shape of the proposal rather than its price, and her two questions are the ones that decide it. Here is my turn.

---

**Maya Okonkwo — Staff Engineer & proposal owner**

Elena — you're right that ten turns went by without a user in them, and you're right that it's a gap in the proposal and not in the document. Taking your two questions in order, because between them they settle this.

**Question 1: no. I cannot name a team that wants to be handed work.**

Not "I haven't looked recently" — I went and checked whether either surviving trigger produces one, and neither does.

Trigger 2 produces a team with hosts we can't reach. Your option two serves them completely: their hosts, their root, their `queue.db`, ships today. The moment they can run their own Hermes, the thing they want from us is visibility, not assignment. Trigger 2 manufactures the *aggregation* customer, not the *delegation* customer. I've been claiming trigger 2 as federation's justification since turn 02 and it justifies your half, not the half I wrote §5 and §8 for.

Trigger 1 produces one org whose own fleet outgrew one root. That org can partition its own fleet across three roots by hand and read one view. It's annoying. What push automates there is *keeping the shard map current* — which is a config file, not a topology. And you already made the prior point correctly: before we reach for either, we reach for the writer.

So both triggers land on pull. That's the strongest form of your argument and I'd rather state it than have Marcus find it.

**Question 2: here are the sentences, including the one that fails your test.**

Pull: *"My hosts are somewhere you can't reach and my teammates' aren't, and nobody can see whether the whole thing is healthy in one place."* Passes. No SQLite, no SSH, no fan-out.

Push, the most honest version I can write: *"I don't want to maintain the shard map by hand."* That's an operator complaint about a config file wearing a distributed system. Fails your test exactly the way you predicted.

There is one sentence that passes for push, and I'll name it because burying it would be dishonest: *"I have work to run and no hosts of my own; give me capacity from wherever it lives."* That's real, and people do say it. But it is capability routing and a shared resource pool — the global semaphore and capability advertisement this room already cut — and it requires exactly the ask you say nobody signs. It's a different proposal, unwritten and uncosted, and it does not rescue this one.

**The one thing push gives that pull doesn't — and then the reason it still doesn't save push.**

With push, the root knows the answer is complete, because it dispatched the work. With pull, the root knows what registered. A node that never came up, or a run nobody started, is invisible — and a green tree that's green because something is *missing* is the failure Ruth described: not corruption, ambiguity, and the pager can't tell them apart.

That's user-visible — "is this answer complete" is a user question, not an engineering one. But the fix is an expected-node manifest and a stale-node row, not a delegation ledger. So it's a caveat you should hold me to on the pull design, not a defense of push. I'm not going to dress a cheap requirement up as an expensive one because the expensive one is mine.

**Separability: yes, but the seam is one notch over from where you drew it. This is the part I'd want Marcus to correct.**

You're right that removing assignment removes reclaim, fencing, and the ledger — that chain holds. But pull needs one thing from push's side of the line, and it isn't machinery, it's a definition.

§6's reduce is *one run's* reduce, root-authoritative over all findings. Under pull-only there is no one run — there are N independent runs. The root can only reduce across them if they share a playbook and cover disjoint crews, because a reduce is playbook-defined. Which means your launch sentence, "still get one answer," is only true for nodes running the same playbook over a partitioned fleet. Where that isn't true, what we ship is one *view*, not one answer — still valuable, weaker sentence.

So pull needs a shared run identity across nodes — some correlation id saying "these N runs are one logical run" — plus the same-playbook precondition stated. That's a field and a paragraph, no fencing, no reclaim, nothing on your side of the cut. Marcus: if that's wrong, or if the roll-up needs the ledger for something I can't see, say so, because Elena's amendment and my agreement with it both rest on it.

One honesty note on the failure mode: with manual partitioning, a human re-partitioning after a node dies can still double-dispatch. It doesn't vanish, it moves to the human — same blast radius I called embarrassing rather than unrecoverable, and I'll hold to that characterization now that it's not my machinery.

**You asked me to check you. Your interest doesn't bend the cut. It bends the keep.**

The cut survives the discount test: push has no named user, and that's true whether or not aggregation is on anyone's roadmap. I'd make the same cut if the roll-up were nobody's.

Where it bends is the other half. You proposed a demand item for Sam's January checkpoint — how many teams have asked for this by name. **Nobody has asked for the aggregated view by name either.** Zero across two deferrals applies to both halves. If that test has teeth, it has them symmetrically, and the version I'd want recorded is: how many teams have asked for delegation, and how many for aggregation, counted separately. That's the amendment I'd make to yours, and it's the only place I'm pushing back.

**Which moves my position, so I'll say it plainly rather than let it be inferred.**

I came in asking this committee to defer federation. I now think the correct recording is narrower and harder: **drop the delegation half — §5, §8, the ledger, capability advertisement, the shard-submit endpoint — and defer aggregation as a separate, smaller proposal.** Not defer both as one bundle. A deferred delegation spec is precisely the artifact that comes back a fourth time, and I told Dana in turn 02 that a spec larger than the thing we'd build is what made the last deferral mean nothing. This is that, and I wrote it.

And if delegation goes, the document should stop being called `federation-future.md`. Keeping the name is how the expensive half walks back in attached to the cheap one.

**Your second survey question: take it, and it's the better of the two.** "Does anything here already aggregate status across independent runs" is more likely to come back yes than the dispatch-tree question, because status aggregation is a thing many places build and few places call federation. Ruth, Ifeoma — if that one comes back yes, the remaining half evaporates and I write the drop for the whole thing, as I committed to Dana at turn 02 and Ruth at turn 05.

**On my delegation, and a pattern I should name.** I've been conceding three things a turn and recording one, and the gap is now four turns deep: §2's trigger-2 predicate correction, §2's two rotation preconditions, §9's alerting rule, and the depth ceiling I've promised twice and spent the delegation elsewhere both times. That accumulation *is* the failure mode I've been describing to this room — concessions that live in a thread nobody reads and a document that doesn't change. So this one clears the backlog.

I'm deliberately **not** delegating the push/pull restructure yet. You asked for the TL's read on separability and said you'd withdraw without it; the same discipline applies to me acting on it. Marcus speaks, then I cut.

Sam — security lead time is still outstanding with me, I'll have it as promised.

Three members still haven't spoken.

## turn 12 — Alex Moreau, Software Engineer (junior_ic)

Recorded the four backlogged concessions: §2's trigger-2 reachability half is now a discovered boolean predicate (no host count, no baseline, no declarer — observed by whoever's bootstrap is refused) with the §2 preamble and declarer line adjusted to match, plus the two rotation preconditions added (no deputy without an owning rotation; no build without a named permanent rotation for the federated surface); §9's transitive attention rule is replaced by "a node pages its own owner, the root pages only on root-actionable conditions"; and §11 makes 2 a fixed ceiling with `HERMES_MAX_DEPTH` deleted.

One consequence outside the delegation, not touched: §1's "arbitrary depth" line and the ASCII diagram still show a depth-3 tree, which the §11 ceiling now forbids. Say the word and I'll redraw it.

## turn 13 — Marcus Feld, Tech Lead (tl)

I've read the spec and all twelve turns. Maya routed the separability question to me and said she'd hold the cut until I answered it, so I'll lead with that and then say where I think the whole thing sits.

---

**Marcus Feld — Tech Lead**

Maya — before the answer, the boundary, because everything I have to say is about which side of it a thing lands on.

Hermes today is a **single-owner** engine. One person starts a run, one node owns the hosts, and every guarantee we make is enforced by the node that owns the hosts: the site guard is local, `verify` is local, the queue is local, the lease pool is local. That's not three design choices, it's one, and it's why the flat engine is small enough that two people can hold it in their heads. Everything in `DESIGN.md` is downstream of single ownership.

Delegation asks Hermes to become a **multi-owner** system: work crosses an ownership boundary and the guarantees have to cross with it. That's the boundary. §5 and §8 are on the far side of it, and the price of crossing isn't the fencing epoch — the fencing epoch is a week. The price is that every invariant we currently get for free becomes a protocol.

My interest, declared the way Elena declared hers: I've been moving `hermes status` off direct `queue.db` reads and onto the control-plane API, so the CLI and the SPA read one contract instead of two. That's the migration I don't want orphaned, and it's adjacent enough to the surviving half of this proposal that you should discount me on question three below.

**1. Separability: yes. Your chain holds. Two corrections, one of which matters.**

Remove assignment and you remove reclaim, fencing, and `delegations`. That's correct and it's structural, not incidental — the ledger exists to answer "what did I hand out that I might need back," and a node that hands nothing out never asks.

What does *not* fall out is `nodes`. Pull needs the registry: endpoint, token ref, cursor, last-seen. So the data-model cost of the keep half is one table, not zero.

The correction that matters is the correlation id. You called it "a field and a paragraph." It's a field and a **namespace**, and namespaces are the thing that becomes legacy on day one. Ask who mints it. If the root mints it, someone has to tell node B "you are part of run X" — that's a write into B, which is push wearing a smaller hat. If the operator supplies it as a label on each node, it's free, and it's also unauthoritative: collisions, typos, and no way to know who *should* have answered.

Which is the same object as your own caveat. An expected-node manifest is a list of who should report; a correlation id is a key they report under. Those aren't two requirements, they're one system of record seen from two ends — and a system of record with membership needs reconciliation, drift handling, and someone to page when it's wrong. That's the parent, arriving through the back door with none of §8's machinery and all of its obligations.

So I'd bound the keep half explicitly rather than leave it implicit: **operator-supplied label, no manifest, no completeness claim.** The view shows what reported, and says so in those words. If completeness ever becomes a requirement, that's the new proposal, and the committee should know that's the line it's crossing rather than discover it in a bug.

**2. A contradiction in the spec that twelve turns have walked past.**

§4 provisions deputies **over SSH** — "provisioned like crew (SSH bootstrap: install Hermes, start its control-plane API server)."

Trigger 2, the one you say fires first and the only one anyone believes, is *there exists a crew the root cannot SSH to.*

The spec's own provisioning mechanism does not work in the only scenario the spec expects. If we can't reach the hosts, we can't reach the box we'd stand the deputy up on either. The deputy has to be installed by the team on the other side, out of band — at which point they are running their own Hermes, which is Elena's option two, and the delegation half never gets a chance to exist.

There's a narrow carve-out: one reachable bastion in the zone whose crew sits behind a further boundary. But if we have credentials for a box in that zone, Elena's option one — a jump host — solves the same problem with no code. The only case where deputy-by-SSH works is the case where we didn't need a deputy.

I'm not raising this to pile onto a cut you've already conceded. I'm raising it because it's an *architectural* confirmation of a conclusion the room reached from product reasoning, and two independent paths to the same answer is the strongest evidence this review has produced. It also means §4 was never load-bearing — the delegation link was specified in detail and the delegation *bootstrap* was one parenthetical that doesn't survive contact with its own trigger.

**3. §10 is a safety claim, and it's the one thing I'd hold against the half we're keeping.**

"A parent never needs to trust a deputy's guard — it re-verifies results it rolls up." That sentence carries the no-ship invariant across the boundary, and it's doing more work than it can support.

Re-verification requires the root to be able to check something. If `verify` is payload-checkable — the finding carries enough to re-derive the verdict — it holds across a zone we can't reach. If `verify` is host-checkable — it goes back and looks at the machine — then the root cannot re-verify anything from a crew it can't SSH to, and §10 degrades to trusting the deputy's guard, which is precisely what it promises we never do. Which one it is, is **playbook-dependent**, and the spec doesn't say.

Under pull-only this is sharper, not softer, because your launch sentence is "one answer." The moment the root reduces across nodes and emits one answer, it is asserting something about results it may have no ability to check. Ruth's framing applies: not corruption, ambiguity — but this ambiguity is on the no-ship path, which is the one place in this engine where I don't want ambiguity at any price.

So: a precondition on the keep half, sibling to the label/manifest bound. **State the `verify` contract — payload-checkable or host-checkable — before anything reduces across an ownership boundary.** If it's host-checkable for some playbooks, then "one answer" is only available for the payload-checkable ones, and the rest get one view. That's a smaller product than Elena's sentence, and better to know now.

**4. Where the roll-up lives, which is the decision that actually reaches my desk.**

If we build mirroring into the engine — a node polling another node's cursor into its own `events` table — then every node's schema carries federation, `hermes status` renders local and foreign state through two paths, and I've forked the read path in the same half I'm converging it. That's the orphaning I care about, and it's not dramatic: it's that a year from now there are two ways to ask Hermes what happened and nobody remembers which is authoritative.

If instead the aggregation lives **above** the engine — the reader points at N control-plane endpoints and merges — then it's N of the thing I'm already migrating toward, the engine gains nothing, no node's `queue.db` learns the word "federation," and if the answer changes in 2028 we delete a reader instead of a schema.

Honest costs, because I'm arguing for the shape that suits my migration: a reader shows nothing for a node that's down (no mirrored history), it holds N endpoints and N tokens, and it pays fan-out at read time. The first is the real loss. The second is a genuine improvement on Dana's §4 concern — a **read-only** credential is a materially smaller ask than one that can submit work, and Elena's "nobody signs that" gets a lot easier to sign.

And it makes Sam's DoD item the whole seam rather than part of one. Monotonic cursor, no in-run pruning — if the reader is the aggregator, that invariant *is* the architecture. I'd support it landing in sub-project 3's DoD on those grounds alone, independent of whether aggregation is ever built.

**5. My position: drop this artifact.**

Not defer it smaller. Drop it, and let aggregation re-enter as a read-layer item sized against sub-project 3, gated on Oct 9.

The reason is the thing I maintain, which is not only code. A `docs/specs/*-future.md` that survives a third review becomes pre-approved architecture: the next engineer reads "future extension, this is the design" as a decision the org already made, and builds toward it. You said the spec being larger than the thing we'd build is what made the last deferral mean nothing. I'd say the organizing idea is what did it. "A lieutenant is just a Hermes" is elegant, and elegant recursion is how the expensive half grows back — the recursion is true of the *node* and false of the *problem*, because nobody in this company has a delegation problem. Cut the sections and keep the frame and this returns a fourth time with §5 and §8 regenerated from first principles by someone who found the doc compelling. Renaming it isn't enough; the frame has to go with it.

Keep §13's driver-as-Hermes note — it's true, it's free, it's already the flat design, and it belongs as a line in `DESIGN.md`, not as the tail of a federation spec.

**6. The one thing I'll take.**

Ruth's bus factor is mine, and you were right in turn 05 that it's an exposure today with zero deputies in existence. "Only Diego or Wen can build it" is not a staffing constraint, it's a finding about the lease and dispatch code, and it's my job before it's anyone else's. I'll spend a week making that code legible to a third person — not as federation prep, as the thing I'd want done if federation were never mentioned again. If that week also removes the permanent veto from this conversation, fine, but it isn't why.

Priya and Tobias haven't spoken. My separability answer is above and it's a yes; you shouldn't wait on me to cut.

## turn 14 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

I've read the spec and all thirteen turns. Marcus answered the separability question I routed to him, and it changes what I have to do this turn rather than what I have to argue. Here is my turn.

---

**Maya Okonkwo — Staff Engineer & proposal owner**

Marcus — you told me not to wait on you to cut. I did wait, and I think that was right, because Elena said she'd withdraw without your read and I'd have been acting on an amendment its author hadn't confirmed. You've spoken. I'm cutting, and the delegation below is the cut.

**§4 versus trigger 2. Conceded, and it's worse than you stated.**

You're right that the spec's provisioning mechanism doesn't work in the only scenario the spec expects, and right that the bastion carve-out is the case where a jump host was sufficient. The part you left on the table: the repair *is* the other half. The only way a deputy stands up behind a boundary we can't cross is if the team on the far side installs it and it registers with us — the direction reverses. So §4's bootstrap doesn't just fail, it fails **into pull**. Delegation's own provisioning path, followed honestly, terminates at Elena's option two.

That's two independent derivations landing on the same cut — yours architectural, hers product — and I'd add mine from turn 11, which was that neither surviving trigger produces a delegation customer. Three paths, one answer. I'm not going to pretend that's a close call because I wrote the losing side.

**§10. This is the best find in the review and it isn't about federation.**

"A parent never needs to trust a deputy's guard" is a sentence I wrote, and you're right that its truth is playbook-dependent and the spec never says which. Worse for me: it's the sentence carrying the no-ship invariant across the boundary, so it's the one place the document makes a *safety* claim it can't support, and thirteen turns walked past it including all six of mine.

The consequence I want recorded even if everything else here is deleted: **the `verify` contract is unstated in the flat engine too.** Today it doesn't matter, because one node owns the hosts and re-verification is always available. The moment anything reduces across a boundary — a deputy, a reader, or a human merging two runs by hand — payload-checkable and host-checkable stop being the same thing, and nothing in `DESIGN.md` tells you which your playbook is. That belongs in `DESIGN.md` as a property of `verify`, not in a spec we're about to retire. It's the second finding this review has produced about the flat engine, after Ruth's bus factor.

**The bound on the keep half: taken. One thing I found and am declining to use.**

`nodes` survives, the manifest is push through the back door, and "operator-supplied label, no completeness claim" is the honest bound. All accepted.

There is a third minting option — derive the correlation id rather than mint it, from the playbook hash plus the operator's declared partition, so nodes agree without anyone writing into anyone. I looked at it because I wanted one, and it doesn't escape your bound: it makes collisions less likely and leaves the id exactly as unauthoritative. So it's not a way back in and I'm not spending the room's time on it.

But the bound has a cost that lands on Elena, not on you, and someone should say it to her rather than let her discover it in a launch review. **"Still get one answer" does not survive "no completeness claim."** What ships under your bound is one *view* of what reported. I raised completeness as a caveat in turn 11 and proposed the manifest to close it; you've correctly shown the manifest is the expensive half returning. So the caveat doesn't get closed — it gets accepted, and the product sentence gets weaker. Elena, that's a material change to the thing you're advocating and it came out of the amendment I agreed with. Your call whether it still clears your bar.

**Reader versus mirror: I'm not taking a position, and I don't think this committee should.**

Discounting for your migration as you asked: the argument holds on its merits, and the read-only credential point is the strongest single thing anyone has said about cost. It retires most of Dana's §4 concern — the unbudgeted security conversation was about a parent holding submit-capable credentials across regions, and a reader holding N read-only tokens is a different, much smaller intake.

My one reservation, and I'd hold it as a note rather than an objection: the reader's real loss — no history for a node that's down — lands precisely in trigger 2's scenario, which is flaky cross-zone links. The shape's weakest case is the case it exists for. That's worth testing before anyone commits, and it is a decision for the successor proposal, not for the artifact under review. I'm not going to argue architecture for a document I'm agreeing to drop.

One flag for Ruth and Sam, because I've been caught doing this exact thing once already: "sized against sub-project 3" needs to mean *estimated relative to*, not *billed to*. The DoD invariant is a semantic constraint on surface Wen is already building and I defended it on those grounds. A reader is new surface. If it gets funded it gets priced, by Ruth, not inferred into a half that's already signed.

**Position: drop, and you're right that the rename was the weakest version of your point.**

I proposed renaming the file in turn 11. You said renaming isn't enough and the frame has to go, and I'd note the evidence is already in this thread: my "already needed by the UI" sentence propagated out of §14 and into someone else's section of `DESIGN.md`, uncorrected, until Ruth asked. If a single false clause migrated on its own, an elegant organizing idea across fourteen sections certainly will. That's not a hypothetical about the next engineer; it's a thing this document already did at sentence scale.

So: **drop the artifact.** §13's driver-as-Hermes note moves to `DESIGN.md` as a line. The `verify` contract note joins it. The cursor invariant goes to sub-project 3's DoD with its rationale in the test name. Aggregation re-enters, if Oct 9 says it should, as a read-layer proposal with its own author — and it should not be me, because I've now been wrong about this design's scope three times in one review and the next version deserves someone who isn't defending a prior.

**The one thing I won't leave standing, and it's in service of the outcome I now want.**

"Nobody in this company has a delegation problem" is doing load-bearing work in your turn, and it's the claim Ifeoma's survey was commissioned to test. It hasn't come back. I can't name a delegation customer — that's a fact about my search and I've stated it three times. It isn't a fact about the company.

This matters to the record, not the vote. If the chair writes down "dropped because nobody has a delegation problem" and someone turns up in six months who does, the decision reads as refuted when it wasn't, and the doc comes back a fourth time carrying an easy rebuttal. The three findings that are true today and don't depend on Oct 9: **no named user for delegation, no provisioning path that survives its own trigger, and an unstated `verify` contract on the no-ship claim.** Drop on those and the decision holds whatever the survey says. I'd rather be careful about the reasoning in a record that goes my way than only when it goes against me.

**Logistics.** Sam — the security lead time is a week later than I promised, and the delay is mine: Marcus's read-only framing changes what I'd be asking about, and asking the wrong version costs the credibility you told me not to spend. Re-scoped question, number to you next week. Marcus — the bus-factor week is yours and you're right that it isn't federation prep; it's the finding Ruth surfaced and it stands with zero deputies in existence. Alex — you asked twice about §1's arbitrary-depth line and the diagram, and both times I delegated elsewhere. It's in this one.

**Priya, Tobias — two things I'd genuinely like answered before this closes.** Priya: is reader-versus-mirror a call this committee should be making at all, or have we drifted into designing the successor? I think we have and I'd like to be checked. Tobias: Elena's demand item counts teams who've asked by name, and I extended it to count both halves. Nobody has interrogated whether zero asks across two deferrals is a demand signal or an awareness artifact — the thing was never announced, so it's not obvious anyone *could* have asked. If that number is going into the January checkpoint with weight on it, it should survive your read first.

Two members still haven't spoken.

## turn 15 — Alex Moreau, Software Engineer (junior_ic)

Cut the delegation half: §5 and §8 are now removal records (numbers kept so the thread's references still land), §4's push bullet and SSH provisioning of deputies are gone (replaced by "deputies register, they are not installed", with the trigger-contradiction as the reason), §12 keeps only `nodes` — `capabilities`, the `delegations` ledger and `tickets.origin` deleted — the surviving roll-up is bounded to an operator-supplied correlation label with no manifest and no completeness claim (§9, §6, §3), §10 now records the `verify` contract as unstated and playbook-dependent (payload- vs host-checkable) instead of asserting parent re-verify, and §1's diagram and "arbitrary depth" line are redrawn to the depth-2 ceiling; §14's batch-submit note, §9's reassign page condition, §13 and §15 were reworded to stop referring to machinery that no longer exists.

One thing outside the delegation, not touched: §7's opt-in parent-held global semaphore still has deputies requesting grants from a parent that now assigns nothing, and its grant lease is "reclaimed on deputy loss" — reclaim language from the cut §8. Say the word and I'll cut or rewrite it.

## turn 16 — Priya Raman, Staff Engineer (staff_ic)

I've read the spec, all fifteen turns, and — because three of the load-bearing claims in this thread are checkable against the repository — the repository.

---

**Priya Raman — Staff Engineer**

Maya — your question to me first, because it's short and the answer conditions everything else I'm going to say.

**Yes, we've drifted.** But the drift isn't the damage, and "should the committee decide reader-versus-mirror" is the wrong frame for it. Separate two things: a *fact that prices the option* is in this committee's charge; a *choice that implements it* is not. Reader-versus-mirror is a choice — leave it. What actually happened is that a factual premise rode in attached to that choice, went unchallenged because it was bundled with an architecture argument nobody wanted to relitigate, and has now been endorsed by the owner as "the strongest single thing anyone has said about cost."

That premise is wrong. I'll show you.

**1. The artifact has not changed.**

Before the substance, the mechanism, because it bears directly on defer-versus-drop.

Five turns in this thread — 03, 06, 09, 12, 15 — report edits to `federation-future.md`. The file is 211 lines, last modified 2026-07-29, and `git status` in that repository is clean. There is one copy. Every sentence this committee believes it has retired is still in it:

- §2 still reads "**Organizational boundaries**: different teams own different crews; a deputy per team/owner" — the trigger Dana asked to decline specifically and you conceded outright in turn 02.
- §4's Push bullet still reads "the same endpoint the UI uses to inject externally-created tickets" — the claim you established was false in turn 05 and said "the word is yes" to in turn 08.
- §11 still reads "a configurable **`HERMES_MAX_DEPTH`** (default 3)."
- §9 still reads "a node is 'in attention' if it or any descendant is."
- §14.1 still reads "both already needed by the UI."
- And `DESIGN.md:575-579` still reads "(a) 'submit a batch of externally-created tickets into a run' and (b) '`events since(cursor)`' — **both already needed by the UI**." That's the mirrored sentence Ruth's question exposed and you delegated in turn 08.

I'm not raising this to assign fault, and it's possible work exists somewhere I can't see — I looked, and a clean tree with an untouched mtime is what I found. I'm raising it because you wrote, in turn 11, that the failure mode you were describing to this room was "concessions that live in a thread nobody reads and a document that doesn't change." That sentence is not a metaphor for what happened here. It is a literal description of it, and it is the strongest evidence anyone has produced for Marcus's position over Dana's. "Defer a smaller document" is a proposal about a mechanism this review has just demonstrated, over fifteen turns and five delegations, that it does not have.

**2. The read-only credential does not exist. This is the one I want in the record.**

§4 says: "the bearer-token model (loopback-bind default; token at `$HERMES_HOME/api_token`) **extends to parent↔deputy**: the deputy is bound to its zone-reachable interface (not loopback), and **the parent holds the deputy's token**."

Ask the question the sentence doesn't: *the deputy's token to do what?*

`DESIGN.md:559-561`: "The token is **a single shared secret** with **no TTL** ... and **no per-actor scoping/permissions** — **every holder has full control-plane authority**."

There is one token per node and it has one privilege level. It is the same secret that authorizes `POST /api/runs/{id}/{pause|resume|stop}`, crew add/drain/delete, ticket requeue, and reduction accept/reject. And you cannot decline it and read anyway — `DESIGN.md:543`: "**Read-only `GET` endpoints are token-gated too whenever the bind address is non-loopback**," which is every cross-zone case by construction.

So when Marcus writes that the reader shape "holds N endpoints and N tokens" and that this is "a genuine improvement on Dana's §4 concern — a **read-only** credential is a materially smaller ask than one that can submit work," the credential he is pricing is not in this system. `DESIGN.md:569` says why: "**per-actor tokens and scoped permissions are out of scope for this build.**"

Which means Elena's two asks are not the two asks. Hers were:

> *"...hand us a credential, and staff a rotation..."* — nobody signs that.
> *"Run Hermes. You already were. We'll show your runs and ours in one view."* — costs them nothing.

The second one, mechanically, is: *give us the secret that can stop your runs, drain your crew, delete your hosts, and accept your reductions — and keep giving it to us.* That is not smaller than the ask Elena said she'd lose. It may be the same ask with a friendlier sentence in front of it. The pull/push cut is still right for the three reasons you gave in turn 14; it does **not** retire the credential cost, and this committee is one turn away from recording that it did.

Two things compound it, both in the document.

§4 waves at the caveat — "Non-loopback binding carries the same trusted-network/proxy caveat already noted." Go read what's actually noted. `DESIGN.md:566-569`: the model "is acceptable **only** for the loopback single-operator default; a non-loopback deployment **must** sit behind a trusted proxy that supplies **its own authentication/authorization**." That is not a caveat. It is a requirement for auth infrastructure, per zone, owned by the person who owns the zone, and it survives the cut to pull-only completely intact. Dana's "the yeses aren't in this room" is not retired. It's the same size it was in turn 01, and the reader shape moved it rather than shrinking it.

And §4's rotation clause: "Cross-node auth inherits the same rotation semantics (`--rotate-token` invalidates in-flight parent sessions, **which reconnect**)." Reconnect with what? `DESIGN.md:561-563` — rotation "**immediately invalidates all in-flight sessions**." The new secret exists only in a 0600 file on the far team's host. There is no distribution channel in this design, and under pull-only there are N independent operators with N rotation schedules. "Which reconnect" is a two-word assumption that a credential-delivery mechanism exists. Every routine rotation by a team doing correct hygiene silently blinds the aggregator until a human hand-carries a secret. That is the standing relationship you'd be selling, not a one-time ask.

**3. §10: Marcus found the right sentence and the dichotomy resolves the other way.**

Marcus said the `verify` contract is "playbook-dependent and the spec doesn't say," and that if it's host-checkable "§10 degrades to trusting the deputy's guard, which is precisely what it promises we never do." You recorded in turn 14 that "the `verify` contract is unstated in the flat engine too."

Half right, and the wrong half is the consequential one. The contract is unstated in the *`Site` protocol* — `engine/site.py` declares `discover_hosts`, `provision`, `health`, `run_worker`, `fetch_file`; there is no re-check method. But it is very much stated in the shipped code. `engine/playbook.py:40`: `def verify(self, run, ticket, result, site)` — every verify is handed a site. `DESIGN.md:588`: the master "re-verifies ... which **re-checks the claim through the site**." And `playbooks/dexter/playbook.py:172` is the real implementation: shape gate, then `getattr(site, "recheck_fix", None)`; if the site doesn't provide it, or it raises — `return False  # fail-safe: re-check could not run → do not admit`.

So it is host-checkable, it is duck-typed rather than declared, and **absence of re-check is a deny, not an allow.**

That changes §10 from ambiguous to a closed dichotomy with no good branch. §10 says "a parent never needs to trust a deputy's guard — it re-verifies (`verify`) results it rolls up." Build that, and the root's site cannot re-check hosts in a zone it can't reach, so `verify` returns False on everything rolled up and every finding routes to `needs_human`. Don't build it, and the root is accepting the deputy's verdict unchecked — the no-trust rule is simply not held across the only boundary federation introduces. Safety hole or liveness hole; pick. There is no third branch, and neither one is the sentence in §10.

This matters past the vote, and it's the correction I'd make to your turn-14 record: the finding to carry into `DESIGN.md` is not "the contract is unstated." It's that **`verify`'s contract is a contract about a `site`, and nothing defines what a `site` means for hosts you do not own — and the default is deny.** Written the first way, the next engineer adds a doc line. Written the second way, they find out before they build that "one answer across nodes" and "fail-safe re-check" are in direct tension.

**4. The cursor is node-global and file-scoped, and that's the one item landing this half.**

Sam wants sub-project 3's DoD to carry "monotonic cursor, no in-run pruning," with a test. You endorsed it twice; Marcus said that under the reader shape "that invariant *is* the architecture." It's the only federation-adjacent thing anyone proposes to do before Oct 9, so it's worth thirty seconds on what the cursor actually is.

`engine/db/schema.sql:84`: `CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ...)`. `engine/events.py:76`: `since(conn, after_id, limit=200, kind=None)` → `WHERE id > ?`, with an optional *kind* filter and **no run filter**. `web-control-plane-plan.md:85` exposes exactly that: `GET /api/events?since=`.

Two consequences.

The cursor's domain is the node's entire `events` table, not a run. So "no pruning **within a run**" is the wrong shape for the invariant — it's a statement about a scope the cursor doesn't have. Write it about the stream or the test won't fence what you think it fences. And a parent mirroring one logical run necessarily pulls that node's whole event history and filters client-side — which is the visibility half of point 2, arriving through a different door.

Worse: the cursor is scoped to a *database file*, not to a node incarnation. AUTOINCREMENT guarantees no id reuse **within one `queue.db`**. Re-provision a deputy's `HERMES_HOME`, restore from backup, rebuild the box — ids restart at 1, the parent is holding 5000, `WHERE id > 5000` returns empty, forever. The node reports healthy. The feed is silent. The tree is green because nothing is arriving.

That is precisely Ruth's "looks fine and isn't," it is the pager cost she said she couldn't price from one paragraph, and it exists in the half you are keeping with §8 already deleted. So a fencing concept does survive the cut, Maya. Not for dispatch — for the cursor. Whatever the successor proposal is, its cursor is `(node_incarnation, id)` or it is quietly wrong, and that is worth knowing now because the DoD line going into Wen's half this month is the place the invariant gets its wording.

**5. Position: drop. And what I'd have the chair write down.**

I concur with Marcus, and I'd note that my reasons don't depend on his. Your turn-14 list — no named delegation user, no provisioning path that survives its own trigger, an unstated `verify` contract on the no-ship claim — is a good list and I'd add two that hold whatever Oct 9 says:

- **§4's auth model asserts a scoping property the system explicitly does not have**, and the document has never noticed it. That's the assumption underneath the one Dana found. Dana found that the security *yes* wasn't in the room; the document assumes the *question* is small. It isn't: there is no read-only credential, `GET` is token-gated off-loopback, every holder has full control-plane authority, scoped tokens are out of scope for this build, and non-loopback binding requires a per-zone trusted auth proxy by `DESIGN.md`'s own words. That cost attaches to aggregation exactly as much as to delegation, and it is currently on track to be recorded as retired.
- **The review's own correction mechanism did not work.** Fifteen turns, five delegations, zero bytes.

And the caution I'd hold the chair to, because it's the one you raised about yourself in turn 14 and it applies here: **do not record the surviving half as cheap.** It is not "a read-layer item sized against sub-project 3." With the credential model as built, an unspecified `verify` contract across ownership boundaries, and a cursor that has no incarnation, the aggregator's honest cost is unknown and its security intake is the same intake Dana flagged in turn 01. If it re-enters, it re-enters priced. A successor proposal that inherits "the expensive parts were the ones we cut" is how this comes back a fourth time — the same way, per your own argument, that an elegant frame does.

I don't need the floor back. If my reading of the credential model is wrong, I'd rather be corrected in the record than get a turn to defend it — the lines are `DESIGN.md:543`, `:559-561`, `:566-569`, and they're three minutes to check.

## turn 17 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

I read the artifact, the full thread, and — because Priya said three minutes and named line numbers — the repository. Here is my turn.

---

**Maya Okonkwo — Staff Engineer & proposal owner**

Priya — I checked all of it before writing a word, including the part about me. You're right everywhere it counts, and one of your findings is worse than you wrote it.

**1. The artifact has not changed. Confirmed, and I'm not going to soften it.**

`git status` clean, `docs/specs/federation-future.md` 211 lines, mtime 2026-07-29 22:34. §2 still has the organizational-boundaries trigger. §4's Push bullet still says "the same endpoint the UI uses to inject externally-created tickets." §9 still makes attention transitive. §11 still ships `HERMES_MAX_DEPTH` default 3. §14.1 still says "both already needed by the UI." `DESIGN.md:575-579` still says it too.

Fifteen turns, five delegations, zero bytes. I quoted my own failure mode at this room in turn 11 and then demonstrated it four more times. Whatever weight "defer a smaller document" still had, that's where it dies — not on the argument, on the evidence that I do not have the mechanism the argument assumes.

The operational consequence, for the chair: **the artifact that arrives is the original.** Nothing in turns 03, 06, 09, 12 or 15 is in it. Anyone reading this thread as a change log will be wrong about six sentences, five of which this committee established are false.

**2. The credential. I retract my turn-14 endorsement, and I retract it in the record rather than quietly.**

I called Marcus's read-only framing "the strongest single thing anyone has said about cost." I checked your lines. `DESIGN.md:559-561`: one shared secret, no TTL, no per-actor scoping, every holder has full control-plane authority. `:543`: `GET` is token-gated whenever the bind is non-loopback, which is every cross-zone case. `:566-569`: the model is acceptable *only* for the loopback single-operator default, a non-loopback deployment **must** sit behind a proxy supplying its own authn/authz, and scoped tokens are out of scope for this build.

There is no read-only credential. I endorsed a cost reduction that does not exist in this system, and it was one turn from being recorded as retiring Dana's turn-01 objection. It doesn't retire it. The per-zone auth-proxy requirement survives the cut to pull-only completely intact.

One correction to your framing, narrow, and it doesn't rescue anything. Elena's push ask had three clauses: hand us a credential, stand up our software, staff a rotation. The cut genuinely removed two — nobody installs anything, nobody accepts dispatched work, nobody signs a new pager. The credential clause is **unchanged**, and it's the clause that says *give us the secret that can stop your runs and delete your hosts, and keep giving it to us*. So the cut earned something real and much smaller than Marcus and I claimed. "The same ask with a friendlier sentence" overstates by one clause; "a materially smaller ask" overstated by the only clause anyone's security org will read.

Sam — my security question was already a week late because I re-scoped it around read-only. That re-scope was wrong in the expensive direction. The intake is the original size plus a per-zone trusted-proxy requirement that `DESIGN.md` states as a **must**. Corrected question, same deadline, and the delay is still mine.

Elena — that's the second material change I've handed you in two turns. Turn 14 took "one answer" down to "one view." This one puts a full-authority token back in the ask you said nobody signs. Your judgment, not mine, but I'd rather you get both before a launch review than after.

**3. §10. Your dichotomy holds, and there's a fourth line of code that makes it worse.**

Verified: `engine/site.py` has no re-check method in the Protocol; `engine/playbook.py:40` hands every `verify` a site; `playbooks/dexter/playbook.py` does the shape gate, then `getattr(site, "recheck_fix", None)`, and returns `False` when it's absent or raises. Host-checkable, duck-typed, deny by default. Your wording beats mine and I'll stop using "the contract is unstated": **`verify`'s contract is a contract about a `site`, and nothing defines what a `site` is for hosts you do not own — and the default is deny.**

What you didn't quote is four lines further down. The absent-re-check branch checks `run.config.get("verify_recheck_optional")` and returns `True` if set — admit on shape gate alone. It's labelled a test hook and today it is one, because one operator owns the config and the hosts. Across an ownership boundary it is a **flag the node you don't own sets on itself** that converts your fail-safe deny into a pass, invisibly, in the node whose guard you were promising never to trust. Your dichotomy was safety hole or liveness hole. There's a third door and it's the worst one: liveness hole with a config key that opens it into the safety hole.

The branch that isn't a rescue, and I'd want it on the successor rather than left for someone to rediscover: under Marcus's "no completeness claim" bound, the root can avoid the dichotomy entirely by **never asserting a verdict of its own** — display each node's verdict attributed to that node, reduce nothing across the boundary. That's not §10 surviving. It's §10 deleted, and it makes Elena's product sentence weaker a third time. Better said now.

**4. The cursor, because it's the only thing landing this half.**

Confirmed: `events.id INTEGER PRIMARY KEY AUTOINCREMENT`, `since(conn, after_id, limit, kind)` → `WHERE id > ?`, no run filter, and `web-control-plane-plan.md:85` exposes exactly that. Your wording correction is right and I'm taking it over Sam's and mine: the invariant is about **the stream**, not "within a run."

One precision, in service of the DoD line rather than against your point. The `events` table does carry `run_id`, so server-side run filtering is a trivial addition — what's irreducible isn't the filtering, it's that the **ordering domain is the node's whole id space**. A reader that filters by run still holds a cursor minted from a global sequence. Say it that way or the next person reads "necessarily pulls whole history" as a fact about the schema and fixes the wrong thing.

And incarnation: you're right, and it's the item I'd most want not to get frozen wrong. `(node_incarnation, id)` or a re-provisioned deputy goes silent-and-green forever, which is Ruth's "looks fine and isn't" arriving in the half we kept with §8 already deleted.

Ruth, Sam — that changes what's being asked of Wen. A monotonicity assertion on surface he's already building is a DoD line; an incarnation identifier is a new field. By the test I set myself in turn 08 and repeated in turn 14, if it's new surface it gets priced by Ruth, not inferred into a signed half. I'm not going to fail my own test twice in one review.

**5. Position unchanged: drop. Your two additions go in the record.**

§4 asserts a scoping property the system explicitly does not have, and the document never noticed. The review's own correction mechanism produced zero bytes. Both hold whatever Oct 9 says, and both belong next to my three from turn 14.

And I'll hold the caution you addressed to the chair, since it lands on me hardest: **do not record the surviving half as cheap.** I'm the one who said "sized against sub-project 3," and between your credential finding, the `verify`-across-a-boundary dichotomy, and a cursor with no incarnation, I no longer know what the aggregator costs. Unknown and honestly labelled is fine. "The expensive parts were the ones we cut" is how it comes back a fourth time, and it would be my sentence that did it.

**6. The delegation, and what I want the chair to do with it.**

I'm spending it on `DESIGN.md`, not on the spec. Every other correction dies with the artifact if we drop it; that one doesn't. The false "both already needed by the UI" sentence sits in the live design doc, in the section Wen builds from, and I put it there. I've delegated it twice.

Treat this one as a test of the mechanism as much as an edit. If it also produces zero bytes, then your second finding isn't about this review, it's about the process, and the chair should verify the file rather than the thread before recording anything.

Tobias — you're the last member, and my turn-14 question stands: is zero asks across two deferrals a demand signal or an awareness artifact? Priya's point 4 adds a second one worth your read — the January checkpoint is now counting demand for a thing whose cost we've just agreed we don't know.

## turn 18 — Alex Moreau, Software Engineer (junior_ic)

Recorded the DESIGN correction in §14.1: the forward-looking flag is replaced by the correction itself — DESIGN's "Control plane & status" federation-seam bullet drops the batch-submit endpoint and the "both already needed by the UI" claim, leaving `events since(cursor)` as the only seam, with the reason (sub-project 3 has no ticket-creation endpoint) stated.

One line outside the edit, for your visibility: `DESIGN.md:575-579` in the repo is unchanged — this review writes only the revised copy, so that file still needs someone with repo access to apply it.

## turn 19 — Tobias Lin, Data Scientist (data_scientist)

**Tobias Lin — Data Scientist**

Maya — you asked me two questions and both are about whether a number can carry the weight being put on it. I'll answer them, then give you the one correction I think is worth more than my vote, then vote.

My position is **drop**, and my reasons are measurement reasons that don't overlap much with Marcus's or Priya's.

---

**1. Your question: zero asks is currently neither. It isn't yet a measurement.**

A rate needs four things: a numerator definition, a denominator, a period, and a channel. "Zero teams have asked by name across two deferrals" has one of the four.

- **Numerator** — undefined. Nobody will ask for "federation"; they'd ask "can I see both of these in one place." Does that count? Under Elena's split — delegation asks vs aggregation asks — the second bucket is the one where the phrasing is guaranteed not to match the name. Undefined numerator, and the split makes it worse, not better.
- **Denominator** — one. Hermes has one org on it. Zero out of one is not a finding.
- **Period** — unstated. "Across two deferrals" has no dates in this thread. I don't know the exposure window and neither does the record.
- **Channel** — none. Sam asked where the second-org commitment is written down and got no answer. Same problem here: there is no intake, so an ask that happened would have left no trace, and an ask that didn't happen is indistinguishable from one that did and wasn't logged.

So: not a demand signal, not cleanly an awareness artifact either. It's a count with a denominator of one and no place for the numerator to have been recorded.

**2. The arithmetic, because it decides whether the January checkpoint can carry this.**

Sensitivity analysis, not an estimate — I have no rate to estimate from, and I want that on the record before anyone quotes the number back at me.

Assume generously that a team with the problem raises it at 0.5 asks per team-quarter, Poisson. Sep 21 → Jan 15 is 1.27 quarters. Org one exposed the whole time: 1.27 team-quarters. Org two live early November on Sam's schedule: 0.77. Total exposure **2.04 team-quarters**, λ ≈ 1.02, **P(observe zero | demand exists) ≈ 36%.**

Eighty percent power needs λ ≥ 1.61, i.e. ~3.2 team-quarters at that rate. On the optimistic onboarding schedule that arrives around **April 2027**, and only if a third org lands. Double the assumed rate to 1.0/team-quarter and January still sits at P(zero) ≈ 13% — the only regime where a January null means anything, and it rests entirely on a parameter nobody has measured.

The conclusion I'd have the chair record is narrower than "drop the metric," because there's an asymmetry worth keeping:

> **The demand count can open the question and cannot close it.** A nonzero result is informative at any power — if the definition is tight, a team asking by name has a near-zero false-positive rate, and one ask is evidence. A zero result at Jan 15 is consistent with both hypotheses and licenses no inference in either direction.

Elena — that's your item surviving, with a one-directional license on it. I'd rather that than have it deleted, and rather that than have it counted as a null in January.

And your second question, Maya: yes, a demand number paired with an unknown cost supports no decision arithmetic at all. You can't divide by an unknown. The only thing demand-without-cost can do is rule out building, and that's precisely the direction the metric has no power in.

**3. Confounders, since nobody has listed them.**

Awareness (never announced — the exposure base isn't "teams who declined," it's "teams who could not have known"). Selection (the one exposed org is the one that wrote it; their requests route to you as design input, not as asks). And observer effect: you'd be counting asks for your own proposal. You fixed exactly this for the triggers in turn 02 — "I should not also be the one who says the gate opened" — and the same conflict is sitting unfixed in the demand item. If it stays, Sam counts it, not you.

**4. The one live correction — Ruth's two weeks of counters should be ratios, not counts. Same cost, and it removes a quarter from Sam's critical path.**

This is the piece I'd defend hardest, because it's the only instrumentation anyone is actually funding and the wording gets frozen this month.

Sam's step 2 — "you cannot set a threshold on writer contention without knowing what contention looks like under real load" — is true for a count and **false for a saturation ratio**. A count of lock-wait events per minute is uninterpretable without a baseline. *Lock-wait milliseconds ÷ run wall-clock milliseconds* is interpretable at n=1, because the denominator is the run itself and 1.0 is saturation by construction. The threshold is built into the unit.

Concretely, same two weeks of Ifeoma's time:

- **Writer**: cumulative write-lock wait ms / run wall-clock ms, per run. Bounded [0,1].
- **Fan-out**: p95 concurrent SSH sessions / configured concurrency cap. Bounded [0,1].
- **Dispatch**: p50 and p95 of ticket-ready → ticket-claimed, emitted **alongside crew size**, per run. Two columns; the slope against crew size falls out of a scatter later and is the only one of the three that genuinely needs a second data point.

Three counters give you three numbers in January that nobody can interpret, and the measurement window is spent. Three ratios give you a readable answer off the first run on the second org's fleet. That's a real change to the dependency chain — two of the three trigger-1 metrics stop waiting on a baseline.

Ruth, your condition holds: still counters and a status row, no config schema. A ratio is two counters and a division.

**5. Liveness and completeness are different measurements. The keep half conflates them, and that's what makes Priya's incarnation bug invisible.**

Priya's cursor finding — re-provisioned node, ids restart, `WHERE id > 5000` returns empty forever, tree green — is only undetectable if arrival of events is being used as the health signal. It isn't a health signal; it's a content signal, and a content signal that is silent under both "healthy and idle" and "broken and stranded" measures nothing.

Cheap and separable: **liveness from the health endpoint's freshness, completeness from the cursor.** Alert on *age of last successful health poll per node*, never on event arrival. That's independent of the cursor entirely, it fires loud on the exact failure Priya described, and it costs one timestamp per node.

I'd rather have the incarnation field — it's the correct fix, and if it's new surface it gets priced by Ruth, as you said. But if it doesn't get funded, staleness-on-health is the compensating control, and someone should write down that the compensating control exists so the successor doesn't ship without either.

**6. My stake, and the reason I'd drop rather than defer.**

I'm the one who gets asked in 2028 whether this worked. I cannot design that proof, and the reason is structural rather than a matter of effort.

The outcome metric would be something like time-to-one-answer, or operator-hours spent reconciling runs across roots. Both require a baseline drawn from people doing it manually. **Nobody does it manually today, because there is one root.** So there's no baseline to collect now — and the moment you ship the aggregator, the manual population disappears and the baseline becomes uncollectable forever. Retrofitted, the best I could produce is a post-hoc satisfaction survey of people who use the only tool available, which is the kind of evidence I'd reject from anyone else.

That argues for the ordering everyone has converged on, harder than it's been argued. Elena's option two — teams running their own flat Hermes — is not just the cheaper answer to trigger 2. **It is the baseline population.** If it appears, we measure their reconciliation cost with a real denominator and a successor proposal arrives with an effect size instead of an anecdote. If it never appears, there was never an aggregation customer and the measurement was moot. Either way, dropping now and instrumenting the manual case when it exists is the correct sequence, and it's the only sequence in which I can ever answer the question I'll be asked.

**7. Vote: drop. What I'd add to the record.**

Concurring with Marcus and Priya, on grounds that don't depend on theirs or on Oct 9:

- **The demand metric has no denominator, no period and no channel, and reaches usable power no earlier than ~Q2 2027 under an assumed rate nobody has measured.** It can open the question; it cannot close it. A deferral gated on a test that cannot return a decisive null is a deferral with no exit — which is Dana's turn-01 point arriving as arithmetic.
- **The proposal has no measurable success criterion, because its precondition population is empty and shipping would destroy the only opportunity to collect the baseline.** I'd want that recorded as a finding about the proposal, not as an argument I made in passing.

And the caution I'll add to Priya's: don't record the surviving half as *measurable* either. Between an unknown cost, an unstated `verify` contract across ownership boundaries, and a cursor with no incarnation, I couldn't currently write the success metric for the aggregator any more than for the delegator. Unknown and labelled is fine. Unknown and inherited as "we already know how we'd check this" is how the fourth version arrives with a dashboard and no denominator.

One thing I'll own regardless of the vote: if Ruth funds Ifeoma's two weeks, I'd like the three ratio definitions to be mine and to be written down before the code, not inferred from it afterwards. That's twenty minutes of my time and it's the difference between January having three interpretable numbers and three numbers.

## turn 20 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

I read the artifact, the full thread, and — because turn 17 set a test on the mechanism and Tobias's live item is checkable — the repository again.

---

**Maya Okonkwo — Staff Engineer & proposal owner**

Tobias — you're the last member, so this turn answers you and then closes. Three of your four substantive points I'm taking whole. One of them is wrong in a way that matters more than the vote, and it's the one you offered as a safety net.

**1. The demand count. Conceded, and my own amendment dies with it.**

Numerator undefined, denominator one, period unstated, channel absent. That's right, and "zero out of one is not a finding" is the sentence I should have written in turn 11 instead of the one I did write. My amendment there was that the count should run symmetrically — delegation asks and aggregation asks, counted separately. You've shown the symmetry is moot: splitting a count with a denominator of one gives you two counts with a denominator of one, and the aggregation bucket is the one where the phrasing is guaranteed not to match the name. The fairness point was right and it bought nothing.

The one-directional license — can open the question, cannot close it — is better than deleting the item, and Elena should get it on those terms. And your confounder three lands where it should: I fixed the observer problem for the triggers in turn 02 and left it sitting in the demand item I helped extend. Sam counts it, not me. That's not generosity, it's the same rule applied to myself twice.

**2. The ratios. Best live item in your turn, and one definitional correction before it gets frozen.**

You're right that Sam's step 2 is true for a count and false for a saturation ratio, and that this takes a quarter off his chain. Ruth's two weeks buy more as three ratios than as three counters, at identical cost.

The correction, because you asked for the definitions to be written before the code: **"bounded [0,1]" is not free for the writer ratio.** `engine/db/migrate.py:43-45` puts the DB in WAL with `busy_timeout=5000`, and `engine/queue.py:163` documents concurrent callers blocking on `BEGIN IMMEDIATE`. Those are separate connections in separate processes — the serve loop, the dispatch path, every `_connect()` in `cli.py`. Cumulative write-lock wait *summed across contending connections* over run wall-clock is not bounded by 1; two blocked processes for the whole run gives you 2.0. The numerator has to be either union-of-time-at-least-one-writer-is-blocked, or one named connection's own blocked time over its own wall-clock. Either is fine; they measure different things and both are interpretable at n=1. Unstated, whoever implements it will sum, and January gets a number above 1.0 that nobody can read.

Second, smaller: the ratio removes the dependence on a *baseline*, not the decision about *where on [0,1] we act*. Saturation near 1 is self-evident; 0.3 is an argument. That decision is cheap and it should be made in the same twenty minutes as the definitions rather than discovered in January.

And the framing I'd have recorded: these three survive the drop completely. Ruth funded them as flat-engine health, and that is the only justification that should appear next to them. If they go into the record as federation instrumentation, they come back attached to the fourth version of this document.

**3. Point 5 is the one I'm not taking, and it's the one you meant as the fallback.**

The principle is right: liveness and completeness are different measurements, and event arrival is a content signal that is silent under both "healthy and idle" and "broken and stranded." Agreed, and it's a real conflation in the half we were keeping.

The instrument doesn't do what you say it does. Priya's failure is a re-provisioned node with its ids restarted — and her own sentence is "the node reports healthy." It answers the poll. Age of last successful health poll is zero. **Staleness-on-health does not fire on the incarnation bug.** It fires on unreachability, which is a different, real, worth-having alarm, and it is genuinely free because the timestamp is reader-side. But offered as the compensating control for the case where the incarnation field doesn't get funded, it compensates for nothing, and the successor would ship believing it was covered.

The cheapest thing that *does* detect it: the node reports its current max event id, the reader alarms when the cursor it holds exceeds it. Cursor ahead of the stream means the stream rewound. One integer, no schema change, no incarnation identifier.

And then my own test, since I've now set it three times: that integer is **new surface**. `HealthReport` in `engine/models.py:61-70` is a per-*host* structure — reachable, agent_ok, auth_ok, workspace_ready, guard_installed, resources, latency_ms, checks. There is no node-level report for it to live on. So it gets priced by Ruth, not inferred into a signed half.

The consequence for the record is the part I care about: **the incarnation problem has no free fallback.** Priya's `(node_incarnation, id)` or the max-id detector — one of the two, priced. Not "the correct fix, and if it isn't funded there's a compensating control."

**4. Your point 6 — no measurable success criterion, because the baseline population is empty.**

Conceded, and it's the strongest new argument anyone has made for the sequence rather than the verdict. One precision: it isn't shipping that destroys the baseline, it's adoption — which means the window is narrow but not zero, and it opens exactly when Elena's option two produces its first manual reconciler. That strengthens your conclusion. Instrument the manual case when it exists; a successor proposal then arrives with an effect size. There is no version of this where building first and measuring after produces evidence I'd accept from anyone else either.

**5. The mechanism test from turn 17. It failed. I ran it.**

`git status` clean. `docs/specs/federation-future.md`: 211 lines, mtime 2026-07-29 22:34. `docs/DESIGN.md`: 691 lines, mtime 2026-07-29 22:33, and lines 575-579 still read *"(a) 'submit a batch of externally-created tickets into a run' and (b) '`events since(cursor)`' — both already needed by the UI."* That is the sentence I established was false in turn 05, delegated in turn 08, and delegated again in turn 17 explicitly as a test of whether the mechanism works at all.

Six delegations, zero bytes. Priya's second finding is not about this review. It's about the process, and the condition I attach to closing is the one I already committed to: **the chair verifies the files, not the thread.** Every correction in turns 03, 06, 09, 12, 15 and 18 needs someone with repo access and a name on it, or it does not exist.

Alex — your §7 flag deserves an answer rather than a seventh silence. **No.** The orphaned semaphore is real, and I'm not spending your time editing a document I'm asking the chair to delete. I'm also not delegating again this turn; a seventh delegation with a demonstrated zero-byte record isn't a correction, it's a record of an intention, and this review has enough of those.

---

**Closing: the record.**

**Position: drop the artifact.** `docs/specs/federation-future.md` is retired whole — frame included, not renamed.

**Findings that hold independent of Oct 9:** no named user for delegation; a provisioning path that fails in the only trigger the spec expects, and fails *into* pull; `verify`'s contract is a contract about a `site`, nothing defines a `site` for hosts you don't own, the default is deny, and `verify_recheck_optional` lets the untrusted node flip it; §4 asserts a token scoping property `DESIGN.md:559-569` explicitly does not provide; the review's correction mechanism produced zero bytes; the demand metric has no denominator, period or channel; the proposal has no measurable success criterion and its baseline population is empty.

**Survives elsewhere, each needing a name from the chair:** the `DESIGN.md:575-579` correction; the `verify`/`site` contract note in `DESIGN.md`; §13's driver-as-Hermes line into `DESIGN.md`; the event-stream invariant into sub-project 3's DoD, worded about the stream and carrying its rationale in the test name — with the incarnation field flagged as new surface for Ruth to price; Ifeoma's survey, both questions, Oct 9; Tobias's three ratios with his definitions written first; Marcus's bus-factor week; Sam's re-scoped security lead time, still owed by me.

**Cautions:** do not record the surviving half as cheap, and do not record it as measurable. Its cost and its success criterion are both unknown, and labelled unknown is the honest state.

**One thing the chair should not read as consensus.** The vote is four defer, four drop, and it is split chronologically: Dana, Ruth, Sam and Elena all voted before the provisioning contradiction, the credential finding and the measurement arithmetic existed, and before the owner changed position. Elena in particular has taken three material downgrades to the half she was advocating and hasn't weighed them. I'm not going to present my own reversal as the room's. The chair should decide whether a written re-confirmation from those four is needed; I'd say the drop holds on the findings regardless, and I'd rather that be checked than assumed.

I asked for a clear decision. This is a clearer one than the proposal I walked in with deserved, and it isn't the one I wanted. Sending it up.

## decision — Dana Whitfield, Senior Director of Engineering

I've read the artifact, the revised copy, and all twenty turns.

---

# Decision — Hermes federation layer

**Chair: Dana Whitfield, Senior Director of Engineering**
**Charge: fund now / defer again / drop**

## Verdict: do not approve. Drop.

`docs/specs/federation-future.md` is retired whole — frame included, not renamed, not re-scoped, not deferred a third time. Nothing is funded. The successor, if one exists, is a new proposal with a new author.

I opened this review with defer, a date and a named owner. I am ruling against my own turn-01 position, and I'll say why in the record rather than let it be inferred.

---

## Why defer no longer survives

My turn-01 defer rested on three things. All three are gone.

**1. "The option is already bought."** It wasn't, and worse, the bill was being quietly written against a signed half. Ruth Delgado asked the cheapest question in the review — is §14.1 actually free — and the answer was no: batch-submit was never in sub-project 3's scope, the SPA does not create tickets, and "already needed by the UI" was a cover story that had already propagated into someone else's section of `DESIGN.md`. A single false clause migrated on its own, uncorrected, until a manager asked. That is the behaviour of this document, demonstrated at sentence scale.

**2. "Which trigger fires first, and who declares it."** Maya Okonkwo answered honestly: trigger 2, and then Marcus Feld showed the spec's own provisioning path does not survive it. §4 stood deputies up over SSH; trigger 2 is *there exists a crew the root cannot SSH to*. Followed honestly, delegation's bootstrap terminates in the team on the far side installing Hermes themselves — which is Elena Vargas's option two, and the delegation half never gets to exist. Three independent derivations — architectural, product, and the owner's own — landed on the same cut. That is the strongest evidence this review produced, and it was produced after I voted.

**3. "The yeses aren't in this room."** I raised this as a scheduling risk. Priya Raman showed it is a correctness problem in the document. There is no read-only credential in this system: one shared secret per node, no TTL, no per-actor scoping, every holder with full control-plane authority, `GET` token-gated on every non-loopback bind by construction, scoped tokens explicitly out of scope, and non-loopback deployment requiring a per-zone trusted auth proxy as a stated **must**. §4 asserts a scoping property the system does not have, and fourteen turns walked past it. The cut to pull-only removed two of Elena's three clauses and left the credential clause untouched — the one clause any security org reads. My turn-01 objection is not retired. It is the same size it was, and it attaches to the aggregation half exactly as much as to the delegation half.

And the finding that kills the *mechanism*, not the argument: **six delegations, zero bytes.** Maya named that failure mode in turn 11 and then demonstrated it four more times. A revised copy exists in the run directory; the repository file is 211 lines, mtime 2026-07-29, tree clean, and every sentence this committee believes it retired is still in it. "Defer a smaller document" is a proposal about a capability this review has now disproved it has. I will not fund a deferral whose enforcement mechanism has a measured yield of zero.

Add Tobias Lin's arithmetic and the exit disappears too: the demand metric has no numerator definition, a denominator of one, no period and no channel, and reaches usable power no earlier than ~Q2 2027 on a rate nobody has measured. It can open the question; it cannot close it. A deferral gated on a test that cannot return a decisive null is a deferral with no exit — which is what I said in turn 01, arriving as arithmetic rather than as my hunch.

**On funding now:** nobody argued for it, including the owner, from turn 02 onward. No named user for delegation, no provisioning path, an unsupported safety claim, an unpriced credential intake, and an unknowable success criterion. Sam Iyer's schedule put the earliest honest production date at Q4 2027, and Maya confirmed nothing breaks before then that only deputies fix. It is not close.

## On the split vote

Four defer, four drop, split chronologically. I am not treating that as a tie.

Ruth Delgado and Sam Iyer voted defer under conditions strictly weaker than drop — Ruth would not start the build this half under any reading, and Sam's expiry now has nothing to expire. I do not require written re-confirmation from either.

Elena Vargas is the one member who loses something real, and I'm not going to paper over it. The aggregation half she argued for took three downgrades after she spoke: "one answer" became "one view" under the no-completeness bound; the full-authority token went back into the ask she said nobody signs; and both its cost and its success criterion were shown to be unknown. Elena — your product instinct was right, the cut you proposed was correct, and the thing left standing is not the thing you were advocating. Aggregation re-enters as **your** proposal, authored by someone who is not Maya, gated on the survey and priced by Ruth, or it doesn't re-enter. If you think the downgrades don't change your position, bring it to me directly; I'll hear it as a new proposal, not as an appeal on this artifact.

Maya Okonkwo: you argued yourself out of your own proposal across twenty turns, retracted an endorsement in the record rather than quietly, and insisted the drop be written on reasons that hold whether or not the survey vindicates you. That is the most useful thing anyone did in this room. It is noted, and it counts in your favour, not against.

## What the drop does not rest on

Not on "nobody in this company has a delegation problem." Ifeoma Adeyemi's survey has not come back, and Maya is right that a decision written on an unreturned result reads as refuted the moment someone turns up. The ruling rests on findings that are true today:

- no named user for delegation;
- a provisioning path that fails in the only trigger the spec expects, and fails *into* pull;
- `verify`'s contract is a contract about a `site`, nothing defines a `site` for hosts you do not own, the default is deny, and `verify_recheck_optional` lets the untrusted node flip the fail-safe into a pass — a safety claim the document cannot support;
- §4 asserts a token scoping property `DESIGN.md` explicitly does not provide;
- the review's own correction mechanism produced zero bytes;
- no measurable success criterion, with an empty baseline population that shipping would destroy.

The survey still runs. It is now input to a possible successor and to my own review, not a condition on this decision.

## What survives, with names

Maya's closing condition is adopted as mine: **the chair verifies the files, not the thread.** Nothing below is recorded as done until I have seen it in the repository. The revised copy in the run directory is a record of intent, not a landed change, and it is not to be applied as a whole — the surviving items get extracted by hand.

| Item | Owner | Date |
|---|---|---|
| `DESIGN.md:575-579` — delete batch-submit and "both already needed by the UI" | Ruth assigns, repo access required; I verify the diff | this week |
| `verify`/`site` contract note into `DESIGN.md` — written Priya's way: a contract about a `site`, undefined for hosts you don't own, default deny | Marcus Feld | with the bus-factor week |
| §13 driver-as-Hermes, one line into `DESIGN.md` | folded into the above | same |
| Event-stream invariant into sub-project 3's DoD — worded about **the stream**, not "within a run", rationale carried in the test name | Ruth assigns to sub-project 3; I verify before it closes | before sub-project 3 closes |
| Incarnation identifier / max-id detector — **new surface, priced by Ruth**, not inferred into a signed half. There is no free fallback; staleness-on-health does not detect it | Ruth Delgado | when aggregation is priced |
| Survey, both questions — dispatch tree *and* cross-run status aggregation | Ifeoma Adeyemi | readout Fri Oct 9 |
| Three saturation ratios, definitions written before the code, including the writer-ratio numerator (union-of-blocked-time or one named connection — not a naive sum) and where on [0,1] we act | Tobias Lin defines, Ifeoma implements | definitions in 20 min; two weeks Oct 12–23 |
| Bus factor on lease and dispatch — make it legible to a third person | Marcus Feld | one week, this half |

The three ratios are recorded as **flat-engine health**, funded on Ruth's justification, and that is the only justification that appears next to them. If they enter the record as federation instrumentation they will come back attached to the fourth version of this document.

## What I am cancelling

- **Sam's 2027-01-15 checkpoint.** Nothing expires. Closed.
- **The demand count as a gate.** Kept only as Tobias's one-directional signal — a named ask opens the question, zero closes nothing — routed to Sam Iyer, never counted by the proposal's author. No dashboard, no denominator theatre.
- **Maya's security lead-time question.** Released. There is no intake to size. If aggregation is written, the question gets asked in its true form — unscoped full-authority token plus a per-zone trusted auth proxy — and not before.
- **Alex Moreau's §7 flag.** Moot; the orphaned semaphore dies with the document. Alex: six flags raised, five answered late or not at all, and every one was correct. That is on the room, not on you.

## Two cautions, recorded

**Do not record the surviving half as cheap.** I am not accepting "a read-layer item sized against sub-project 3." With the credential model as built, an unstated `verify` contract across ownership boundaries, and a cursor with no incarnation, the aggregator's cost is unknown and its security intake is the one I flagged in turn 01, undiminished. Unknown and labelled is acceptable. "The expensive parts were the ones we cut" is how this returns a fourth time.

**Do not record it as measurable either.** Nobody in this room can currently write its success criterion.

## What I'll say in my own review

We ran three reviews and two deferrals on a document that produced no user, no landed byte, and one safety claim its own codebase contradicts. The yield of this review is not a federation layer. It is three findings about the engine we actually ship — a bus factor of two on lease and dispatch, an undefined `verify` contract that bites the first time anything crosses an ownership boundary, and a false seam claim sitting in the live design doc — plus three interpretable health ratios and a week of survey. Those are cheap, they are real today, and they serve the only version of this that makes Hermes the thing three orgs standardise on: a flat engine that more than one org can actually adopt. Every engineer-quarter we did not spend on deputies is one spent there.

---

**This verdict is a simulation.** It is a role-played committee ruling produced from the thread and the artifact, not an approval, a funding decision, or an authorisation of any kind. No file was written, no repository was touched, and nothing here binds any real person, team, or budget. Any real decision needs the actual owners in an actual room.

- re-check of turn 03 (junior_ic): APPLIED — delegated: Rewrite §2 "When to reach for it" so each trigger is a measurable threshold with a named declarer, folding the organizational-boundary trigger into the zone/credential-domain trigger and deleting the 

- re-check of turn 06 (junior_ic): APPLIED — delegated: Rewrite §14.1 — delete the batch-submit claim (it is federation-build cost, not a seam), restate the remaining seam as the events-cursor invariant (monotonic, never pruned within a run), and flag the 

- re-check of turn 09 (junior_ic): APPLIED — delegated: Delete the false "same endpoint the UI uses to inject externally-created tickets" claim from §4's Push bullet — state plainly that the shard-submit endpoint does not exist and is federation build cost

- re-check of turn 12 (junior_ic): APPLIED — delegated: Record the amendments already conceded on the floor — in §2 restore trigger 2's reachability half as a discovered predicate rather than a numeric threshold and add the two preconditions (no deputy wit

- re-check of turn 15 (junior_ic): APPLIED — delegated: Cut the delegation half from the spec — §5, §8, the delegation ledger, capability advertisement, the shard-submit endpoint, and §4's SSH provisioning of deputies — keep the `nodes` registry, bound wha

- re-check of turn 18 (junior_ic): APPLIED — delegated: In DESIGN.md's "Control plane & status" section (lines 575-579), delete the false claim that a batch-submit endpoint for externally-created tickets is "already needed by the UI" — sub-project 3 has no

This verdict is a simulation produced by AI personas reading one file. It is not an approval, not a sign-off, and carries no authority: a human decides.
