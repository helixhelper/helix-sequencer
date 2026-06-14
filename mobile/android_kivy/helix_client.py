"""Client helpers for the Helix Android Kivy MVP.

The Android app can run in two modes:

1. Mock mode: no HELIX_API_URL configured. This is useful on a phone before a
   desktop/cloud runner is available.
2. API mode: HELIX_API_URL points at the Helix mobile job server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import time
from typing import Any, Dict, List, Optional

try:
    import requests
except Exception:  # pragma: no cover - Kivy can still run mock mode without requests.
    requests = None  # type: ignore[assignment]


DEFAULT_ARTIFACTS = ["sequence.xsq", "preview.mp4", "run_manifest.json", "helix.log"]


@dataclass(frozen=True)
class HelixJobRequest:
    audio_path: str
    profile: str = "master"
    style: str = "vendor_like"
    layout: str = "aaatest"

    def to_json(self) -> Dict[str, str]:
        return {
            "audio_path": self.audio_path,
            "profile": self.profile,
            "style": self.style,
            "layout": self.layout,
        }


@dataclass(frozen=True)
class HelixJobStatus:
    job_id: str
    status: str
    message: str = ""
    artifacts: List[str] = field(default_factory=list)
    output_dir: Optional[str] = None

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "HelixJobStatus":
        return cls(
            job_id=str(data.get("job_id", "unknown")),
            status=str(data.get("status", "unknown")),
            message=str(data.get("message", "")),
            artifacts=list(data.get("artifacts", [])),
            output_dir=data.get("output_dir"),
        )


class HelixClient:
    def __init__(self, base_url: Optional[str] = None, timeout_seconds: float = 20.0) -> None:
        self.base_url = (base_url or os.environ.get("HELIX_API_URL") or "").rstrip("/")
        self.timeout_seconds = timeout_seconds

    @property
    def is_mock(self) -> bool:
        return not self.base_url

    def submit_job(self, request: HelixJobRequest) -> HelixJobStatus:
        if self.is_mock:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            return HelixJobStatus(
                job_id=f"mock-{stamp}",
                status="mock_complete",
                message="Mock mode: set HELIX_API_URL to submit to a real Helix runner.",
                artifacts=DEFAULT_ARTIFACTS,
                output_dir=f"outputs/beta/mock-{stamp}",
            )

        if requests is None:
            raise RuntimeError("requests is required when HELIX_API_URL is set")

        response = requests.post(
            f"{self.base_url}/jobs",
            json=request.to_json(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return HelixJobStatus.from_json(response.json())

    def get_status(self, job_id: str) -> HelixJobStatus:
        if self.is_mock:
            return HelixJobStatus(
                job_id=job_id,
                status="mock_complete",
                message="Mock mode status response.",
                artifacts=DEFAULT_ARTIFACTS,
                output_dir=f"outputs/beta/{job_id}",
            )

        if requests is None:
            raise RuntimeError("requests is required when HELIX_API_URL is set")

        response = requests.get(f"{self.base_url}/jobs/{job_id}", timeout=self.timeout_seconds)
        response.raise_for_status()
        return HelixJobStatus.from_json(response.json())
