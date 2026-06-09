"""Real-time relay aggregation.

The relay sits in the event stream between an ElevenLabs agent and the user. As
ElevenLabs client/server events flow through it
(``user_transcript``, ``agent_response``, ``agent_response_correction``,
``interruption``, ``ping``, ``vad_score``), this module accumulates them into a
:class:`LiveConversation` that tracks live latency, interruptions and turns, and
emits compact "observability frames" for dashboards watching in real time.

When the call ends, the accumulated turns are converted to the same
:class:`ConversationData` shape used by the webhook path and persisted through
the normalizer — so live calls land in the dashboard identically to post-call
ingestion.

Reference event shapes (server -> client)::

    {"type":"user_transcript","user_transcription_event":{"user_transcript":"..."}}
    {"type":"agent_response","agent_response_event":{"agent_response":"..."}}
    {"type":"agent_response_correction","agent_response_correction_event":{
        "original_agent_response":"...","corrected_agent_response":"..."}}
    {"type":"interruption","interruption_event":{"event_id":7}}
    {"type":"ping","ping_event":{"event_id":3,"ping_ms":48}}
    {"type":"vad_score","vad_score_event":{"vad_score":0.92}}
    {"type":"conversation_initiation_metadata",
     "conversation_initiation_metadata_event":{"conversation_id":"..."}}
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.schemas.elevenlabs import (
    ConversationData,
    MetadataModel,
    TranscriptTurn,
    TurnMetrics,
    TurnMetricValue,
)


@dataclass
class LiveConversation:
    """Accumulates real-time events for a single in-flight call."""

    agent_id: str
    conversation_id: str
    started_monotonic: float = field(default_factory=time.monotonic)
    started_unix: int = field(default_factory=lambda: int(time.time()))

    turns: list[TranscriptTurn] = field(default_factory=list)
    ping_samples_ms: list[float] = field(default_factory=list)
    vad_samples: list[float] = field(default_factory=list)
    interruptions: int = 0
    _last_user_at: float | None = None

    # ---- derived live values ----
    @property
    def elapsed_secs(self) -> float:
        return round(time.monotonic() - self.started_monotonic, 2)

    @property
    def avg_ping_ms(self) -> float | None:
        return round(sum(self.ping_samples_ms) / len(self.ping_samples_ms), 1) if (
            self.ping_samples_ms
        ) else None

    @property
    def last_vad(self) -> float | None:
        return self.vad_samples[-1] if self.vad_samples else None

    def handle_event(self, event: dict) -> None:
        """Update live state from a single ElevenLabs event."""
        etype = event.get("type")
        now = self.elapsed_secs

        if etype == "conversation_initiation_metadata":
            meta = event.get("conversation_initiation_metadata_event", {})
            self.conversation_id = meta.get("conversation_id", self.conversation_id)

        elif etype == "user_transcript":
            text = event.get("user_transcription_event", {}).get("user_transcript", "")
            self.turns.append(
                TranscriptTurn(role="user", message=text, time_in_call_secs=now)
            )
            self._last_user_at = now

        elif etype == "agent_response":
            text = event.get("agent_response_event", {}).get("agent_response", "")
            # Synthesize per-turn latency: response time since the user finished.
            ttfb_secs = (now - self._last_user_at) if self._last_user_at is not None else None
            metrics = None
            if ttfb_secs is not None and ttfb_secs >= 0:
                metrics = TurnMetrics(
                    metrics={
                        "convai_llm_service_ttfb": TurnMetricValue(elapsed_time=ttfb_secs)
                    }
                )
            self.turns.append(
                TranscriptTurn(
                    role="agent",
                    message=text,
                    time_in_call_secs=now,
                    conversation_turn_metrics=metrics,
                )
            )

        elif etype == "agent_response_correction":
            # The agent was interrupted mid-utterance and corrected its response.
            corr = event.get("agent_response_correction_event", {})
            self.interruptions += 1
            if self.turns and self.turns[-1].role == "agent":
                self.turns[-1].interrupted = True
                self.turns[-1].original_message = corr.get("original_agent_response")

        elif etype == "interruption":
            self.interruptions += 1
            if self.turns and self.turns[-1].role == "agent":
                self.turns[-1].interrupted = True

        elif etype == "ping":
            ping_ms = event.get("ping_event", {}).get("ping_ms")
            if ping_ms is not None:
                self.ping_samples_ms.append(float(ping_ms))

        elif etype == "vad_score":
            score = event.get("vad_score_event", {}).get("vad_score")
            if score is not None:
                self.vad_samples.append(float(score))

    def frame(self) -> dict:
        """Compact live observability frame for dashboard subscribers."""
        return {
            "type": "frame",
            "conversation_id": self.conversation_id,
            "agent_id": self.agent_id,
            "elapsed_secs": self.elapsed_secs,
            "turn_count": len(self.turns),
            "interruptions": self.interruptions,
            "avg_ping_ms": self.avg_ping_ms,
            "vad_score": self.last_vad,
            "last_role": self.turns[-1].role if self.turns else None,
            "last_message": self.turns[-1].message if self.turns else None,
        }

    def to_conversation_data(self, termination_reason: str = "client_ended") -> ConversationData:
        """Convert accumulated live turns into the canonical ConversationData."""
        return ConversationData(
            agent_id=self.agent_id,
            conversation_id=self.conversation_id,
            status="done",
            transcript=self.turns,
            metadata=MetadataModel(
                start_time_unix_secs=self.started_unix,
                call_duration_secs=int(self.elapsed_secs),
                termination_reason=termination_reason,
                conversation_initiation_source="relay",
            ),
        )


class RelayManager:
    """Tracks in-flight live conversations and dashboard monitor subscribers."""

    def __init__(self) -> None:
        self._live: dict[str, LiveConversation] = {}
        self._monitors: set = set()

    # ---- live conversation lifecycle ----
    def start(self, agent_id: str, conversation_id: str) -> LiveConversation:
        live = LiveConversation(agent_id=agent_id, conversation_id=conversation_id)
        self._live[conversation_id] = live
        return live

    def end(self, conversation_id: str) -> LiveConversation | None:
        return self._live.pop(conversation_id, None)

    def get(self, conversation_id: str) -> LiveConversation | None:
        return self._live.get(conversation_id)

    @property
    def active(self) -> list[dict]:
        return [live.frame() for live in self._live.values()]

    # ---- monitor pub/sub ----
    def subscribe(self, ws) -> None:
        self._monitors.add(ws)

    def unsubscribe(self, ws) -> None:
        self._monitors.discard(ws)

    async def broadcast(self, frame: dict) -> None:
        """Send a frame to all monitors, dropping any that have disconnected."""
        dead = []
        for ws in list(self._monitors):
            try:
                await ws.send_json(frame)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._monitors.discard(ws)


# Process-wide singleton.
manager = RelayManager()
