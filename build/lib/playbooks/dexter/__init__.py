"""The dexter forensic investigator playbook adapter.

Implements a root-cause investigation methodology over goals. Discovers, localizes,
verifies fixes, and banks reusable learnings via cross-host deduplication.

Importing this package will register DexterPlaybook under the name "dexter".
"""
from playbooks.dexter import playbook as playbook  # noqa: F401
