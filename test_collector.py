import argparse
import tempfile
import signal
from pathlib import Path
import unittest
from unittest.mock import patch

from collector import append_record, browse, collect, completed_urls, read_urls


class BrowserError(Exception):
    pass


class BrowserTimeout(BrowserError):
    pass


class FakePage:
    def goto(self, url, **kwargs):
        self.url = url
        if url.endswith("/fail"):
            raise BrowserError("Navigation failed")

    def locator(self, selector):
        self.selector = selector
        return self

    @property
    def first(self):
        return self

    def wait_for(self, **kwargs):
        pass

    def wait_for_function(self, script, **kwargs):
        if self.url.endswith("/challenge"):
            raise BrowserTimeout("Challenge did not clear")

    def evaluate(self, script):
        return {"url": self.url, "title": "Profile", "body": "<body>Örnek</body>"}

    def wait_for_timeout(self, ms):
        pass

    def is_closed(self):
        return False


class FakeContext:
    def __init__(self):
        self.closed = False
        self.pages = []

    def new_page(self):
        page = FakePage()
        page.url = "https://example.com/current"
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True


class CollectorTests(unittest.TestCase):
    def test_limit_applies_after_resume_and_counts_failures(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            urls = root / "urls.txt"
            urls.write_text("https://example.com/done\nhttps://example.com/fail\nhttps://example.com/first\nhttps://example.com/later", encoding="utf-8")
            output = root / "pages.jsonl"
            append_record(output, {"requested_url": "https://example.com/done"})
            args = argparse.Namespace(urls=urls, output=output, errors=root / "errors.jsonl",
                                      profile=root / "profile", resume=True, ready_selector=".profile",
                                      timeout=1, settle=0, delay=0, limit=2)
            context = FakeContext()
            self.assertEqual(collect(args, lambda *a, **kw: context, BrowserError, BrowserTimeout), 1)
            self.assertEqual(completed_urls(output), {"https://example.com/done", "https://example.com/first"})
            self.assertNotIn("later", output.read_text())

    def test_interrupt_during_navigation_preserves_previous_record(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            urls = root / "urls.txt"
            urls.write_text("https://example.com/first\nhttps://example.com/second", encoding="utf-8")
            args = argparse.Namespace(urls=urls, output=root / "pages.jsonl", errors=root / "errors.jsonl",
                                      profile=root / "profile", resume=False, ready_selector=".profile",
                                      timeout=1, settle=0, delay=0)
            context = FakeContext()
            original = FakePage.goto
            def interrupt_second(page, url, **kwargs):
                if url.endswith("second"):
                    raise KeyboardInterrupt
                original(page, url, **kwargs)
            with patch.object(FakePage, "goto", interrupt_second):
                with self.assertRaises(KeyboardInterrupt):
                    collect(args, lambda *a, **kw: context, BrowserError, BrowserTimeout)
            self.assertTrue(context.closed)
            self.assertEqual(completed_urls(args.output), {"https://example.com/first"})

    def test_ctrl_c_during_write_finishes_record_and_restores_handler(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            output = Path(tmp) / "pages.jsonl"
            previous = signal.getsignal(signal.SIGINT)
            with patch("collector.os.fsync", side_effect=lambda fd: signal.raise_signal(signal.SIGINT)):
                with self.assertRaises(KeyboardInterrupt):
                    append_record(output, {"requested_url": "https://example.com/saved"})
            self.assertEqual(completed_urls(output), {"https://example.com/saved"})
            self.assertEqual(signal.getsignal(signal.SIGINT), previous)

    def test_auto_never_prompts_and_skips_blocked_page(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            urls = root / "urls.txt"
            urls.write_text("https://example.com/challenge\nhttps://example.com/first\nhttps://example.com/second", encoding="utf-8")
            args = argparse.Namespace(url=None, urls=urls, output=root / "pages.jsonl",
                                      errors=root / "errors.jsonl", resume=False, auto=True,
                                      profile=root / "profile", ready_selector=None,
                                      timeout=1, settle=0, delay=0)
            context = FakeContext()
            with patch("builtins.input", side_effect=AssertionError("Auto must not prompt")):
                self.assertEqual(collect(args, lambda *a, **kw: context, BrowserError, BrowserTimeout), 1)
            self.assertEqual(completed_urls(args.output), {"https://example.com/first", "https://example.com/second"})
            self.assertIn("Challenge did not clear", args.errors.read_text())
            self.assertTrue(context.closed)

    def test_browse_captures_current_page_without_navigation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            args = argparse.Namespace(output=root / "pages.jsonl", resume=True,
                                      profile=root / "profile", ready_selector=None, settle=0)
            context = FakeContext()
            with patch("builtins.input", side_effect=["", "", "q"]):
                self.assertEqual(browse(args, lambda *a, **kw: context, BrowserError), 0)
            self.assertTrue(context.closed)
            self.assertEqual(len(args.output.read_text(encoding="utf-8").splitlines()), 1)
            self.assertEqual(completed_urls(args.output), {"https://example.com/current"})

    def test_single_url_without_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            args = argparse.Namespace(url="https://example.com/one", urls=None, output=root / "pages.jsonl",
                                      errors=root / "errors.jsonl", resume=False, profile=root / "profile",
                                      ready_selector=".profile", timeout=1, settle=0, delay=0)
            context = FakeContext()
            self.assertEqual(collect(args, lambda *a, **kw: context, BrowserError, TimeoutError), 0)
            self.assertEqual(completed_urls(args.output), {args.url})

    def test_urls_validate_before_capture(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            path = Path(tmp) / "urls.txt"
            path.write_text("# comment\nhttps://example.com\nhttps://example.com\n", encoding="utf-8-sig")
            self.assertEqual(read_urls(path), ["https://example.com"])
            path.write_text("file:///private.txt", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_urls(path)

    def test_resume_and_failure_continue(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            urls = root / "urls.txt"
            urls.write_text("https://example.com/done\nhttps://example.com/fail\nhttps://example.com/new", encoding="utf-8")
            output = root / "output/pages.jsonl"
            append_record(output, {"requested_url": "https://example.com/done"})
            args = argparse.Namespace(urls=urls, output=output, errors=root / "errors.jsonl",
                                      profile=root / "profile", resume=True, ready_selector=".profile",
                                      timeout=1, settle=0, delay=0)
            context = FakeContext()
            self.assertEqual(collect(args, lambda *a, **kw: context, BrowserError, TimeoutError), 1)
            self.assertTrue(context.closed)
            self.assertEqual(completed_urls(output), {"https://example.com/done", "https://example.com/new"})
            self.assertIn("Örnek", output.read_text(encoding="utf-8"))
            self.assertIn("Navigation failed", args.errors.read_text())

    def test_damaged_output_is_not_silently_skipped(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            output = Path(tmp) / "pages.jsonl"
            output.write_text('{"requested_url":', encoding="utf-8")
            with self.assertRaises(ValueError):
                completed_urls(output)


if __name__ == "__main__":
    unittest.main()
