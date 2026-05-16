"""Async LLM subtree selection with timeout, retry, and circuit-breaker policy."""

from __future__ import annotations

import concurrent.futures
import json
import time
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from sim.adaptation import AdaptationResponse, Cluster, mock_adaptation_provider
from sim.authored_subtree import LlmAdaptationResult, normalize_llm_result
from sim.constants import (
    LLM_AUTHOR_REQUEST_TIMEOUT_SEC,
    LLM_AUTHOR_RETRY_MAX_ATTEMPTS,
    LLM_CIRCUIT_COOLDOWN_SEC,
    LLM_CIRCUIT_FAILURE_THRESHOLD,
    LLM_REQUEST_TIMEOUT_SEC,
    LLM_RETRY_MAX_ATTEMPTS,
)

if TYPE_CHECKING:
    from sim.world import World

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm-adapt")


def request_timeout_sec(world: World) -> float:
    adapter = world.llm_adapter
    if isinstance(adapter, OllamaLlmAdapter) and adapter.mode == "author":
        return LLM_AUTHOR_REQUEST_TIMEOUT_SEC
    return LLM_REQUEST_TIMEOUT_SEC


def ollama_model_available(base_url: str, model: str, *, timeout_sec: float = 2.0) -> bool:
    """Return True when Ollama is reachable and exposes the requested model."""
    req = Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (TimeoutError, URLError, OSError, json.JSONDecodeError):
        return False
    models = payload.get("models", [])
    names = [str(item.get("name", "")) for item in models if isinstance(item, dict)]
    return any(name == model or name.startswith(f"{model}:") for name in names)


@dataclass
class LlmCircuitState:
    consecutive_failures: int = 0
    open_until_tick: int = 0

    def is_open(self, tick: int) -> bool:
        return tick < self.open_until_tick

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.open_until_tick = 0

    def record_failure(self, tick: int) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= LLM_CIRCUIT_FAILURE_THRESHOLD:
            self.open_until_tick = tick + int(LLM_CIRCUIT_COOLDOWN_SEC)


@dataclass
class PendingLlmJob:
    signature: str
    species_id: str
    member_ids: list[int]
    future: concurrent.futures.Future
    enqueued_tick: int
    enqueued_monotonic: float = field(default_factory=time.perf_counter)
    attempt: int = 1
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


class LlmAdapter(Protocol):
    def submit(
        self,
        cluster: Cluster,
        world: World,
        signature: str,
    ) -> concurrent.futures.Future[AdaptationResponse]: ...


@dataclass
class StubLlmAdapter:
    """Injectable adapter for tests (simulates live slow-path latency/failures)."""

    delay_sec: float = 0.0
    fail_until_attempt: int = 0
    response: AdaptationResponse | LlmAdaptationResult | None = None
    raise_error: str | None = None

    def submit(
        self,
        cluster: Cluster,
        world: World,
        signature: str,
    ) -> concurrent.futures.Future[LlmAdaptationResult]:
        return _executor.submit(self._run, cluster, world, signature)

    def _run(
        self,
        cluster: Cluster,
        world: World,
        signature: str,
    ) -> LlmAdaptationResult:
        if self.delay_sec > 0:
            time.sleep(self.delay_sec)
        if self.raise_error:
            raise RuntimeError(self.raise_error)
        if self.response is not None:
            return normalize_llm_result(self.response)
        pick = mock_adaptation_provider(cluster, world)
        return LlmAdaptationResult(
            use_existing=True,
            subtree_key=pick.subtree_key,
            confidence=pick.confidence,
            rationale=pick.rationale,
        )


