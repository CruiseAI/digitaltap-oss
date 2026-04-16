"""Databricks collector — connects to Databricks workspace API.

Requires: pip install digitaltap-ai[databricks]
Set DATABRICKS_HOST and DATABRICKS_TOKEN environment variables.
"""

from __future__ import annotations

import os

from digitaltap.models.cluster import ClusterInfo

from .base import BaseCollector


class DatabricksCollector(BaseCollector):
    """Collect cluster info from a Databricks workspace."""

    def __init__(self, host: str | None = None, token: str | None = None):
        self.host = host or os.environ.get("DATABRICKS_HOST", "")
        self.token = token or os.environ.get("DATABRICKS_TOKEN", "")

    async def collect(self) -> list[ClusterInfo]:
        # TODO: Implement using databricks-sdk
        # from databricks.sdk import WorkspaceClient
        # w = WorkspaceClient(host=self.host, token=self.token)
        # for c in w.clusters.list(): ...
        raise NotImplementedError(
            "Databricks collector not yet implemented. "
            "Use --demo for mock data, or contribute at github.com/digitaltap/digitaltap-ai-oss"
        )

    async def test_connection(self) -> bool:
        return bool(self.host and self.token)
