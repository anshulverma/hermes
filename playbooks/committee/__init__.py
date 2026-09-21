"""The committee playbook adapter: one artifact reviewed by a simulated committee.

A cast of nine personas takes turns in a single-threaded discussion over one file --
an opening round in seniority order, then a FIFO floor queue, an owner reply after
every reviewer turn, owner-delegated edits applied by a junior IC to a revised copy,
and a closing decision by the chair. The transcript is a thread.md under HERMES_HOME;
the verdict it reaches is a simulation, not an approval.

Importing this package will register CommitteePlaybook under the name "committee".
"""
from playbooks.committee import playbook as playbook  # noqa: F401
