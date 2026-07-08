"""
Block Island Triathlon — Rebuild the Live Site's Embedded Data
==================================================================
index.html is a single static file with the entire dataset embedded
inline, in a <script id="data-payload" type="application/json"> tag --
there's no server and nothing is fetched at runtime. All the Chart.js
setup and rendering logic lives in the plain <script> tag right below
that one, and reads from `DATA = JSON.parse(...)` at the top.

This script swaps in a freshly-built data_payload.json without touching
any of the HTML/CSS/JS around it -- useful for adding a new season's
results without hand-editing the page.

Usage:
    python 03_update_html_data.py index.html data_payload.json index_updated.html
"""
import sys
import re

HTML_IN = sys.argv[1] if len(sys.argv) > 1 else 'index.html'
JSON_IN = sys.argv[2] if len(sys.argv) > 2 else 'data_payload.json'
HTML_OUT = sys.argv[3] if len(sys.argv) > 3 else 'index.html'

with open(HTML_IN, 'r') as f:
    html = f.read()
with open(JSON_IN, 'r') as f:
    payload_json = f.read()

pattern = re.compile(
    r'(<script id="data-payload" type="application/json">)(.*?)(</script>)',
    re.S,
)
if not pattern.search(html):
    raise SystemExit('Could not find the data-payload <script> tag in ' + HTML_IN)

new_html = pattern.sub(lambda m: m.group(1) + payload_json + m.group(3), html, count=1)

with open(HTML_OUT, 'w') as f:
    f.write(new_html)

print(f"Wrote {HTML_OUT} with refreshed data ({len(payload_json)/1024:.0f} KB payload)")
