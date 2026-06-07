"""Hermes Core — web search and extract tools."""

import json
import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

WEB_SEARCH_SCHEMA = {
    "name": "web_search",
    "description": "Search the web for information on any topic. Returns up to 5 relevant results with titles, URLs, and descriptions.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query to look up on the web"},
        },
        "required": ["query"],
    },
}

WEB_EXTRACT_SCHEMA = {
    "name": "web_extract",
    "description": "Extract content from web page URLs. Returns page content in markdown format. Pages under 5000 chars return full markdown; larger pages are summarized. If a URL fails or times out, use the browser tool to access it instead.",
    "parameters": {
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of URLs to extract content from (max 5 URLs per call)",
                "maxItems": 5,
            },
        },
        "required": ["urls"],
    },
}


def _check_web_requirements() -> bool:
    return bool(os.getenv("FIRECRAWL_API_KEY") or os.getenv("TAVILY_API_KEY")
                or os.getenv("EXA_API_KEY") or os.getenv("PARALLEL_API_KEY"))


def _is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = (parsed.hostname or "").lower()
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return False
        if hostname.startswith("10.") or hostname.startswith("192.168.") or hostname.startswith("172."):
            parts = hostname.split(".")
            if hostname.startswith("172.") and len(parts) >= 2:
                second = int(parts[1])
                if 16 <= second <= 31:
                    return False
            else:
                return False
        return True
    except Exception:
        return False


def web_search(query: str) -> str:
    if not query.strip():
        return json.dumps({"error": "Empty search query"})

    api_key = os.getenv("TAVILY_API_KEY")
    if api_key:
        try:
            import httpx
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "max_results": 5},
                timeout=30,
            )
            data = resp.json()
            results = data.get("results", [])
            output = []
            for r in results[:5]:
                output.append(f"**{r.get('title', 'Untitled')}**\n{r.get('url', '')}\n{r.get('content', '')}\n")
            return "\n".join(output) if output else json.dumps({"result": "No results found"})
        except Exception as e:
            logger.warning("Tavily search failed: %s", e)

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if api_key:
        try:
            import httpx
            resp = httpx.post(
                "https://api.firecrawl.dev/v1/search",
                json={"query": query, "limit": 5},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
            )
            data = resp.json()
            if data.get("success"):
                results = data.get("data", [])
                output = []
                for r in results[:5]:
                    output.append(f"**{r.get('title', 'Untitled')}**\n{r.get('url', '')}\n{r.get('description', '')}\n")
                return "\n".join(output) if output else json.dumps({"result": "No results found"})
        except Exception as e:
            logger.warning("Firecrawl search failed: %s", e)

    return json.dumps({"error": "No web search backend configured. Set TAVILY_API_KEY or FIRECRAWL_API_KEY."})


def web_extract(urls: list[str]) -> str:
    if not urls:
        return json.dumps({"error": "No URLs provided"})

    safe_urls = [u for u in urls[:5] if _is_safe_url(u)]
    if not safe_urls:
        return json.dumps({"error": "No safe URLs to extract"})

    results = []
    for url in safe_urls:
        try:
            import httpx
            resp = httpx.get(url, timeout=30, follow_redirects=True,
                             headers={"User-Agent": "HermesAgent/1.0"})
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                results.append(f"## {url}\n(Skipped: non-text content type: {content_type})")
                continue

            text = resp.text
            if len(text) > 100_000:
                text = text[:100_000] + "\n\n[...truncated]"
            results.append(f"## {url}\n\n{text[:5000]}")
        except Exception as e:
            results.append(f"## {url}\n(Error: {e})")

    return "\n\n---\n\n".join(results)
