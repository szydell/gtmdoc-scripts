#!/usr/bin/env python3

"""
Migrates GT.M documentation HTML files to Markdown for Hugo (Hextra theme)
"""

import os
import re
import shutil
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString
import markdownify

# Mapping of DocBook admonition CSS classes to Hextra callout types
_ADMONITION_TYPES = {
    'note': 'info',
    'tip': 'default',
    'important': 'important',
    'warning': 'warning',
    'caution': 'warning',
}

def clean_html(soup: BeautifulSoup):
    """Remove navigation wrappers, scripts, and hidden elements to keep only the content."""
    # Remove nav headers and footers typical for DocBook
    for nav in soup.find_all('div', class_=['navheader', 'navfooter', 'breadcrumbs']):
        nav.decompose()
    for script in soup.find_all('script'):
        script.decompose()
    for iframe in soup.find_all('iframe'):
        iframe.decompose()
    # Remove DocBook "Return to top" links (class="returntotop") – Hextra provides scroll-to-top
    for rtt in soup.find_all('p', class_='returntotop'):
        rtt.decompose()
    for a in soup.find_all('a', string=lambda t: t and t.strip() == 'Return to top'):
        a.decompose()
    # Remove DocBook ToC – Hextra renders its own "On this page" sidebar navigation
    for toc in soup.find_all('div', class_='toc'):
        toc.decompose()
    
    # Try to find the main content div or return body
    content = (soup.find('div', class_='article')
               or soup.find('div', class_='sect1')
               or soup.find('div', class_='chapter')
               or soup.find('body'))
    return content

def transform_anchors(soup) -> dict:
    """Replace <a id="..."> anchor targets with unique markers; return marker→span map.

    Skips anchors inside heading tags – Hugo generates its own heading anchors.
    Only preserves anchors needed for within-page cross-references (e.g. footnotes).
    """
    markers = {}
    counter = 0
    _HEADING_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
    for a in soup.find_all('a', id=True):
        # Don't inject span inside headings – it pollutes heading text and TOC
        if a.parent and a.parent.name in _HEADING_TAGS:
            continue
        anchor_id = a['id']
        key = f'ZZZANCHOR{counter}ZZZ'
        counter += 1
        markers[key] = f'<span id="{anchor_id}"></span>'
        del a['id']
        a.insert_before(NavigableString(key))
    return markers


def transform_admonitions(soup) -> dict:
    """Replace DocBook admonition divs with unique markers; return marker→shortcode map."""
    markers = {}
    counter = 0
    for css_class, callout_type in _ADMONITION_TYPES.items():
        for div in soup.find_all('div', class_=css_class):
            # Content td: has text but no image
            content_td = div.find('td', attrs={'align': 'left', 'valign': 'top'})
            if not content_td:
                # Fallback: first td without an img child
                for td in div.find_all('td'):
                    if not td.find('img') and td.get_text(strip=True):
                        content_td = td
                        break
            if not content_td:
                continue
            inner_md = markdownify.markdownify(
                content_td.decode_contents().replace('\u00a0', ' '),
                heading_style='ATX',
                strip=['script', 'style'],
            ).strip()
            key = f'ZZZADMONITION{counter}ZZZ'
            counter += 1
            markers[key] = f'{{{{< callout type="{callout_type}" >}}}}\n{inner_md}\n{{{{< /callout >}}}}'
            div.replace_with(NavigableString(key))
    return markers


def rewrite_href(href: str) -> str:
    """Rewrite HTML file links to Hugo pretty URLs, leave PDFs and external links as-is."""
    if not href or href.startswith('http') or href.startswith('#') or href.endswith('.pdf'):
        return href
    if href.endswith('/index.html'):
        return href[:-len('index.html')]
    if href.endswith('.html'):
        return href[:-5] + '/'
    return href


def index_html_to_markdown(soup: BeautifulSoup) -> str:
    """Convert the GT.M index page HTML structure into clean Hugo Markdown."""
    page = soup.find("div", class_="page")
    if not page:
        return ""

    lines: list[str] = []

    def render_entry(entry_div) -> None:
        title_el = entry_div.find(class_="entry-title")
        badges_el = entry_div.find(class_="badges")
        if not title_el:
            return
        title = title_el.get_text(strip=True)
        if not title:
            return
        # Try to find an <a> directly in entry-title; otherwise use first HTML badge
        a = title_el.find("a")
        href = rewrite_href(a.get("href", "")) if a else ""
        if not href and badges_el:
            first_badge = badges_el.find("a")
            if first_badge:
                href = rewrite_href(first_badge.get("href", ""))
        line = f"- [{title}]({href})" if href else f"- {title}"
        if badges_el:
            for badge in badges_el.find_all("a"):
                badge_text = badge.get_text(strip=True)
                badge_href = rewrite_href(badge.get("href", ""))
                css_class = "gtm-pdf" if "pdf" in badge_text.lower() else "gtm-html"
                line += f' <a href="{badge_href}" class="{css_class}">{badge_text}</a>'
        lines.append(line)

    for section in page.find_all("section", recursive=False):
        header = section.find(["h2", "h3"])
        section_title = header.get_text(strip=True) if header else ""
        if header:
            lines.append(f"\n## {section_title}\n")
        is_release_notes = "release notes" in section_title.lower()
        details_count = 0
        for child in section.children:
            if not hasattr(child, 'name') or not child.name:
                continue
            if child.name == "div" and "entry" in (child.get("class") or []):
                render_entry(child)
            elif child.name == "details":
                summary = child.find("summary")
                summary_text = summary.get_text(strip=True) if summary else ""
                entries = child.find_all("div", class_="entry")
                if is_release_notes and details_count > 0:
                    # Older version groups: heading visible (→ TOC) + list collapsed via shortcode
                    if summary_text:
                        lines.append(f"\n### {summary_text}\n")
                    lines.append('{{< details title="Show releases" closed="true" >}}')
                    for entry in entries:
                        render_entry(entry)
                    lines.append("{{< /details >}}")
                else:
                    # Newest version group (or non-release-notes): keep expanded as ### heading
                    if summary_text:
                        lines.append(f"\n### {summary_text}\n")
                    for entry in entries:
                        render_entry(entry)
                details_count += 1
        lines.append("")

    return "\n".join(lines)


