#!/usr/bin/env python3
"""Test script for _clean_calibre_markers"""

import re
import os
import tempfile
import zipfile

# Read HTML from HTMLZ
input_path = '/home/neo/prj/sunny-narrator/tests/data/test_book.fb2'
with tempfile.TemporaryDirectory() as temp_dir:
    htmlz_path = f'{temp_dir}/output.htmlz'
    os.system(f'ebook-convert {input_path} {htmlz_path} 2>/dev/null')
    
    with zipfile.ZipFile(htmlz_path, 'r') as zf:
        for name in zf.namelist():
            if name.endswith('.html'):
                html = zf.read(name).decode('utf-8')
                
                # Full cleanup
                # Remove comments
                html = re.sub(r'<!--\s*\d+\s*-->', '', html)
                
                # Remove section markers (:::{...}::: inside <div> or <p>)
                html = re.sub(r'<[^>]*>:::\s*\{#calibre_link-\d+\s+\.calibre\d+\}\s*:::</[^>]*>', '', html, flags=re.DOTALL)
                html = re.sub(r'<[^>]*>:::\s*\{\.calibre\d+\}\s*:::</[^>]*>', '', html, flags=re.DOTALL)
                html = re.sub(r'<[^>]*>:::</[^>]*>', '', html, flags=re.DOTALL)
                html = re.sub(r':::', '', html)
                
                # Remove inline markers {#...} and {.class}
                html = re.sub(r'\{#[^}]+\}', '', html)
                html = re.sub(r'\{\.\w+\}', '', html)
                
                # Remove IDs and classes
                html = re.sub(r'\s+class\s*=\s*["\'][^"\']*calibre[^"\']*["\']', '', html, flags=re.IGNORECASE)
                html = re.sub(r'\s+id\s*=\s*["\'][^"\']*calibre_link[^"\']*["\']', '', html, flags=re.IGNORECASE)
                
                print('=== FINAL CLEANUP CHECK ===')
                remaining = []
                for line in html.split('\n'):
                    if ':::' in line or 'calibre' in line.lower():
                        remaining.append(line.strip()[:80])
                
                if remaining:
                    print(f'FOUND {len(remaining)} LINES WITH REMAINING PATTERNS')
                    for line in remaining[:10]:
                        print(f'  {line}')
                else:
                    print('All markers removed ✓')
                break
