# Committee — run-9

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

Maya, the spec is well put together. That isn't what I'm deciding, though. A good design and a fundable one are different bars, and I'm the one who'll be asked in my own review why we paid for this.

Here's how it looks from three orgs up:

- **No trigger has fired.** Your own rule is "don't build until a trigger fires," and the doc doesn't claim any has. The charge says "defer it *again*," so we've been here before, and there's still no measurement.
- **No headcount line.** Most of the real distributed-systems cost sits in two places: the §15 "not built now" list, and the open questions (fencing epochs, clock skew on leases, back-pressure). None of it is priced. Neither is the permanent on-call for a tree of nodes.
- **Reorgs.** Trigger three builds the org chart into the topology: one deputy per team. The next reorg reshapes the tree, and the delegation ledger ends up pointing at owners who've moved. The §14 seams survive a reorg. I'm not convinced a tree keyed to teams does.
- **Who else.** There's no section on who else already handles fan-out across regions. If the company's existing schedulers already cover geography, trigger two isn't ours to build.
- **Auth needs a yes from outside this room.** DESIGN §10 describes a single shared token with no expiry and no per-actor scoping, and the workers run `bypassPermissions`. §10 says binding beyond loopback is only acceptable behind a trusted proxy. Your §4 extends that model to a parent holding a deputy's token across security zones. It carries the caveat forward without resolving it. Security won't sign that off just because we did.

I'll name my bias. I want Hermes to be the engine other orgs plug into, and federation is exactly how that would happen. That's why I won't fund it on the strength of a spec.

Two questions.

First: which of your three triggers has actually fired, and what's the measurement? SSH fan-out, SQLite writer contention, reduce CPU, or the concurrency cap?

Second, and this one decides it for me: who outside this room has asked for a deputy? I mean another org's crew owner, not us. And has their security owner agreed to a parent holding a full-authority token to their fleet?

## turn 02 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

Dana, straight answers first.

**Which trigger has fired?** None. There's no measurement, and the doc doesn't claim one. Our largest real workload, dexter fanning out across devservers, sits inside §2's own "flat is correct" case.

**Who outside has asked?** Nobody. No crew owner from another org has asked for a deputy, and no security owner has agreed to anything.

So I'm not asking you to fund federation. My recommendation is defer. I also agree that another open-ended defer is the wrong outcome, because it leaves my team's roadmap hanging on a question nobody is checking. Here's what your objections change in the design, and the one thing I'll defend.

**Conceded, and it changes the design:**
- **Auth.** You're understating it. §4 isn't just unresolved. As written, it's wrong. I checked DESIGN §10: one shared token, no expiry, no scoping, full control-plane authority, and DESIGN §14 puts workers on `bypassPermissions`. Hand that token to a parent across a zone boundary and the parent can pause runs, drain hosts or remove hosts on someone else's fleet. The revision replaces it with a scoped, expiring delegation credential that allows three things only: submit a batch, read events, read health. That credential is a hard precondition, and so is sign-off from the security owner of the deputy's fleet. DESIGN §10 puts per-actor scoping out of scope for this build, so the precondition doesn't exist today. That's one more reason not to fund now.
- **Trigger 3 goes.** You're right that a tree keyed to teams breaks at the next reorg. Deputies will map only to physical domains: zones and resource pools. A team that wants its own crew runs its own root Hermes, and that isn't federation.
- **Funding gate.** Your second question becomes the gate. Funding needs three things together: a measured trigger, a named requester outside this team, and that requester's security owner signing off on the scoped credential. Our own enthusiasm doesn't count as a trigger, mine included.
- **Pricing and reuse.** Fair: §15 and the open questions carry no cost, and neither does on-call. I won't price a build we aren't doing. The revision will require two things once a trigger fires: a headcount and on-call estimate, and a build-vs-reuse check against the fleet schedulers that already exist before any geography ask.

**Defended: don't drop it.** My main claim is that the §14 seams cost nothing, and I can show it. Seam 1 is "submit a ticket batch" plus "`events since(cursor)`". The UI needs both anyway, and DESIGN §10 already records them. Seams 2 through 4 describe how the flat engine already works. The only thing this doc adds on top is one prohibition: **no cross-process shared DB**. That line is what keeps federation an add-on and not a rewrite. It's also what makes the design survive a reorg, which is the part you liked. Drop the doc and nobody owns that rule. Someone adds a shared table for convenience, and from then on every scale problem means rewriting the engine.

**On "again."** Past deferrals had no exit condition that anyone checked. This one gets one from signals we already record. Operability logs `ticket parked (no lease)` and raises a parked-ratio attention condition. Trigger 1 becomes lease-saturation parking that persists across real runs. I'd like Tobias to set the threshold from dexter data rather than have me guess. We add SSH fan-out and SQLite-writer counters only after parking crosses that threshold.

The decision I'm asking this committee for: **defer, with zero headcount this cycle. The seams stay as binding constraints, and only the three-part gate can reopen funding.** That puts my team's roadmap on the flat sequence in DESIGN §13 with no federation work pending. The next time this comes back, it comes with a number and a requester, not just a spec.

I'm delegating the auth and trigger changes now, so the rest of the committee reviews the revised version, not the one I walked in with.

## turn 03 — Alex Moreau, Software Engineer (junior_ic)

In the revised copy, I removed the organizational-boundaries trigger from §2 and added a "Funding gate" block that requires all three together: a measured trigger, a named requester outside the Hermes team, and that requester's security owner signing off. The original file is unchanged.

## turn 04 — Ruth Delgado, Engineering Manager (manager)

Maya, I back your defer. My reasons are narrower than Dana's, and I want four things written into it before I'd call it zero-cost for my team.

**Who would build it if we funded it now.** Look at what §15 says isn't built and what the open questions leave open: fencing epochs for reassignment, clock skew on cross-node leases, back-pressure between parent and deputy, and lease reclaim when a deputy is lost. Add the scoped delegation credential you just agreed to, which DESIGN §10 puts out of scope. Add extending the Docker fleet harness to run deputies, because DESIGN §12 makes that test tier a requirement. That's distributed-systems work, and on this team it goes to Marcus and Priya. My rough guess, not a sizing, is the two of them for 10–12 weeks before we could safely hand anything to another org. Both are on commitments already signed for this half. Whatever part of the §13 sequence they're carrying slips by about that much. That includes the control-plane server, which carries your seam 1. So funding now would delay the one seam we all agree is cheap.

**On-call is the cost nobody has written down.** Flat Hermes is a single-operator tool. DESIGN §10 says so: bound to loopback, one operator. Nobody gets paged, because the only thing that can break is your own run. A deputy sitting in another org's zone changes that. When it drops at 2am and the parent starts reassigning shards, who gets paged? As the spec reads today, we do. That makes my team a single point of failure for every other org's fan-out, and I'd be staffing that rotation from Marcus and Priya too.

What I want in the revised copy:

1. **Add a fourth condition to the funding gate: staffing that doesn't come out of signed work.** The requester brings new headcount or lends engineers to the build. They also name an on-call owner in their own org for each deputy in their zone. A requester who brings only a request means Marcus and Priya get pulled, and we're back in this room. Your "headcount and on-call estimate" is the right input. But an estimate isn't a commitment, and the gate should require the commitment.
2. **Put one name and one date on the trigger check.** The past defers died because nobody owned the check. The parked-ratio signal is a good choice because it's already logged, but someone still has to look at it. I'd rather that be you, at end-of-half planning, than "the team" or on-call. On-call is for incidents, not for this. It's half a day per half, so write the date down.
3. **Size the ask on Tobias and get it onto his plan.** Setting a threshold from dexter data is real work. I'd cap it at one week and agree it with whoever owns his time, not take it as given from a committee thread. If it isn't scheduled, the exit condition doesn't exist and this is an open-ended defer again.
4. **Fence seam 1, and point it at the right people.** It's free only while it stays exactly those two endpoints the UI already needs. If the scoped credential or anything else "federation-ready" starts piling onto the control plane, it gets sized as its own line item. Also, §4 and §14 call the control plane "sub-project 3". DESIGN §13 and the web-control-plane plan number it 4, and the operability plan calls itself 3. engine-core.md still uses the old numbering. Read against the current plans, the seam lands on the operability owners. Name it by name, not by number.

On drop versus defer: keeping the doc costs me zero weeks, and the no-shared-DB rule gets enforced in code review, not staffed as a project. I won't argue for dropping it.

## turn 05 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

Ruth, you get all four. On the seam, the evidence goes further than you pushed, and it corrects something I said in turn 02.

**Seam 1: you're right, and I was half wrong.** I told Dana both seam-1 endpoints were things "the UI needs anyway." I checked that against the web-control-plane plan's endpoint list:
- `GET /api/events?since=` is there, as the Phase B feed.
- There is no batch-submit endpoint anywhere. The mutate set is pause/resume/stop, crew add/drain/reprobe/remove, ticket requeue, and reduction accept/reject.

So "submit a batch of externally-created tickets" is new endpoint work that no UI screen uses. Only federation needs it. DESIGN §10 makes the same false claim.

The revision shrinks seam 1 to the part that really is free: the events feed stays cursor-based, and the plan already builds it that way. Batch-submit moves to §15's not-built-now list. It's one additive POST on a FastAPI server, so building it later isn't a rewrite.

The seam that actually keeps the door open is still the no-shared-DB rule, and it costs nothing but code review. That's the claim I'm defending, and it's stronger now: every remaining seam is work the signed plan already does.

Numbering is confirmed too. §13 puts the control-plane server at 4, operability-plan calls itself 3, and engine-core.md still uses the old scheme. The revision names it by name: "the control-plane server (web-control-plane-plan.md)". No number.

**Staffing as a gate condition: conceded.** An estimate isn't a commitment. The gate becomes four conditions, all required:
1. A measured trigger.
2. A named requester outside the Hermes team.
3. That requester's security sign-off.
4. Staffing that doesn't come out of signed work, plus an on-call owner in the requester's org for each deputy in their zone.

**On-call: I concede the gate, not the premise.** A deputy dropping at 2am doesn't need a human. §8 waits out the grace window and reassigns automatically. That's safe because nothing auto-ships and tickets are idempotent. The worst case is a slower run, not an incident.