@dataclass
class OllamaLlmAdapter:
    """Optional live Ollama JSON adapter (httpx). Falls back to mock on import/network errors."""

    base_url: str = "http://127.0.0.1:11434"
    model: str = "llama3.2"
    mode: Literal["pick", "author"] = "pick"

    @property
    def timeout_sec(self) -> float:
        return LLM_AUTHOR_REQUEST_TIMEOUT_SEC if self.mode == "author" else LLM_REQUEST_TIMEOUT_SEC

    def submit(
        self,
        cluster: Cluster,
        world: World,
        signature: str,
    ) -> concurrent.futures.Future[LlmAdaptationResult]:
        return _executor.submit(self._run, cluster, world, signature)

    def _build_prompt(self, cluster: Cluster) -> str:
        from sim.llm_prompts import build_author_subtree_prompt, build_pick_existing_prompt

        if self.mode == "author":
            return build_author_subtree_prompt(cluster)
        return build_pick_existing_prompt(cluster)

    def _parse_response(self, text: str) -> LlmAdaptationResult:
        from sim.llm_prompts import parse_llm_json_payload

        payload = parse_llm_json_payload(text)
        if "use_existing" not in payload and "subtree_key" in payload:
            return normalize_llm_result(AdaptationResponse.model_validate(payload))
        return LlmAdaptationResult.model_validate(payload)

    def _run(
        self,
        cluster: Cluster,
        world: World,
        signature: str,
    ) -> LlmAdaptationResult:
        try:
            import httpx
        except ImportError as exc:
            if self.mode == "author":
                raise RuntimeError("httpx is required for live Ollama author mode") from exc
            return normalize_llm_result(mock_adaptation_provider(cluster, world))

        prompt = self._build_prompt(cluster)
        try:
            with httpx.Client(timeout=self.timeout_sec) as client:
                resp = client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": self.model, "prompt": prompt, "stream": False, "format": "json"},
                )
                resp.raise_for_status()
                data = resp.json()
                text = data.get("response", "{}")
                return self._parse_response(text)
        except Exception as exc:
            if self.mode == "author":
                raise RuntimeError(f"Ollama {self.mode} request failed: {exc}") from exc
            return normalize_llm_result(mock_adaptation_provider(cluster, world))


def emit_llm_event(
    world: World,
    event_name: str,
    *,
    message: str,
    signature: str = "",
    species_or_cluster_id: str = "",
    severity: str = "info",
    correlation_id: str = "",
) -> None:
    world.adaptation_events.append(
        {
            "event_name": event_name,
            "tick": world.tick,
            "floor": world.floor_profile.depth_index,
            "species_or_cluster_id": species_or_cluster_id,
            "signature": signature,
            "severity": severity,
            "message": message,
            "correlation_id": correlation_id or f"{world.tick}:{event_name}",
        }
    )


def get_circuit(world: World, signature: str) -> LlmCircuitState:
    if signature not in world.llm_circuits:
        world.llm_circuits[signature] = LlmCircuitState()
    return world.llm_circuits[signature]


def enqueue_llm_request(world: World, cluster: Cluster, signature: str) -> None:
    if world.llm_adapter is None:
        return
    if signature in world.pending_llm:
        return

    job = PendingLlmJob(
        signature=signature,
        species_id=cluster.species_id,
        member_ids=[m.id for m in cluster.members],
        future=world.llm_adapter.submit(cluster, world, signature),
        enqueued_tick=world.tick,
    )
    world.pending_llm[signature] = job
    emit_llm_event(
        world,
        "llm.request.started",
        message=f"attempt {job.attempt}",
        signature=signature,
        species_or_cluster_id=cluster.species_id,
        correlation_id=job.correlation_id,
    )


def _rebuild_cluster(world: World, job: PendingLlmJob) -> Cluster | None:
    members = [o for o in world.organisms if o.id in job.member_ids and o.alive]
    if len(members) < 1:
        return None
    return Cluster(species_id=job.species_id, members=members)


def _handle_llm_failure(world: World, job: PendingLlmJob, message: str) -> None:
    circuit = get_circuit(world, job.signature)
    circuit.record_failure(world.tick)
    emit_llm_event(
        world,
        "llm.request.failed",
        message=message,
        signature=job.signature,
        species_or_cluster_id=job.species_id,
        severity="warning",
        correlation_id=job.correlation_id,
    )
    if circuit.is_open(world.tick):
        emit_llm_event(
            world,
            "llm.circuit.open",
            message=f"circuit open until tick {circuit.open_until_tick}",
            signature=job.signature,
            species_or_cluster_id=job.species_id,
            severity="warning",
            correlation_id=job.correlation_id,
        )


def _max_llm_attempts(world: World) -> int:
    adapter = world.llm_adapter
    if isinstance(adapter, OllamaLlmAdapter) and adapter.mode == "author":
        return LLM_AUTHOR_RETRY_MAX_ATTEMPTS
    return LLM_RETRY_MAX_ATTEMPTS


