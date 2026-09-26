"""The committee playbooks: a simulated review committee, and the eval that scores one.

A cast of nine personas takes turns in a single-threaded discussion over one file --
an opening round in seniority order, then a FIFO floor queue, an owner reply after
every reviewer turn, owner-delegated edits applied by a junior IC to a revised copy,
and a closing decision by the chair. The transcript is a thread.md under HERMES_HOME;
the verdict it reaches is a simulation, not an approval.

The second playbook, committee-eval (eval.py), scores one finished committee run on
six dimensions. Python measures the record and scores three of them. One judge
ticket scores the other three, on quotes the master verifies. The eval never writes
to the run it scores, other than that run's own eval.json.

Importing this package registers CommitteePlaybook under the name "committee" and
CommitteeEvalPlaybook under "committee-eval". eval is imported second because it
reads names from playbook.
"""
from playbooks.committee import playbook as playbook  # noqa: F401
from playbooks.committee import eval as eval  # noqa: F401
