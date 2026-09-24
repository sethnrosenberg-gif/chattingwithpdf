"""The one polite HTTP client every module uses.

- At most one request per second per host (or the host's Crawl-delay if larger),
  enforced across threads *and* processes via a lock file per host, so parallel
  subagents can't gang up on one server.
- Retries with exponential backoff on 429/5xx/transport errors (honors Retry-After).
- robots.txt checked before every request (RFC 9309 wildcards, longest match).
- Bot walls (Cloudflare challenge pages) are detected and the host is skipped, never bypassed.
- Responses cached under cache/http/ (TTL from RADAR_CACHE_TTL_HOURS).
- Every hit, cache hit, block and failure is appended to data/runs/<run>/http-<pid>.jsonl,
  which radar.runlog turns into out/run_log.md.
"""
from __future__ import annotations

import base64
import contextlib
import contextvars
import hashlib
import json
import os
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

import httpx
from tenacity import RetryError, Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from . import config, robots

_channel: contextvars.ContextVar[str] = contextvars.ContextVar("channel", default="misc")


@contextlib.contextmanager
def channel(name: str):
    """Tag every request made inside the block with a channel name for the run log."""
    tok = _channel.set(name)
    try:
        yield
    finally:
        _channel.reset(tok)


def current_channel() -> str:
    return _channel.get()


RETRY_STATUSES = {429, 500, 502, 503, 504, 520, 522, 524}
CACHEABLE_STATUSES = {200, 203, 204, 301, 302, 303, 307, 308, 404, 410}


class _Retryable(Exception):
    def __init__(self, status: int, retry_after: float | None):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.retry_after = retry_after


