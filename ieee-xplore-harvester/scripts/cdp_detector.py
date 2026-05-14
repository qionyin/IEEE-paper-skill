"""Edge CDP browser detection and login verification."""

import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from utils import setup_logger

logger = setup_logger("cdp_detector")

CDP_LIST_URL = "http://127.0.0.1:{port}/json/list"
CDP_VERSION_URL = "http://127.0.0.1:{port}/json/version"
IEEE_HOST = "ieeexplore.ieee.org"


def fetch_json(url: str, timeout: int = 5) -> Any:
    """Fetch JSON from a CDP endpoint."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        logger.error("Cannot connect to CDP at %s: %s", url, e)
        return None
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON from %s: %s", url, e)
        return None


def detect_browser(port: int = 9222) -> dict | None:
    """Check if Edge remote debugging is available."""
    version_url = CDP_VERSION_URL.format(port=port)
    data = fetch_json(version_url)
    if data is None:
        logger.error(
            "No Edge debug port found at port %d. "
            "Restart Edge with: msedge.exe --remote-debugging-port=%d",
            port, port,
        )
        return None
    browser_name = data.get("Browser", "")
    if "Edge" not in browser_name and "Edg" not in browser_name:
        logger.warning("Browser is '%s', expected Microsoft Edge.", browser_name)
    logger.info("Connected to %s (port %d)", browser_name, port)
    return data


def list_tabs(port: int = 9222) -> list[dict]:
    """Return all open tabs from CDP."""
    list_url = CDP_LIST_URL.format(port=port)
    data = fetch_json(list_url)
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return []


def find_ieee_tabs(port: int = 9222) -> list[dict]:
    """Find all tabs whose URL contains ieeexplore.ieee.org."""
    tabs = list_tabs(port)
    # Only match actual IEEE pages (not ad/tracking URLs that embed ieeexplore in query params)
    ieee_tabs = [t for t in tabs if t.get("url", "").startswith("https://ieeexplore.ieee.org")]
    if not ieee_tabs:
        logger.warning(
            "No IEEE Xplore tabs found. Open https://ieeexplore.ieee.org in Edge first."
        )
    else:
        for t in ieee_tabs:
            logger.info(
                "Found IEEE tab: %s (title: %s)",
                t.get("url", "")[:100], t.get("title", "")[:60],
            )
    return ieee_tabs


def get_ws_url(tab: dict) -> str | None:
    """Extract WebSocket debugger URL from a tab dict."""
    return tab.get("webSocketDebuggerUrl")


def get_browser_ws_url(port: int = 9222) -> str | None:
    """Get the browser-level WebSocket debugger URL (needed for Playwright CDP)."""
    version_url = CDP_VERSION_URL.format(port=port)
    data = fetch_json(version_url)
    if data is None:
        return None
    return data.get("webSocketDebuggerUrl")


def main():
    """CLI entry: detect and list IEEE Xplore tabs."""
    import argparse
    parser = argparse.ArgumentParser(description="Detect Edge browser and IEEE Xplore tabs")
    parser.add_argument("--port", type=int, default=9222, help="CDP debug port")
    parser.add_argument("--json", action="store_true", help="Output tab list as JSON")
    args = parser.parse_args()

    browser = detect_browser(args.port)
    if browser is None:
        sys.exit(1)

    ieee_tabs = find_ieee_tabs(args.port)

    if args.json:
        print(json.dumps(ieee_tabs, ensure_ascii=False, indent=2))
    elif ieee_tabs:
        print(f"\nFound {len(ieee_tabs)} IEEE Xplore tab(s):")
        for i, t in enumerate(ieee_tabs, 1):
            print(f"  [{i}] {t.get('title', '')[:80]}")
            print(f"      {t.get('url', '')[:120]}")
    else:
        print("No IEEE Xplore tabs found.")


if __name__ == "__main__":
    main()