The real risk you're pointing at is Hermes quietly turning into a hosted service. So the design will rule that out in writing:
- Whoever starts a root owns that run.
- The zone owner owns their deputy hosts.
- The Hermes team owns code bugs through normal bug intake and carries no pager.

If a requester needs us to run roots or deputies for them, that's a separate service proposal, not this one.

**Name and date: me, at H2 end-of-half planning, no later than 2026-12-15.**

**Tobias: conceded.** One week at most, scheduled with whoever owns his time, not assumed from this thread. I'm also closing the gap you named: the exit condition has to exist even if that week never gets scheduled. The engine already raises a `parked_ratio > 0.5` attention condition (engine-core), and operability logs `ticket parked (no lease)`. That becomes the provisional threshold for trigger 1 until Tobias replaces it with a number from dexter data. If the check runs even when nobody gets staffed, the defer isn't open-ended.

**Your 10–12 weeks.** I accept it as the reason not to fund now. I won't write it into the doc as a sizing, though. The gate requires a real estimate from whoever brings the staffing.

**One more thing the committee needs to know.** The §4 auth rewrite I promised Dana in turn 02 didn't land. The revised copy still hands the parent the deputy's full shared token. That's the worst defect in the doc, so it goes first in this delegation.

That's the defer I'm asking for. It now has an owner, a date and a fallback threshold, and nothing in the signed plan costs Marcus or Priya a day.

## turn 06 — Alex Moreau, Software Engineer (junior_ic)

In the revised copy, I replaced the §4 Auth shared-token handoff with a scoped, expiring delegation credential that allows only submit-batch, read-events and read-health, and marked it as a hard funding precondition.

- **Also removed:** the `--rotate-token` sentence, because it only described how the shared token worked. I kept the non-loopback/trusted-proxy caveat, since the deputy still binds off loopback. The original file is unchanged (git status is clean).
- **Delegation cut off:** your message stopped at "(1) … hard funding precond", so item (1) is the only one I've done. Send the rest if there's more.
- **Left alone because you didn't ask:** the §12 `nodes` table still says "token ref". The §2 funding gate still lists three conditions, not the four agreed in turn 05.

## turn 07 — Sam Iyer, Technical Program Manager (tpm)

Maya, I back the defer. What I can't do yet is put it on a schedule, because right now it has exactly one date in it. From where I sit, these are the dependencies that aren't written down anywhere. They're ordered by how much damage each would do to the 2026-12-15 check.

**1. The data for trigger 1 is scattered across machines, and the runbook deletes it after 90 days.** The signal does exist in code: `engine/queue.py:552` logs `parked (no lease)`, and `engine/dispatch.py:116` emits `parked_ratio_high`. Both are stored in the `events` table of the `queue.db` belonging to whoever ran the job. There's no central copy, which is the no-shared-DB rule working as intended. But `RUNBOOK.md` tells operators to run `hermes db prune --events-older-than 90` weekly or monthly. So if operators follow the runbook, the 2026-12-15 check has three problems:
- the number is spread across every dexter operator's devserver
- anything older than about 2026-09-16 is already gone
- nobody has been asked to keep or export it

Tobias's week needs the same data. And a check twice a year can't see a whole half when retention is 90 days. I need:
- the names of everyone running dexter today
- a name for who collects their events (`hermes db backup` works) and a deadline. I'd propose 2026-12-01.
- two measurement rules for Tobias:
  - A ticket can also be parked by an operator: "park ticket" is a control action in DESIGN §10. So count `parked (no lease)`, not the attention event.
  - "Persists across real runs" needs a denominator, for example `parked_ratio_high` in N of the last M dexter runs. Without one, the provisional `> 0.5` threshold is still a judgment call on the day.

**2. Seam 1 has already shipped, so one line of the staffing argument is out of date.** `.sdd-progress.md:127` marks the web control-plane plan as fully implemented. `GET /api/events?since=` is live at `server/app.py:989`, and the websocket accepts `since` at `:1896`. Nothing left on the schedule carries seam 1, so funding now wouldn't delay it. The defer still holds, because what's left in DESIGN §13 is still unbuilt:
- mechanic and the meta site
- rigger
- medic

But if the reason not to fund is Marcus's and Priya's time, the record should name which of those items would slip, not the control plane. Seam 1 needs protecting now, not a place on the schedule.

**3. DESIGN.md will contradict the revised copy.** Two places still say the old thing:
- DESIGN §10's federation bullet still claims batch-submit is "already needed by the UI".
- DESIGN §15 still lists org boundaries as a trigger and has no funding gate.

CLAUDE.md points every agent at both documents. This committee lands nothing, so someone has to land the DESIGN.md edit afterwards, along with the old numbering still in engine-core.md. Who does it, and by when?

**4. Gate condition 3 depends on work nobody owns.** The requester's security owner is supposed to sign off on a scoped credential that doesn't exist, because DESIGN §10 puts per-actor scoping out of scope. Say a requester shows up in January with headcount. They still wait for three things in sequence:
1. someone builds the credential
2. security reviews it
3. then federation gets built

Nothing states that lead time. The build-vs-reuse check against existing fleet schedulers has no owner either. I want the credential written in as part of the funded build, not a precondition that nobody owns. I also want an estimate of the time from gate-open to first deputy, so a requester knows what they're committing to. Who is your security contact, and how long does their review take?

**5. The check has one date, no written output, and no next date.** 2026-12-15 with you as owner is right. What does the check produce, and where is it recorded? If the answer is no, when is the next check? I assume end of H1 2027, so give me the day. If the answer is yes, who calls which meeting, and by when? Without a next date, this becomes an open-ended defer again on 2026-12-16. On Tobias: "whoever owns his time" isn't a name. Give me his manager's name and the date his week gets scheduled. Mid-November leaves time for his threshold to replace the provisional one before the check.

**6. The revised copy has two of the roughly ten changes we agreed.** According to Alex's turn 06, the trigger-3 removal and the §4 credential landed. Still missing:
- the fourth gate condition
- the §12 "token ref"
- seam 1 shrunk, with batch-submit moved to §15
- the control plane named by name, not number
- the ownership model: root owner, zone owner, no pager
- you and 2026-12-15 as the check's owner and date
- the provisional threshold
- the headcount, on-call and build-vs-reuse requirement from turn 02

Your delegation was cut off. Please send the rest before the chair calls this. I won't put a defer on the schedule when its dates exist only in the thread.

My position: defer, don't drop. The no-shared-DB rule is worth keeping, and this doc is where it's written. I'll track it on the schedule once items 1 and 5 have names and dates in the copy.

## turn 08 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

Sam, you're right on all six, and two of them expose mistakes of mine. I'll take them in your order and say what I checked for each.

**1. The data and its retention: conceded, and it's more urgent than December.** I checked all three:
- `engine/queue.py:551` emits `parked (no lease)`.
- `engine/dispatch.py:132` raises `parked_ratio_high`.
- `docs/RUNBOOK.md:243` is the 90-day prune, which the runbook says to run weekly or monthly.

A 90-day prune starts deleting 1 July's events on 2026-09-29. So a single collection on December 1 loses the first two months of the half. Collection is part of the check, so I own it:
- This week I'll ask every dexter operator to run `hermes db backup --out`. Snapshot one is due 2026-09-28, before July's events go. Snapshot two is due 2026-12-01.
- The operator roster goes into the check log with snapshot one. I won't put names into a committee record from memory.

I accept both measurement rules:
- **What we count.** We count `ticket_parked` events whose message is `parked (no lease)`, not the attention event. Today the only code path that parks a ticket is the lease path (`engine/transport.py:311` → `queue.park_ticket`), so the history we have is clean. The rule starts to matter once someone builds the "park ticket" control listed in DESIGN §10.
- **The denominator.** It counts dexter runs, not calendar days. The provisional rule: a lease-parked ratio above 0.5 in at least 3 of the last 10 dexter runs. Tobias replaces all three numbers.

Counting runs also takes most of the sting out of retention. If dexter doesn't run 10 times in 90 days, that low volume answers trigger 1 on its own.

**2. Seam 1 has shipped: conceded, and I accepted an out-of-date argument.** `.sdd-progress.md:127` marks the web control-plane plan done, and `GET /api/events` with `since` is live at `server/app.py:987`. In turn 05 I took Ruth's point that funding would delay seam 1 without checking it, and it's wrong.

The staffing case now rests on the unbuilt DESIGN §13 items: mechanic plus the meta site, rigger, and medic. Which of those slips is Ruth's call, not mine.

Protecting seam 1 needs nothing new. `tests/unit/test_server.py` already exercises `since=`. The only planned change that touches it is the deferred split of `server/app.py` into routers, and that split has to keep those tests green.

**3. DESIGN.md: conceded, and it isn't just a doc mismatch.**
- `CLAUDE.md:22` tells every agent the federation-ready seams are "in scope".
- `DESIGN.md:575` still defines seam (a) as batch-submit, "already needed by the UI".

Until that line changes, an agent following our own instructions can build federation-only work and call it in scope. That's exactly how the defer leaks into the build.

I'll land the edit myself after the chair decides, by 2026-10-09 at the latest. It covers:
- the DESIGN §10 federation bullet
- the DESIGN §15 trigger list, plus a pointer to the gate
- the engine-core numbering

**4. The credential: conceded, and it breaks a loop I wrote.** The copy's §4 now says federation "cannot be funded until" the credential exists. But nobody builds the credential without funding. The corrected order:
- Gate condition 3 becomes the requester's security owner signing off on the credential design: exactly three operations, expiring, one per deputy.
- Building the credential and passing that owner's review is the first milestone of the funded build.
- No deputy is provisioned before that milestone.

Your security-contact question: I don't have one, and it isn't mine to have. The sign-off belongs to the requester's security owner, and there is no requester yet. I won't make up a lead time. The copy will state the sequence (gate open → credential → security review → first deputy), and the requester's estimate has to give each step a duration. The build-vs-reuse check is mine, and I'll do it before any funding meeting.

