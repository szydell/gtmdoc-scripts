#!/usr/bin/env python3
"""Mirror https://fis-gtm.sourceforge.io/ into ../gtmdoc for mumps.pl."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import secrets
import time
import shutil
import subprocess  # nosec B404
import sys
from collections import Counter, deque
from pathlib import Path
from urllib.parse import unquote, urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser


DEFAULT_SOURCE = "https://fis-gtm.sourceforge.io/"
DEFAULT_TARGET_DOMAIN = "mumps.pl"

GITHUB_BASE = "https://github.com/szydell/gtmdoc/blob/master"

MANUALS = [
    ("Administration and Operations Guide", "manuals/ao/ao_screen.pdf"),
    ("Programmer's Guide", "manuals/pg/pg_screen.pdf"),
    ("Messages and Recovery Procedures Manual", "manuals/mr/mr_screen.pdf"),
]

SEED_PATHS = [
    "manuals/ao/index.html",
    "manuals/ao/toc.html",
    "manuals/pg/index.html",
    "manuals/pg/toc.html",
    "manuals/mr/index.html",
    "manuals/mr/toc.html",
]

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
]

INDEX_HTML = "index.html"
HTML_GLOB = "*.html"


def jitter(low: float, high: float) -> float:
    if high <= low:
        return low
    span = high - low
    # Use secrets to avoid Bandit B311 on random.* in CI policy.
    return low + (secrets.randbelow(1_000_000) / 1_000_000.0) * span


def run(cmd: list[str], cwd: Path | None = None, dry_run: bool = False, ignore_codes: list[int] | None = None) -> None:
    pretty = " ".join(cmd)
    print(f"$ {pretty}")
    if dry_run:
        return
    try:
        subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)  # nosec B603
    except subprocess.CalledProcessError as e:
        if ignore_codes and e.returncode in ignore_codes:
            print(f"Command returned ignored exit code {e.returncode}")
        else:
            raise


def run_returncode(cmd: list[str], cwd: Path | None = None, dry_run: bool = False) -> int:
    pretty = " ".join(cmd)
    print(f"$ {pretty}")
    if dry_run:
        return 0
    result = subprocess.run(  # nosec B603
        cmd,
        cwd=str(cwd) if cwd else None,
        check=False,
    )
    return result.returncode


def normalize_source_url(url: str, source_host: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    host = parsed.netloc or source_host
    if host != source_host:
        return None
    path = parsed.path or "/"
    normalized = f"https://{source_host}{path}"
    if parsed.query:
        normalized = f"{normalized}?{parsed.query}"
    normalized, _ = urldefrag(normalized)
    return normalized


def source_url_from_local_html(html_path: Path, mirror_dir: Path, source_host: str) -> str:
    rel = html_path.relative_to(mirror_dir).as_posix()
    if rel == INDEX_HTML:
        return f"https://{source_host}/"
    if rel.endswith(f"/{INDEX_HTML}"):
        return f"https://{source_host}/{rel[:-10]}"
    return f"https://{source_host}/{rel}"


def extract_links_from_html(raw: bytes, base_url: str, source_host: str) -> set[str]:
    links: set[str] = set()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="ignore")

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return links

    soup = BeautifulSoup(text, "html.parser")
    for tag in soup.find_all(True):
        for attr in ("href", "src"):
            value = tag.get(attr)
            if not value:
                continue
            if isinstance(value, list):
                continue
            absolute = urljoin(base_url, str(value))
            normalized = normalize_source_url(absolute, source_host)
            if normalized:
                links.add(normalized)
    return links


def collect_candidate_urls(mirror_dir: Path, source_host: str) -> set[str]:
    candidates: set[str] = set()
    for html in mirror_dir.rglob(HTML_GLOB):
        base_url = source_url_from_local_html(html, mirror_dir, source_host)
        try:
            raw = html.read_bytes()
        except OSError:
            continue
        candidates.update(extract_links_from_html(raw, base_url, source_host))
    return candidates


def local_path_for_url(url: str, mirror_dir: Path, content_type: str) -> Path | None:
    parsed = urlparse(url)
    raw_path = unquote(parsed.path or "/")
    if raw_path.endswith("/"):
        raw_path = f"{raw_path}{INDEX_HTML}"
    if raw_path == "/":
        raw_path = f"/{INDEX_HTML}"

    rel = raw_path.lstrip("/")
    if not rel:
        rel = INDEX_HTML

    rel_path = Path(rel)
    if any(part == ".." for part in rel_path.parts):
        return None

    if "text/html" in content_type and rel_path.suffix == "":
        rel_path = rel_path.with_suffix(".html")
    return mirror_dir / rel_path


def get_robot_parser(source_url: str) -> RobotFileParser | None:
    robots_url = urljoin(source_url, "/robots.txt")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception as exc:
        print(f"[!] Could not read robots.txt ({robots_url}): {exc}")
        return None
    return parser


def backoff_sleep(attempt: int) -> None:
    time.sleep((2 ** (attempt - 1)) + jitter(0.0, 1.0))


def classify_http_status(status_code: int, attempt: int, max_retries: int) -> str:
    if status_code == 403 and attempt < max_retries:
        return "retry"
    if status_code == 403:
        return "http_403"
    if status_code == 404:
        return "http_404"
    if status_code in {429, 500, 502, 503, 504} and attempt < max_retries:
        return "retry"
    return f"http_{status_code}"


def perform_request(session: object, url: str) -> object:
    return session.get(  # type: ignore[attr-defined]
        url,
        timeout=30,
        allow_redirects=True,
        impersonate="chrome",
        headers={"User-Agent": secrets.choice(USER_AGENTS)},
    )


def save_success_response(response: object, normalized: str, source_host: str, mirror_dir: Path) -> dict[str, object]:
    content_type = str(response.headers.get("content-type", "")).lower()  # type: ignore[attr-defined]
    output_path = local_path_for_url(normalized, mirror_dir, content_type)
    if output_path is None:
        return {"status": "invalid_path", "new_urls": set()}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)  # type: ignore[attr-defined]
    new_urls: set[str] = set()
    if "text/html" in content_type or output_path.suffix.lower() == ".html":
        new_urls = extract_links_from_html(response.content, normalized, source_host)  # type: ignore[attr-defined]
    return {
        "status": "success",
        "path": str(output_path.relative_to(mirror_dir)),
        "new_urls": new_urls,
    }


def process_queue_item(
    session: object,
    current_url: str,
    source_host: str,
    mirror_dir: Path,
    visited: set[str],
    robot_parser: RobotFileParser | None,
) -> tuple[str, str | None, list[str]]:
    normalized = normalize_source_url(current_url, source_host)
    if not normalized:
        return "skip", None, []
    if normalized in visited:
        return "skip", normalized, []

    visited.add(normalized)
    if robot_parser and not robot_parser.can_fetch("*", normalized):
        return "disallowed_by_robots", normalized, []

    result = fetch_one_url(session, normalized, source_host, mirror_dir)
    status = str(result.get("status", "error"))
    return status, normalized, iter_new_urls(result)


def fetch_one_url(
    session: object,
    url: str,
    source_host: str,
    mirror_dir: Path,
    max_retries: int = 3,
) -> dict[str, object]:
    from curl_cffi.requests import RequestsError

    for attempt in range(1, max_retries + 1):
        try:
            response = perform_request(session, url)
        except RequestsError as exc:
            if attempt == max_retries:
                return {"status": "error", "error": str(exc), "new_urls": set()}
            backoff_sleep(attempt)
            continue

        normalized = normalize_source_url(str(response.url), source_host)  # type: ignore[attr-defined]
        if not normalized:
            return {"status": "offsite", "new_urls": set()}

        status_code = int(response.status_code)  # type: ignore[attr-defined]
        if status_code == 200:
            return save_success_response(response, normalized, source_host, mirror_dir)

        status = classify_http_status(status_code, attempt, max_retries)
        if status != "retry":
            return {"status": status, "new_urls": set()}
        backoff_sleep(attempt)

    return {"status": "error", "new_urls": set()}


def iter_new_urls(result: dict[str, object]) -> list[str]:
    new_urls_obj = result.get("new_urls", set())
    if isinstance(new_urls_obj, set):
        return [u for u in new_urls_obj if isinstance(u, str)]
    if isinstance(new_urls_obj, list):
        return [u for u in new_urls_obj if isinstance(u, str)]
    return []


def push_discovered_urls(queue_ref: deque[str], visited_ref: set[str], discovered_urls: list[str]) -> None:
    for discovered in discovered_urls:
        if discovered not in visited_ref:
            queue_ref.append(discovered)


def track_samples(status: str, normalized: str, sample_403: list[str], sample_errors: list[str]) -> None:
    if status == "http_403" and len(sample_403) < 25:
        sample_403.append(normalized)
    if status in {"error", "offsite", "invalid_path"} and len(sample_errors) < 25:
        sample_errors.append(f"{normalized} ({status})")


def fetch_urls_with_retry(
    source_url: str,
    source_host: str,
    mirror_dir: Path,
    seed_urls: set[str],
    max_urls: int,
    dry_run: bool,
) -> dict[str, object]:
    queue = deque(sorted(seed_urls))
    visited: set[str] = set()
    status_counts: Counter[str] = Counter()
    sample_403: list[str] = []
    sample_errors: list[str] = []

    if dry_run:
        return {
            "attempted": 0,
            "status_counts": {},
            "sample_403": [],
            "sample_errors": [],
            "remaining_queue": len(queue),
        }

    robot_parser = get_robot_parser(source_url)
    from curl_cffi import requests as curl_requests

    with curl_requests.Session() as session:
        while queue and len(visited) < max_urls:
            current = queue.popleft()
            status, normalized, discovered_urls = process_queue_item(
                session=session,
                current_url=current,
                source_host=source_host,
                mirror_dir=mirror_dir,
                visited=visited,
                robot_parser=robot_parser,
            )

            if status == "skip":
                continue

            status_counts[status] += 1

            if normalized:
                track_samples(status, normalized, sample_403, sample_errors)
            push_discovered_urls(queue, visited, discovered_urls)

            time.sleep(jitter(0.35, 1.1))

    return {
        "attempted": len(visited),
        "status_counts": dict(status_counts),
        "sample_403": sample_403,
        "sample_errors": sample_errors,
        "remaining_queue": len(queue),
    }


def _wget_supports_option(option: str) -> bool:
    """Return True if the installed wget accepts the given option (wget2 specific flags)."""
    wget_bin = shutil.which("wget")
    if wget_bin is None:
        return False
    try:
        result = subprocess.run(  # nosec B603
            [wget_bin, option, "--help"],
            capture_output=True, text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def build_wget_base_cmd(mirror_dir: Path, source_host: str) -> list[str]:
    cmd = [
        "wget",
        "--mirror",
        "--recursive",
        "--level=inf",
        "--no-parent",
        "--page-requisites",
        "--convert-links",
        "--adjust-extension",
        "--no-host-directories",
        f"--domains={source_host}",
        "--execute",
        "robots=off",
        "--wait=5",          # 5 s between requests; --random-wait makes it 2.5–7.5 s
        "--random-wait",
        "--waitretry=120",   # wait up to 2 min before retrying a throttled URL
        "--directory-prefix",
        str(mirror_dir),
    ]
    # wget2 defaults to 5 parallel threads which triggers 429; force sequential.
    if _wget_supports_option("--max-threads=1"):
        cmd.append("--max-threads=1")
    return cmd


def run_wget_seed_with_retry(base_cmd: list[str], url: str, max_retries: int = 4) -> int:
    for attempt in range(1, max_retries + 1):
        rc = run_returncode(base_cmd + [url])
        if rc == 0:
            return 0
        if rc in {4, 8} and attempt < max_retries:
            # wget exit 8 covers HTTP 4xx/5xx including 429 (rate-limited).
            # Wait several minutes before re-running the entire seed crawl.
            sleep_secs = 120 * attempt + jitter(0.0, 30.0)
            print(f"wget exit {rc} on attempt {attempt}/{max_retries}; retrying in {sleep_secs:.0f}s")
            time.sleep(sleep_secs)
            continue
        return rc
    return 1


def wget_fallback_bootstrap(
    source_host: str,
    mirror_dir: Path,
    seed_urls: set[str],
) -> dict[str, object]:
    require_tool("wget")
    base_cmd = build_wget_base_cmd(mirror_dir, source_host)

    results: dict[str, int] = {}
    for seed in sorted(seed_urls):
        results[seed] = run_wget_seed_with_retry(base_cmd, seed)

    return {
        "attempted": len(seed_urls),
        "exit_codes": results,
        "all_success": all(code == 0 for code in results.values()),
    }

def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required tool: {name}")


def parse_pdf_info(pdf_path: Path) -> tuple[str, str]:
    """Extract version (e.g. V7.1-011) and publication date from a GT.M PDF."""
    if not pdf_path.exists():
        return "", ""
    pdftotext_bin = shutil.which("pdftotext")
    if pdftotext_bin is None:
        return "", ""
    try:
        result = subprocess.run(  # nosec B603
            [pdftotext_bin, "-f", "1", "-l", "2", str(pdf_path), "-"],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError:
        return "", ""

    version = ""
    date = ""
    lines = result.stdout.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not version and re.match(r"^V\d+\.\d+-\d+$", stripped):
            version = stripped
        if "Publication date" in stripped:
            rest = stripped.replace("Publication date", "").strip()
            if rest:
                date = rest
            elif i + 1 < len(lines):
                date = lines[i + 1].strip()
    return version, date


def generate_readme(target_repo: Path) -> None:
    """Write README.md to target_repo with current PDF revision info."""
    lines = [
        "# gtmdoc\n",
        "Track changes in the gt.m documentation\n",
        "Visit the site with documents mirror at https://mumps.pl\n",
    ]
    for name, rel_pdf in MANUALS:
        pdf_path = target_repo / rel_pdf
        version, date = parse_pdf_info(pdf_path)
        parts = [f"* [{name} PDF]({GITHUB_BASE}/{rel_pdf})"]
        if version or date:
            parts.append(f"Revision {version} {date}".strip())
        lines.append(" ".join(parts))

    readme_path = target_repo / "README.md"
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[*] Generated {readme_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mirror fis-gtm docs to local gtmdoc repo")
    parser.add_argument("--source-url", default=DEFAULT_SOURCE)
    parser.add_argument("--target-domain", default=DEFAULT_TARGET_DOMAIN)
    parser.add_argument(
        "--target-repo",
        default="../gtmdoc",
        help="Path to destination repo (default: ../gtmdoc)",
    )
    parser.add_argument(
        "--work-dir",
        default=".work",
        help="Temporary work directory (default: .work)",
    )
    parser.add_argument(
        "--seed-url",
        action="append",
        default=[],
        help="Additional URL to seed crawler (can be repeated)",
    )
    parser.add_argument("--keep-work-dir", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--branch", default="main")
    return parser.parse_args()


def rewrite_html(source_root: Path, source_host: str, target_domain: str) -> tuple[int, int]:
    html_paths = list(source_root.rglob(HTML_GLOB))
    changed = 0

    rules = [
        (f"https://{source_host}", f"https://{target_domain}"),
        (f"http://{source_host}", f"https://{target_domain}"),
        (f"//{source_host}", f"//{target_domain}"),
    ]

    for html in html_paths:
        raw = html.read_bytes()

        try:
            text = raw.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
            encoding = "latin-1"

        new_text = text
        for old, new in rules:
            new_text = new_text.replace(old, new)

        if new_text != text:
            html.write_text(new_text, encoding=encoding)
            changed += 1

    return len(html_paths), changed


def unrewrite_html(source_root: Path, source_host: str, target_domain: str) -> int:
    """Reverse a previous rewrite_html pass: restore target_domain links back to source_host.

    Called before a wget crawl so that wget finds the original fis-gtm URLs in cached
    HTML files (not the already-rewritten mumps.pl URLs) and can follow them correctly.
    """
    rules = [
        (f"https://{target_domain}", f"https://{source_host}"),
        (f"//{target_domain}", f"//{source_host}"),
    ]
    changed = 0
    for html in source_root.rglob(HTML_GLOB):
        raw = html.read_bytes()
        try:
            text = raw.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
            encoding = "latin-1"
        new_text = text
        for old, new in rules:
            new_text = new_text.replace(old, new)
        if new_text != text:
            html.write_text(new_text, encoding=encoding)
            changed += 1
    return changed


def grep_for_source(source_root: Path, source_host: str) -> int:
    count = 0
    for path in source_root.rglob(HTML_GLOB):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="latin-1")
        if source_host in text:
            count += 1
    return count


def mirror(args: argparse.Namespace, script_dir: Path) -> Path:
    source_url = args.source_url.rstrip("/") + "/"
    source_host = source_url.split("//", 1)[1].split("/", 1)[0]

    work_dir = (script_dir / args.work_dir).resolve()
    mirror_dir = work_dir / "mirror"

    # Removed cleaning of mirror_dir by default to keep delta updates working.
    if args.keep_work_dir or not args.dry_run:
        pass # Allow the directory to exist for caching in CI

    if not args.dry_run:
        mirror_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        return mirror_dir

    seed_urls = {
        source_url,
        *(urljoin(source_url, seed) for seed in SEED_PATHS),
        *(urljoin(source_url, seed) for seed in args.seed_url),
    }
    fetch_report = fetch_urls_with_retry(
        source_url=source_url,
        source_host=source_host,
        mirror_dir=mirror_dir,
        seed_urls=seed_urls,
        max_urls=6000,
        dry_run=args.dry_run,
    )

    index_path = mirror_dir / "index.html"
    crawl_successes = int(fetch_report.get("status_counts", {}).get("success", 0))  # type: ignore[union-attr]
    crawl_attempted = int(fetch_report.get("attempted", 0))  # type: ignore[arg-type]
    need_fallback = not index_path.exists() or (crawl_attempted > 0 and crawl_successes == 0)
    if need_fallback:
        if not index_path.exists():
            reason = "index.html missing"
        else:
            reason = f"crawler made 0 successful downloads ({crawl_attempted} attempted, all blocked)"
        print(f"Primary crawler ineffective ({reason}); trying wget fallback.")
        # Restore original source URLs in cached HTML files so wget can follow
        # fis-gtm.sourceforge.io links instead of the already-rewritten mumps.pl ones.
        reverted = unrewrite_html(mirror_dir, source_host, args.target_domain)
        if reverted:
            print(f"Reverted {reverted} HTML files to original source URLs before wget run.")
        fallback_report = wget_fallback_bootstrap(
            source_host=source_host,
            mirror_dir=mirror_dir,
            seed_urls=seed_urls,
        )
        fetch_report["wget_fallback"] = fallback_report

    report_path = work_dir / "mirror_fetch_report.json"
    report_path.write_text(json.dumps(fetch_report, indent=2, sort_keys=True), encoding="utf-8")
    status_counts = fetch_report.get("status_counts", {})
    print(f"Fetch summary: {status_counts}")
    sample_403 = fetch_report.get("sample_403", [])
    if isinstance(sample_403, list) and sample_403:
        print(f"Warning: {len(sample_403)} URLs ended with HTTP 403 (soft-fail).")

    total_html, changed_html = rewrite_html(mirror_dir, source_host, args.target_domain)
    stale_refs = grep_for_source(mirror_dir, source_host)
    print(f"Rewrote {changed_html}/{total_html} HTML files")
    if stale_refs:
        print(f"Warning: {stale_refs} HTML files still contain '{source_host}'")

    if not index_path.exists():
        raise SystemExit("Mirror failed: index.html missing in staging")

    return mirror_dir


def deploy(args: argparse.Namespace, source_dir: Path, script_dir: Path) -> Path:
    target_repo = (script_dir / args.target_repo).resolve()
    if not target_repo.exists():
        raise SystemExit(f"Target repo does not exist: {target_repo}")

    rsync_cmd = [
        "rsync",
        "-a",
        "--delete",
        "--exclude=.git/",
        "--exclude=README.md",
        f"{source_dir}/",
        f"{target_repo}/",
    ]
    run(rsync_cmd, dry_run=args.dry_run)
    return target_repo


def maybe_commit_and_push(args: argparse.Namespace, target_repo: Path) -> None:
    if not args.commit and not args.push:
        return

    timestamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    msg = f"Mirror fis-gtm docs ({timestamp})"

    run(["git", "status", "--short"], cwd=target_repo, dry_run=args.dry_run)

    if args.commit or args.push:
        git_bin = shutil.which("git")
        if git_bin is None:
            raise SystemExit("Missing required tool: git")
        # Ensure we are on the target branch (handles detached HEAD and empty repos).
        # git checkout -B creates the branch if it doesn't exist, or resets it to
        # current HEAD if it does — safe for both fresh clones and subsequent runs.
        run([git_bin, "checkout", "-B", args.branch], cwd=target_repo, dry_run=args.dry_run)
        run([git_bin, "add", "-A"], cwd=target_repo, dry_run=args.dry_run)
        diff_rc = run_returncode([git_bin, "diff", "--cached", "--quiet"], cwd=target_repo, dry_run=args.dry_run)
        if diff_rc == 0:
            print("No changes to commit.")
        else:
            run([git_bin, "commit", "-m", msg], cwd=target_repo, dry_run=args.dry_run)

    if args.push:
        git_bin = shutil.which("git")
        if git_bin is None:
            raise SystemExit("Missing required tool: git")
        # Use HEAD:branch so the push works regardless of local HEAD state.
        run([git_bin, "push", "origin", f"HEAD:{args.branch}"], cwd=target_repo, dry_run=args.dry_run)


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent

    for tool in ("rsync",):
        require_tool(tool)

    if args.commit or args.push:
        require_tool("git")

    mirror_dir = mirror(args, script_dir)
    target_repo = deploy(args, mirror_dir, script_dir)
    generate_readme(target_repo)
    maybe_commit_and_push(args, target_repo)

    print("Done.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}", file=sys.stderr)
        raise