def _retry_llm_job(world: World, job: PendingLlmJob, *, message: str) -> bool:
    if job.attempt >= _max_llm_attempts(world):
        return False
    cluster = _rebuild_cluster(world, job)
    if cluster is None or world.llm_adapter is None:
        return False
    job.attempt += 1
    job.enqueued_monotonic = time.perf_counter()
    job.future = world.llm_adapter.submit(cluster, world, job.signature)
    emit_llm_event(
        world,
        "llm.request.started",
        message=f"{message} attempt {job.attempt}",
        signature=job.signature,
        species_or_cluster_id=job.species_id,
        correlation_id=job.correlation_id,
    )
    return True


def _handle_llm_success(
    world: World,
    job: PendingLlmJob,
    response: AdaptationResponse | LlmAdaptationResult,
) -> bool:
    """Return True when the pending job should be removed."""
    from sim.adaptation import AdaptationResponse as PickResponse
    from sim.adaptation import ingest_adaptation, validate_adaptation_full
    from sim.authored_subtree import ingest_authored_subtree

    cluster = _rebuild_cluster(world, job)
    if cluster is None:
        _handle_llm_failure(world, job, "cluster dissolved before completion")
        return True

    result = normalize_llm_result(response)

    if not result.use_existing and result.authored is not None:
        if ingest_authored_subtree(world, cluster, job.signature, result.authored):
            get_circuit(world, job.signature).record_success()
            emit_llm_event(
                world,
                "llm.request.completed",
                message=f"authored {result.authored.name}",
                signature=job.signature,
                species_or_cluster_id=job.species_id,
                correlation_id=job.correlation_id,
            )
            return True
        if _retry_llm_job(world, job, message="retry after authored rejection"):
            return False
        _handle_llm_failure(world, job, "authored validation or approval failed")
        return True

    if not result.subtree_key:
        _handle_llm_failure(world, job, "missing subtree_key")
        return True

    pick = PickResponse(
        subtree_key=result.subtree_key,
        confidence=result.confidence,
        rationale=result.rationale,
    )
    if not validate_adaptation_full(pick, cluster, world):
        _handle_llm_failure(world, job, "validation failed")
        return True

    ingest_adaptation(world, cluster, job.signature, pick)
    get_circuit(world, job.signature).record_success()
    emit_llm_event(
        world,
        "llm.request.completed",
        message=f"subtree {pick.subtree_key}",
        signature=job.signature,
        species_or_cluster_id=job.species_id,
        correlation_id=job.correlation_id,
    )
    return True


def poll_llm_completions(world: World) -> None:
    """Non-blocking poll of in-flight LLM work (must not block tick)."""
    if not world.pending_llm:
        return

    finished: list[str] = []
    for signature, job in list(world.pending_llm.items()):
        elapsed_sec = time.perf_counter() - job.enqueued_monotonic
        timed_out = elapsed_sec > request_timeout_sec(world)

        if not job.future.done():
            if timed_out:
                job.future.cancel()
                if job.attempt < _max_llm_attempts(world):
                    cluster = _rebuild_cluster(world, job)
                    if cluster is not None and world.llm_adapter is not None:
                        job.attempt += 1
                        job.enqueued_tick = world.tick
                        job.enqueued_monotonic = time.perf_counter()
                        job.future = world.llm_adapter.submit(cluster, world, signature)
                        emit_llm_event(
                            world,
                            "llm.request.started",
                            message=f"retry attempt {job.attempt}",
                            signature=signature,
                            species_or_cluster_id=job.species_id,
                            correlation_id=job.correlation_id,
                        )
                        continue
                _handle_llm_failure(world, job, "timeout")
                finished.append(signature)
            continue

        try:
            response = job.future.result(timeout=0)
        except Exception as exc:
            if job.attempt < LLM_RETRY_MAX_ATTEMPTS:
                cluster = _rebuild_cluster(world, job)
                if cluster is not None and world.llm_adapter is not None:
                    job.attempt += 1
                    job.enqueued_tick = world.tick
                    job.enqueued_monotonic = time.perf_counter()
                    job.future = world.llm_adapter.submit(cluster, world, signature)
                    emit_llm_event(
                        world,
                        "llm.request.started",
                        message=f"retry attempt {job.attempt} after {exc}",
                        signature=signature,
                        species_or_cluster_id=job.species_id,
                        correlation_id=job.correlation_id,
                    )
                    continue
            _handle_llm_failure(world, job, str(exc))
            finished.append(signature)
            continue

        if _handle_llm_success(world, job, response):
            finished.append(signature)

    for signature in finished:
        world.pending_llm.pop(signature, None)