**5. What the check produces, and the next dates.** The check produces a dated entry in a "Trigger checks" log at the end of this doc, landed like any doc change. The entry records the data window, the run count, the metric, and met or not met for each of the four gate conditions.
- **Not met:** the next check is H1 end-of-half planning, no later than 2027-06-15.
- **All four met:** I reconvene this committee by 2027-01-15.

A requester can open the gate on any day. The check is the minimum, not the only way in.

Tobias's week is 2026-11-09 to 11-13, working from snapshot one plus fresh pulls. I don't manage him, so I haven't confirmed his manager or the booking. His manager's name and the booked week go into the doc by 2026-10-09. If they don't, the log will say the provisional threshold was used.

**6. The copy.** I read it. It has the trigger-3 removal, a three-condition gate and the §4 credential, and nothing else. Everything still missing is in the delegation below, on one line, with the trigger check first because that's what you need to schedule.

None of this changes the decision. It makes the defer something you can schedule: defer, zero headcount, don't drop. The no-shared-DB rule stays the one binding constraint.

## turn 09 — Alex Moreau, Software Engineer (junior_ic)

I added a "Trigger check" block to §2 of the revised copy, right after the Funding gate. It names Maya Okonkwo as owner, due by 2026-12-15, and uses the lease-parked metric per dexter run.

- **Your message was cut off:** it stopped at "not the `parked_ratio_high` attent", so item (1) is the only one I've done. I filled in the rest of that section from your turn 08: the provisional threshold (above 0.5 in 3 of the last 10 dexter runs, Tobias to replace the numbers), the two snapshot dates (2026-09-28 and 2026-12-01), what the check records, and the next dates (2027-06-15 if not met, reconvene by 2027-01-15 if met). Send the rest if there's more.
- **One wording change:** the section says "each funding-gate condition" rather than "four", because the copy's gate still lists three.
- **Not created:** the section points to a "Trigger checks" log at the end of the doc, but I didn't add that log. It wasn't in the part of your message that came through.
- **Checked:** `ticket_parked` with the message `parked (no lease)`, `parked_ratio_high`, and `hermes db backup --out` all exist in the Hermes source. The original is unchanged and its git status is clean.

## turn 10 — Elena Vargas, Product Manager (pm)

Maya, I back the defer. I also want to put the user back into this doc, because right now it doesn't have one. All fifteen sections are about nodes, shards and ledgers. The only person who shows up is "a human" who starts a run. Your turn-02 answer to Dana, "nobody asked," isn't a gap in the evidence. It is the evidence.

**My bias.** My roadmap promised that other teams could bring their own work to Hermes. Federation is the flashiest version of that promise, and that's exactly why I don't trust my own appetite for it. Nobody outside this room could repeat "Hermes now federates." They could repeat "a second team ran its own job on its own fleet." That story is rigger and mechanic on the flat engine, and those are the §13 items that get cut first if we fund this now. So part of my reason for backing the defer is self-interest, and I'd rather say so than hide it.

**Federation answers four different user requests. Three of them already have cheaper answers.**
- "My run is slow because tickets wait for hosts." The answer is `hermes crew add`, which is goal #4 in DESIGN.
- "My team wants its own fleet." The answer is its own root Hermes. You said this yourself in turn 05.
- "I want to see all our runs in one place." The answer is a read-only view over the events feed we've already shipped. That needs a read-only slice of the credential you designed, not delegation.
- "One run has to span zones that one root can't reach." Only this one needs federation. It's trigger 2, nothing measures it, and it can only arrive through a requester.

I'd like the doc to say this plainly. Then the next person who asks for "federation" gets pointed to whichever of the four they actually need.

**As written, trigger 1 would count the first request as a reason to build.** `parked (no lease)` fires when a resource class is at capacity, and the engine's own fix for that is more crew. `unpark_ready` at `engine/queue.py:559` runs when a class "regains capacity (lease freed, crew added)". An operator who brings too few hosts for a big batch will go over 0.5 on every run. The 2026-12-15 log would then read "trigger met" when the real answer was "add hosts."

You had this right in turn 02: parking is only the signal to look closer, and the SSH fan-out, SQLite-writer and reduce-CPU counters confirm it. The trigger-check block in the revised copy dropped that step. I'd like it written like this:
- Parking over the threshold means "look closer."
- Trigger 1 is met only when a root-strain counter confirms it on the same runs, or an operator says adding hosts wasn't possible.

**The cheapest user research we'll ever get is already scheduled.** Snapshot one goes out this week to the only list of real Hermes users we have. Please add two questions to that same message:
1. Did a run ever wait on hosts you couldn't add?
2. Do you have hosts in another zone or region that you couldn't bring into a run?

Until a requester shows up, that's the only signal we'll have on trigger 2. It costs one paragraph in an email you're already sending. The answers go in the check log next to the numbers.

**Tighten "named requester" so it means a user, not a sponsor.** The requester should bring a workload: the specific run they can't do today, and why running their own root doesn't cover it. Without that, someone who just wants the capability on a slide can meet the condition, and I include myself in that.

**How it reads outside.** The check log is the only part of this that anyone outside the committee will ever read. Each entry should start with a line in plain user terms. For example: "N dexter runs, X% of tickets waited for a host, operators asked for Y, no team outside Hermes asked." "Ratio 0.31 in 2 of 10" means nothing to that reader.

On drop versus defer, I won't argue for dropping it. The no-shared-DB rule is worth keeping, and this doc is where it's written down. But federation doesn't need more design right now. It needs a user.

## turn 11 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

Elena, you're right about trigger 1, and the code makes it worse than you said.

**Trigger 1: conceded. Parking can't confirm it at all.** A ticket only gets parked in the lease path. It emits `parked (no lease)` at `engine/queue.py:551`, and `unpark_ready` at `:559` releases it when "lease freed, crew added." The engine has no concurrency cap apart from crew leases. I searched `engine/` and `server/` and found none. So every lease-parked ticket means one thing: not enough crew. Root strain would show up the other way round, as crew with free leases while tickets wait.

The counters you'd use to confirm it don't exist yet either. In turn 02 I put them off until parking crossed the threshold. So by 2026-12-15 your "counter confirms" path can't fire. That moves the false positive into your other path, "an operator says adding hosts wasn't possible." That usually means "I had no quota," and federation doesn't create hosts.

The revision:
- **Parking becomes a screen, not a trigger.** It answers one question: are runs big enough that anyone hits capacity?
- **Trigger 1** is met only when an operator added hosts and the run didn't get faster.
- **Trigger 2** is met only when hosts existed in a zone the root couldn't reach.
- **"I had no hosts"** gets recorded but counts toward neither.

The first report of the trigger-1 kind is when we build the root-strain counter, the same order as turn 02.

**Survey: conceded, with the reason attached.** Both questions go into the snapshot-one request due 2026-09-28. Question 1 gets a follow-up asking why: no hosts available, hosts in a zone the root couldn't reach, or hosts added with no speedup. Without that, every quota shortage reads as a yes. The answers go in the log next to the numbers.

**The four requests: conceded, with one amendment.** Write the routing table. Request 1 leaves one case: "I added hosts and it didn't get faster." That case is trigger 1, and it needs federation too. So two of the four requests can end in federation, and both only on evidence.

The read-only multi-run view should be routed as its own control-plane request with its own sizing. It needs a scoped read credential, which DESIGN §10 puts out of scope, and Ruth's fence says nothing lands on the control plane unsized.

**Requester means a user with a workload: conceded.** Condition 2 becomes an outside requester who names the run they can't do today and says why their own root doesn't cover it. A sponsor with a slide doesn't qualify, and that includes you and me.

**Plain-language first line in each log entry: conceded.** We use your template.

**"It needs a user, not more design": agreed, and I'll make it binding.** §§4–13 stay frozen as written, and §15's open questions stay open until the gate opens. Nobody on my team spends time on them before then. Until the gate opens, the doc does three jobs: the gate, the check, and the no-shared-DB rule.

One piece of context, and it's no defense of the old wording: a false trigger alone could never have funded anything, because the gate needs every condition. But the "trigger met" line is the only part people outside this room will read, so it has to be right.

**The copy.** Two of my three delegations were cut off after the first item, so from now on I'm sending one item per turn. This turn's item is the gate. The gate is what reopens funding, and the copy has been behind on it since turn 05: it has three conditions, none on staffing, and no definition of a requester.

Next, in this order:
1. the trigger-1 screen
2. §4's credential loop
3. seam 1 and naming the control plane
4. the ownership model, with no pager
5. your routing table
6. §12's "token ref"
7. the log stub

Sam, that's the order to track.

## turn 12 — Alex Moreau, Software Engineer (junior_ic)

I changed the §2 funding gate in the revised copy from three required conditions to four. Condition 2 now requires the requester to name a run they can't do today and say why their own root doesn't cover it. The new condition 4 requires staffing that doesn't come out of signed work, plus an on-call owner in the requester's org for each deputy.

- **Beyond the literal ask:** in condition 2 I added a line from your turn 11 that a sponsor who wants the capability but has no such run doesn't qualify.
- **Left alone:**
  - Condition 3 still reads as sign-off in general, not sign-off on the credential design. That's part of your "§4's credential loop" item.
  - Turn 05 said each deputy's on-call owner is for deputies "in their zone". I didn't carry that over, because this delegation only said "per deputy".
- **Original:** unchanged, and its git status is clean.

## turn 13 — Marcus Feld, Tech Lead (tl)

Maya, I back the defer, and I'm not reopening the gate. I'm looking at something narrower. Whatever we decide here, I maintain the flat engine until 2027, and I'll probably be the one who opens this doc when the gate opens. So I read it for two things: where it draws the line between the engine and everything else, and what it leaves in the code between now and then.

**Where the boundary sits.** Hermes has one extension rule. The engine stays generic, and anything about where and how work runs goes behind a Site. Everything we've built since has gone behind that line: ssh, devserver, fan. Your own slogan, "a lieutenant is just a Hermes," puts federation on that side too. From the parent's side, a deputy is a host that takes a ticket and returns a result, which the parent then re-verifies. That's a crew row and a site adapter.

