"""
tests.unit.test_playbook_views — the playbook view seam, playbook-agnostic.

A stub playbook stands in for the committee: the seam is two duck-typed methods
and the server must not care which playbook supplies them.
"""
import os
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.db.migrate import apply_migrations, connect
from engine.models import Reduction
from engine.queue import record_reduction
from server.app import create_app


@pytest.fixture
def temp_home(tmp_path: Path, monkeypatch):
    """A temp HERMES_HOME with migrations applied."""
    home = tmp_path / "hermes-test"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    apply_migrations(str(home / "queue.db"))
    yield home
    monkeypatch.delenv("HERMES_HOME", raising=False)


def _run_row(home: Path, run_id: str, playbook: str) -> str:
    """Insert one run row; no tickets, which the view routes never read."""
    conn = connect(str(home / "queue.db"))
    try:
        conn.execute(
            """INSERT INTO runs
               (id, playbook, site, state, phase, base_ref, config_json,
                created_at, updated_at)
               VALUES (?, ?, 'local', 'running', 'open', 'main', '{}',
                       '2026-09-21T00:00:00Z', '2026-09-21T00:00:00Z')""",
            (run_id, playbook),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def _reduction_row(home: Path, run_id: str, doc: dict) -> None:
    """Record one reduction through the queue's own writer."""
    conn = connect(str(home / "queue.db"))
    try:
        record_reduction(conn, run_id, "open", Reduction(kind="turn", json=doc))
    finally:
        conn.close()


@pytest.fixture
def viewed(tmp_path: Path):
    """A playbook registered as 'stubview' that ships a view."""
    asset = tmp_path / "stubview.umd.js"
    asset.write_text("window.HermesView_stubview = 1;\n", encoding="utf-8")

    class StubViewPlaybook:
        name = "stubview"
        phases = ["open"]

        def view_asset(self):
            return asset

        def view_data(self, run, reductions):
            return {"kind": "stubview", "run": run.id,
                    "turns": [r.json for r in reductions]}

    from engine import playbook as playbook_module
    playbook_module.register("stubview", StubViewPlaybook())
    yield asset
    playbook_module._REGISTRY.pop("stubview", None)


@pytest.fixture
def blind(tmp_path: Path):
    """A playbook registered as 'stubblind' with no view seam at all."""
    class StubBlindPlaybook:
        name = "stubblind"
        phases = ["open"]

    from engine import playbook as playbook_module
    playbook_module.register("stubblind", StubBlindPlaybook())
    yield "stubblind"
    playbook_module._REGISTRY.pop("stubblind", None)


@pytest.fixture
def client(temp_home: Path):
    return TestClient(create_app())


def test_has_view_true_when_the_playbook_ships_one(client, temp_home, viewed):
    run_id = _run_row(temp_home, "run-view", "stubview")
    body = client.get(f"/api/runs/{run_id}").json()
    assert body["has_view"] is True


def test_has_view_false_for_a_playbook_without_the_seam(client, temp_home, blind):
    run_id = _run_row(temp_home, "run-blind", "stubblind")
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["has_view"] is False


def test_has_view_false_for_an_unregistered_playbook(client, temp_home):
    run_id = _run_row(temp_home, "run-unknown", "no-such-playbook")
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["has_view"] is False


def test_asset_route_serves_the_registered_playbooks_bundle(client, temp_home, viewed):
    response = client.get("/api/playbooks/stubview/view.js")
    assert response.status_code == 200
    assert response.text == "window.HermesView_stubview = 1;\n"
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_asset_route_404s_an_unregistered_name(client, temp_home):
    assert client.get("/api/playbooks/no-such-playbook/view.js").status_code == 404


def test_asset_route_404s_a_playbook_without_the_seam(client, temp_home, blind):
    assert client.get("/api/playbooks/stubblind/view.js").status_code == 404


def test_asset_route_404s_a_missing_file(client, temp_home, viewed):
    viewed.unlink()
    assert client.get("/api/playbooks/stubview/view.js").status_code == 404


@pytest.mark.parametrize("name", [
    "../../../etc/passwd",          # the client normalises the dots away
    "..%2F..%2Fetc%2Fpasswd",       # decodes to slashes; matches no route
    "stubview/../../../etc/passwd",
    "%2E%2E",                       # reaches the handler as the name ".."
])
def test_asset_route_cannot_escape_the_package(client, temp_home, viewed, name):
    """The name is a registry key, so traversal has nothing to traverse."""
    response = client.get(f"/api/playbooks/{name}/view.js")
    assert response.status_code == 404
    assert "root:" not in response.text


def test_view_route_returns_view_data(client, temp_home, viewed):
    run_id = _run_row(temp_home, "run-view", "stubview")
    _reduction_row(temp_home, run_id, {"turn": 1, "body": "hello"})
    response = client.get(f"/api/runs/{run_id}/view")
    assert response.status_code == 200
    assert response.json() == {
        "kind": "stubview", "run": run_id, "turns": [{"turn": 1, "body": "hello"}],
    }


def test_view_route_404s_a_run_without_a_view(client, temp_home, blind):
    run_id = _run_row(temp_home, "run-blind", "stubblind")
    assert client.get(f"/api/runs/{run_id}/view").status_code == 404


def test_view_route_404s_an_unknown_run(client, temp_home, viewed):
    """404, and no side effect: a GET for a made-up run writes nothing.

    Neither route may mkdir ``runs/<whatever-the-url-said>/`` under HERMES_HOME.
    """
    assert client.get("/api/runs/no-such-run/view").status_code == 404
    assert client.get(
        "/api/runs/no-such-run/view/artifact?path=doc/t03.md").status_code == 404
    assert not (temp_home / "runs").exists()


def _doc(home: Path, run_id: str) -> Path:
    """``runs/<run_id>/doc/`` under the server's own home -- where the route reads."""
    doc = home / "runs" / run_id / "doc"
    doc.mkdir(parents=True, exist_ok=True)
    return doc


def test_artifact_route_serves_a_file_from_the_runs_own_directory(
    client, temp_home, viewed
):
    run_id = _run_row(temp_home, "run-view", "stubview")
    doc = _doc(temp_home, run_id)
    (doc / "00-original.md").write_text("the original\n", encoding="utf-8")
    (doc / "t03.md").write_text("after turn 3\n", encoding="utf-8")

    assert client.get(f"/api/runs/{run_id}/view/artifact?path=doc/00-original.md").json() == {
        "text": "the original\n", "truncated": False}
    assert client.get(f"/api/runs/{run_id}/view/artifact?path=doc/t03.md").json() == {
        "text": "after turn 3\n", "truncated": False}


def test_artifact_route_reads_no_reduction(client, temp_home, viewed, tmp_path):
    """A readable file a reduction names is never what the route serves.

    That path is the master's; in a container it is not there at all, which is
    exactly the 404 this route used to give. Only ``runs/<id>/doc/`` counts.
    """
    elsewhere = tmp_path / "proposal.md"
    elsewhere.write_text("the host's copy\n", encoding="utf-8")
    run_id = _run_row(temp_home, "run-view", "stubview")
    _reduction_row(temp_home, run_id, {"artifact": str(elsewhere), "revised": str(elsewhere)})

    url = f"/api/runs/{run_id}/view/artifact?path=doc/00-original.md"
    assert client.get(url).status_code == 404
    (_doc(temp_home, run_id) / "00-original.md").write_text("the snapshot\n", encoding="utf-8")
    assert client.get(url).json()["text"] == "the snapshot\n"


@pytest.mark.parametrize("path", [
    "", None, "../../etc/passwd", "/etc/passwd", "doc/../../x", "doc/../thread.md",
    "doc", "thread.md", "traces/1.jsonl", "doc/a/b", "doc/t03\x00.md",
    "doc/.t03.md",       # a leading dot: a temp file mid-write is never served
    "doc/" + "a" * 129,  # one past the 128-character name bound
])
def test_artifact_route_400s_a_path_that_is_not_dir_slash_name(
    client, temp_home, viewed, path
):
    run_id = _run_row(temp_home, "run-view", "stubview")
    (_doc(temp_home, run_id).parent / "thread.md").write_text("root:x:0:0\n", encoding="utf-8")
    params = {} if path is None else {"path": path}

    response = client.get(f"/api/runs/{run_id}/view/artifact", params=params)

    assert response.status_code == 400, path
    assert "root:" not in response.text


def _missing(doc: Path, outside: Path) -> None:
    pass


def _symlink_to_passwd(doc: Path, outside: Path) -> None:
    (doc / "t03.md").symlink_to("/etc/passwd")


def _doc_symlinked_out(doc: Path, outside: Path) -> None:
    (outside / "t03.md").write_text("outside the run\n", encoding="utf-8")
    doc.rmdir()
    doc.symlink_to(outside, target_is_directory=True)


def _a_directory(doc: Path, outside: Path) -> None:
    (doc / "t03.md").mkdir()


def _symlink_to_the_run_root(doc: Path, outside: Path) -> None:
    """Inside the run, but outside ``doc/``: the route serves ``<dir>/`` only."""
    (doc.parent / "thread.md").write_text("outside the run\n", encoding="utf-8")
    (doc / "t03.md").symlink_to("../thread.md")


def _run_dir_symlinked_out(doc: Path, outside: Path) -> None:
    (outside / "doc").mkdir()
    (outside / "doc" / "t03.md").write_text("outside the run\n", encoding="utf-8")
    doc.rmdir()
    doc.parent.rmdir()
    doc.parent.symlink_to(outside, target_is_directory=True)


@pytest.mark.parametrize("prepare", [
    _missing, _symlink_to_passwd, _symlink_to_the_run_root,
    # A doc/ swapped for a symlink mid-request is this case by the time the
    # route opens it: the walk holds an fd per directory, so there is no
    # window between a check and an open for the swap to land in.
    _doc_symlinked_out,
    _run_dir_symlinked_out, _a_directory,
])
def test_artifact_route_404s_anything_but_a_regular_file_inside_the_run(
    client, temp_home, viewed, tmp_path, prepare
):
    """A directory is no file; a symlink at any level below ``runs/`` -- the
    run's directory, ``doc/``, or the file -- is not the run's."""
    run_id = _run_row(temp_home, "run-view", "stubview")
    outside = tmp_path / "outside"
    outside.mkdir()
    prepare(_doc(temp_home, run_id), outside)

    response = client.get(f"/api/runs/{run_id}/view/artifact?path=doc/t03.md")

    assert response.status_code == 404
    assert "root:" not in response.text
    assert "outside the run" not in response.text


def test_artifact_route_refuses_a_fifo_without_blocking(client, temp_home, viewed):
    """``O_NONBLOCK``: without it the open waits for a writer that never comes.
    The request runs on a thread so that fails here at the timeout rather than
    hanging the suite."""
    run_id = _run_row(temp_home, "run-view", "stubview")
    fifo = _doc(temp_home, run_id) / "t03.md"
    os.mkfifo(fifo)
    result = {}
    worker = threading.Thread(daemon=True, target=lambda: result.update(
        response=client.get(f"/api/runs/{run_id}/view/artifact?path=doc/t03.md")))

    worker.start()
    worker.join(timeout=5)
    blocked = worker.is_alive()
    if blocked:  # hand the stuck open a writer so the thread can finish
        os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        worker.join(timeout=5)

    assert not blocked, "the open blocked on a FIFO"
    assert result["response"].status_code == 404


def test_open_run_file_closes_every_fd_it_opened_but_the_one_it_returns(temp_home):
    from fastapi import HTTPException

    from server.app import _open_run_file

    doc = _doc(temp_home, "run-view")
    (doc / "t03.md").write_text("fine\n", encoding="utf-8")
    (doc / "t04.md").symlink_to(doc / "t03.md")
    (doc / "t05.md").mkdir()
    before = len(os.listdir("/proc/self/fd"))

    fd = _open_run_file(temp_home, "run-view", "doc/t03.md")
    assert os.read(fd, 16) == b"fine\n"
    os.close(fd)
    for run_id, path in [("run-view", "doc/t04.md"), ("run-view", "doc/t05.md"),
                         ("run-view", "doc/t06.md"), ("no-such-run", "doc/t03.md")]:
        with pytest.raises(HTTPException) as caught:
            _open_run_file(temp_home, run_id, path)
        assert caught.value.status_code == 404

    assert len(os.listdir("/proc/self/fd")) == before


def test_artifact_route_404s_a_playbook_without_a_view(client, temp_home, blind):
    """The other side of the kill-switch test: a readable file, and the route
    still refuses because this playbook ships no view."""
    run_id = _run_row(temp_home, "run-blind", "stubblind")
    (_doc(temp_home, run_id) / "t03.md").write_text("readable\n", encoding="utf-8")

    assert client.get(
        f"/api/runs/{run_id}/view/artifact?path=doc/t03.md").status_code == 404


@pytest.mark.parametrize("extra, truncated", [(1, True), (0, False)])
def test_artifact_route_caps_the_read_in_characters(
    client, temp_home, viewed, extra, truncated
):
    """The document is an operator-chosen file of unbounded size; over the cap
    the response says it was cut rather than lying by omission."""
    from server.app import ARTIFACT_MAX_CHARS

    run_id = _run_row(temp_home, "run-view", "stubview")
    # Two bytes a character: a cap counted in bytes cuts this at half.
    (_doc(temp_home, run_id) / "t03.md").write_text(
        "é" * (ARTIFACT_MAX_CHARS + extra), encoding="utf-8")

    body = client.get(f"/api/runs/{run_id}/view/artifact?path=doc/t03.md").json()

    assert body["truncated"] is truncated
    assert body["text"] == "é" * ARTIFACT_MAX_CHARS


def test_kill_switch_404s_all_three_routes_and_clears_has_view(
    client, temp_home, viewed, monkeypatch
):
    """The file must be one the route WOULD serve, or the 404 proves nothing."""
    run_id = _run_row(temp_home, "run-view", "stubview")
    (_doc(temp_home, run_id) / "t03.md").write_text("would be served\n", encoding="utf-8")
    assert client.get(
        f"/api/runs/{run_id}/view/artifact?path=doc/t03.md").status_code == 200

    monkeypatch.setenv("HERMES_PLAYBOOK_VIEWS", "0")
    assert client.get("/api/playbooks/stubview/view.js").status_code == 404
    assert client.get(f"/api/runs/{run_id}/view").status_code == 404
    assert client.get(
        f"/api/runs/{run_id}/view/artifact?path=doc/t03.md").status_code == 404
    # Including a malformed path: the gate is above the path check, so a server
    # with the feature off never answers 400 and confirms the route is live.
    assert client.get(
        f"/api/runs/{run_id}/view/artifact?path=../x").status_code == 404
    assert client.get(f"/api/runs/{run_id}").json()["has_view"] is False


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "No", " off "])
def test_every_falsy_kill_switch_value_turns_the_feature_off(
    client, temp_home, viewed, monkeypatch, value
):
    """An operator reaching for a kill switch writes `false` as readily as `0`,
    and getting the feature fully ENABLED for it is the silent footgun."""
    monkeypatch.setenv("HERMES_PLAYBOOK_VIEWS", value)
    assert client.get("/api/playbooks/stubview/view.js").status_code == 404


