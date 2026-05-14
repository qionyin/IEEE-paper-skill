"""PDF download with retry, validation, and logging."""

import sys
import urllib.parse
import urllib.request
import urllib.error
import ssl
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from utils import setup_logger, sanitize_filename, validate_pdf, retry, save_json

logger = setup_logger("pdf_downloader")


class PDFDownloader:
    """Downloads PDFs from IEEE Xplore using browser session cookies."""

    def __init__(self, output_dir: Path, cookies: list[dict] | None = None, library_dir: Path | None = None):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.library_dir = library_dir or output_dir.parent
        self.cookies = cookies or []
        self.log: list[dict] = []
        self.ssl_context = ssl.create_default_context()

    def _cookie_header(self, url: str = "") -> str:
        """Build Cookie header from browser cookies that apply to the target URL."""
        if not self.cookies:
            return ""
        host = urllib.parse.urlparse(url).hostname or ""
        parts = []
        for cookie in self.cookies:
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            domain = cookie.get("domain", "").lstrip(".")
            if not name:
                continue
            if domain and host and not (host == domain or host.endswith(f".{domain}")):
                continue
            parts.append(f"{name}={value}")
        return "; ".join(parts)

    def _candidate_urls(self, paper: dict, pdf_url: str) -> list[str]:
        """Return possible IEEE PDF endpoints for a paper."""
        urls: list[str] = []
        if pdf_url:
            urls.append(pdf_url)
        arnumber = str(paper.get("arnumber", "")).strip()
        if arnumber:
            urls.extend([
                f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={arnumber}",
                f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={arnumber}",
            ])
        return list(dict.fromkeys(urls))

    def _pdf_filename(self, index: int, paper: dict) -> str:
        """Generate standardized PDF filename."""
        title = sanitize_filename(paper.get("title", "untitled"), 50)
        arnumber = paper.get("arnumber", "unknown")
        return f"{index:03d}_{title}_{arnumber}.pdf"

    def _existing_pdf(self, paper: dict) -> Path | None:
        title = sanitize_filename(paper.get("title", ""), 50).lower()
        arnumber = str(paper.get("arnumber", "")).strip().lower()
        doi = sanitize_filename(str(paper.get("doi", "")), 80).lower()
        if not self.library_dir.exists():
            return None
        for path in self.library_dir.rglob("*.pdf"):
            name = path.stem.lower()
            if arnumber and arnumber in name:
                return path
            if doi and doi in name:
                return path
            if title and title in name:
                return path
        return None

    @retry(max_attempts=3, base_delay=3.0, backoff=2.0, exceptions=(urllib.error.URLError, OSError))
    def _download_file(self, url: str, dest: Path) -> bool:
        """Download a single file with cookie auth."""
        req = urllib.request.Request(url)
        req.add_header(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        )
        req.add_header("Accept", "application/pdf,*/*")
        req.add_header("Referer", "https://ieeexplore.ieee.org/")
        cookie = self._cookie_header(url)
        if cookie:
            req.add_header("Cookie", cookie)

        with urllib.request.urlopen(req, timeout=60, context=self.ssl_context) as resp:
            content_type = resp.headers.get("Content-Type", "")
            content = resp.read()
            if "text/html" in content_type or content.startswith(b"<!DOCTYPE html"):
                return False
            dest.write_bytes(content)
        return True

    def download(self, index: int, paper: dict, pdf_url: str) -> dict:
        """Download PDF for a paper. Returns log entry."""
        filename = self._pdf_filename(index, paper)
        dest = self.output_dir / filename
        entry: dict[str, Any] = {
            "index": index,
            "title": paper.get("title", ""),
            "arnumber": paper.get("arnumber", ""),
            "filename": filename,
            "success": False,
            "error": None,
        }

        if not pdf_url and not paper.get("arnumber"):
            entry["error"] = "No PDF URL"
            self.log.append(entry)
            return entry

        existing = self._existing_pdf(paper)
        if existing:
            entry["success"] = True
            entry["skipped"] = True
            entry["existing_file"] = str(existing)
            entry["size_kb"] = round(existing.stat().st_size / 1024, 1)
            logger.info("Skipping existing PDF [%03d]: %s", index, existing.name)
            self.log.append(entry)
            return entry

        access_status = str(paper.get("access_status") or paper.get("accessStatus") or "").lower()
        if "open" not in access_status and not pdf_url:
            entry["skipped"] = True
            entry["error"] = "No accessible PDF link"
            logger.info("Skipping PDF without accessible link [%03d]: %s", index, paper.get("title", "")[:60])
            self.log.append(entry)
            return entry

        logger.info("Downloading PDF [%03d]: %s", index, paper.get("title", "")[:60])
        last_error = None
        for candidate_url in self._candidate_urls(paper, pdf_url):
            try:
                ok = self._download_file(candidate_url, dest)
                if ok and validate_pdf(dest):
                    size_kb = dest.stat().st_size / 1024
                    entry["success"] = True
                    entry["size_kb"] = round(size_kb, 1)
                    entry["url"] = candidate_url
                    logger.info("  OK (%.1f KB)", size_kb)
                    break
                if ok:
                    last_error = "Invalid PDF header"
                    logger.warning("  Invalid PDF from %s", candidate_url)
                else:
                    last_error = "No download permission or login expired"
                    logger.warning("  No download permission or login expired: %s", candidate_url)
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}"
                if e.code in (401, 403, 404):
                    entry["skipped"] = True
                    logger.warning("  Skipping inaccessible PDF (HTTP %d): %s", e.code, candidate_url)
                    break
                logger.error("  HTTP %d from %s", e.code, candidate_url)
            except Exception as e:
                last_error = str(e)[:200]
                logger.error("  Failed from %s: %s", candidate_url, e)
            dest.unlink(missing_ok=True)

        if not entry["success"]:
            entry["error"] = last_error or "No PDF URL"

        self.log.append(entry)
        return entry

    def save_log(self) -> None:
        """Write download log to JSON."""
        save_json(self.output_dir / "download_log.json", self.log)

    def summary(self) -> dict:
        """Return summary of download results."""
        total = len(self.log)
        success = sum(1 for e in self.log if e["success"] and not e.get("skipped"))
        skipped = sum(1 for e in self.log if e.get("skipped"))
        total_size = sum(e.get("size_kb", 0) for e in self.log if e["success"])
        return {
            "total": total,
            "success": success,
            "skipped": skipped,
            "failed": total - success - skipped,
            "total_size_kb": round(total_size, 1),
        }


def extract_pdf_urls(page) -> list[str]:
    """Extract possible PDF URLs from an IEEE Xplore detail page.

    Uses JavaScript evaluation on a Playwright page object.
    """
    js = """
    () => {
        const links = [];
        document.querySelectorAll('a').forEach(a => {
            const href = a.href || '';
            if (href.includes('/stamp/stamp.jsp') || href.includes('.pdf')) {
                links.push(href);
            }
        });
        return [...new Set(links)];
    }
    """
    try:
        return page.evaluate(js)
    except Exception:
        return []
