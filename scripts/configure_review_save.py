#!/usr/bin/env python3
"""Set the public save-service origin and matching report CSP permission."""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('service_url')
args = parser.parse_args()
url = urlsplit(args.service_url)
if (url.scheme != 'https' or not url.hostname or url.path not in ('', '/')
        or url.query or url.fragment or url.username or url.password
        or not re.fullmatch(r'[A-Za-z0-9.-]+', url.hostname)):
    parser.error('Supply a plain HTTPS service origin without a path or credentials.')
origin = f'https://{url.netloc}'
root = Path(__file__).resolve().parents[1]
page = root / 'docs/index.html'
html = page.read_text()
html, count = re.subn(r"connect-src [^;]+;", f"connect-src 'self' https://api.github.com https://raw.githubusercontent.com {origin};", html)
if count != 1:
    raise SystemExit('Expected exactly one connect-src policy; no files changed.')
page.write_text(html)
(root / 'docs/save-config.json').write_text(json.dumps({'service_url': origin}, indent=2) + '\n')
print(f'Configured direct saving through {origin}; no credentials were written.')