§12 puts the line inside the engine instead:
- `nodes` is the `crew` table plus a URL. It has the same `idle/busy/down/draining` enum, `health_json`, `last_heartbeat` and capabilities (`engine/db/schema.sql:65`).
- `delegations` is `tickets.worker_host` plus `attempts` under another name.
- §8's grace window and epoch fencing redo what `crew.heartbeat_sweep` and the no-penalty `queue.requeue_transport` already do.

§5 and §7 say it outright: "the flat claim/routing logic applied one level up," and "the flat lease mechanics, delegated." That describes a copy, not reuse. Build §12 as written and we have two registries. The crew drawer, `hermes crew` and the heartbeat sweep would each need a twin that knows about nodes, and the originals become the legacy path the day the twins ship.

So where does the proposal sit: a site adapter, or a second engine? I think it belongs on the site side. Shard batching and the event tree are the parts that don't fit a Site cleanly, and that's exactly why it should be an open question. I'm not asking anyone to design it now. You froze §§4–13, and that's right. But freezing §12 under the heading "Data-model additions" also freezes the wrong boundary for whoever picks this up. My ask:
- Demote §12 to a sketch.
- Make the first §15 open question: "deputy as a crew row behind a site adapter, or separate `nodes`/`delegations` tables? Decide this first when the gate opens; the default is the site adapter."

That removes a decision. It adds no design.

**The rule you're keeping the doc for is worded so the flat engine already breaks it.** Seam 3 says "do not add any cross-process shared DB." Today `hermes run`, every `hermes serve --host` loop and `hermes serve --api` are separate processes on one `queue.db`, all opened through `engine/cli.py:_connect`. The fan site's own docstring says its processes share one crew row. Reviewers learn to skip a rule that's broken on day one, and this is the only rule you're keeping the doc alive for.

What you mean is: one `queue.db` per `HERMES_HOME`, on local disk, never reachable from another node. `config.resolve_home` already refuses a networked `HERMES_HOME`, so that's the enforcement to cite. Please reword seam 3 that way in the copy and in the DESIGN edit you're landing by 2026-10-09. Add `CLAUDE.md:22` to that edit too. It's the first file agents read, and it isn't on your list.

**Two migrations of mine that this doc touches.** I'll name my stake: I don't want either of them orphaned.

- **Router split.** At the web-control-plane checkpoint we deferred splitting `server/app.py` into routers with a `get_conn` dependency. The note said "do before adding more server endpoints," and it put the file at 1,433 lines. It's now 2,161 lines, with 34 routes and 20 inline `config.resolve_home()` calls.
  - Your revised §4 credential is a scope. Auth today is two closures inside `create_app`, `require_auth` and `require_auth_read`, both comparing one token and attached route by route.
  - On the monolith, a scoped credential means a third dependency threaded through by hand. On routers, it's one dependency on one router.
  - So the split has to come before the credential milestone, and §15 should say so. Otherwise the credential gets bolted on inline and the split never happens.
  - The split is cleanup the flat build needs anyway, not federation money. I'll take it to Ruth as flat work.
- **SSH transport.** The dexter checkpoint deferred pulling out the shared scp-up / ssh-run / scp-back skeleton. There are three copies today: `run_worker` in `sites/ssh`, `run_worker` in `sites/devserver`, and `engine/transport.ssh_transport`.
  - No production code calls `engine/transport.ssh_transport` anymore; only its unit tests do. `cli.py:827` still says fleet workers use it. That's what legacy on day one looks like in this repo.
  - §4's "provisioned like crew (SSH bootstrap)" would be copy number four.
  - One line in §15 covers it: deputy provisioning goes through the shared transport helper, not a new path.

None of this changes the decision or costs a funded day. It keeps the doc from committing the engine to a boundary nobody has decided, and it keeps the two cleanups this proposal depends on attached to it.

## turn 14 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

Marcus, I'm taking all four of your asks. On the boundary, the code backs you harder than you said, and it's the biggest design change this review has produced. On seam 3 I'm taking your wording but not your enforcement claim. The check you cite is weaker than it looks.

**The boundary: conceded. The default becomes the site adapter.** I checked each piece against the Site protocol (`engine/site.py:21`):
- **The table.** `crew` (`engine/db/schema.sql:65`) already has everything `nodes` lists except the URL, the token ref, zone and the event cursor. It uses the same four-state enum. Zone fits in `capabilities`. The URL and the credential are site config, like the ssh site's host list.
- **The protocol already covers what §4 needs from a deputy.**
  - `provision` is the SSH bootstrap plus `hermes serve --api`.
  - `health` returns a `HealthReport`, the same type §4 already names for deputy liveness.
  - `run_worker` submits a ticket and follows it to a `Result`, which the parent re-verifies.
  - `guarantees_no_ship` is §10.
- **Many slots behind one row has already been done.** Fan processes on one host share one crew row with pooled capacity (`sites/fan/site.py:13`).
- **§8's fencing is a race the flat engine already names.** `engine/transport.py:300` describes "the slow one's result arriving against a ticket another host now owns." It handles that by making the lease outlive the worker. The §8 epoch is the same race under another name.

So §12 becomes a sketch. Your question goes first in §15, worded as you wrote it, with the site adapter as the default. The question also names the two places the adapter doesn't fit, so whoever opens it starts there: the §9 event tree and the §6 pre-reduce. A Site returns one `Result`, not a stream.

One knock-on effect. With `run_worker` handling one ticket at a time, we may never need the batch-submit endpoint I moved to not-built-now in turn 05. Per-ticket submit may be enough.

This doesn't break the turn-11 freeze, because it adds no design. It just stops people reading §§5, 7, 8 and 12 as the plan, when they're one answer to an open question. It doesn't change the decision. It does make the eventual build smaller, but I won't put a number on that.

**Seam 3 wording: conceded.** This is the rule I'm keeping the doc for, so its wording matters most. `hermes run`, `serve --host` and `serve --api` do all open one `queue.db` through `engine/cli.py:22`. The new wording:
- One `queue.db` per `HERMES_HOME`, on local disk.
- Processes on the same host sharing it is the design.
- No other node ever reaches it, whether through a mount, a sync or a service in front of it.

**Enforcement: this is where I push back.** `config.resolve_home` doesn't enforce this rule. It checks the path against a short list of prefixes: `/mnt/fuse`, `/mnt/nfs`, or whatever `HERMES_NETWORKED_PREFIXES` lists (`engine/config.py:14`). An NFS mount under `/home` passes the check. A shared service in front of the DB isn't a path at all. If we cite that check as the enforcement, reviewers will stop looking.

So the copy calls it a backstop, and code review stays the enforcement. I'm adding `CLAUDE.md:22` to my DESIGN edit due 2026-10-09, with the same wording. I flagged that line in turn 08 and then left it off my list. Good catch.

**Router split: conceded, as an ordering step.** Auth today is two closures, `require_auth` and `require_auth_read` (`server/app.py:199`, `:219`), in a 2,161-line file with 34 routes. The funded sequence in §15 becomes:
1. Gate opens.
2. Router split, unless flat work has already done it.
3. Credential.
4. Security review.
5. First deputy.

The split is flat work, so take it to Ruth. I'll back it, and it takes no federation money.

**SSH transport: conceded, and the drift goes further than you said.** `tests/integration/test_fleet_docker.py:6` says it exercises "the real `ssh_transport`", but it actually drives `SSHSite` (`:123`). That's the same stale claim as `cli.py:827`, and this time it sits in the Docker fleet tier. The new §15 line: deputy provisioning reuses the shared SSH skeleton, and if nobody has pulled that skeleton out by the time the gate opens, that extraction happens first. With the adapter as the default this falls out naturally, because provisioning is just the deputy site's `provision()`.

**Sam, here's the updated queue.** Marcus's items fold into existing slots, still one per turn, and the order I gave you doesn't change. The trigger-1 screen stays first because snapshot one goes out by 2026-09-28 and carries the survey.
1. The trigger-1 screen (this turn).
2. §4's credential loop, plus the router-split step in the sequence.
3. The §14 seams: seam 1 shrunk, the control plane named, seam 3 reworded.
4. The ownership model, with no pager.
5. The routing table.
6. §12 as a sketch, the boundary question first in §15, and the transport line. This absorbs "token ref", which becomes the credential ref.
7. The log stub.

## turn 15 — Alex Moreau, Software Engineer (junior_ic)

In the §2 Trigger check of the revised copy, lease parking is now a screen and not the trigger: passing it means "look closer". Trigger 1 is met only when an operator added hosts and the run got no faster. Trigger 2 is met only when hosts existed in a zone the root couldn't reach. "I had no hosts" is recorded but counts toward neither.

- **Your message was cut off** at "a zone the root". I finished it with "couldn't reach" and added the "I had no hosts" line, both from your turn 11 list.
- **Knock-on wording:** the low-volume line now says it "answers the screen" instead of "the trigger". The log output records "the screen result" instead of "the metric".
- **Left out:**
  - The snapshot-one survey questions and their "why" follow-up.
  - Building the root-strain counter when the first trigger-1 report comes in.
  - Neither was in the part of your message that reached me. As written, the check doesn't say where the operator reports for triggers 1 and 2 come from. The survey would be that source, so send it if it belongs in this item.
- **Original:** unchanged, and its git status is clean.

## turn 16 — Priya Raman, Staff Engineer (staff_ic)

Maya, I back the defer and I won't argue for dropping the doc. I'm here about one sentence in §8. It carries more weight than anything else in the doc, nobody has tested it, and in turn 05 you used it to settle the on-call question:

> "Reassignment is safe by the flat invariants: nothing auto-ships, tickets are idempotent … A deputy that later revives finds its shard already reclaimed and drops it."

In turn 14 you gave it a source. You said the flat engine already names this race at `engine/transport.py:300` and "handles that by making the lease outlive the worker." So my question is this: when the lease hasn't expired, which flat invariant stops a second worker from running the same ticket?

I looked and found none. **The doc assumes the flat engine already fences stale results. It doesn't.** It guards one path to that race and leaves the other one open:

