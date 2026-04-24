# Agent context — gtmdoc-scripts

This file provides context for AI coding assistants (GitHub Copilot, Cursor, Aider, Claude, etc.) working in this repository.

---

## Project goal

Mirror GT.M documentation from `https://fis-gtm.sourceforge.io/` and republish it as a modern static site (Hugo + Hextra theme) at `https://mumps.pl/`.

**Deployment**: Hugo builds to `site/public/`, which is synced to **AWS S3** and distributed via **CloudFront**. Built files are also committed to the sibling repo `../gtmdoc-mumps.pl` as a static source mirror. **GitHub Pages is NOT used.**

---

## Two-stage pipeline

### Stage 1 — `sync_mirror.py`
- Crawls upstream with `wget`, stores result in `.work/mirror/`
- Rewrites absolute links (`fis-gtm.sourceforge.io` → `mumps.pl`)
- Optionally rsyncs to sibling repo `../gtmdoc` and git-pushes
- Generates `../gtmdoc/README.md` with current PDF revision info (version + date) extracted via `pdftotext` (from `poppler-utils`)

### Stage 2 — `migrate.py`
- Reads `.work/mirror/`, writes Hugo Markdown to `site/content/`
- Root `index.html` → `site/content/_index.md` via `index_html_to_markdown()`
- Other HTML pages → Markdown via `markdownify`; framesets get a stub landing page
- **Manual directories** (those containing both `index.html` and `toc.html`) are handled specially — see *Manual (DocBook frameset) handling* below
- Static assets (PDF, PNG, CSS…) copied as-is
- Safe to re-run; all output is overwritten

Run both stages:
```bash
uv run python sync_mirror.py
uv run migrate.py
```

---

## Hugo project (`site/`)

| Setting | Value |
|---|---|
| Generator | Hugo Extended v0.152.2 |
| Theme | Hextra v0.12.2 (`github.com/imfing/hextra`) |
| Base URL | `https://szydell.github.io/gtmdoc-mumps.pl/` |
| Config | `site/hugo.toml` |

Key `hugo.toml` flags:
- `disablePathToLower = true` — preserves original file case in URLs
- `markup.goldmark.renderer.unsafe = true` — allows raw HTML in Markdown
- `params.search.type = "flexsearch"` — client-side search
- `[[menus.main]]` with `type = "theme-toggle"` — dark/light toggle in navbar

---

## Custom layouts & partials

| File | What it does |
|---|---|
| `site/layouts/index.html` | Home page: invisible sidebar placeholder (width balance) + TOC + content |
| `site/layouts/partials/navbar-title.html` | Renders logo as inline SVG via `readFile` so CSS `var()` works |
| `site/layouts/partials/custom/head-end.html` | Injects `<style>` into `<head>`: logo CSS variables + badge link styles + manuals-specific width/sidebar overrides |

---

## Logo & dark mode

Logo file: `site/static/images/gtmdoc.svg`
- Inline SVG (no `<img>` tag) — injected by `navbar-title.html` via `readFile`
- Uses `var(--gtm-bg)` and `var(--gtm-fg)` for fill/stroke — no hardcoded colors in SVG

CSS variables defined in `head-end.html`:
```css
:root               { --gtm-bg: #111111; --gtm-fg: #ffffff; }
.dark,
[data-theme="dark"] { --gtm-bg: #f3f3f3; --gtm-fg: #111111; }
@media (prefers-color-scheme: dark) { :root { --gtm-bg: #f3f3f3; --gtm-fg: #111111; } }
```

Hextra's JS toggles `.dark` on `<html>` — that's the primary mechanism. `prefers-color-scheme` is an OS-level fallback before JS runs.

---

## Badge links (HTML / PDF)

`migrate.py` emits raw `<a>` tags with classes `gtm-html` or `gtm-pdf`:
```html
<a href="..." class="gtm-html">HTML</a>
<a href="..." class="gtm-pdf">PDF</a>
```

Styled in `head-end.html` — outlined pill buttons, color-coded, dark-mode-aware.

---

## Manual (DocBook frameset) handling

Manual directories (`manuals/ao/`, `manuals/mr/`, `manuals/pg/`) contain a two-frame DocBook layout: `index.html` (frameset), `toc.html` (left nav), `titlepage.html` (cover), and per-chapter HTML files.

`migrate.py` detects a manual directory by the presence of **both** `toc.html` and `index.html`:

- `toc.html` — **skipped** (pure navigation, no output page)
- `index.html` — generates `_index.md` sourced from `titlepage.html` (real cover content), with `type: docs` + `cascade: width: full`; the `cascade` propagates Hextra's native full-width page mode to every subpage
- All other `.html` — generates `{stem}.md` with `type: docs` + `weight` derived from TOC link order via `parse_manual_toc()`

Key functions in `migrate.py`:
- `parse_manual_toc(toc_path)` — returns `{stem: weight}` dict in TOC reading order
- `process_html_file(..., cascade=dict)` — writes `cascade:` block into frontmatter

### Why `type: docs`?

Hextra's default `layouts/single.html` hardcodes `disableSidebar: true`. Manual subpages need the sidebar, so `type: docs` forces Hugo to use `layouts/docs/single.html` (sidebar visible).

### Width & sidebar for manuals

`head-end.html` injects additional CSS when `{{ eq .Section "manuals" }}`:
- `--hextra-max-content-width: 100%` — removes the 72rem content width cap
- `.hextra-sidebar-container` and `.hx\:md\:w-64` set to `20rem` (default: 16rem = 256px) — widens the left nav to reduce wrapping

Hextra's native `params.page.width` controls `--hextra-max-page-width` (page shell) and is set via `cascade: width: full` in `_index.md`.

---

## Front matter conventions

| Page type | Front matter |
|---|---|
| Root index (`_index.md`) | `title` only — layout handles sidebar placeholder |
| Subpages (converted HTML) | `title` + `sidebar:\n  hide: true` |
| Auto-generated section index | `title` + `toc: false` |
| Frameset stub | `title` + `toc: false` |
| Manual landing (`_index.md`) | `title` + `type: docs` + `cascade:\n  width: full` |
| Manual subpage | `title` + `type: docs` + `weight: <N>` |

---

## Python environment

- **Package manager: `uv` exclusively** — do not use `pip`, do not create `venv` manually
- Run scripts: `uv run migrate.py`, `uv run python sync_mirror.py`
- Dependencies declared in `pyproject.toml`: `beautifulsoup4`, `markdownify`
- **System dependency: `poppler-utils`** (`pdftotext`) — required by `sync_mirror.py` to extract version and date from PDFs; install with `sudo dnf install poppler-utils` (Fedora) or `sudo apt-get install poppler-utils` (Debian/Ubuntu/CI)

---

## What NOT to do

- Do not edit files under `site/content/` by hand — they are fully regenerated by `migrate.py`
- Do not add `<style>` blocks inside `gtmdoc.svg` — colors are controlled externally via CSS variables
- Do not use `sidebar.hide: true` on the root index front matter — the layout injects its own sidebar placeholder
- Do not use `pip` or `python -m venv`
- **Before writing any custom HTML/CSS**, always audit Hextra's built-in shortcodes first — Hextra v0.12.2 ships `details`, `callout`, `badge`, `tabs`, `cards`, `steps` and more. Check `~/.cache/hugo_cache/modules/filecache/modules/pkg/mod/github.com/imfing/hextra@*/layouts/_shortcodes/` or the [official Hextra shortcodes docs](https://imfing.github.io/hextra/docs/guide/shortcodes/).
