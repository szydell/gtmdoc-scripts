#!/usr/bin/env python3
"""Mirror https://fis-gtm.sourceforge.io/ into ../gtmdoc for mumps.pl."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path


DEFAULT_SOURCE = "https://fis-gtm.sourceforge.io/"
DEFAULT_TARGET_DOMAIN = "mumps.pl"


def run(cmd: list[str], cwd: Path | None = None, dry_run: bool = False) -> None:
    pretty = " ".join(cmd)
    print(f"$ {pretty}")
    if dry_run:
        return
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)  # nosec B603


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required tool: {name}")


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
    html_paths = list(source_root.rglob("*.html"))
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


def grep_for_source(source_root: Path, source_host: str) -> int:
    count = 0
    for path in source_root.rglob("*.html"):
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

    if mirror_dir.exists() and not args.keep_work_dir and not args.dry_run:
        shutil.rmtree(mirror_dir)

    if not args.dry_run:
        mirror_dir.mkdir(parents=True, exist_ok=True)

    wget_base = [
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
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (gtm-mirror-bot)",
        "--directory-prefix",
        str(mirror_dir),
    ]

    run(wget_base + [source_url], dry_run=args.dry_run)
    for seed in args.seed_url:
        run(wget_base + [seed], dry_run=args.dry_run)

    if args.dry_run:
        return mirror_dir

    total_html, changed_html = rewrite_html(mirror_dir, source_host, args.target_domain)
    stale_refs = grep_for_source(mirror_dir, source_host)
    print(f"Rewrote {changed_html}/{total_html} HTML files")
    if stale_refs:
        print(f"Warning: {stale_refs} HTML files still contain '{source_host}'")

    index_path = mirror_dir / "index.html"
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

    timestamp = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    msg = f"Mirror fis-gtm docs ({timestamp})"

    run(["git", "status", "--short"], cwd=target_repo, dry_run=args.dry_run)

    if args.commit or args.push:
        run(["git", "add", "-A"], cwd=target_repo, dry_run=args.dry_run)
        run(["git", "commit", "-m", msg], cwd=target_repo, dry_run=args.dry_run)

    if args.push:
        run(["git", "push", "origin", args.branch], cwd=target_repo, dry_run=args.dry_run)


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent

    for tool in ("wget", "rsync"):
        require_tool(tool)

    if args.commit or args.push:
        require_tool("git")

    mirror_dir = mirror(args, script_dir)
    target_repo = deploy(args, mirror_dir, script_dir)
    maybe_commit_and_push(args, target_repo)

    print("Done.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}", file=sys.stderr)
        raise