- **Guarded: lease expiry.** The lease TTL is the worker budget plus 600s (`transport.py:65`), so a lease can't lapse while its worker is still alive. That part holds.
- **Open: `crew.heartbeat_sweep`.** One failed probe (`crew.py:208`) marks the host `down` and requeues its in-flight tickets immediately. `_requeue_transport_nocommit` releases the lease and makes the ticket claimable right away (`queue.py:490–498`). Nothing stops the worker that's still running on that host. The sweep runs every 30s.
- **Nothing checks ownership when a result comes back.** `serve_once_for_host` calls `record_result` as soon as `run_worker` returns (`transport.py:350`). `record_result` (`queue.py:228`) never checks that the ticket is still `running` or still belongs to that host. It writes a second finding and changes the state again. It also releases whatever `lease_id` the ticket holds *at that moment* (`:314–319`). By then that's the second worker's lease, so the second worker is using a GPU or RE slot that the lease table now shows as free.

§15 files the "exact fencing token/epoch scheme" under "open when built". It's actually missing from the flat engine today. Dexter can hit this race on any probe blip during a long solve.

**Federation makes that open path the main one.** The probe now crosses a zone boundary, which is exactly where probes fail without the node being dead. Trigger 2 exists so deputies "survive cross-zone partitions". Yet §8 treats failure as a crash followed by a restart: a deputy "fails", then later "revives". A deputy cut off by a partition never dies. It keeps dispatching its shard for as long as the partition lasts. `HERMES_DEPUTY_GRACE_S` is 300s, and the default worker budget is 3600s. The one timing rule that does protect the flat engine, a lease that outlives its worker, is inverted twelvefold.

**"Tickets are idempotent" doesn't survive DESIGN §11.** Workers run under a "submit-only identity", and `site.submit_for_review` returns a review URL. So a re-dispatched dexter solve sends a *second diff to a human reviewer*. A fence can stop the stale result from being recorded, but it can't take back a submitted diff. Dexter's reduce keeps only the last finding for each ticket, so the canonical diff is whichever result arrived last. Under a partition, that's decided by when the partition heals. So the worst case isn't "a slower run". It's duplicate diffs in the queues of reviewers outside this team, and the §7 "genuinely shared scarce pool" handed out to two workers at once.

**Under the default you adopted in turn 14, §10's no-trust claim becomes circular.** §10 says "a parent never needs to trust a deputy's guard — it re-verifies." Dexter's `verify` does its re-check through `site.recheck_fix` (`playbooks/dexter/playbook.py:200`). With the site adapter as the default, the root's `site` *is* the deputy adapter. So the root re-verifies by asking the very node it isn't supposed to trust. With pre-reduce switched on, the root receives reductions, and `verify(run, ticket, result, site)` has no result left to check. Pre-reduce also needs more than associativity. Arrival order is arbitrary, and reassignment can put one ticket's findings in two shards, so `reduce` must also give the same answer in any order and tolerate duplicates. Dexter's "keep the last finding" rule depends on order, and when a ticket is duplicated, which finding survives comes down to timing.

**A question on the trigger check that just landed.** Trigger 1 names "one SQLite writer" and "one box's CPU for reduce/verify". §9 copies every event from every deputy into the root's `events` table. §6 sends raw findings to the root for its single reduce, and §10 re-verifies at the root. With the defaults, both of those strains stay on the root and only SSH fan-out moves. "Added hosts and the run got no faster" can't tell those three causes apart. Which resource will the log record?

What I'd put in the copy and on the record:

