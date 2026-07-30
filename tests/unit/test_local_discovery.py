"""Unit tests for local adapter auto-discovery.

Tests the HERMES_LOCAL_DIR / ~/.hermes/local zero-config adapter loading.
"""
import os
import sys
import tempfile
from pathlib import Path
import pytest


def test_local_dir_default():
    """config.local_dir() defaults to resolve_home()/local when HERMES_LOCAL_DIR is unset."""
    from engine.config import local_dir, resolve_home

    old_val = os.environ.pop('HERMES_LOCAL_DIR', None)
    old_home = os.environ.pop('HERMES_HOME', None)
    try:
        # Use a temp HERMES_HOME to avoid networked-mount issues
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['HERMES_HOME'] = tmpdir
            expected = Path(tmpdir) / 'local'
            assert local_dir() == expected
    finally:
        if old_val is not None:
            os.environ['HERMES_LOCAL_DIR'] = old_val
        if old_home is not None:
            os.environ['HERMES_HOME'] = old_home
        else:
            os.environ.pop('HERMES_HOME', None)


def test_local_dir_from_env():
    """config.local_dir() honors HERMES_LOCAL_DIR when set."""
    from engine.config import local_dir

    with tempfile.TemporaryDirectory() as tmpdir:
        custom_local = str(Path(tmpdir) / 'custom_local')
        os.environ['HERMES_LOCAL_DIR'] = custom_local
        try:
            assert local_dir() == Path(custom_local)
        finally:
            os.environ.pop('HERMES_LOCAL_DIR', None)


def test_local_dir_in_known_vars():
    """HERMES_LOCAL_DIR appears in config.KNOWN_VARS."""
    from engine.config import KNOWN_VARS

    assert 'HERMES_LOCAL_DIR' in KNOWN_VARS
    assert isinstance(KNOWN_VARS['HERMES_LOCAL_DIR'], str)
    assert len(KNOWN_VARS['HERMES_LOCAL_DIR']) > 0


def test_local_playbook_auto_discovery():
    """A playbook module in local/ is auto-imported and resolves with NO env var."""
    from engine.cli import _load_playbook_site_agent
    from engine import playbook
    from argparse import Namespace

    # Clear any env module vars
    old_pb_modules = os.environ.pop('HERMES_PLAYBOOK_MODULES', None)
    old_home = os.environ.pop('HERMES_HOME', None)
    old_local_dir = os.environ.pop('HERMES_LOCAL_DIR', None)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['HERMES_HOME'] = tmpdir
            local_path = Path(tmpdir) / 'local'
            local_path.mkdir()

            # Write a playbook module that registers on import
            playbook_file = local_path / 'test_playbook.py'
            playbook_file.write_text('''
from engine import playbook
from engine.models import Driver, Finding, Reduction, Result, Run, Ticket

class TestLocalPlaybook:
    name = "testlocal"
    phases = ["phase1"]

    def seed(self, run, site):
        return []

    def payload_schema(self, phase):
        return {}

    def result_schema(self, phase):
        return {}

    def driver(self, phase):
        return Driver(command="echo", args={}, loop=False)

    def reduce(self, run, phase, findings, site):
        return []

    def verify(self, run, ticket, result, site):
        return True

    def next_phase(self, run):
        return None

    def is_done(self, run):
        return True

playbook.register("testlocal", TestLocalPlaybook())
''')

            # Load playbook without any env var set
            args = Namespace(playbook="testlocal", site="local", agent="claude")
            pb, st, ag = _load_playbook_site_agent(args)

            assert pb is not None
            assert pb.name == "testlocal"
    finally:
        if old_pb_modules is not None:
            os.environ['HERMES_PLAYBOOK_MODULES'] = old_pb_modules
        if old_home is not None:
            os.environ['HERMES_HOME'] = old_home
        else:
            os.environ.pop('HERMES_HOME', None)
        if old_local_dir is not None:
            os.environ['HERMES_LOCAL_DIR'] = old_local_dir


