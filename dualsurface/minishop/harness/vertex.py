"""Google Cloud Vertex AI backend helpers for the MiniShop model loop.

Auth is Application Default Credentials (ADC), never a static API key,
because Vertex access tokens expire after about an hour. Run
`gcloud auth application-default login` once per environment before using
a Vertex model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class VertexEndpoint:
    base_url: str
    project: str
    location: str


def vertex_endpoint() -> VertexEndpoint:
    """Build the Vertex OpenAI-compatible base URL from env vars.

    Reads GOOGLE_CLOUD_PROJECT (or GCP_PROJECT) and VERTEX_LOCATION
    (default "global"). Global uses the regionless host; any other
    location uses the region-prefixed host, matching Vertex's OpenAI
    compatibility docs (cloud.google.com/vertex-ai/generative-ai/docs/start/openai).
    """
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    if not project:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT (or GCP_PROJECT) is not set. Set it to your GCP project id "
            "and run `gcloud auth application-default login` before using a Vertex model."
        )
    location = os.environ.get("VERTEX_LOCATION", "global")
    if location == "global":
        host = "aiplatform.googleapis.com"
    else:
        host = f"{location}-aiplatform.googleapis.com"
    base_url = f"https://{host}/v1/projects/{project}/locations/{location}/endpoints/openapi"
    return VertexEndpoint(base_url=base_url, project=project, location=location)


class VertexAccessToken:
    """Lazily refreshing bearer token from Application Default Credentials.

    Vertex access tokens expire after about an hour, so `.get()` must be
    called on every request rather than cached once at startup. This class
    caches the underlying credentials object but refreshes the token only
    when it is missing or expired.
    """

    _SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

    def __init__(self) -> None:
        self._credentials = None

    def _load_credentials(self):
        try:
            import google.auth
        except ImportError as exc:
            raise RuntimeError(
                "google-auth is required for Vertex models. Install it with "
                "`pip install google-auth` (see requirements.txt)."
            ) from exc
        credentials, _ = google.auth.default(scopes=self._SCOPES)
        return credentials

    def get(self) -> str:
        try:
            import google.auth.transport.requests
        except ImportError as exc:
            raise RuntimeError(
                "google-auth is required for Vertex models. Install it with "
                "`pip install google-auth` (see requirements.txt)."
            ) from exc

        if self._credentials is None:
            self._credentials = self._load_credentials()

        if not self._credentials.valid or self._credentials.expired:
            self._credentials.refresh(google.auth.transport.requests.Request())

        if not self._credentials.token:
            raise RuntimeError(
                "Failed to obtain a Vertex access token. Run "
                "`gcloud auth application-default login` and retry."
            )
        return self._credentials.token