@pytest.mark.parametrize("value", ["", "  ", "1", "true", "00"])
def test_a_value_that_is_not_falsy_leaves_the_feature_on(
    client, temp_home, viewed, monkeypatch, value
):
    """Empty is NOT off: `-e HERMES_PLAYBOOK_VIEWS` with nothing behind it is a
    variable the operator did not set, and must read the way unset does."""
    monkeypatch.setenv("HERMES_PLAYBOOK_VIEWS", value)
    assert client.get("/api/playbooks/stubview/view.js").status_code == 200


def test_a_broken_view_seam_costs_the_run_page_nothing(client, temp_home):
    """Acceptance criterion 1 says an absent seam changes nothing; a BROKEN seam
    must be the same as an absent one, not a dead run page. `GET /api/runs/{id}`
    is a pre-existing core route that could not 500 before the seam existed."""
    class Exploding:
        name = "stubboom"
        phases = ["open"]

        def view_asset(self):
            raise RuntimeError("the view seam is broken")

        def view_data(self, run, reductions):
            return {}

    class NotAPath:
        name = "stubjunk"
        phases = ["open"]

        def view_asset(self):
            return 12345

        def view_data(self, run, reductions):
            return {}

    from engine import playbook as playbook_module
    playbook_module.register("stubboom", Exploding())
    playbook_module.register("stubjunk", NotAPath())
    try:
        for name in ("stubboom", "stubjunk"):
            run_id = _run_row(temp_home, f"run-{name}", name)
            response = client.get(f"/api/runs/{run_id}")
            assert response.status_code == 200, name
            assert response.json()["has_view"] is False, name
            assert client.get(
                f"/api/playbooks/{name}/view.js").status_code == 404, name
    finally:
        playbook_module._REGISTRY.pop("stubboom", None)
        playbook_module._REGISTRY.pop("stubjunk", None)


