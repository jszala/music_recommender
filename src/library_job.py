"""Durable job accounting and frozen HTTP operations for full-library collection."""

from collections import defaultdict, deque
import fcntl
import json
import os
from pathlib import Path
from urllib.parse import urlencode

from .fetch_musicbrainz import CACHE_VERSION, FetchError, digest, json_bytes, utc_now
from .match_recordings import normalize


class StageBudgetReached(RuntimeError):
    """A persistent stage ceiling, distinct from a provider failure."""


def atomic_json(path: Path, value: object) -> None:
    atomic_bytes(path, json_bytes(value))


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_json(path: Path):
    return json.loads(path.read_bytes())


def balanced_rows(tracks: list[dict]) -> list[dict]:
    groups = defaultdict(deque)
    for track in sorted(tracks, key=lambda t: t["line_number"]):
        groups[normalize(track["artist_text"])].append(track)
    result = []
    while any(groups.values()):
        for name in sorted(groups):
            if groups[name]:
                result.append(groups[name].popleft())
    return result


class LibraryJob:
    def __init__(self, directory: Path, binding: dict, budgets: dict, *, resume=False, wait=False):
        self.directory, self.binding, self.budgets = directory, binding, budgets
        self.resume = resume
        self.wait = wait
        self.path = directory / "manifest.json"
        self.lock = None

    def __enter__(self):
        if self.directory.exists() and not self.resume:
            raise ValueError("Job exists; use --resume or a new job directory")
        if self.resume and not self.path.exists():
            raise ValueError("No initialized job to resume")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = (self.directory / ".job.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | (0 if self.wait else fcntl.LOCK_NB))
            if self.path.exists():
                self.state = read_json(self.path)
                if self.state.get("binding") != self.binding:
                    raise ValueError("Job input, rules, source imports, or country changed; create a new job")
            else:
                self.state = {"format_version": 1, "kind": "full library job", "binding": self.binding,
                              "created_at": utc_now(), "stages": {}, "datasets": {},
                              "request_limits": self.budgets,
                              "counters": {stage: {"attempts": 0, "tranche": 1, "tranche_attempts": 0}
                                           for stage in self.budgets}, "active_operation": None}
                self.save()
        except BaseException:
            self.lock.close()
            self.lock = None
            raise
        return self

    def __exit__(self, *args):
        if self.lock:
            self.lock.close()
            self.lock = None

    def save(self):
        atomic_json(self.path, self.state)

    def debit(self, stage: str, query: str, retry: int):
        counter, budget = self.state["counters"][stage], self.budgets[stage]
        if counter["attempts"] >= budget["total_attempts"]:
            self.state["stages"][stage] = "budget_exhausted"
            self.save()
            raise StageBudgetReached(f"{stage} cumulative request budget exhausted")
        if counter["tranche_attempts"] >= budget["tranche_attempts"]:
            counter["tranche"] += 1
            counter["tranche_attempts"] = 0
        counter["attempts"] += 1
        counter["tranche_attempts"] += 1
        self.state["active_operation"] = {"stage": stage, "query": query, "retry": retry,
                                          "charged_attempt": counter["attempts"], "started_at": utc_now()}
        self.save()  # The debit must reach disk before the transport is entered.


class CheckpointClient:
    """Adapt existing collectors without changing their decision rules.

    Completed operations replay from job-owned envelopes. An unfinished row can
    rerun its deterministic decision code without resending completed requests.
    """

    def __init__(self, client, job: LibraryJob, stage: str):
        self.client, self.job, self.stage = client, job, stage
        self.cache_dir = job.directory / "operations" / ("apple" if stage == "apple" else "musicbrainz")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.events = []
        client.before_attempt = lambda query, retry: job.debit(stage, query, retry)

    @property
    def limits(self):
        return self.client.limits

    @property
    def offline(self):
        return self.client.offline

    @property
    def network_attempts(self):
        return self.client.network_attempts

    def get(self, endpoint, **params):
        url = self.client.api + endpoint + "?" + urlencode(sorted({**self.client.query_defaults, **params}.items()))
        path = self.cache_dir / (digest(url.encode()) + ".json")
        if path.exists():
            envelope = read_json(path)
            if (envelope["format_version"] != CACHE_VERSION or envelope["query"] != url
                    or digest(envelope["response_text"].encode()) != envelope["response_sha256"]):
                raise ValueError("Corrupt frozen job operation")
            if not envelope["error"] or not self.client.retry_failures:
                self.events.append(self.client._event(envelope, path, "checkpoint"))
                if envelope["error"]:
                    raise FetchError(f"Cached failure: {envelope['error']}")
                return json.loads(envelope["response_text"])
        self.job.state["cursor"] = {"stage": self.stage, "query": url}
        self.job.save()
        start = len(self.client.events)
        try:
            return self.client.get(endpoint, **params)
        finally:
            for event in self.client.events[start:]:
                if event.get("cache_file"):
                    envelope = read_json(self.client.cache_dir / event["cache_file"])
                    atomic_json(path, envelope)
                self.events.append(event)
            if len(self.client.events) > start:
                self.job.state["active_operation"] = None
                self.job.save()

    def search(self, term, country, rules):
        body = self.get("search", term=term, country=country, media="music", entity="song",
                        explicit="Yes", limit=rules.search_limit)
        if (not isinstance(body.get("results"), list) or type(body.get("resultCount")) is not int
                or body["resultCount"] != len(body["results"])):
            raise FetchError("Malformed Apple search response")
        return body
