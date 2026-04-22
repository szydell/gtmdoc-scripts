#!/usr/bin/env python3

"""
Migrates GT.M documentation HTML files to Markdown for Hugo (Hextra theme)
"""

import os
import shutil
from pathlib import Path
from bs4 import BeautifulSoup
import markdownify

def clean_html(soup: BeautifulSoup):
    """Remove navigation wrappers, scripts, and hidden elements to keep only the content."""
    # Remove nav headers and footers typical for DocBook
    for nav in soup.find_all('div', class_=['navheader', 'navfooter', 'breadcrumbs']):
        nav.decompose()
    for script in soup.find_all('script'):
        script.decompose()
    for iframe in soup.find_all('iframe'):
        iframe.decompose()
    
    # Try to find the main content div or return body
    content = soup.find('div', class_='sect1') or soup.find('div', class_='chapter') or soup.find('body')
    return content

def process_html_file(file_path: Path, output_file: Path, is_root_index: bool = False):
    if not file_path.exists():
        return
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f, "html.parser")
    
    title_tag = soup.find("title")
    title = title_tag.text.strip() if title_tag else file_path.stem

    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Special handling for the main mirror homepage to preserve its CSS grid/flex layout
    if is_root_index:
        # Extract style and the main page div, skipping the body background
        style_tag = soup.find("style")
        style_content = style_tag.string if style_tag else ""
        # Provide stronger CSS scoping
        style_content = style_content.replace("body {", ".hextra-wrapper {")
        # Cancel Hextra prose margin-top on section headers
        style_content += "\n    .hextra-wrapper section > h2, .hextra-wrapper section > h3 { margin-top: 0 !important; color: #fff !important; font-size: 1rem !important; font-weight: 600 !important; }\n"
        
        page_content = soup.find("div", class_="page")
        html_str = str(page_content) if page_content else str(soup.body)
        
        # Strip the <header> block — title already appears in navbar
        from bs4 import BeautifulSoup as _BS
        _tmp = _BS(html_str, "html.parser")
        _hdr = _tmp.find("header")
        if _hdr:
            _hdr.decompose()
        html_str = str(_tmp)
        
        # Ensure consistent heading levels
        html_str = html_str.replace('<h3>GT.M Release Notes</h3>', '<h2>GT.M Release Notes</h2>')
        html_str = html_str.replace('<h3>Technical Bulletins</h3>', '<h2>Technical Bulletins</h2>')

        # Rewrite link extensions for Hugo Hextra routing
        html_str = html_str.replace('href="manuals/ao/index.html"', 'href="manuals/ao/"')
        html_str = html_str.replace('href="manuals/mr/index.html"', 'href="manuals/mr/"')
        html_str = html_str.replace('href="manuals/pg/index.html"', 'href="manuals/pg/"')
        html_str = html_str.replace('.html"', '/"')
        
        # Enclose in our CSS payload scope
        raw_html = f"<style>\n{style_content}\n</style>\n<div class=\"hextra-wrapper\">\n{html_str}\n</div>"
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"---\ntitle: \"{title}\"\ntoc: false\n---\n\n")
            f.write(raw_html)
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
            f.write(f"---\ntitle: \"{title}\"\ntoc: false\n---\n\n")
            f.write(md_content)
        return

    if not content:
        return
        
    md_content = markdownify.markdownify(str(content), heading_style="ATX", strip=['script', 'style'])
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"---\ntitle: \"{title}\"\nsidebar:\n  hide: true\n---\n\n")
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
                    f.write(f"---\ntitle: \"{section_title}\"\ntoc: false\n---\n")
        
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
