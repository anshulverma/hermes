"""Tests for the research playbook and its item-source registry.

TDD: written first.
"""
import pytest

from engine.models import Finding, Reduction, Result, Run, Ticket


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Keep host configuration out of the tests."""
    for var in (
        "HERMES_RESEARCH_SOURCE",
        "HERMES_RESEARCH_AGENTS",
        "HERMES_RESEARCH_LIMIT",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def source(request):
    """Register a controllable item source and return its mutable item list."""
    from playbooks.research import sources

    items: list[dict] = []
    name = f"test-source-{request.node.name}"
    sources.register(name, lambda config: list(items))
    return name, items


def _run(config=None, phase="research", reductions=None):
    """Helper: construct a Run for testing."""
    return Run(
        id="research-20260803-000000",
        playbook="research",
        site="fan-claude",
        base_ref="main",
        config=config if config is not None else {},
        phase=phase,
        reductions=reductions or [],
    )


def _finding(run: Run, ticket_id: str, answer: str) -> Finding:
    """Helper: construct a Finding the way the queue writes one."""
    return Finding(
        run_id=run.id,
        ticket_id=ticket_id,
        kind="result",
        json={"answer": answer},
    )


def _result(payload) -> Result:
    """Helper: construct a worker Result."""
    return Result(
        outcome="ok",
        termination_reason="goal_met",
        result_ref="r1",
        error_summary=None,
        started_at=1000.0,
        ended_at=2000.0,
        payload=payload,
    )


def _playbook():
    """Helper: a fresh playbook instance (a fresh process's view)."""
    from playbooks.research.playbook import ResearchPlaybook

    return ResearchPlaybook()


# --- item sources ---------------------------------------------------------


def test_source_registry_register_and_load():
    """A registered source resolves back by name."""
    from playbooks.research import sources

    def fn(config):
        return [{"id": "a", "title": "A", "context": "ctx"}]

    sources.register("__test_source__", fn)
    assert sources.load("__test_source__") is fn


def test_source_registry_unknown_name_lists_known_names():
    """Loading an unregistered source names the registered ones."""
    from playbooks.research import sources

    with pytest.raises(KeyError) as excinfo:
        sources.load("no-such-source")
    message = str(excinfo.value)
    assert "no-such-source" in message
    assert "config" in message


def test_config_source_turns_goals_into_items():
    """The built-in config source reads items straight out of the run config."""
    from playbooks.research import sources

    items = sources.load("config")({"goals": ["Look at the cache", "Look at the queue"]})

    assert [i["title"] for i in items] == ["Look at the cache", "Look at the queue"]
    assert [i["context"] for i in items] == ["Look at the cache", "Look at the queue"]
    ids = [i["id"] for i in items]
    assert len(set(ids)) == 2
    for item_id in ids:
        assert item_id
        assert "/" not in item_id
        assert " " not in item_id


def test_config_source_passes_explicit_items_through():
    """Explicit item dicts keep their id and their extra keys."""
    from playbooks.research import sources

    items = sources.load("config")({
        "items": [{"id": "cache", "title": "Cache", "context": "ctx", "url": "u"}],
    })

    assert items == [{"id": "cache", "title": "Cache", "context": "ctx", "url": "u"}]


def test_config_source_with_no_items_returns_nothing():
    """No goals and no items is an empty set, not an error."""
    from playbooks.research import sources

    assert sources.load("config")({}) == []


# --- protocol conformance -------------------------------------------------


def test_research_playbook_conforms_to_the_protocol():
    """The registered research playbook satisfies the Playbook protocol."""
    import playbooks.research  # noqa: F401  (registers "research")
    from engine import playbook as _playbook
    from engine.playbook import Playbook

    pb = _playbook.load("research")
    assert isinstance(pb, Playbook)
    assert pb.name == "research"
    assert pb.phases == ["research", "synthesize", "report", "complete"]


# --- seeding --------------------------------------------------------------


def test_seed_research_fans_items_across_agents(source):
    """One ticket per (item x agent), each routed to its own agent class."""
    name, items = source
    items.extend([
        {"id": "one", "title": "One", "context": "first"},
        {"id": "two", "title": "Two", "context": "second"},
    ])
    run = _run({"source": name, "agents": ["claude", "codex"]})

    tickets = _playbook().seed(run, site=None)

    assert len(tickets) == 4
    assert [t.id for t in tickets] == [
        f"{run.id}/research-one-claude",
        f"{run.id}/research-one-codex",
        f"{run.id}/research-two-claude",
        f"{run.id}/research-two-codex",
    ]
    assert [t.resource_req for t in tickets] == [
        "agent:claude", "agent:codex", "agent:claude", "agent:codex",
    ]
    assert {t.phase for t in tickets} == {"research"}
    assert {t.state for t in tickets} == {"queued"}
    assert tickets[0].payload["agent"] == "claude"
    assert tickets[0].payload["item"]["id"] == "one"
    assert tickets[0].payload["item"]["context"] == "first"
    assert "one" in tickets[0].payload["goal"]


def test_seed_research_defaults_to_the_config_source_and_one_agent():
    """With nothing configured, goals become items and claude gets them all."""
    run = _run({"goals": ["Alpha", "Beta"]})

    tickets = _playbook().seed(run, site=None)

    assert len(tickets) == 2
    assert {t.resource_req for t in tickets} == {"agent:claude"}


def test_seed_research_honours_the_limit(source):
    """The limit caps the item count, because cost is items x agents."""
    name, items = source
    items.extend(
        {"id": f"i{n}", "title": f"I{n}", "context": "c"} for n in range(10)
    )
    run = _run({"source": name, "agents": ["claude"], "limit": 3})

    tickets = _playbook().seed(run, site=None)

    assert len(tickets) == 3


def test_seed_research_reads_configuration_from_the_environment(source, monkeypatch):
    """Absent run config, source/agents/limit come from the environment."""
    name, items = source
    items.extend(
        {"id": f"i{n}", "title": f"I{n}", "context": "c"} for n in range(10)
    )
    monkeypatch.setenv("HERMES_RESEARCH_SOURCE", name)
    monkeypatch.setenv("HERMES_RESEARCH_AGENTS", "claude, codex")
    monkeypatch.setenv("HERMES_RESEARCH_LIMIT", "2")
    run = _run({})

    tickets = _playbook().seed(run, site=None)

    assert len(tickets) == 4
    assert {t.resource_req for t in tickets} == {"agent:claude", "agent:codex"}


def test_seed_merge_phases_route_to_the_first_configured_agent(source):
    """synthesize and report are served by the first agent in the list."""
    name, items = source
    items.append({"id": "one", "title": "One", "context": "first"})
    pb = _playbook()
    config = {"source": name, "agents": ["codex", "claude"]}

    synth_run = _run(config, phase="synthesize", reductions=[Reduction(
        kind="item_analyses",
        json={
            "item": {"id": "one", "title": "One", "context": "first"},
            "analyses": [{"agent": "codex", "analysis": "text"}],
            "succeeded_agents": ["codex"],
            "failed_agents": [],
            "status": "ok",
        },
    )])
    synth_tickets = pb.seed(synth_run, site=None)
    assert [t.id for t in synth_tickets] == [f"{synth_run.id}/synthesize-one"]
    assert synth_tickets[0].resource_req == "agent:codex"

    report_run = _run(config, phase="report", reductions=[Reduction(
        kind="item_syntheses",
        json={
            "syntheses": [{"ticket_id": "t", "item_id": "one", "synthesis": "text"}],
            "item_count": 1,
        },
    )])
    report_tickets = pb.seed(report_run, site=None)
    assert [t.id for t in report_tickets] == [f"{report_run.id}/report-0"]
    assert report_tickets[0].resource_req == "agent:codex"


def test_seed_complete_phase_has_no_tickets():
    """The sentinel phase carries no work."""
    run = _run({"goals": ["Alpha"]}, phase="complete")
    assert _playbook().seed(run, site=None) == []


def test_seeded_payloads_satisfy_their_phase_schema(source):
    """Every seeded payload validates against the phase's payload schema."""
    from engine import contracts

    name, items = source
    items.append({"id": "one", "title": "One", "context": "first"})
    pb = _playbook()
    config = {"source": name, "agents": ["claude"]}

    research = pb.seed(_run(config), site=None)
    synth = pb.seed(_run(config, phase="synthesize", reductions=[Reduction(
        kind="item_analyses",
        json={
            "item": {"id": "one", "title": "One", "context": "first"},
            "analyses": [{"agent": "claude", "analysis": "text"}],
            "succeeded_agents": ["claude"],
            "failed_agents": [],
            "status": "ok",
        },
    )]), site=None)
    report = pb.seed(_run(config, phase="report", reductions=[Reduction(
        kind="item_syntheses",
        json={
            "syntheses": [{"ticket_id": "t", "item_id": "one", "synthesis": "text"}],
            "item_count": 1,
        },
    )]), site=None)

    for ticket in research + synth + report:
        contracts.validate(ticket.payload, pb.payload_schema(ticket.phase))


# --- goal + title ---------------------------------------------------------

# A goal is an instruction, not a document: the material it refers to travels
# in the payload, so no phase's goal has any business being kilobytes long.
GOAL_MAX_CHARS = 1500

_BULK = (
    "The item is a landed change to the queue module. It releases the lease as "
    "soon as the ticket leaves running rather than at TTL expiry. "
) * 40


def _bulky_phase_tickets(source):
    """Seed one ticket per phase from deliberately bulky material."""
    name, items = source
    items.extend(
        {"id": f"item-{n}", "title": f"Item {n}", "context": _BULK} for n in range(5)
    )
    pb = _playbook()
    config = {"source": name, "agents": ["claude", "codex"]}

    research = pb.seed(_run(config), site=None)[0]
    synthesize = pb.seed(_run(config, phase="synthesize", reductions=[Reduction(
        kind="item_analyses",
        json={
            "item": {"id": "item-0", "title": "Item 0", "context": _BULK},
            "analyses": [
                {"agent": "claude", "analysis": _BULK},
                {"agent": "codex", "analysis": _BULK},
            ],
            "succeeded_agents": ["claude", "codex"],
            "failed_agents": [],
            "status": "ok",
        },
    )]), site=None)[0]
    report = pb.seed(_run(config, phase="report", reductions=[Reduction(
        kind="item_syntheses",
        json={
            "syntheses": [
                {
                    "ticket_id": f"run-1/synthesize-item-{n}",
                    "item_id": f"item-{n}",
                    "synthesis": _BULK,
                }
                for n in range(5)
            ],
            "item_count": 5,
        },
    )]), site=None)[0]
    return research, synthesize, report


def test_every_seeded_ticket_carries_a_one_line_title(source):
    """Each phase names itself in a title the UI can use as a heading."""
    research, synthesize, report = _bulky_phase_tickets(source)

    for ticket in (research, synthesize, report):
        title = ticket.payload["title"]
        assert title.strip(), f"{ticket.phase} seeded an empty title"
        assert "\n" not in title
        assert len(title) <= 120, f"{ticket.phase} title is {len(title)} chars"
        assert 10 <= len(title.split()) <= 16, (
            f"{ticket.phase} title is {len(title.split())} words: {title!r}"
        )

    # And each says what the ticket is for, naming its item.
    assert "item-0" in research.payload["title"]
    assert "item-0" in synthesize.payload["title"]
    assert "5" in report.payload["title"]


def test_goals_stay_short_and_still_name_their_item(source):
    """Bulky material does not inflate the goal; the goal still identifies the item."""
    research, synthesize, report = _bulky_phase_tickets(source)

    for ticket in (research, synthesize, report):
        goal = ticket.payload["goal"]
        assert len(goal) < GOAL_MAX_CHARS, (
            f"{ticket.phase} goal is {len(goal)} chars"
        )
        assert _BULK[:80] not in goal, f"{ticket.phase} goal inlines its material"

    assert "item-0" in research.payload["goal"]
    assert "item-0" in synthesize.payload["goal"]
    assert "item-0" in report.payload["goal"]


def test_the_material_the_goal_refers_to_is_still_in_the_payload(source):
    """Shortening the prose moves the material, it does not drop it."""
    research, synthesize, report = _bulky_phase_tickets(source)

    assert research.payload["item"]["context"] == _BULK
    assert synthesize.payload["item"]["context"] == _BULK
    assert [a["analysis"] for a in synthesize.payload["analyses"]] == [_BULK, _BULK]
    assert [s["synthesis"] for s in report.payload["syntheses"]] == [_BULK] * 5
    assert report.payload["summary"] == {"item_count": 5}


def test_synthesize_goal_names_the_agents_that_did_not_deliver(source):
    """A missing analysis is stated in the instruction, not left to be inferred."""
    name, items = source
    items.append({"id": "one", "title": "One", "context": "ctx"})
    config = {"source": name, "agents": ["claude", "codex"]}
    ticket = _playbook().seed(_run(config, phase="synthesize", reductions=[Reduction(
        kind="item_analyses",
        json={
            "item": {"id": "one", "title": "One", "context": "ctx"},
            "analyses": [{"agent": "claude", "analysis": "text"}],
            "succeeded_agents": ["claude"],
            "failed_agents": ["codex"],
            "status": "ok",
        },
    )]), site=None)[0]

    assert "codex" in ticket.payload["goal"]


# --- reduce ---------------------------------------------------------------


def test_reduce_research_derives_items_from_finding_ticket_ids(source):
    """The reduced set comes from what was seeded, not from a source that
    now answers differently."""
    name, items = source
    items.extend([
        {"id": "one", "title": "One", "context": "first"},
        {"id": "two", "title": "Two", "context": "second"},
    ])
    config = {"source": name, "agents": ["claude"], "limit": 10}
    run = _run(config)
    tickets = _playbook().seed(run, site=None)
    findings = [_finding(run, t.id, "analysis text") for t in tickets]

    # Another process: the source now answers with more items.
    items.extend([
        {"id": "three", "title": "Three", "context": "third"},
        {"id": "four", "title": "Four", "context": "fourth"},
    ])

    reductions = _playbook().reduce(run, "research", findings, site=None)

    assert [r.kind for r in reductions] == ["item_analyses", "item_analyses"]
    assert [r.json["item"]["id"] for r in reductions] == ["one", "two"]
    # Metadata enrichment still works for the items that were seeded.
    assert reductions[0].json["item"]["title"] == "One"


def test_reduce_research_survives_a_source_that_now_fails(source):
    """A source that raises later cannot lose the seeded items."""
    from playbooks.research import sources

    name, items = source
    items.append({"id": "one", "title": "One", "context": "first"})
    run = _run({"source": name, "agents": ["claude"]})
    tickets = _playbook().seed(run, site=None)
    findings = [_finding(run, t.id, "analysis text") for t in tickets]

    def boom(config):
        raise RuntimeError("source unavailable")

    sources.register(name, boom)

    reductions = _playbook().reduce(run, "research", findings, site=None)

    assert [r.json["item"]["id"] for r in reductions] == ["one"]
    assert reductions[0].json["status"] == "ok"


def test_reduce_research_partial_failure_still_synthesises(source):
    """One agent failing does not sink the item; the failure is recorded."""
    name, items = source
    items.append({"id": "one", "title": "One", "context": "first"})
    config = {"source": name, "agents": ["claude", "codex"]}
    run = _run(config)
    findings = [
        _finding(run, f"{run.id}/research-one-claude", "claude's analysis"),
        _finding(run, f"{run.id}/research-one-codex", "   "),
    ]

    reductions = _playbook().reduce(run, "research", findings, site=None)

    assert len(reductions) == 1
    doc = reductions[0].json
    assert doc["status"] == "ok"
    assert doc["succeeded_agents"] == ["claude"]
    assert doc["failed_agents"] == ["codex"]
    assert doc["analyses"] == [{"agent": "claude", "analysis": "claude's analysis"}]

    # And that reduction still seeds a synthesis ticket.
    synth_run = _run(config, phase="synthesize", reductions=reductions)
    synth_tickets = _playbook().seed(synth_run, site=None)
    assert [t.id for t in synth_tickets] == [f"{run.id}/synthesize-one"]
    assert "codex" in synth_tickets[0].payload["goal"]


def test_reduce_research_item_with_no_successes_is_failed(source):
    """Zero successful analyses is a failed item and seeds no synthesis."""
    name, items = source
    items.append({"id": "one", "title": "One", "context": "first"})
    config = {"source": name, "agents": ["claude", "codex"]}
    run = _run(config)
    findings = [
        _finding(run, f"{run.id}/research-one-claude", ""),
        _finding(run, f"{run.id}/research-one-codex", ""),
    ]

    reductions = _playbook().reduce(run, "research", findings, site=None)

    assert len(reductions) == 1
    assert reductions[0].json["status"] == "failed"
    assert reductions[0].json["analyses"] == []
    assert reductions[0].json["failed_agents"] == ["claude", "codex"]

    synth_run = _run(config, phase="synthesize", reductions=reductions)
    assert _playbook().seed(synth_run, site=None) == []


def test_reduce_synthesize_folds_into_one_report_input(source):
    """Every per-item synthesis lands in a single reduction."""
    name, items = source
    run = _run({"source": name, "agents": ["claude"]}, phase="synthesize")
    findings = [
        _finding(run, f"{run.id}/synthesize-one", "one's synthesis"),
        _finding(run, f"{run.id}/synthesize-two", "two's synthesis"),
        _finding(run, f"{run.id}/synthesize-three", ""),
    ]

    reductions = _playbook().reduce(run, "synthesize", findings, site=None)

    assert len(reductions) == 1
    doc = reductions[0].json
    assert reductions[0].kind == "item_syntheses"
    assert doc["item_count"] == 2
    assert [s["item_id"] for s in doc["syntheses"]] == ["one", "two"]
    assert doc["syntheses"][0]["synthesis"] == "one's synthesis"


def test_reduce_report_banks_the_report(source):
    """The report phase reduces to the report text."""
    name, _items = source
    run = _run({"source": name}, phase="report")
    findings = [_finding(run, f"{run.id}/report-0", "the whole story")]

    reductions = _playbook().reduce(run, "report", findings, site=None)

    assert len(reductions) == 1
    assert reductions[0].kind == "research_report"
    assert reductions[0].json["report"] == "the whole story"


def test_reduce_report_with_no_text_banks_nothing(source):
    """An empty report is not a report."""
    name, _items = source
    run = _run({"source": name}, phase="report")
    findings = [_finding(run, f"{run.id}/report-0", "  ")]

    assert _playbook().reduce(run, "report", findings, site=None) == []


# --- verify / advancement / completion ------------------------------------


def test_verify_requires_answer_text():
    """A result is admitted only when it carries text under answer."""
    pb = _playbook()
    run = _run({})
    ticket = Ticket(
        id=f"{run.id}/research-one-claude",
        run_id=run.id,
        phase="research",
        state="running",
        resource_req="agent:claude",
        priority=0.0,
        attempts=0,
        payload={},
    )

    assert pb.verify(run, ticket, _result({"answer": "something"}), site=None) is True
    assert pb.verify(run, ticket, _result({"answer": "   "}), site=None) is False
    assert pb.verify(run, ticket, _result({}), site=None) is False


def test_next_phase_walks_the_phases():
    """research -> synthesize -> report -> complete -> None."""
    pb = _playbook()

    assert pb.next_phase(_run({}, phase=None)) == "research"
    assert pb.next_phase(_run({}, phase="research")) == "synthesize"
    assert pb.next_phase(_run({}, phase="synthesize")) == "report"
    assert pb.next_phase(_run({}, phase="report")) == "complete"
    assert pb.next_phase(_run({}, phase="complete")) is None


def test_is_done_only_with_a_real_report():
    """Reaching the sentinel phase is not enough; a report must exist."""
    pb = _playbook()
    report = Reduction(kind="research_report", json={"report": "the whole story"})
    empty = Reduction(kind="research_report", json={"report": "   "})

    assert pb.is_done(_run({}, phase="complete", reductions=[report])) is True
    assert pb.is_done(_run({}, phase="complete", reductions=[empty])) is False
    assert pb.is_done(_run({}, phase="complete", reductions=[])) is False
    assert pb.is_done(_run({}, phase="report", reductions=[report])) is False


def test_driver_is_goal_only():
    """No methodology command: the prompt is the goal."""
    driver = _playbook().driver("research")
    assert driver.command is None
    assert driver.args == {}
    assert driver.loop is None


def test_result_schema_is_uniform_across_phases():
    """Every phase returns its prose under the same key."""
    pb = _playbook()
    for phase in pb.phases:
        schema = pb.result_schema(phase)
        assert schema["required"] == ["answer"]
