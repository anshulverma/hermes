"""The research playbook adapter: multi-agent research over a set of items.

Fans every item from a configured item source out to every configured agent for an
independent analysis, merges the per-agent views into one view per item, and turns
those into a single report. Both the items and the agents are configuration.

Importing this package registers ResearchPlaybook under the name "research" and the
built-in ``config`` item source.
"""
from playbooks.research import sources as sources  # noqa: F401
from playbooks.research import playbook as playbook  # noqa: F401
