#!/bin/sh
# Build the two example sitemaps and show the bad-input check.
# The bad-urls check exits 1 on purpose, so the script keeps going
# and exits 0 either way.
set -e
cd "$(dirname "$0")/.."
python3 src/sitemap_generator.py --urls-file examples/urls.txt --changefreq weekly -o examples/sitemap-from-urls.xml
python3 src/sitemap_generator.py --dir examples/site --base-url https://example.com -o examples/sitemap-from-folder.xml
python3 src/sitemap_generator.py --urls-file examples/bad-urls.txt -o examples/sitemap-from-bad-urls.xml || true
