from typing import List, Protocol, Tuple


class StoreUnavailable(Exception):
    """The data store cannot be reached or answered with an error."""


class RecordStore(Protocol):
    def list_pipelines(self, env: str) -> List[str]:
        """Names of every pipeline with any key (flow, step or marker) in `env`. Read only."""
        ...

    def list_flows(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        """Return `(key, raw_json)` pairs for every run's flow description. Read only."""
        ...

    def list_records(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        """Return `(key, raw_json)` pairs for every audit record. Read only."""
        ...

    def list_markers(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        """Return `(key, raw_json)` pairs for every start marker. Read only."""
        ...

    def list_alive(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        """Return `(key, raw_json)` pairs for every run's latest heartbeat. Read only."""
        ...

    def list_died(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        """Return `(key, raw_json)` pairs for every stored died verdict. Read only."""
        ...

    def list_failures(self, env: str, pipeline: str) -> List[Tuple[str, str]]:
        """Return `(key, raw_json)` pairs for every failure item. Read only."""
        ...

    def record_died(self, key: str, value: str, alive_key: str) -> bool:
        """Store a died verdict once (never overwrite). The only write the monitor makes.

        The verdict expires with the run's heartbeat item `alive_key`. Returns True when this call
        stored it; False when it already existed or the write failed. Never raises.
        """
        ...

    def ping(self) -> None:
        """Raise StoreUnavailable if the store cannot be reached."""
        ...
