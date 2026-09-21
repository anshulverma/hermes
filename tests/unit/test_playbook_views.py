"""
tests.unit.test_playbook_views — the playbook view seam, playbook-agnostic.

A stub playbook stands in for the committee: the seam is two duck-typed methods
and the server must not care which playbook supplies them.
"""
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

    ``view_data`` reaches the filesystem only through paths the reductions
    carry. Were it to call ``thread.path()`` instead, this GET would mkdir
    ``runs/<whatever-the-url-said>/`` under HERMES_HOME.
    """
    assert client.get("/api/runs/no-such-run/view").status_code == 404
    assert client.get(
        "/api/runs/no-such-run/view/artifact?which=original").status_code == 404
    assert not (temp_home / "runs").exists()


def test_artifact_route_reads_the_path_off_the_newest_reduction(
    client, temp_home, viewed, tmp_path
):
    original = tmp_path / "proposal.md"
    original.write_text("the original\n", encoding="utf-8")
    revised = tmp_path / "revised.md"
    revised.write_text("the revised copy\n", encoding="utf-8")
    run_id = _run_row(temp_home, "run-view", "stubview")
    _reduction_row(temp_home, run_id,
                   {"artifact": str(original), "revised": str(revised)})

    assert client.get(f"/api/runs/{run_id}/view/artifact?which=original").json() == {
        "text": "the original\n"}
    assert client.get(f"/api/runs/{run_id}/view/artifact?which=revised").json() == {
        "text": "the revised copy\n"}


def test_artifact_route_400s_an_unknown_which(client, temp_home, viewed):
    """``which`` names a KEY on the reduction, so it is one of exactly two.

    Everything else is 400 -- including every shape of traversal, because the
    only thing a traversal could reach here is a dict lookup that misses.
    """
    run_id = _run_row(temp_home, "run-view", "stubview")
    assert client.get(
        f"/api/runs/{run_id}/view/artifact?which=sideways").status_code == 400
    for which in ("../../../etc/passwd", "/etc/passwd", "..%2F..%2Fetc%2Fpasswd",
                  "original/../../../etc/passwd", "", "ORIGINAL", "artifact"):
        response = client.get(
            f"/api/runs/{run_id}/view/artifact", params={"which": which})
        assert response.status_code == 400, which
        assert "root:" not in response.text


def test_artifact_route_404s_a_revised_copy_that_does_not_exist(
    client, temp_home, viewed, tmp_path
):
    run_id = _run_row(temp_home, "run-view", "stubview")
    _reduction_row(temp_home, run_id,
                   {"artifact": str(tmp_path / "gone.md"), "revised": ""})
    assert client.get(
        f"/api/runs/{run_id}/view/artifact?which=revised").status_code == 404


def test_kill_switch_404s_all_three_routes_and_clears_has_view(
    client, temp_home, viewed, monkeypatch
):
    run_id = _run_row(temp_home, "run-view", "stubview")
    monkeypatch.setenv("HERMES_PLAYBOOK_VIEWS", "0")
    assert client.get("/api/playbooks/stubview/view.js").status_code == 404
    assert client.get(f"/api/runs/{run_id}/view").status_code == 404
    assert client.get(
        f"/api/runs/{run_id}/view/artifact?which=original").status_code == 404
    assert client.get(f"/api/runs/{run_id}").json()["has_view"] is False


def test_non_loopback_gates_all_three_routes(temp_home, viewed):
    from server.auth import read_token

    run_id = _run_row(temp_home, "run-view", "stubview")
    client = TestClient(create_app(bind="0.0.0.0"))
    paths = [
        "/api/playbooks/stubview/view.js",
        f"/api/runs/{run_id}/view",
        f"/api/runs/{run_id}/view/artifact?which=original",
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
