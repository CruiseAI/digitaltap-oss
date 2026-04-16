"""Base collector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from digitaltap.models.cluster import ClusterInfo


class BaseCollector(ABC):
    """Abstract base for data collectors."""

    @abstractmethod
    async def collect(self) -> list[ClusterInfo]:
        """Collect cluster information from the platform."""
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the collector can reach its data source."""
        ...

    async def stop_cluster(self, cluster_id: str) -> bool:
        """Stop/terminate a cluster. Returns True on success."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support stop_cluster")

    async def hibernate_cluster(self, cluster_id: str) -> bool:
        """Hibernate a cluster (preserve state for fast resume). Returns True on success."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support hibernate_cluster")

    @property
    def supports_actions(self) -> bool:
        """Whether this collector supports stop/hibernate actions."""
        return False
