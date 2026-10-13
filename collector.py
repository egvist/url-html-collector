"""Capture page bodies from a URL, a URL list, or manual browsing."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent

# Heuristic only: a site-specific --ready-selector is more reliable.
AUTO_READY = """() => {
    if (!document.body || document.readyState === 'loading') return false;
    const title = document.title.trim().toLowerCase();
    if (['just a moment...', 'attention required! | cloudflare',
         'access denied', 'security verification'].includes(title)) return false;
    const visible = element => element.getClientRects().length > 0;
    const markers = document.querySelectorAll(
        '#challenge-running, #challenge-stage, #challenge-form, ' +
        'iframe[src*="challenges.cloudflare.com"]'
    );
    if (Array.from(markers).some(visible)) return false;
    return document.body.innerText.trim().length > 0;
}"""


def wait_for_auto(page, args):
    page.wait_for_function(AUTO_READY, timeout=args.timeout * 1000, polling=500)


def validate_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Expected an HTTP/HTTPS URL without embedded credentials")
    return url


def read_urls(path):
    urls = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        try:
            validate_url(url)
        except ValueError as error:
            raise ValueError(f"Invalid HTTP/HTTPS URL on line {number}") from error
        if url not in urls:
            urls.append(url)
    return urls


def completed_urls(path):
    completed = set()
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    completed.add(record["requested_url"])
                except (ValueError, KeyError, TypeError) as error:
                    raise ValueError(f"Invalid output record on line {number}; repair it before resuming") from error
    return completed


def append_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def capture(page, args, requested_url=None):
    if args.settle:
        page.wait_for_timeout(args.settle * 1000)
    if getattr(args, "auto", False):
        wait_for_auto(page, args)
    record = page.evaluate("""() => {
        if (!document.body) throw new Error('Page has no body');
        return {url: location.href, title: document.title, body: document.body.outerHTML};
    }""")
    validate_url(record["url"])
    record["requested_url"] = requested_url or record["url"]
    record["captured_at"] = datetime.now(timezone.utc).isoformat()
    return record


def browse(args, launch, browser_error):
    done = completed_urls(args.output) if args.resume else set()
    context = launch(str(args.profile.resolve()), headless=False)
    saved = 0
    try:
        context.new_page()
        print("Navigate in this browser, finish verification, then return here to save.")
        while True:
            answer = input("Enter = choose a page to save, q = quit: ").strip().lower()
            if answer == "q":
                break
            if answer:
                continue
            pages = [page for page in context.pages if not page.is_closed()]
            if not pages:
                print("No open pages.")
                break
            if len(pages) == 1:
                page = pages[0]
            else:
                for index, page in enumerate(pages, 1):
                    print(f"{index}: {page.url}")
                choice = input("Page number (Enter = cancel): ").strip()
                if not choice.isdigit() or not 1 <= int(choice) <= len(pages):
                    continue
                page = pages[int(choice) - 1]
            try:
                if args.ready_selector:
                    page.locator(args.ready_selector).first.wait_for(state="visible", timeout=args.timeout * 1000)
                record = capture(page, args)
                if record["requested_url"] in done:
                    print("Already saved; skipped (--resume).")
                    continue
                append_record(args.output, record)
                if args.resume:
                    done.add(record["requested_url"])
                saved += 1
                print(f"Saved: {record['url']}")
            except (browser_error, ValueError) as error:
                print(f"Could not capture this page: {error}")
    finally:
        context.close()
    print(f"Saved: {saved}. Output: {args.output}")
    return 0


def collect(args, launch, browser_error, timeout_error):
    urls = [validate_url(args.url)] if getattr(args, "url", None) else read_urls(args.urls)
    done = completed_urls(args.output) if args.resume else set()
    pending = [url for url in urls if url not in done]
    if not pending:
        print("No pending URLs.")
        return 0
    context = launch(str(args.profile.resolve()), headless=False)
    failures = 0
    saved = 0
    try:
        page = context.new_page()
        for index, url in enumerate(pending, 1):
            print(f"[{index}/{len(pending)}] {url}")
            try:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                except timeout_error:
                    if args.ready_selector or getattr(args, "auto", False):
                        raise
                    print("Navigation timed out. Inspect the browser before saving.")
                if args.ready_selector:
                    # Select actual target content, not a generic body element.
                    page.locator(args.ready_selector).first.wait_for(
                        state="visible", timeout=args.timeout * 1000
                    )
                elif getattr(args, "auto", False):
                    wait_for_auto(page, args)
                else:
                    answer = input("Complete verification and wait for the content. Enter = save, s = skip, q = quit: ").strip().lower()
                    while answer not in ("", "s", "q"):
                        answer = input("Enter = save, s = skip, q = quit: ").strip().lower()
                    if answer == "q":
                        break
                    if answer == "s":
                        continue
                record = capture(page, args, url)
                append_record(args.output, record)
                saved += 1
                print(f"Saved {len(record['body']):,} characters")
            except (browser_error, ValueError) as error:
                failures += 1
                append_record(args.errors, {
                    "requested_url": url, "error": str(error),
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                })
                print(f"Failed; recorded in {args.errors}")
                if page.is_closed():
                    break
            if index < len(pending) and args.delay:
                page.wait_for_timeout(args.delay * 1000)
    finally:
        context.close()
    print(f"Saved: {saved}; failed: {failures}. Output: {args.output}")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", type=Path, nargs="?", help="UTF-8 URL file (legacy positional form)")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--url", help="Open and capture one HTTP/HTTPS URL")
    modes.add_argument("--urls", type=Path, dest="url_file", help="UTF-8 file, one URL per line")
    modes.add_argument("--browse", action="store_true", help="Browse manually and capture chosen open pages")
    parser.add_argument("--output", type=Path, default=ROOT / "output/pages.jsonl")
    parser.add_argument("--errors", type=Path, default=ROOT / "output/errors.jsonl")
    parser.add_argument("--profile", type=Path, default=ROOT / ".browser-profile")
    parser.add_argument("--resume", action="store_true", help="Skip URLs already present in output")
    parser.add_argument("--auto", action="store_true", help="Capture URL(s) without prompts; wait for common challenge screens to clear")
    parser.add_argument("--ready-selector", help="Automatically save once this target-content CSS selector is visible")
    parser.add_argument("--timeout", type=float, default=120, help="Navigation/content timeout in seconds")
    parser.add_argument("--delay", type=float, default=2, help="Seconds between pages")
    parser.add_argument("--settle", type=float, default=1, help="Extra seconds before capture")
    args = parser.parse_args()
    if args.urls and (args.url or args.url_file or args.browse):
        parser.error("Choose only one input mode")
    args.urls = args.url_file or args.urls
    if not (args.urls or args.url or args.browse):
        parser.error("Choose --url, --urls, or --browse")
    if args.auto and args.browse:
        parser.error("--auto requires --url or --urls; --browse uses manual page selection")
    if args.timeout <= 0 or args.delay < 0 or args.settle < 0:
        parser.error("Timeout must be positive; delay and settle must be nonnegative")
    args.output = args.output.expanduser().resolve()
    args.errors = args.errors.expanduser().resolve()
    args.profile = args.profile.expanduser().resolve()
    paths = [args.output, args.errors]
    if args.urls:
        paths.append(args.urls.resolve())
    if len(set(paths)) != len(paths):
        parser.error("URL input, output, and error files must have different paths")
    try:
        from cloakbrowser import launch_persistent_context
        from playwright.sync_api import Error, TimeoutError
    except ImportError:
        parser.exit(1, "Install dependencies: python -m pip install -r requirements.txt\n")
    try:
        if args.browse:
            return browse(args, launch_persistent_context, Error)
        return collect(args, launch_persistent_context, Error, TimeoutError)
    except (KeyboardInterrupt, EOFError):
        print("Stopped. Use --resume to continue saved progress.")
        return 130
    except (OSError, ValueError, Error) as error:
        print(f"Error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
