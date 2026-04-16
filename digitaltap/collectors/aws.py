"""AWS EMR collector — connects to AWS EMR API.

Requires: pip install digitaltap-ai[aws]
Uses standard AWS credentials (AWS_PROFILE, AWS_ACCESS_KEY_ID, etc.).
"""

from __future__ import annotations

from digitaltap.models.cluster import ClusterInfo

from .base import BaseCollector


class AWSCollector(BaseCollector):
    """Collect cluster info from AWS EMR."""

    def __init__(self, region: str = "us-east-1"):
        self.region = region

    async def collect(self) -> list[ClusterInfo]:
        # TODO: Implement using boto3
        # import boto3
        # emr = boto3.client("emr", region_name=self.region)
        # for cluster in emr.list_clusters(...)["Clusters"]: ...
        raise NotImplementedError(
            "AWS EMR collector not yet implemented. "
            "Use --demo for mock data, or contribute at github.com/digitaltap/digitaltap-ai-oss"
        )

    async def test_connection(self) -> bool:
        try:
            import boto3  # noqa: F401
            return True
        except ImportError:
            return False
