"""The devserver site adapter.

Provisions and runs investigations on internal development servers with native
buck2/sl/test tooling, with guaranteed no-ship protection via PATH guard shims.

Importing this package will register DevserverSite under the name "devserver".
"""
from sites.devserver import site as site  # noqa: F401