def test_local_site_package_auto_discovery():
    """A site package in local/ is auto-imported and resolves."""
    from engine.cli import _load_playbook_site_agent
    from argparse import Namespace

    old_site_modules = os.environ.pop('HERMES_SITE_MODULES', None)
    old_home = os.environ.pop('HERMES_HOME', None)
    old_local_dir = os.environ.pop('HERMES_LOCAL_DIR', None)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['HERMES_HOME'] = tmpdir
            local_path = Path(tmpdir) / 'local'
            local_path.mkdir()

            # Create a site package (directory with __init__.py)
            site_pkg = local_path / 'test_site'
            site_pkg.mkdir()
            (site_pkg / '__init__.py').write_text('''
from engine import site
from engine.models import HealthReport, Issue, IssueQuery, Result

class TestLocalSite:
    name = "testlocalsite"

    def discover_hosts(self):
        return []

    def provision(self, host, base_ref):
        pass

    def health(self, host, agent):
        return HealthReport(checks=[])

    def run_worker(self, host, envelope, agent):
        return Result(
            findings=[],
            next_actions=[],
            termination_reason="success",
            metadata={}
        )

    def resource_classes(self):
        return []

    def guarantees_no_ship(self):
        return True

    def submit_for_review(self, host, change):
        return "test://review"

    def issue_source(self, query):
        return []

site.register("testlocalsite", TestLocalSite())
''')

            # Load site without any env var set
            args = Namespace(site="testlocalsite", agent="claude")
            _, st, _ = _load_playbook_site_agent(args)

            assert st is not None
            assert st.name == "testlocalsite"
    finally:
        if old_site_modules is not None:
            os.environ['HERMES_SITE_MODULES'] = old_site_modules
        if old_home is not None:
            os.environ['HERMES_HOME'] = old_home
        else:
            os.environ.pop('HERMES_HOME', None)
        if old_local_dir is not None:
            os.environ['HERMES_LOCAL_DIR'] = old_local_dir


def test_local_underscore_prefixed_file_skipped():
    """A _-prefixed file in local/ is NOT imported."""
    from engine.cli import _load_playbook_site_agent
    from argparse import Namespace

    old_home = os.environ.pop('HERMES_HOME', None)
    old_local_dir = os.environ.pop('HERMES_LOCAL_DIR', None)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['HERMES_HOME'] = tmpdir
            local_path = Path(tmpdir) / 'local'
            local_path.mkdir()

            # Write a _-prefixed file that would fail if imported
            (local_path / '_private.py').write_text('raise RuntimeError("Should not import")')

            # Should not raise (file is skipped)
            args = Namespace(site="local", agent="claude")
            _load_playbook_site_agent(args)
    finally:
        if old_home is not None:
            os.environ['HERMES_HOME'] = old_home
        else:
            os.environ.pop('HERMES_HOME', None)
        if old_local_dir is not None:
            os.environ['HERMES_LOCAL_DIR'] = old_local_dir


def test_local_broken_module_raises_config_error():
    """A broken module in local/ raises ConfigError naming the file."""
    from engine.cli import _load_playbook_site_agent
    from engine.config import ConfigError
    from argparse import Namespace

    old_home = os.environ.pop('HERMES_HOME', None)
    old_local_dir = os.environ.pop('HERMES_LOCAL_DIR', None)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['HERMES_HOME'] = tmpdir
            local_path = Path(tmpdir) / 'local'
            local_path.mkdir()

            # Write a broken module
            (local_path / 'broken.py').write_text('this is not valid python syntax !@#')

            # Should raise ConfigError naming the module
            args = Namespace(site="local", agent="claude")
            with pytest.raises(ConfigError) as exc_info:
                _load_playbook_site_agent(args)

            # Should name the offending module
            assert 'broken' in str(exc_info.value)
    finally:
        if old_home is not None:
            os.environ['HERMES_HOME'] = old_home
        else:
            os.environ.pop('HERMES_HOME', None)
        if old_local_dir is not None:
            os.environ['HERMES_LOCAL_DIR'] = old_local_dir


def test_missing_local_dir_unchanged_behavior():
    """Missing/nonexistent local dir => unchanged resolution of built-ins (no-op)."""
    from engine.cli import _load_playbook_site_agent
    from argparse import Namespace

    old_home = os.environ.pop('HERMES_HOME', None)
    old_local_dir = os.environ.pop('HERMES_LOCAL_DIR', None)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['HERMES_HOME'] = tmpdir
            # Do NOT create local/ dir

            # Should work normally (load built-in local site)
            args = Namespace(site="local", agent="claude")
            _, st, _ = _load_playbook_site_agent(args)

            assert st is not None
            assert st.name == "local"
    finally:
        if old_home is not None:
            os.environ['HERMES_HOME'] = old_home
        else:
            os.environ.pop('HERMES_HOME', None)
        if old_local_dir is not None:
            os.environ['HERMES_LOCAL_DIR'] = old_local_dir