def rewrite_html_links(md: str, current_stem: str) -> str:
    """Rewrite ](foo.html) and ](foo.html#anchor) Markdown links to Hugo pretty URLs.

    - Same-page references (foo == current_stem): strip filename, keep only #anchor.
    - Sibling page references: rewrite to ../foo/ (or ../foo/#anchor).
    """
    def _replace(m):
        stem = m.group(1)          # filename without .html
        anchor = m.group(2) or ''  # '#anchor' or '' (group is None when absent)
        if stem == current_stem:
            # Same page – keep anchor only (or drop entirely if no anchor)
            return f"]({anchor})" if anchor else "]()"
        # Sibling page
        return f"](../{stem}/{anchor})"

    # Match ](stem.html) and ](stem.html#anchor)
    return re.sub(r'\]\(([^)#\s]+?)\.html(#[^)\s]*)?\)', _replace, md)


def process_html_file(file_path: Path, output_file: Path, is_root_index: bool = False):
    if not file_path.exists():
        return
    with open(file_path, "rb") as f:
        soup = BeautifulSoup(f, "html.parser")
    
    title_tag = soup.find("title")
    title = title_tag.text.strip() if title_tag else file_path.stem

    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    if is_root_index:
        md_content = index_html_to_markdown(soup)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"---\ntitle: \"{title}\"\n---\n\n")
            f.write(md_content)
        return
        
    content = clean_html(soup)
    
    # Frameset page (no body) - generate a landing page pointing to the main frame
    frameset = soup.find("frameset")
    if not content and frameset:
        frames = frameset.find_all("frame")
        # Pick the frame that's most likely the content (not toc/list)
        body_frame = next(
            (f for f in frames if f.get("name") in ("body", "content", "main")),
            frames[-1] if frames else None
        )
        src = body_frame.get("src", "titlepage") if body_frame else "titlepage"
        src_md = src.replace(".html", "")
        md_content = f"## {title}\n\nSee: [{src_md}]({src_md}/)\n"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"---\ntitle: \"{title}\"\ndescription: \"{title}\"\ntoc: false\n---\n\n")
            f.write(md_content)
        return

    if not content:
        return

    anchor_markers = transform_anchors(content)
    markers = transform_admonitions(content)
    md_content = markdownify.markdownify(str(content).replace('\u00a0', ' '), heading_style="ATX", strip=['script', 'style'])
    for key, shortcode in markers.items():
        md_content = md_content.replace(key, shortcode)
    for key, span in anchor_markers.items():
        md_content = md_content.replace(key, span)
    md_content = rewrite_html_links(md_content, file_path.stem)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"---\ntitle: \"{title}\"\ndescription: \"{title}\"\nsidebar:\n  hide: true\n---\n\n")
        f.write(md_content)

def traverse_and_convert(src_dir: Path, dest_dir: Path):
    if not src_dir.exists():
        return
        
    for root, dirs, files in os.walk(src_dir):
        root_path = Path(root)
        rel_path = root_path.relative_to(src_dir)
        target_dir = dest_dir / rel_path
        
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate _index.md for dirs without index.html so Hugo serves them
        if "index.html" not in files and rel_path != Path("."):
            auto_index = target_dir / "_index.md"
            if not auto_index.exists():
                section_title = rel_path.name.replace("-", " ").replace("_", " ").title()
                with open(auto_index, "w", encoding="utf-8") as f:
                    f.write(f"---\ntitle: \"{section_title}\"\ndescription: \"{section_title}\"\ntoc: false\n---\n")
        
        for file in files:
            if file.endswith(".html"):
                out_name = "_index.md" if file == "index.html" else f"{file[:-5]}.md"
                is_root = file == "index.html" and root_path == src_dir
                process_html_file(root_path / file, target_dir / out_name, is_root)
            elif file.endswith(('.pdf', '.png', '.jpg', '.gif', '.css', '.txt')):
                # Copy static assets directly
                shutil.copy2(root_path / file, target_dir / file)

def main():
    base_dir = Path(".work/mirror")
    out_dir = Path("site/content")
    
    if not base_dir.exists():
        print("[!] Mirror directory not found at .work/mirror")
        return

    print(f"[*] Starting migration from {base_dir} to {out_dir}")
    traverse_and_convert(base_dir, out_dir)
    print("[*] Migration completed!")

if __name__ == "__main__":
    main()
