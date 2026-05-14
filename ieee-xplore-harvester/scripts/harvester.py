#!/usr/bin/env python3
"""
IEEE Xplore Harvester - Main Entry Point

Connects to an already-open Edge browser via CDP, searches IEEE Xplore,
extracts paper metadata, downloads PDFs, and generates structured output.

Usage:
    python harvester.py --keyword "lithium battery" --years 2022-2025 --count 30 --download-pdf
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

# Ensure scripts/ is on path
sys.path.insert(0, str(Path(__file__).parent))

from cdp_detector import detect_browser, find_ieee_tabs, get_browser_ws_url
from ieee_automation import IEEEXploreAutomation
from pdf_downloader import PDFDownloader
from storage import OutputManager
from reporter import generate_statistics, generate_html_report, generate_search_log
from utils import setup_logger, generate_output_dir, sanitize_filename, save_json

logger = setup_logger("harvester")


def classify_priority(paper: dict, idx: int) -> str:
    """Classify a paper into high/medium/low priority based on available signals."""
    access = paper.get("access_status", "").lower()
    year_str = paper.get("year", "")
    citation_count = paper.get("citation_count", "0")

    score = 0

    # Open Access papers are preferred
    if "open" in access:
        score += 3

    # Newer papers preferred
    try:
        year = int(year_str)
        current_year = datetime.now().year
        if year >= current_year - 1:
            score += 2
        elif year >= current_year - 3:
            score += 1
    except (ValueError, TypeError):
        pass

    # Highly cited papers
    try:
        cites = int(citation_count)
        if cites >= 50:
            score += 3
        elif cites >= 10:
            score += 1
    except (ValueError, TypeError):
        pass

    if score >= 5:
        return "high"
    elif score >= 3:
        return "medium"
    return "low"


def main():
    parser = argparse.ArgumentParser(
        description="IEEE Xplore Harvester - Academic literature automation via Edge CDP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python harvester.py --keyword "solid electrolyte" --count 20
  python harvester.py --keyword "perovskite solar" --years 2023-2025 --count 50 --download-pdf
  python harvester.py --keyword "transformer attention" --years 2020-2025 --sort newest --count 100

Prerequisites:
  1. Start Edge with: msedge.exe --remote-debugging-port=9222
  2. Sign in to https://ieeexplore.ieee.org in that Edge window
  3. pip install playwright && playwright install chromium
        """,
    )
    parser.add_argument("--keyword", "-k", type=str, required=True,
                        help="Search keyword(s) (required)")
    parser.add_argument("--years", "-y", type=str, default="2020-2025",
                        help="Year range, e.g. 2020-2025 (default: 2020-2025)")
    parser.add_argument("--count", "-c", type=int, default=50,
                        help="Maximum number of papers to collect (default: 50)")
    parser.add_argument("--sort", "-s", type=str, default="relevance",
                        choices=["relevance", "newest", "oldest", "cited"],
                        help="Sort order (default: relevance)")
    parser.add_argument("--download-pdf", "-d", action="store_true", default=False,
                        help="Download PDF full-text for each paper")
    parser.add_argument("--min-if", type=float, default=0.0,
                        help="Minimum impact factor filter (requires EasyScholar extension)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output directory (auto-generated if not set)")
    parser.add_argument("--cdp-port", "-p", type=int, default=9222,
                        help="Edge remote debugging port (default: 9222)")
    args = parser.parse_args()

    # ── Step 1: Detect Edge browser ──
    logger.info("=" * 60)
    logger.info("IEEE Xplore Harvester")
    logger.info("=" * 60)

    browser = detect_browser(args.cdp_port)
    if browser is None:
        logger.error(
            "Cannot connect to Edge. Please start Edge with:\\n"
            "  msedge.exe --remote-debugging-port=%d", args.cdp_port
        )
        sys.exit(1)

    # ── Step 2: Find IEEE Xplore tab ──
    ieee_tabs = find_ieee_tabs(args.cdp_port)
    if not ieee_tabs:
        logger.error("No IEEE Xplore tabs found. Open https://ieeexplore.ieee.org and sign in.")
        sys.exit(1)

    browser_ws_url = get_browser_ws_url(args.cdp_port)
    if not browser_ws_url:
        logger.error("Could not get browser WebSocket URL.")
        sys.exit(1)

    # ── Step 3: Create output directory ──
    output_dir = generate_output_dir(args.output, args.keyword)
    logger.info("Output directory: %s", output_dir)

    # Set up file logger in output directory
    log_file = output_dir / "reports" / "search_log.txt"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = __import__("logging").FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logger.handlers[0].formatter)
    logger.addHandler(fh)

    output = OutputManager(output_dir, args.keyword, args.years)

    # ── Step 4: Connect via Playwright CDP ──
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        )
        sys.exit(1)

    with sync_playwright() as pw:
        logger.info("Connecting to Edge via CDP...")
        browser_obj = pw.chromium.connect_over_cdp(browser_ws_url)
        context = browser_obj.contexts[0]

        # Find the existing IEEE Xplore page among open tabs
        page = None
        for p in context.pages:
            if p.url.startswith("https://ieeexplore.ieee.org"):
                page = p
                logger.info("Using existing IEEE tab: %s", p.url[:80])
                break
        if page is None:
            logger.error("No IEEE Xplore page found among open tabs. Open ieeexplore.ieee.org and login first.")
            sys.exit(1)

        auto = IEEEXploreAutomation(page, browser_ws_url)

        # ── Step 5: Verify login ──
        if not auto.check_login_status():
            logger.error(
                "Not signed in to IEEE Xplore. Please sign in at https://ieeexplore.ieee.org"
            )
            sys.exit(1)

        # ── Step 6: Execute search ──
        logger.info("Searching: '%s' (%s) [max %d papers]",
                    args.keyword, args.years, args.count)
        auto.navigate_to_search(args.keyword, args.years, args.sort)

        # ── Step 7: Collect results with pagination ──
        all_papers: list[dict] = []
        seen_papers: set[str] = set()
        page_num = 1

        while len(all_papers) < args.count:
            logger.info("--- Page %d ---", page_num)
            papers = auto.extract_result_list()
            if not papers:
                logger.warning("No results found on page %d", page_num)
                break

            added = 0
            for paper in papers:
                if len(all_papers) >= args.count:
                    break
                dedupe_key = paper.get("arnumber") or paper.get("doi") or paper.get("url") or paper.get("title", "").lower()
                if dedupe_key in seen_papers:
                    continue
                seen_papers.add(dedupe_key)
                paper["index"] = len(all_papers) + 1
                all_papers.append(paper)
                added += 1

            logger.info("Collected %d/%d papers so far", len(all_papers), args.count)

            if len(all_papers) >= args.count:
                break
            if not auto.go_next_page():
                logger.info("No more pages available")
                break
            page_num += 1

        logger.info("Total candidates from search: %d", len(all_papers))

        if not all_papers:
            logger.error("No papers collected. Check search parameters.")
            sys.exit(1)

        # ── Step 8: Extract full metadata from detail pages ──
        logger.info("Extracting full metadata from detail pages...")
        cookies = auto.get_cookies()
        bib_entries: list[str] = []
        pending: list[dict] = []

        for i, paper in enumerate(all_papers):
            idx = paper["index"]
            url = paper.get("url", "")
            if not url:
                continue

            logger.info("[%03d/%d] Opening detail: %s", idx, len(all_papers),
                        paper.get("title", "")[:60])

            if not auto.open_detail(url):
                pending.append({"index": idx, "title": paper.get("title", ""),
                                "reason": "Failed to open detail page", "url": url})
                continue

            detail = auto.extract_detail()

            # Merge detail into paper
            for key in ("abstract", "keywords", "doi", "arxiv", "arnumber",
                        "citation_count", "access_status", "pdf_urls"):
                if key in detail and detail[key]:
                    paper[key] = detail[key]

            # Classify priority
            paper["priority"] = classify_priority(paper, idx)

            # Extract citations
            bib = auto.extract_bibtex()
            ris = auto.extract_ris()
            if bib:
                bib_entries.append(bib)
            output.save_citation(idx, paper, bib, ris)

            # Save abstract
            output.save_abstract(idx, paper)

            # Progress save every 5 papers
            if idx % 5 == 0:
                output.save_candidates(all_papers)
                logger.info("  Progress saved (%d/%d)", idx, len(all_papers))

        # ── Step 9: Final save ──
        output.save_candidates(all_papers)
        output.save_priority_split(all_papers)
        output.save_urls_csv(all_papers)
        if bib_entries:
            output.save_references_bib(bib_entries)
            output.save_all_references_bib(bib_entries)
        output.save_all_abstracts(all_papers)

        if pending:
            output.save_pending_csv(pending)
            logger.warning("%d papers marked as pending", len(pending))

        # ── Step 10: Download PDFs ──
        download_summary = None
        if args.download_pdf:
            logger.info("Downloading PDFs...")
            downloader = PDFDownloader(output.pdfs_dir, cookies, output_dir.parent)
            for paper in all_papers:
                idx = paper["index"]
                pdf_urls = paper.get("pdf_urls", [])
                pdf_url = pdf_urls[0] if pdf_urls else ""
                result = downloader.download(idx, paper, pdf_url)
                if result.get("skipped"):
                    continue
                if not result["success"] and pdf_url:
                    pending.append({
                        "index": idx,
                        "title": paper.get("title", ""),
                        "reason": result.get("error", "Unknown"),
                        "url": pdf_url,
                    })
            downloader.save_log()
            download_summary = downloader.summary()
            output.save_pending_csv(pending)

        # ── Step 11: Generate reports ──
        logger.info("Generating reports...")
        stats = generate_statistics(all_papers, download_summary)
        save_json(output.reports_dir / "statistics.json", stats)

        generate_html_report(
            all_papers, stats, args.keyword, args.years,
            output.reports_dir / "summary.html",
        )
        generate_search_log(
            args.keyword, args.years, args.count, stats,
            download_summary, output.reports_dir / "search_log.txt",
        )

        # ── Done ──
        logger.info("=" * 60)
        logger.info("Done! Output: %s", output_dir)
        logger.info("  Papers:  %d collected", len(all_papers))
        if download_summary:
            logger.info("  PDFs:    %d downloaded, %d skipped, %d failed",
                        download_summary["success"], download_summary.get("skipped", 0), download_summary["failed"])
        logger.info("  Pending: %d items", len(pending))
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