@dataclass
class Result:
    url: str
    method: str = "GET"
    status: int | None = None
    final_url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    content: bytes = b""
    from_cache: bool = False
    error: str | None = None  # network error, robots block, bot wall, retries exhausted
    blocked: str | None = None  # "robots" | "challenge" | "host-blocked"
    elapsed_ms: int = 0
    redirects: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    @property
    def text(self) -> str:
        ctype = self.headers.get("content-type", "")
        enc = "utf-8"
        if "charset=" in ctype:
            enc = ctype.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        try:
            return self.content.decode(enc, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8", errors="replace"))

    def describe(self) -> str:
        if self.blocked:
            return f"blocked ({self.blocked}): {self.error or ''}".strip()
        if self.error:
            return f"error: {self.error}"
        return f"HTTP {self.status}"


def _is_challenge(status: int, headers: dict[str, str], body: bytes) -> bool:
    if status not in (403, 429, 503):
        return False
    head = body[:6000].lower()
    return (
        b"just a moment" in head
        or b"cf-chl" in head
        or b"challenge-platform" in head
        or b"captcha" in head
        or b"px-captcha" in head
        or (headers.get("server", "").lower() == "cloudflare" and b"attention required" in head)
    )


class _HostGate:
    """Cross-process spacing of request start times per host."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _paths(self, host: str) -> tuple[Path, Path]:
        safe = host.replace(":", "_")
        return self.root / f"{safe}.lock", self.root / f"{safe}.ts"

    @contextlib.contextmanager
    def _lock(self, host: str):
        lock, _ = self._paths(host)
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > 60:  # stale lock from a killed process
                        lock.unlink(missing_ok=True)
                        continue
                except (FileNotFoundError, PermissionError):
                    pass
                time.sleep(0.05 + random.random() * 0.05)
            except PermissionError:  # Windows: file being deleted by another process
                time.sleep(0.05)
        try:
            yield
        finally:
            for _ in range(20):
                try:
                    lock.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.05)

    def wait_turn(self, host: str, delay: float) -> None:
        _, ts = self._paths(host)
        with self._lock(host):
            try:
                last = float(ts.read_text() or 0)
            except (FileNotFoundError, ValueError, PermissionError):
                last = 0.0
            gap = last + delay - time.time()
            if gap > 0:
                time.sleep(gap)
            ts.write_text(f"{time.time():.3f}")


class PoliteClient:
    def __init__(
        self,
        *,
        use_cache: bool = True,
        cache_ttl_hours: float | None = None,
        timeout: float = 30.0,
        max_attempts: int = 4,
    ):
        self.use_cache = use_cache
        self.ttl = (cache_ttl_hours if cache_ttl_hours is not None else config.CACHE_TTL_HOURS) * 3600
        self.max_attempts = max_attempts
        self._client = httpx.Client(
            headers={
                "User-Agent": config.USER_AGENT,
                "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
                "Accept-Language": "en-US,en;q=0.8",
            },
            timeout=timeout,
            follow_redirects=False,  # followed by hand so each hop gets a robots check
            http2=False,
        )
        self._gate = _HostGate(config.CACHE / "_ratelimit")
        self._robots: dict[str, robots.Rules] = {}
        self._robots_lock = threading.Lock()
        self._blocked_hosts: dict[str, str] = {}
        self._log_lock = threading.Lock()
        self._log_path = config.run_dir() / f"http-{os.getpid()}.jsonl"

    # ---------------------------------------------------------------- logging
    def _log(self, res: Result, *, note: str = "") -> None:
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "channel": current_channel(),
            "method": res.method,
            "url": res.url,
            "status": res.status,
            "cache": res.from_cache,
            "ms": res.elapsed_ms,
            "error": res.error,
            "blocked": res.blocked,
        }
        if note:
            rec["note"] = note
        with self._log_lock, open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    # ------------------------------------------------------------------ cache
    def _cache_path(self, method: str, url: str, body: bytes | None) -> Path:
        h = hashlib.sha256(method.encode() + b" " + url.encode() + b"\n" + (body or b"")).hexdigest()
        host = urlsplit(url).netloc.replace(":", "_") or "_"
        return config.CACHE / "http" / host / h[:2] / f"{h}.json"

    def _cache_get(self, path: Path) -> Result | None:
        if not self.use_cache or not path.exists():
            return None
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if time.time() - d.get("fetched_at", 0) > self.ttl:
            return None
        return Result(
            url=d["url"],
            method=d.get("method", "GET"),
            status=d["status"],
            final_url=d.get("final_url"),
            headers=d.get("headers", {}),
            content=base64.b64decode(d["body_b64"]),
            from_cache=True,
        )

    def _cache_put(self, path: Path, res: Result) -> None:
        if res.status not in CACHEABLE_STATUSES:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        keep = {k: v for k, v in res.headers.items() if k in ("content-type", "location", "last-modified", "etag")}
        path.write_text(
            json.dumps(
                {
                    "url": res.url,
                    "method": res.method,
                    "status": res.status,
                    "final_url": res.final_url,
                    "headers": keep,
                    "fetched_at": time.time(),
                    "body_b64": base64.b64encode(res.content).decode(),
                }
            ),
            encoding="utf-8",
        )

    # ----------------------------------------------------------------- robots
    def robots_for(self, url: str) -> robots.Rules:
        parts = urlsplit(url)
        host = parts.netloc.lower()
        with self._robots_lock:
            if host in self._robots:
                return self._robots[host]
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        res = None
        for _ in range(5):  # RFC 9309: follow at least five redirects
            cpath = self._cache_path("GET", robots_url, None)
            res = self._cache_get(cpath)
            if res is None:
                res = self._raw("GET", robots_url, None, None, delay=config.MIN_HOST_DELAY)
                if res.status is not None:
                    self._cache_put(cpath, res)
                self._log(res, note="robots.txt")
            if res.status in (301, 302, 303, 307, 308) and res.headers.get("location"):
                robots_url = urljoin(robots_url, res.headers["location"])
                continue
            break
        if res.status is None:
            rules = robots.Rules(state="error", note=f"robots.txt unreachable: {res.error}")
        elif _is_challenge(res.status, res.headers, res.content):
            rules = robots.Rules(state="challenge", note=f"bot wall on robots.txt (HTTP {res.status})")
        elif 400 <= res.status < 500:
            rules = robots.Rules(state="missing", note=f"robots.txt HTTP {res.status} (allow all per RFC 9309)")
        elif res.status >= 500:
            rules = robots.Rules(state="error", note=f"robots.txt HTTP {res.status}")
        else:
            rules = robots.parse(res.text, config.UA_TOKEN)
        with self._robots_lock:
            self._robots[host] = rules
        return rules

    def host_delay(self, url: str) -> float:
        rules = self.robots_for(url)
        return max(config.MIN_HOST_DELAY, rules.crawl_delay or 0.0)

    # --------------------------------------------------------------- requests
    def _raw(self, method: str, url: str, body: bytes | None, headers: dict | None, delay: float) -> Result:
        host = urlsplit(url).netloc.lower()
        t0 = time.time()
        res = Result(url=url, method=method)

        def attempt() -> httpx.Response:
            self._gate.wait_turn(host, delay)
            r = self._client.request(method, url, content=body, headers=headers)
            if r.status_code in RETRY_STATUSES and not _is_challenge(r.status_code, dict(r.headers), r.content):
                ra = r.headers.get("retry-after")
                raise _Retryable(r.status_code, float(ra) if ra and ra.isdigit() else None)
            return r

        def wait(retry_state) -> float:
            exc = retry_state.outcome.exception() if retry_state.outcome else None
            if isinstance(exc, _Retryable) and exc.retry_after:
                return min(exc.retry_after, 120.0)
            return wait_exponential(multiplier=2, min=2, max=60)(retry_state)

        try:
            r = Retrying(
                stop=stop_after_attempt(self.max_attempts),
                wait=wait,
                retry=retry_if_exception(lambda e: isinstance(e, (_Retryable, httpx.TransportError))),
                reraise=False,
            )(attempt)
            res.status = r.status_code
            res.final_url = str(r.url)
            res.headers = {k.lower(): v for k, v in r.headers.items()}
            res.content = r.content
        except RetryError as e:
            last = e.last_attempt.exception()
            if isinstance(last, _Retryable):
                res.status = last.status
                res.error = f"gave up after {self.max_attempts} attempts (HTTP {last.status})"
            else:
                res.error = f"gave up after {self.max_attempts} attempts ({type(last).__name__}: {last})"
        except httpx.HTTPError as e:
            res.error = f"{type(e).__name__}: {e}"
        res.elapsed_ms = int((time.time() - t0) * 1000)
        return res

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
        headers: dict | None = None,
        use_cache: bool | None = None,
        check_robots: bool = True,
        max_redirects: int = 6,
    ) -> Result:
        if params:
            url = url + ("&" if "?" in url else "?") + urlencode(params, doseq=True)
        body = json.dumps(json_body).encode() if json_body is not None else None
        hdrs = dict(headers or {})
        if body is not None:
            hdrs.setdefault("Content-Type", "application/json")

        hops: list[str] = []
        cur, cur_method, cur_body = url, method, body
        for _ in range(max_redirects + 1):
            res = self._one(cur_method, cur, cur_body, hdrs, use_cache, check_robots)
            if res.status in (301, 302, 303, 307, 308) and res.headers.get("location"):
                nxt = urljoin(cur, res.headers["location"])
                hops.append(nxt)
                if res.status == 303 or (res.status in (301, 302) and cur_method == "POST"):
                    cur_method, cur_body = "GET", None
                cur = nxt
                continue
            break
        res.redirects = hops
        if res.final_url is None:
            res.final_url = cur
        return res

    def _one(self, method, url, body, hdrs, use_cache, check_robots) -> Result:
        host = urlsplit(url).netloc.lower()
        if host in self._blocked_hosts:
            res = Result(url=url, method=method, blocked="host-blocked", error=self._blocked_hosts[host])
            self._log(res)
            return res

        cpath = self._cache_path(method, url, body)
        if use_cache is not False:
            cached = self._cache_get(cpath)
            if cached:
                self._log(cached)
                return cached

        if check_robots and host not in config.ROBOTS_EXEMPT_HOSTS:
            rules = self.robots_for(url)
            if rules.state == "challenge":
                self._blocked_hosts[host] = rules.note
                res = Result(url=url, method=method, blocked="challenge", error=rules.note)
                self._log(res)
                return res
            if not rules.allowed(url):
                res = Result(url=url, method=method, blocked="robots", error=rules.note or "disallowed by robots.txt")
                self._log(res)
                return res
            delay = max(config.MIN_HOST_DELAY, rules.crawl_delay or 0.0)
        else:
            delay = config.MIN_HOST_DELAY

        res = self._raw(method, url, body, hdrs, delay)
        if res.status is not None and _is_challenge(res.status, res.headers, res.content):
            res.blocked = "challenge"
            res.error = f"bot wall (HTTP {res.status}); not bypassed"
            self._blocked_hosts[host] = res.error
        elif res.status in (401, 403) and "html" in res.headers.get("content-type", ""):
            reason = res.headers.get("x-pantheon-serious-reason") or "access denied"
            res.blocked = f"http-{res.status}"
            res.error = f"server refused this client (HTTP {res.status}: {reason}); not worked around"
        elif res.status is not None:
            self._cache_put(cpath, res)
        self._log(res)
        return res

    def get(self, url: str, **kw) -> Result:
        return self.request("GET", url, **kw)

    def post_json(self, url: str, body: Any, **kw) -> Result:
        return self.request("POST", url, json_body=body, **kw)

    def close(self) -> None:
        self._client.close()


_shared: PoliteClient | None = None
_shared_lock = threading.Lock()


def client() -> PoliteClient:
    """Process-wide client (thread-safe)."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = PoliteClient()
        return _shared
