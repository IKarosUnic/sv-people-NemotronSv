"""Security Allowlist & Safe HTTP Fetcher for SALTBOR Phase 1.20 Data Sync."""

from __future__ import annotations

import hashlib
import urllib.parse
import urllib.request
from typing import Dict, Optional, Set, Tuple

ALLOWED_OFFICIAL_HOSTS: Set[str] = {
    "nominatim.openstreetmap.org",
    "overpass-api.de",
    "censo2024.bcr.gob.sv",
    "www.bcr.gob.sv",
    "www.mined.gob.sv",
    "www.salud.gob.sv",
    "download.geofabrik.de",
}


class DomainNotAllowedError(ValueError):
    """Raised when an external URL is outside SALTBOR's trusted official allowlist."""


class SafeHTTPFetcher:
    """Pure-stdlib bounded HTTP client enforcing domain allowlist, timeouts, and size caps."""

    USER_AGENT = "SALTBOR-DataSync/1.20 (Apache-2.0; El Salvador Territorial Research)"

    def __init__(
        self,
        allowed_hosts: Optional[Set[str]] = None,
        allow_localhost_for_tests: bool = False,
    ) -> None:
        self.allowed_hosts = set(allowed_hosts) if allowed_hosts is not None else set(ALLOWED_OFFICIAL_HOSTS)
        self.allow_localhost_for_tests = allow_localhost_for_tests

    def validate_url(self, url: str) -> urllib.parse.ParseResult:
        parsed = urllib.parse.urlparse(url.strip())
        host = (parsed.hostname or "").lower()
        is_local_test = self.allow_localhost_for_tests and host in ("127.0.0.1", "localhost")
        if not is_local_test:
            if parsed.scheme != "https":
                raise DomainNotAllowedError(f"Solo se permiten URLs HTTPS seguras; recibido '{parsed.scheme}'.")
            if host not in self.allowed_hosts:
                raise DomainNotAllowedError(
                    f"Dominio '{host}' no está en la lista blanca oficial permitida: {sorted(self.allowed_hosts)}."
                )
        return parsed

    def fetch_bytes(
        self,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_sec: float = 12.0,
        max_bytes: int = 5 * 1024 * 1024,
    ) -> Tuple[bytes, str]:
        """Fetch bytes safely and return (payload_bytes, sha256_hex)."""
        self.validate_url(url)
        req_headers = {"User-Agent": self.USER_AGENT}
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, data=data, headers=req_headers)
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            chunks = []
            total = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"Respuesta excede límite máximo permitido ({max_bytes} bytes).")
                chunks.append(chunk)
        payload = b"".join(chunks)
        return payload, hashlib.sha256(payload).hexdigest()
