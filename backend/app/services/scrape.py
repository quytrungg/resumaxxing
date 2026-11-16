"""JD URL scraping with SSRF and response-size guards."""
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.jd import title_from_html

MAX_REDIRECTS = 3


def _validate_url(url: str) -> None:
    """Reject non-http(s) URLs and hosts that resolve to private/reserved IPs."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http:// and https:// URLs are allowed")
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no host")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"Could not resolve host: {host}")

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified):
            raise ValueError("URL points to a private or reserved address")


def _fetch_html(url: str) -> str:
    """Fetch a page, validating every redirect hop and capping the body size."""
    current = url
    html = ""
    with httpx.Client(
        timeout=settings.scrape_timeout,
        follow_redirects=False,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Resumaxxing/1.0)"},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _validate_url(current)
            with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise ValueError("Redirect without a Location header")
                    current = urljoin(current, location)
                    continue
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                if "html" not in ctype and "text" not in ctype:
                    raise ValueError(f"Unsupported content type: {ctype or 'unknown'}")
                chunks = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > settings.scrape_max_bytes:
                        raise ValueError("Response is too large to scrape")
                    chunks.append(chunk)
                html = b"".join(chunks).decode(resp.encoding or "utf-8", errors="ignore")
                break
        else:
            raise ValueError("Too many redirects")
    return html


def fetch_jd(url: str) -> tuple[str, str | None]:
    """Return ``(visible_text, page_title)`` for a job posting.

    The title comes from the page's ``<h1>``/``<title>``; callers may fall back
    to text or URL heuristics when it is missing.
    """
    html = _fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split()), title_from_html(html)


def fetch_jd_text(url: str) -> str:
    """Fetch a job posting and return only its visible text."""
    return fetch_jd(url)[0]