def test_local_discovery_composes_with_env_modules():
    """Local module AND a HERMES_PLAYBOOK_MODULES module both load (composition)."""
    from engine.cli import _load_playbook_site_agent
    from argparse import Namespace

    old_pb_modules = os.environ.pop('HERMES_PLAYBOOK_MODULES', None)
    old_home = os.environ.pop('HERMES_HOME', None)
    old_local_dir = os.environ.pop('HERMES_LOCAL_DIR', None)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['HERMES_HOME'] = tmpdir
            local_path = Path(tmpdir) / 'local'
            local_path.mkdir()

            # Create a local playbook
            (local_path / 'local_pb.py').write_text('''
from engine import playbook
from engine.models import Driver, Finding, Reduction, Result, Run, Ticket

class LocalPb:
    name = "frompathlocal"
    phases = ["p1"]
    def seed(self, run, site): return []
    def payload_schema(self, phase): return {}
    def result_schema(self, phase): return {}
    def driver(self, phase): return Driver(command="echo", args={}, loop=False)
    def reduce(self, run, phase, findings, site): return []
    def verify(self, run, ticket, result, site): return True
    def next_phase(self, run): return None
    def is_done(self, run): return True

playbook.register("frompathlocal", LocalPb())
''')

            # Create an env module playbook
            env_module_path = Path(tmpdir) / 'env_pb.py'
            env_module_path.write_text('''
from engine import playbook
from engine.models import Driver, Finding, Reduction, Result, Run, Ticket

class EnvPb:
    name = "frompathenv"
    phases = ["p1"]
    def seed(self, run, site): return []
    def payload_schema(self, phase): return {}
    def result_schema(self, phase): return {}
    def driver(self, phase): return Driver(command="echo", args={}, loop=False)
    def reduce(self, run, phase, findings, site): return []
    def verify(self, run, ticket, result, site): return True
    def next_phase(self, run): return None
    def is_done(self, run): return True

playbook.register("frompathenv", EnvPb())
''')

            # Add env module dir to sys.path and set HERMES_PLAYBOOK_MODULES
            sys.path.insert(0, tmpdir)
            os.environ['HERMES_PLAYBOOK_MODULES'] = 'env_pb'

            try:
                # Load both
                args1 = Namespace(playbook="frompathlocal", site="local", agent="claude")
                pb1, _, _ = _load_playbook_site_agent(args1)
                assert pb1.name == "frompathlocal"

                args2 = Namespace(playbook="frompathenv", site="local", agent="claude")
                pb2, _, _ = _load_playbook_site_agent(args2)
                assert pb2.name == "frompathenv"
            finally:
                sys.path.remove(tmpdir)
    finally:
        if old_pb_modules is not None:
            os.environ['HERMES_PLAYBOOK_MODULES'] = old_pb_modules
        else:
            os.environ.pop('HERMES_PLAYBOOK_MODULES', None)
        if old_home is not None:
            os.environ['HERMES_HOME'] = old_home
        else:
            os.environ.pop('HERMES_HOME', None)
        if old_local_dir is not None:
            os.environ['HERMES_LOCAL_DIR'] = old_local_dir


def test_local_dir_idempotent_import():
    """Calling _import_registration_modules multiple times is safe (idempotent)."""
    from engine.cli import _import_registration_modules

    old_home = os.environ.pop('HERMES_HOME', None)
    old_local_dir = os.environ.pop('HERMES_LOCAL_DIR', None)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ['HERMES_HOME'] = tmpdir
            local_path = Path(tmpdir) / 'local'
            local_path.mkdir()

            # Create a module that tracks import count
            (local_path / 'counter.py').write_text('''
import os
count_file = os.path.join(os.environ.get("HERMES_HOME", "/tmp"), "import_count.txt")
count = 0
if os.path.exists(count_file):
    with open(count_file) as f:
        count = int(f.read().strip())
count += 1
with open(count_file, "w") as f:
    f.write(str(count))
''')

            # Call twice
            _import_registration_modules()
            _import_registration_modules()

            # Check import count (should be 1, not 2 — importlib caches)
            count_file = Path(tmpdir) / "import_count.txt"
            if count_file.exists():
                count = int(count_file.read_text().strip())
                assert count == 1, "Module should only be imported once"
    finally:
        if old_home is not None:
            os.environ['HERMES_HOME'] = old_home
        else:
            os.environ.pop('HERMES_HOME', None)
        if old_local_dir is not None:
            os.environ['HERMES_LOCAL_DIR'] = old_local_dir
