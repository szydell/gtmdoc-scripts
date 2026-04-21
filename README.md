# gtmdoc-scripts
Scripts used in mumps.pl to mirror gt.m documentation site

## Stack
Python + UV & bash  
S3 + CloudFront or Cloudflare Static Page

## Reboot Plan (fis-gtm -> mumps.pl)
1. Mirror upstream static site from `https://fis-gtm.sourceforge.io/` into local staging.
2. Rewrite hardcoded absolute links from `fis-gtm.sourceforge.io` to `mumps.pl` in HTML files.
3. Sync staging content into sibling repository `../gtmdoc` as ready-to-serve static site.
4. Validate that there are no stale upstream links left and that root pages exist.
5. Optionally commit and push to `origin/main`.

The current upstream site now publishes docs from:
- `manuals/`
- `releasenotes/`
- `bulletins/`

Older mirror directories (`books/`, `articles/`, etc.) should be replaced by sync (`rsync --delete`).

## Script
Main script: `sync_mirror.py`

### Requirements
- `uv`
- `wget`
- `rsync`
- `git` (optional, only for `--commit` / `--push`)

### Example
```bash
uv run python sync_mirror.py
```

### Typical production run
```bash
uv run python sync_mirror.py \
	--target-repo ../gtmdoc \
	--target-domain mumps.pl \
	--commit \
	--push
```

### Dry run
```bash
uv run python sync_mirror.py --dry-run
```

`uv run` is enough here; no manual `venv` setup is required.

## Notes
- Script protects `.git/` in `gtmdoc` during rsync.
- By default, script keeps `README.md` in `gtmdoc`.
- If upstream introduces new entry points outside homepage links, add them with `--seed-url`.