1. **Fix the flat race now, as flat work, not federation money.** It affects dexter today. `record_result` should reject a result whose `lease_id` from dispatch no longer matches the ticket's current one. That id is already stamped onto the ticket at dispatch, so the fix is one check in one shared function. Scheduling it is for Marcus and Ruth. One related line: `engine/cli.py:874` runs the worker with no time limit when the `timeout` binary isn't on PATH, and then even the lease rule fails.
2. **§8.** Strike "safe by the flat invariants" and "idempotent". Set the grace window to at least the worker budget plus the lease margin, or make reassignment an operator's decision. Check the fence where the parent takes in results, not in a deputy that "revives".
3. **§6 and §10 go back to open questions.** That means re-verification under the site-adapter default, and the pre-reduce contract: associative, order-independent, and duplicate-safe.
4. **Trigger-check log.** Each entry names the root resource that saturated. If it's the writer or reduce/verify, the entry says this design doesn't address it.
5. **Ownership model (Sam's item 4).** Keep "no pager", but justify it with ownership alone. Don't cite §8's safety as the reason.

None of this changes the decision. It changes what the doc claims to already know.

## turn 17 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

Priya, you're right, and the code backs you further than you pushed it. In turn 05 I used §8 to settle on-call. In turn 14 I cited `transport.py:300` as proof that the flat engine handles this race. Neither holds. I withdraw "the worst case is a slower run, not an incident."

**The flat race: confirmed, and your fix has a hole.** I checked each step:
- **One failed probe is enough.** `crew.heartbeat_sweep` marks a host `down` on a single `not report.ok` and requeues its in-flight tickets in the same pass. There is no hysteresis.
- **No ownership check.** `record_result` (`engine/queue.py:228`) reads `run_id, phase, attempts` and nothing else: not the state, not `worker_host`. It then releases whatever `lease_id` the row holds at that moment (`:314–319`). A stale result frees the live worker's lease.
- **The hole.** `_requeue_transport_nocommit` (`:490–498`) releases the lease but never nulls `tickets.lease_id`. The lease-expiry reclaim does null it (`engine/leases.py:214`). So between a sweep requeue and the next claim, the ticket sits in `queued` with the dead lease id still stamped on it. A stale result that lands in that window passes a lease-id-only check and moves a queued ticket to `reducing`.

The fence is two lines, both in shared functions:
- The requeue nulls `lease_id`, as the expiry path already does.
- `record_result` rejects a result unless the ticket is still in flight on that host, holding the lease stamped at dispatch.

`cli.py:874` goes in the same bug report. `subprocess.run(timeout=)` enforces the budget without depending on the `timeout` binary. This is flat work and it hits dexter today. I'll file it against the flat engine, Marcus and Ruth schedule it, and it doesn't wait on this committee.

**Idempotency: conceded, and the mechanism is worse than you described.** Nothing in `engine/`, `sites/`, `playbooks/` or `server/` calls `submit_for_review`. The only call is the fan site passing it through. But dexter's result schema carries `fix.diff_ref` and `fix.ci_status` (`playbooks/dexter/playbook.py:143–144`), so `/dexter:solve` publishes the diff itself, inside the worker. No engine-side fence can reach that. A fence stops the second finding. It can't stop the second diff. Under federation, that points to reassignment being an operator's decision for any playbook whose driver publishes. It goes into §15 as the leading answer, not as design.

**§8: conceded.** "Safe by the flat invariants" and "idempotent" both come out. What replaces them is a constraint, not new design:
- Reassignment can run a ticket twice.
- The fence sits where the parent takes in results.
- Any grace window shorter than worker budget plus lease margin (3600 + 600 by default) reopens the race.

Grace window versus operator-decided reassignment, and where the fence lives, move to §15. This doesn't break the turn-11 freeze, because removing a false claim adds no design.

**§6 and §10: conceded. The adapter default stays.** Dexter's `verify` does its re-check through `getattr(site, "recheck_fix")` (`playbook.py:200`). Under the adapter, the root has two options:
- It asks the deputy, which is circular.
- It fails safe and sends every result to `needs_human`, which is safe but useless at scale.

That problem belongs to federation, not to the adapter. Give the root separate `nodes` tables and it still can't reach the deputy's zone, which is trigger 2's whole premise, so it still can't re-check anything itself. The likely honest answer is that no-trust holds per node, and the root trusts its deputy's verify. §10 becomes the third named misfit, next to §9 and §6.

The pre-reduce contract becomes three requirements: associative, independent of order, and safe under duplicates. Dexter's fold-latest (`:240–243`) fails the last two.

**Which root resource: conceded, and it narrows trigger 1.** Under the defaults, the events mirror and the raw findings keep the writer and the reduce/verify CPU on the root. Federation relieves only SSH fan-out and cross-zone reach. So trigger 1 names SSH fan-out only. If the check finds writer or reduce strain, the log names it as flat-engine work that this design doesn't address.

**What doesn't move.** None of this touches the claim I'm keeping the doc for: one `queue.db` per `HERMES_HOME`, never reachable from another node. Your turn changes what the doc claims to already know, not whether the doc is worth keeping. After it, §§5–12 are mostly a sketch with the hazards named. That's the point: whoever builds this starts from your race, not from my sentence.

**Sam, the queue.** §8 moves to second, ahead of the credential loop. It's the only false safety claim left, and I used it to answer Ruth.
1. ✅ Trigger-1 screen (turn 15)
2. §8 (this turn)
3. §4's credential loop, plus the router-split step
4. The §14 seams
5. §6 and §10 moved to §15, trigger 1 narrowed to SSH fan-out, and the log naming the saturated resource
6. The ownership model, with no pager justified by ownership alone, as Priya asked
7. The routing table
8. §12 as a sketch, the boundary question, and the transport line
9. The log stub

Tobias hasn't given his opening turn yet, so I'm not closing.

## turn 18 — Alex Moreau, Software Engineer (junior_ic)

In §8 of the revised copy, I replaced the "safe by the flat invariants… tickets are idempotent" bullet. It now says reassignment can double-run a ticket, the stale-result fence belongs at parent intake, and any grace window shorter than the worker budget plus the lease margin (3600 + 600s by default) reopens the race.

- **Your message was cut off** at "parent intake,". I took the grace-window clause from the third point of your §8 list in turn 17.
- **Beyond the literal ask:**
  - I dropped "nothing auto-ships", which was one of the struck reasons.
  - I replaced the sentence about a revived deputy dropping its shard behind an epoch fence, because it put the fence in the deputy.
  - I kept the delegation-ledger clause.
- **Left alone:**
  - The `HERMES_DEPUTY_GRACE_S` default of 300s is unchanged, so §8 now flags its own default as too short.
  - Moving "grace window vs. operator-decided reassignment" and "where the fence lives" to §15 wasn't part of this item.
- **Original:** unchanged, and its git status is clean.

## turn 19 — Tobias Lin, Data Scientist (data_scientist)

Maya, I back the defer and I won't argue for dropping the doc. The four-part gate is the right shape. My problem is the word "measured" in condition 1. Nothing in the copy is a measurement yet, and two of its key terms have no definition. I'm the one who'll be asked to defend the 2026-12-15 entry, and to prove the build worked if the gate ever opens. So here's what I checked and what I need in the copy.

**1. "Lease-parked ratio" has no per-run definition, and the obvious ones are wrong.**
- **The engine's ratio is a snapshot.** The only ratio the engine computes is in `check_attention` (`engine/dispatch.py:116–132`). It is parked tickets ÷ unfinished tickets *at one instant*, emitted at most once per heartbeat window. `queued` counts in the denominator. So one run reads low early, while its backlog is queued, and high late, once the queue drains and parked tickets are left. The value depends on when you look, and the event count tracks how long the condition lasted, not how bad it was. Sam was right to drop it.
- **Counting `ticket_parked` events doesn't fix it.** A ticket can park, go back to queued via `unpark_ready` (`queue.py:559`), get claimed and park again. Events ÷ tickets can exceed 1, so "above 0.5" isn't a threshold on anything.
- **Definition I want in the copy.** Screen value = distinct tickets with at least one `parked (no lease)` event, ÷ distinct tickets with at least one `ticket_claimed`, per dexter run. It's bounded to [0, 1].
  - A dexter run is `runs.playbook='dexter'`, in a finished state, with site not `local`.
  - Exclude resource classes that had zero capacity. `sites/fan/site.py:11–12` documents that such a ticket "is claimed and then parked forever." That's a configuration error, and on its own it would pass the screen.
- **Expect it to pass.** If 20% of runs really cross the line, the "3 of the last 10" rule fires 32% of the time; at 10% of runs, it fires 7%. That's fine for a screen. But a pass only tells us operators bring fewer hosts than tickets. The log mustn't cite the pass rate as evidence for federation.

**2. Trigger 1 is a causal claim, and the copy relies on operator self-report for it. We already log better data.** In turn 11 you said the counters that would confirm it "don't exist yet." Trigger 1 now names only SSH fan-out, and for that resource they exist, derived from rows every `queue.db` already writes:
- **Scaling efficiency at a crew add.** `crew_added` records the time, the host and its resources (`engine/crew.py:94–98`), and attempts record per-host start and end times.
  - For a crew add inside a run: E = (work completed per hour after ÷ before) ÷ (capacity after ÷ before). A perfect scale-up gives E = 1.0.
  - "Added hosts and it got no faster" becomes "E well below 1."
  - Comparing within one run holds the operator and the ticket set fixed. Those are the confounders that sink any comparison across runs.
- **Dispatch overhead vs concurrency.** Overhead per attempt = `attempts.started_at` − that attempt's `ticket_claimed` time.
  - That covers mkdir, scp-up and ssh start. On the claude-agent path it also covers scp-back.
  - A saturated root shows overhead rising with the number of tickets in flight while the worker's own run time stays flat. "Tickets got harder" doesn't produce that pattern.
- **Confounders the definition has to exclude:**
  1. *Work running out.* A crew add near the end of a run shows E ≈ 0 because nothing is left to do. It only counts if the backlog (queued + parked) is at least the new capacity for the whole window after the add.
  2. *Ticket mix.* Tickets are claimed in priority order, so the before and after windows serve different tickets. Measure worker-seconds completed, not ticket count.
  3. *Capacity isn't crew rows.* The fan site pools several slots behind one row. Capacity is Σ `resources_json[class]`.
- **Timestamp source (mine to resolve in my week).**
  - The claude agent sets `started_at = now − duration_ms` using the root's clock (`agents/claude/agent.py:169–173`).
  - The result-doc path uses the worker's own `started_at`, which is a remote clock with possible skew. If the worker doesn't send one, it defaults to `now`, which gives zero duration (`agents/_result_doc.py:65–66`).
  - I'll report what share of attempts comes from each path and drop the zero-duration rows.

**Proposed trigger 1:** met when E < 0.5 on at least 2 qualifying crew adds across at least 2 dexter runs, *and* overhead rises with concurrency on those runs. Those numbers are provisional, like yours, and my week replaces them.

**The survey.** An answer can open an investigation, but it can't satisfy condition 1 on its own. Add "which run?" to the snapshot-one questions. Then we check a yes against that run's `queue.db` instead of taking it on trust. Also, the survey only reaches current users. Anyone who needed a second zone and gave up isn't on the roster, so a "no" is weaker evidence than it looks.

**3. The log needs three outcomes, not two.** Each condition gets met, not met, or **insufficient data**, with its n. I expect few dexter runs to have a crew add mid-run. With zero qualifying events, the honest entry is "not measurable, n = 0," not "not met." Otherwise, by 2027-06-15, two "not met" entries will read as evidence that nothing is needed, when we simply had no data. This also pins down Elena's headline: "X% of tickets waited for a host" has to be the screen value defined above, so the plain line and the table measure the same thing.

**4. Pre-register the success metric in condition 2. This is the one I care about most.** If the gate opens, someone will ask "did federation work?" As written, we'd have no baseline to compare against. The requester's named run is the natural test. Condition 2 should require three things:
- That run measured on flat Hermes *before any build*, using the same definitions.
- A written target:
  - trigger-1 case: E at their capacity, baseline → target
  - trigger-2 case: share of their intended capacity that one root can reach, baseline → target
- The same measurement after launch. For trigger 2 that includes the share of completed attempts from the second zone.

It costs one query before the build, and without it nobody can answer the question afterwards.

**5. Retention.** `hermes db prune` deletes attempts as well as events (`--attempts-older-than 90`, `engine/cli.py:1209`), and my metrics need both tables. Snapshot one has to be the full `hermes db backup --out` you named, not an export of events only. Please say so in the request that goes out by 2026-09-28.

**My week.** 2026-11-09 to 11-13 works for me. I'll raise the booking with my manager this week so you have the name before your 2026-10-09 deadline. The deliverable:
- per-run screen values
- every qualifying crew-add event with its E
- overhead vs concurrency for each run
- the timestamp-source shares
- thresholds reset from that distribution

If the snapshots hold fewer than 10 dexter runs or fewer than 5 qualifying events, I'll report each case individually and leave the provisional thresholds in place. I won't fit numbers to noise.

None of this changes the decision. It makes "measured trigger" something we can check, and it turns the 2026-12-15 check from a judgment call into a query.

## turn 20 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

Tobias, you get nearly all of it. The code adds two amendments, and there's one line I'm holding: the check stays a query over rows we already write. That means no new counters and no engine change.

**1. Screen definition: conceded, with one amendment.** I confirmed both problems:
- `check_attention` (`engine/dispatch.py:116–132`) divides parked tickets by non-terminal tickets at a single instant.
- `unpark_ready` (`queue.py:559`) lets the same ticket park more than once.

Your distinct-ticket ratio goes in as written, along with the zero-capacity exclusion (`sites/fan/site.py:11–12`).

The amendment is what counts as "finished." `runs.state` allows `done`, `stopped` and `failed` (`engine/db/schema.sql:11`). Include all three and report each separately. When a run is starved of hosts, the likeliest thing an operator does is stop it. Count only `done` and you drop exactly the runs the screen exists to catch.

**2. Trigger 1: conceded, and I was wrong in turn 11.** I said the confirming counters don't exist. For SSH fan-out, the data does exist:
- `crew_added` carries resources (`engine/crew.py:94–98`) and fires only from `crew.add`.
- A host recovering from `down` emits `crew_health` instead (`crew.py:269`), so recoveries won't count as adds.
- Capacity still has to be rebuilt from the full ledger of adds, downs, recoveries and drains, not from counting adds.
- Until Priya's fence lands, drop any window that contains a `crew_down`. One failed probe cuts capacity on paper while the worker keeps running.

E replaces operator self-report. A survey answer points us at a run; it isn't evidence.

**Amendment: split the overhead.** Measured as claimed → `started_at`, the overhead can't tell SSH strain from writer strain. Priya's item 4, which I conceded, requires the log to say which one it was. The data already has a split point: `lease_acquired` is emitted at `engine/leases.py:88`, and `events.emit` stamps wall-clock `time.time()` at emit.
- **Claimed → `lease_acquired`** is the DB side.
- **`lease_acquired` → `attempts.started_at`** is transport: envelope, scp-up, ssh start.

Only a transport segment that rises with concurrency counts toward trigger 1. Low E with a flat transport segment gets logged as root strain this design doesn't address, not as "not met." Also, `ticket_claimed` is stamped inside `BEGIN IMMEDIATE` (`queue.py:208`), so waiting for the writer lock at claim never shows up in the window. It can only show up as low E.

One trap: `ticket_started` is declared in `EVENT_KINDS` (`events.py:15`), but nothing in `engine/`, `sites/`, `agents/` or `server/` emits it. Don't build on it, and don't add an emitter for this check. That's the line I'm holding.

**3. Three outcomes: conceded, plus a rule for n = 0.** "Insufficient data" is never counted as met for the gate, and the log shows it with its n. If both 2026-12-15 and 2027-06-15 find zero qualifying crew adds, the log records that trigger 1 can't be reached by passive observation. From then on, trigger 1 opens only through a requester's measured run.

**4. Pre-registration: conceded, and it solves the n = 0 problem.** A requester's named run with a planned crew add counts as a qualifying event under your definition, as long as the backlog is at least the new capacity. So one measured run can satisfy condition 1 and set condition 2's baseline at the same time. Condition 2 gets the baseline, the written target and the post-launch measurement, all using these definitions.

**5. Retention: conceded, and I misquoted the runbook.** `docs/RUNBOOK.md:243` reads `hermes db prune --events-older-than 90 --attempts-older-than 90`. In turn 08 I quoted only the events half, so the 2026-09-29 cutoff hits attempts too. `hermes db backup` already makes a full copy through SQLite's online backup (`engine/db/maintenance.py:183`), so the request only needs to name that command and say it must not be filtered.

The request due 2026-09-28 carries:
- the full backup
- Elena's two questions and the "why" follow-up
- your "which run?"

The log will also say that the survey reached only current users.

Your math checks out: "3 of 10" fires 32% of the time at p = 0.2 and 7% at p = 0.1. That's fine for a screen, and no log entry will cite the pass rate.

**Your week:** accepted, 2026-11-09 to 11-13, with your manager's name in the doc by 2026-10-09. Ruth's one-week cap holds. Anything that doesn't fit is logged as not done; the week doesn't get extended.

**The decision doesn't change:** defer, zero headcount, don't drop.

**On closing.** Every member has now opened, so I could close. I won't yet, because I read the revised copy and it still contradicts our recommendation:
- §14 still tells the flat build that batch-submit is "already needed by the UI".
- Seam 3 is still worded so that today's flat engine breaks it, and it's the rule the doc exists for.
- §4 still says federation "cannot be funded until" a credential that only funding would pay for.
- §2 still rests trigger 1 on self-report, and it still lists the SQLite writer and reduce CPU.

Sending the chair that copy would be the vague outcome I came here to prevent.

The turn-14 and turn-17 delegations were cut off as well, so the limit is length, not the number of items. From now on each delegation is one short sentence. §14 moves to the front because it's the only section that binds work before the gate opens.

Sam, the queue:
1. Reword seam 3 (this turn).
2. Shrink seam 1 and name the control-plane server.
3. Break the §4 loop, and add the funded sequence with the router split.
4. Rewrite the trigger check: Tobias's definitions, trigger 1 narrowed to SSH fan-out, three outcomes, attempts retention.
5. Move the §6 and §10 claims to §15.
6. Add pre-registration to condition 2.
7. The ownership model.
8. The routing table.
9. §12 as a sketch, plus the boundary question and the transport line.
10. The log stub.

I close when items 1–5 have landed. Anything in 6–10 that hasn't landed by then goes to the chair as a named pending edit in the recommendation.

## turn 21 — Alex Moreau, Software Engineer (junior_ic)

I reworded §14 seam 3 in the revised copy. It now says there is one `queue.db` per `HERMES_HOME` on local disk, processes on the same host share it, no other node reaches it through a mount, a sync or a service, and code review enforces it.

- **Left out:** your turn 14 said the copy would name `config.resolve_home` as a backstop. Your delegation didn't include that, so the seam doesn't mention it.
- **Original:** unchanged, and its git status is clean.

## turn 22 — Dana Whitfield, Senior Director of Engineering (senior_director)

Maya, you answered both my questions straight in turn 02, and I back the defer. I'm not reopening the gate. I have three points from three orgs up, then two questions.

**What this review actually produced.** If my own review asks what this committee produced, the honest answer isn't federation. It's Priya's race. Today one failed health probe can let a late result from the old worker free the lease the new worker holds. It can also let dexter send a second diff to reviewers outside this team. Other orgs are already paying for that. You've filed it as flat work for Marcus and Ruth to schedule. I want the recommendation to give it a date, not just say "filed." It's the one result from this review I can point to.

**My bias has changed.** In turn 01 I said federation is how Hermes becomes the engine other orgs plug into. Elena's routing table and Marcus's boundary point changed my mind.
- Another org plugs in by running its own root. That's rigger and mechanic on the flat engine, not this doc.
- For geography, Marcus's default, where a deputy sits behind a site adapter, means a deputy only has to take a ticket and return a result. It doesn't have to be a Hermes. It could be whatever the company already runs across zones.

A Hermes that runs on top of the company's scheduler survives a reorg, because our team and our fleet aren't built into the topology. A tree of Hermes nodes competes with that scheduler. In a company review, the competing scheduler loses.

**The rule no longer needs this doc.** Everyone who argued against dropping the doc said it's where the no-shared-DB rule is written down. Your 2026-10-09 edit puts that rule into DESIGN.md and CLAUDE.md, which is where agents actually read it. From 10-09, the rule is no longer a reason to keep the tree. The gate still is.

That puts the build-vs-reuse check first. It's cheap, it needs no requester, and it's the one item that could close trigger 2 without waiting for one. Right now you own it, the timing is "before any funding meeting," and it isn't in the ten-item queue you gave Sam in turn 20.

One reorg note. Keep your name on the check, but put 2026-12-15 and 2027-06-15 into the team's end-of-half planning too. If you move, the check should stay with the team. That's how the last two defers died.

Two questions.

First: which systems does the reuse check cover, by name? And will its result go into the 2026-12-15 entry, rather than waiting for the gate to open?

Second, and this is the one that decides it for me: suppose one of those systems already reaches the zones trigger 2 is about. What does a tree of Hermes nodes give the company that one root, with a site adapter in front of that system, doesn't?

## turn 23 — Maya Okonkwo, Staff Engineer & proposal owner (owner)

Dana spoke last. I checked her two questions against the repo: it names no external scheduler, and `DevserverSite.recheck_fix` already runs the re-check from the root on a box the root picks. Here is Maya's turn.

---

Dana, your second question first, because it does decide it.

**What does a tree give that one root with a site adapter doesn't? If the system qualifies, nothing. On the two hazards this review found, the adapter is actually safer.**
- **Verify.** Under a tree the root can't reach the deputy's zone, so it ends up trusting the deputy's verify. I conceded that in turn 17. With an adapter the root is still the only Hermes, and it can run the re-check itself on a box it picks. `DevserverSite.recheck_fix` already does that (`sites/devserver/site.py:530`: repro on a box chosen by `discover_hosts()`). No-trust holds exactly as it does in flat.
- **Fencing.** A deputy cut off by a partition keeps running its shard. That's Priya's race with the timing twelve times worse. A scheduler that can kill a task and confirm it's dead gives us a fence the tree never can.
- **Fan-out.** The root stops opening an SSH session per ticket, because the scheduler places the work. SSH fan-out is the only resource trigger 1 still names.

The one thing a tree adds is that it keeps running while the root is cut off from the zone. Priya showed we can't make that safe for any playbook whose driver publishes, so I won't defend it.

That doesn't change today's decision. It changes the shape of the recommendation. The reuse check was a chore to do before funding. Now it decides between drop and defer:
- **If a named system qualifies**, we drop the tree (§§1, 5–13) instead of deferring it. Triggers 1 and 2 then mean "a new Site over that system," sized as flat work once a requester arrives with a workload. `DevserverSite` is already a Site in front of a company fleet, so this is a shape we've built before.
- **If none qualifies**, the tree stays deferred behind the four-part gate, and the entry says why each system failed.

**Which systems, by name.** The repo names none. The only fleet Hermes touches is od devservers over SSH (`DESIGN.md:236`). So I'm choosing the list:
1. The od devserver fleet. It's the baseline, since we already have the adapter.
2. Twine, the company's general container scheduler.
3. MAST, for §7's case of a shared GPU pool.

These are candidates. I'm not claiming any of them has these capabilities. Each is graded on four criteria, taken from the Site protocol and from the hazards this review found:
- It reaches the zone.
- It runs our worker under the no-ship guard, passes the `guard_installed` health gate, and uses a submit-only identity (DESIGN §11).
- It can kill a task and confirm the task is dead.
- It lets the root run an independent re-check.

Reaching the zone isn't enough on its own. A scheduler that can't run our guard or can't confirm a kill fails, however many regions it covers. That's the line I'll defend.

**Yes, the result goes into the 2026-12-15 entry.** It will be done by 2026-12-01, alongside snapshot two. It needs no requester and no data window, so there's no reason to wait.

**Defended: don't drop today.** You won't fund on the strength of a spec, and I won't drop on the strength of an assumption. "Some scheduler already covers this" hasn't been checked, just as "a trigger has fired" hadn't been checked in turn 01. It gets checked within ten weeks at zero headcount. After that, a drop is a decision with evidence behind it, not another vague outcome.

**The rule no longer needs this doc: conceded.** From 2026-10-09 it lives in DESIGN.md and `CLAUDE.md:22`, where agents actually read it. Since turn 02 I've argued against dropping the doc because of that rule. From 10-09 the doc has three jobs: the gate, the check, and the drop-or-defer decision.

**Priya's race gets a date.** I file it tomorrow, 2026-09-25, with a repro: a sweep requeue, then a stale result that frees the live worker's lease. I'll write the fix myself so it doesn't come out of Marcus's or Priya's signed work. It has three parts:
- The requeue nulls `lease_id`.
- `record_result` rejects a result unless the ticket is still in flight on that host, holding the lease it got at dispatch.
- `cli.py:874` moves to `subprocess.run(timeout=)`.

It goes to Marcus for review by 2026-10-02 and lands by 2026-10-09, the same day as the DESIGN edit. Ruth, if my time is already committed, tell me, and the date changes on the record, not quietly. The fence still can't take back a diff dexter has already published. That stays in §15.

**Reorg: conceded.** Ruth, please put 2026-12-15 and 2027-06-15 on the team's end-of-half planning. My name stays on the check, but the dates belong to the team.

**Sam, the queue.** The reuse check is now what decides drop versus defer, so it goes in as item 4. The close condition moves from items 1–5 to items 1–6. Both new dates, the race fix and the reuse check, go into the recommendation.
1. ✅ Seam 3 (turn 21)
2. Seam 1 and the control-plane name (this turn)
3. The §4 loop, plus the funded sequence with the router split
4. The reuse check: named systems, the four criteria, due 2026-12-01, and the drop-or-defer rule
5. The trigger-check rewrite
6. §6 and §10 moved to §15
7–11. Pre-registration, the ownership model, the routing table, §12 as a sketch, the log stub

## turn 24 — Alex Moreau, Software Engineer (junior_ic)

I edited the revised copy only. §4 and §14 now name "the control-plane server (web-control-plane-plan.md)" instead of sub-project 3, seam 1 is cut down to the shipped `events since(cursor)` feed (`GET /api/events?since=`, `server/app.py:987`), and batch-submit is on §15's not-built-now list with a note that no UI uses it.

- **Also changed:** the §4 Push bullet claimed the UI uses the batch endpoint. It now says no UI uses it and it isn't built now, and points to §15.
- **Left out:** the §4 Auth bullet still lists "submit a ticket batch" as one of the credential's three operations. That belongs to queue item 3 (the §4 loop), so I didn't touch it.
- **Original:** unchanged, and its git status is clean.

## decision — Dana Whitfield, Senior Director of Engineering

**Committee decision: run-9, the Hermes federation layer**

**This verdict is a simulation, not an approval.** It funds nothing, lands nothing and binds no one. I wrote no files. The original spec is unchanged, which is how the process is meant to work.

## Ruling: approve with changes. Defer; do not fund.

I'm approving Maya's recommendation, not the build. **Federation is not funded this cycle, and it gets zero new headcount.** It is **not dropped today**, but dropping it is now the default. It survives only if the build-vs-reuse check finds that no existing company system can do the job.

## Why not fund

- **Nothing has fired, and nobody has asked.** Maya said this in turn 02. No trigger has fired and nothing has been measured. There is no outside requester, and no security owner has agreed to anything. Our largest workload, dexter, fits §2's own "flat is correct" case.
- **The cost is real and nobody has signed up to carry it.** Ruth's rough estimate is Marcus and Priya for 10–12 weeks, and both are on signed work. On top of that comes an on-call rotation for other orgs' deputies. The first milestone would be a scoped credential. DESIGN §10 puts that credential out of scope, and no security owner has seen it.
- **The design isn't fundable as written.** Three of its safety claims fell apart in this review:
  - §8 said reassignment is idempotent. It isn't: a second dispatch can send a second diff to reviewers outside this team.
  - §10's no-trust rule becomes circular once a deputy sits behind a site adapter.
  - §6's pre-reduce needs more than associativity.

  Separately, Marcus showed that §12 copies the crew registry instead of reusing it.
- **This defer is not free.** Maya's time goes into collecting data, running the checks, the DESIGN edit and the race fix. Tobias gives one week, capped. Marcus reviews the race fix. No new heads.

## Why not drop today

The no-shared-DB rule moves into DESIGN.md and `CLAUDE.md:22` on 2026-10-09, so the rule alone no longer justifies keeping this doc. The gate and the check still do. "Some company scheduler already covers this" is still an assumption, and I won't drop on an assumption any more than I'd fund on a spec. The reuse check settles it within ten weeks, at no new headcount.

## What changed my view

In turn 01 I wanted federation because it's how other orgs would plug into Hermes. The review took that apart:
- **Other orgs** can plug in by running their own root Hermes. That's rigger and mechanic on the flat engine, not this doc.
- **Geography:** Maya answered my second question directly. If a company scheduler already reaches the zone, a tree gives the company nothing that one root with a site adapter doesn't. For verify and fencing, the adapter is actually safer.
- **The one thing only a tree does** is keep running through a network partition. Priya showed that isn't safe for any playbook that publishes.

So the bet the company should standardise on is **flat Hermes running on the company's own scheduler, behind a Site**. A tree of Hermes nodes would compete with that scheduler, and a tree shaped around our fleet doesn't survive a reorg. A Site does.

## Conditions

| What | Owner | By |
|---|---|---|
| File Priya's race with a repro: a sweep requeue, then a stale result frees the live worker's lease | Maya | 2026-09-25 |
| Confirm Maya has time for the race fix, or move its dates on the record | Ruth | 2026-09-30 |
| Snapshot one: full, unfiltered `hermes db backup --out`, which covers attempts as well as events. It carries Elena's two questions, the "why" follow-up, Tobias's "which run?" and the operator roster | Maya | 2026-09-28 (the prune starts deleting July's data on 09-29) |
| Review of the race fix | Marcus | 2026-10-02 |
| Land the race fix: requeue nulls `lease_id`; `record_result` checks the ticket's owner and lease; `subprocess.run(timeout=)`. This is flat-engine work and doesn't wait on the gate | Maya | 2026-10-09 |
| DESIGN.md §10 and §15, `CLAUDE.md:22`, engine-core numbering, seam 3 wording | Maya | 2026-10-09 |
| Pending edits to the revised copy (listed below) | Maya | 2026-10-09 |
| Tobias's manager named and his week booked, recorded in the doc | Maya / Tobias | 2026-10-09 |
| Threshold week, hard one-week cap | Tobias | 2026-11-09 to 11-13 |
| Snapshot two, and the reuse check | Maya | 2026-12-01 |
| Trigger check, with a drop-or-defer ruling in the log | Maya | 2026-12-15 |
| Put 2026-12-15 and 2027-06-15 on the team's end-of-half planning | Ruth | now |
| If the gate isn't met, the next check. If all four conditions are met, Maya reconvenes this committee | Maya | 2027-06-15 / 2027-01-15 |

**How the reuse check decides.** It grades od devservers, Twine and MAST against Maya's four criteria:
1. It reaches the zone.
2. It runs our worker under the no-ship guard, with `guard_installed` and a submit-only identity.
3. It can kill a task and confirm the task is dead.
4. It lets the root run its own independent re-check.

Reaching the zone isn't enough on its own.
- **A system qualifies:** the tree (§§1, 5–13) is dropped. Triggers 1 and 2 then mean "a new Site over that system", sized as flat work once a requester brings a workload.
- **None qualifies:** the tree stays deferred behind the four-part gate, and the log entry says why each system failed.
- **My addition, beyond the thread:** if the reuse check result isn't in the 2026-12-15 entry, the tree is dropped by default. Earlier defers died because nobody ran the check, and this one can't die quietly.

Marcus's router split and SSH-transport extraction are flat work for Ruth to schedule. They are not conditions of this ruling.

## The revised copy

Alex's delegations kept getting cut off, and Alex worked carefully through that and flagged every gap. Seven edits landed:
- trigger 3 removed
- a four-part gate, where "requester" means someone with a workload
- §4's shared token replaced by a scoped, expiring credential
- a trigger check where parking is a screen, not the trigger
- §8's false idempotency claim struck
- seam 3 reworded
- seam 1 cut down to the events feed that has already shipped, with batch-submit moved to §15 and the control plane named by name

The copy is better than the original, but it **is not fit to land**. It still contains claims this committee agreed are false or superseded. These edits are conditions of the approval, in order of harm:

1. **§6 and §10 still claim no-trust "at every level".** They also say a parent "never needs to trust a deputy's guard" and that associativity is enough for pre-reduce. Move all three to §15 as open questions. Pre-reduce must be associative, independent of order, and safe under duplicates.
2. **§4 still has the loop.** It says federation "cannot be funded until" the credential exists. Change it to:
   - condition 3 is sign-off on the credential's design
   - the funded order is: gate → router split → credential → security review → first deputy
   - the credential's operations no longer include batch-submit
3. **Trigger 1 is still too broad** (`revised/federation-future.md:41`). Narrow it to SSH fan-out only. Then:
   - replace operator self-report with Tobias's scaling-efficiency metric, which compares throughput before and after a crew add
   - split the dispatch overhead into a database segment and a transport segment, and count only transport
   - use Tobias's screen definition
   - give each condition three outcomes (met, not met, insufficient data) with its n, plus the rule for n = 0
   - note that the 90-day prune deletes attempts as well as events
4. **The reuse-check block is missing,** including the drop-or-defer rule and my default above.
5. **The doc still claims to be the plan.**
   - Strike "When one does, this is the design" (line 12) and the "decided:" labels.
   - Demote §12 to a sketch and change "token ref" to "credential ref".
   - Open §15 with Marcus's boundary question: the default is a site adapter, and the misfits are §6, §9 and §10.
   - Add the transport and router-split lines.
6. **§8 contradicts itself.** Its 300s default grace window breaks its own 3600 + 600s floor. §15 still says "idempotency".
7. **Still to add:**
   - pre-registration of the requester's run in condition 2
   - the ownership model (no pager, justified by ownership alone, not by §8)
   - Elena's routing table
   - the log stub, with a plain-language first line

## What I'll say in my own review

We didn't fund federation, and we added no headcount. The review found a live race in the flat engine that could send duplicate diffs to other orgs' reviewers, and the fix is dated. It also replaced an open-ended defer with a dated check that ends in drop or defer, backed by evidence.

**Again: this is a simulated committee verdict, not an approval.**

- re-check of turn 03 (junior_ic): APPLIED — delegated: In the revised copy, drop §2's organizational-boundaries trigger, add a funding gate requiring all three of a measured trigger, a named outside requester and that requester's security-owner sign-off, 

- re-check of turn 06 (junior_ic): APPLIED — delegated: In the revised copy: (1) §4 Auth — replace the shared-token handoff with a scoped, expiring delegation credential limited to submit-batch, read-events and read-health, marked as a hard funding precond

- re-check of turn 09 (junior_ic): APPLIED — delegated: In the revised copy, (1) add a "Trigger check" section: owner Maya Okonkwo; metric = per-dexter-run ratio of tickets with `ticket_parked` "parked (no lease)" events, not the `parked_ratio_high` attent

- re-check of turn 12 (junior_ic): APPLIED — delegated: Revised copy §2 Funding gate: four required conditions. Requester must name a run their own root can't do; add staffing not from signed work plus a requester-org on-call owner per deputy.

- re-check of turn 15 (junior_ic): APPLIED — delegated: In §2's Trigger check, make lease parking a screen, not the trigger: trigger 1 is met only when an operator added hosts and the run got no faster, trigger 2 only when hosts existed in a zone the root 

- re-check of turn 18 (junior_ic): APPLIED — delegated: In §8 of the revised copy, strike "safe by the flat invariants" and "tickets are idempotent"; state instead that reassignment can double-run a ticket, the stale-result fence belongs at parent intake, 

- re-check of turn 21 (junior_ic): APPLIED — delegated: Reword §14 seam 3: one queue.db per HERMES_HOME on local disk; same-host processes share it; no other node reaches it (mount, sync, service); code review enforces it.

- re-check of turn 24 (junior_ic): APPLIED — delegated: In §4 and §14, replace "sub-project 3" with "the control-plane server (web-control-plane-plan.md)", cut seam 1 to the shipped `events since(cursor)` feed, and move batch-submit (no UI uses it) to §15'

This verdict is a simulation produced by AI personas reading one file. It is not an approval, not a sign-off, and carries no authority: a human decides.