def test_non_loopback_gates_all_three_routes(temp_home, viewed):
    from server.auth import read_token

    run_id = _run_row(temp_home, "run-view", "stubview")
    client = TestClient(create_app(bind="0.0.0.0"))
    paths = [
        "/api/playbooks/stubview/view.js",
        f"/api/runs/{run_id}/view",
        f"/api/runs/{run_id}/view/artifact?path=doc/t03.md",
    ]
    for path in paths:
        assert client.get(path).status_code == 401, path

    token = read_token(temp_home)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(paths[0], headers=headers).status_code == 200
    assert client.get(paths[1], headers=headers).status_code == 200


# --- the committee's wiring ---------------------------------------------
# The one playbook that ships a view. Importing it registers "committee"
# process-globally, which is how every other module gets it too; do not pop it.


def test_committee_wires_both_seam_methods_onto_the_playbook():
    """The class delegates to view.py rather than reimplementing the seam."""
    from playbooks.committee import view
    from playbooks.committee.playbook import CommitteePlaybook

    playbook = CommitteePlaybook()
    assert callable(playbook.view_asset)
    assert callable(playbook.view_data)
    assert playbook.view_asset() == view.view_asset()


def test_committee_view_asset_lives_inside_the_package():
    """The asset path is absolute and under playbooks/committee/."""
    import playbooks.committee
    from playbooks.committee import view

    package = Path(playbooks.committee.__file__).resolve().parent
    assert view.DIST.is_absolute()
    assert view.DIST.relative_to(package) == Path("view/dist/committee.umd.js")


def test_committee_view_asset_is_none_until_the_bundle_is_built(tmp_path, monkeypatch):
    """An unbuilt bundle is None, which is what makes has_view false."""
    from playbooks.committee import view

    monkeypatch.setattr(view, "DIST", tmp_path / "not-built.umd.js")
    assert view.view_asset() is None

    built = tmp_path / "committee.umd.js"
    built.write_text("// built\n", encoding="utf-8")
    monkeypatch.setattr(view, "DIST", built)
    assert view.view_asset() == built
