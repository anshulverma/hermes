"""The reference `local` site (localhost + git + shell).

Importing this package registers LocalSite under the name "local".
"""
from sites.local import site as site  # noqa: F401  (import side-effect: registers "local")
