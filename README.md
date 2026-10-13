# URL HTML Collector

Open a single URL, a URL list, or browse manually in a visible CloakBrowser window and save rendered page bodies for later parsing and database import. This is a separate application: no Chrome extension or local HTTP server is required.

## Setup and run

Requires Python 3.10+.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item urls.example.txt urls.txt
```

On Linux, macOS, or WSL (Bash):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp urls.example.txt urls.txt
python collector.py --urls urls.txt --auto --resume
```

Edit `urls.txt` before running the collector. Windows and WSL require separate virtual environments. The visible browser needs a graphical desktop (for example, WSLg when using WSL). On Windows, activate the environment with `.venv\Scripts\Activate.ps1` to use the shorter `python collector.py` commands below.

## Input modes

Single page, without a URL file:

```powershell
.venv\Scripts\python collector.py --url "https://example.com/profile"
```

Manual browsing, without supplying any URL:

```powershell
.venv\Scripts\python collector.py --browse
```

Navigate to a page in the browser window opened by the application. Once its content is ready, return to the terminal and press Enter to capture it. You can navigate to another page and repeat; `q` finishes. With multiple tabs, the application asks which tab to capture. It does not automatically attach to an existing ordinary Chrome window or run inside a website. `--browse` always requires a capture prompt; `--ready-selector` can additionally check content readiness.

URL list: edit `urls.txt`, one HTTP/HTTPS URL per line. Blank lines and lines starting with `#` are ignored. Duplicate URLs are collected once per run.

```powershell
.venv\Scripts\python collector.py --urls urls.txt --resume
```

The positional form `collector.py urls.txt` remains supported. Choose one input mode per run. For single URLs and lists, inspect the browser, complete any verification, and wait for the intended content. In the terminal, press Enter to save, `s` to skip, or `q` to finish. Ctrl+C also stops the run.

## Automatic capture

Use `--auto` with a single URL or URL list to save without pressing Enter:

```bash
python collector.py --urls urls.txt --auto --resume
python collector.py --url "https://example.com/profile" --auto
```

This mode waits for DOM loading, a nonempty page body, and the absence of common visible Cloudflare challenge markers. After the `--settle` pause (default 1 second), it checks again and saves. If navigation or readiness times out, the URL is recorded as failed and the run continues without a prompt. It does not solve challenges itself. Challenge detection is a heuristic and can miss custom verification/error screens or incomplete data. `--auto` is intended for URL inputs; `--browse` retains manual page selection.

For more reliable automatic capture, combine `--auto` with a selector identifying the actual target data:

```bash
python collector.py --urls urls.txt --auto --ready-selector ".user-profile .statistics" --timeout 180 --resume
```

If the pages share a CSS selector identifying actual loaded content, supply it:

```powershell
.venv\Scripts\python collector.py urls.txt --ready-selector ".user-profile .statistics" --timeout 180 --resume
```

The example selector must be replaced with one from your target site. The application waits for that element to become visible, captures the page, and moves to the next URL. A generic selector such as `body` does not distinguish real content from a verification or error page. Required verification must still be completed manually in the browser while the script waits. A timeout is recorded as a failure and the run continues.

## Output and options

`output/pages.jsonl` contains one JSON record per successful capture: `requested_url`, final `url`, `title`, `body`, and UTC `captured_at`. HTML is preserved in the `body` field. Parse these records separately to extract structured data.

```powershell
.venv\Scripts\python collector.py urls.txt --output "D:\captures\pages.jsonl" --errors "D:\captures\errors.jsonl" --delay 3 --settle 2 --resume
```

- `--resume` skips requested URLs already in the chosen output. Failed or skipped URLs remain eligible on the next run. Without it, successful captures are appended again.
- `--delay` sets the pause between pages; `--settle` adds a pause before capture. Neither guarantees that all asynchronous content has loaded.
- `--profile` selects a dedicated browser profile. Cookies and sessions persist; do not share this folder or use your regular Chrome profile.
- Failures are appended to `output/errors.jsonl`. A run with page failures returns exit code 1.
- If interrupted during a write and the output's final record is incomplete, repair/remove that incomplete line before resuming. Run only one collector against a given output/profile at a time.

## Browser dependency and privacy

[CloakBrowser](https://github.com/CloakHQ/CloakBrowser) provides the browser integration and downloads a separate Chromium binary on first launch. Consult its README for available builds and license-key requirements, and its [binary license](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md) for terms. Its detection test results do not guarantee access to a given site. This application does not implement automatic Cloudflare/CAPTCHA solving.

Saved HTML, full URLs, error logs, and browser profiles may contain private information. Default output/profile directories and `urls.txt` are excluded from Git; exclude any custom paths inside your repository too. Use only for pages you are authorized to access and capture.

## License and attribution

The collector's own source code is available under the [MIT License](LICENSE). Browser integration is provided by [CloakBrowser](https://github.com/CloakHQ/CloakBrowser); its wrapper and compiled browser have separate terms. See [third-party dependencies](THIRD_PARTY.md). Browser binaries are downloaded separately and are not included in this repository.

