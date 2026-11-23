"""Thin HTTP client the PC-side runner uses to talk to Rove's server (EATP-037).

Rove lives on the VM (reached over Tailscale); the runner lives on Kevin's PC.
The runner is not a browser, so it sends no `Origin` header, which Rove's
same-origin guard accepts (verified live). Every method raises
`httpx.HTTPError` on failure — the caller decides whether that is fatal.
"""

from __future__ import annotations

from typing import Any

import httpx

from rove import config


class RoveClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._http = httpx.Client(
            base_url=(base_url or config.ROVE_URL).rstrip("/"), transport=transport, timeout=timeout
        )

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str) -> Any:
        response = self._http.get(path)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        response = self._http.post(path, json=body)
        response.raise_for_status()
        return response.json()

    # --- reads -------------------------------------------------------------

    def get_settings(self) -> dict[str, Any]:
        return self._get("/nightly/settings")

    def get_inbox(self) -> dict[str, Any]:
        return self._get("/inbox")

    def get_retry_urls(self) -> list[str]:
        return list(self._get("/nightly/retry").get("urls", []))

    def get_learned_answers(self) -> list[dict[str, Any]]:
        return list(self._get("/nightly/learned-answers").get("items", []))

    def get_open_skipped_urls(self) -> set[str]:
        return {item["url"] for item in self._get("/nightly/skipped").get("items", [])}

    # --- writes ------------------------------------------------------------

    def consume_skip(self) -> dict[str, Any]:
        return self._post("/nightly/consume-skip")

    def track(self, signature: str, action: str) -> dict[str, Any]:
        return self._post("/track", {"signature": signature, "action": action})

    def add_skipped(self, url: str, reason: str, **fields: str) -> dict[str, Any]:
        return self._post("/nightly/skipped", {"url": url, "reason": reason, **fields})

    def add_question(self, question: str, language: str, vacancy: dict[str, str]) -> dict[str, Any]:
        return self._post(
            "/nightly/questions", {"question": question, "language": language, "vacancy": vacancy}
        )
