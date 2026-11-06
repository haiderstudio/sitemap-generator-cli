# sitemap-generator-cli

Generate a sitemap.xml from a URL list or HTML folder, fail CI on bad input.

[![CI](https://github.com/haiderstudio/sitemap-generator-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/sitemap-generator-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`sitemap_generator` builds a valid `sitemap.xml` from pages you
already have, in one of three ways:

1. **A URL list** — a text file with one URL per line
   (`--urls-file`), or URLs right on the command line.
2. **A folder of HTML files** (`--dir` plus `--base-url`) — one
   URL per `.html`/`.htm` file. `index.html` in the top folder
   becomes the base URL itself; every other file becomes the base
   URL plus its path under the folder. The file's own date becomes
   its `lastmod`.
3. **Both at once** — URLs from the command line, a file, and a
   folder are all combined into one sitemap.

- It writes a standard sitemap (`loc`, plus `lastmod`,
  `changefreq` and `priority` when asked for) with the
  `http://www.sitemaps.org/schemas/sitemap/0.9` namespace, and
  prints `OK — wrote N url(s) to sitemap.xml`.
- Every URL is checked before anything is written: it must be an
  absolute `http://` or `https://` URL with a host, no spaces, no
  `#fragment`, no longer than 2048 characters, and no duplicates.
  A bad URL is reported with its file and line number. A sitemap
  holds at most 50,000 URLs, so more than that is a fail too.
- It exits 1 when any problem is found, so it can fail a CI run —
  and when it fails, no sitemap file is written at all.
- It is fully offline: it never fetches a live site, never crawls,
  sends nothing anywhere, and needs no API key.
- `--stdout` prints the sitemap instead of writing a file (the
  summary line goes to stderr, so stdout stays pure XML).
  `--changefreq`, `--priority` (0.0 to 1.0) and `--lastmod`
  (a real `YYYY-MM-DD` date) set the same value on every URL.
  `--json` prints the result as JSON on stderr.

## What it does NOT do

- It does not crawl a live site. If you need a sitemap from a
  site that is already online, that is a crawler's job, not this
  tool's.
- It does not check that a URL actually loads. It checks the
  shape of the URL, not whether the page answers.
- It does not edit your HTML files or your URL list. It only
  reads them and writes the one sitemap file you name.
- It does not split a sitemap into several files or write a
  sitemap index. One run makes one `sitemap.xml`, at most
  50,000 URLs.
- It does not guess a lastmod for a URL list. A URL list has no
  lastmod unless you pass `--lastmod`; folder mode reads the
  date from each file.

## Who it is for

Anyone with a small static site or a list of pages who needs a
plain `sitemap.xml` for search engines, without running a
crawler: a docs folder that should turn into a sitemap on every
build, a hand-kept list of page URLs that must stay valid, or a
team adding a CI step that fails the build when a page URL is
mistyped or listed twice. If the input is right, you get a
sitemap; if one URL is wrong, the report says exactly which
line, and nothing is written.

## How this differs from similar tools

The quoted GitHub search for the exact name,
`"sitemap-generator-cli"`, returns 11 results. The top one is
lgraubner/sitemap-generator-cli, JavaScript, 338 stars — it
creates a sitemap by **crawling a given site**. Next is
wp-cli/google-sitemap-generator-cli, 16 stars — a CLI for a
WordPress plugin. The only Python tool with the same name,
gbvkUtilities/sitemap-generator-cli, 0 stars, also crawls: you
hand it a live URL and it follows the site's links (and needs
extra packages to do it). A search for a local-folder
generator finds one result, a 0-star shell script that writes a
`.txt` list, not a sitemap.xml. The `sitemap-audit-skill`
(Day 4 in this same series) audits a sitemap that already
exists; generating one from local files is the other half of
the job, not an overlap.

This tool does a narrower job: a Python standard-library-only
CLI that takes a URL list or a local folder and writes a valid
sitemap.xml, checks every URL first, and exits 1 for CI when
the input is bad. No crawl, no network, no extra packages.

## Install

Python standard library only — no packages to download. Clone
the repo and run it in place:

```sh
git clone https://github.com/haiderstudio/sitemap-generator-cli.git
cd sitemap-generator-cli
```

Python 3.10 or newer.

## Usage

Build a sitemap from the example URL list:

```sh
python3 src/sitemap_generator.py --urls-file examples/urls.txt --changefreq weekly -o examples/sitemap-from-urls.xml
```

Real output:

```text
OK — wrote 3 url(s) to examples/sitemap-from-urls.xml
```

The file it writes (`examples/sitemap-from-urls.xml`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/</loc>
    <changefreq>weekly</changefreq>
  </url>
  <url>
    <loc>https://example.com/about.html</loc>
    <changefreq>weekly</changefreq>
  </url>
  <url>
    <loc>https://example.com/blog/first-post.html</loc>
    <changefreq>weekly</changefreq>
  </url>
</urlset>
```

Build a sitemap from the example folder:

```sh
python3 src/sitemap_generator.py --dir examples/site --base-url https://example.com -o examples/sitemap-from-folder.xml
```

Real output:

```text
OK — wrote 3 url(s) to examples/sitemap-from-folder.xml
```

The folder has `index.html`, `about.html` and
`blog/first-post.html` (a `style.css` is skipped — only HTML
files become URLs), so the sitemap holds
`https://example.com/`, `https://example.com/about.html` and
`https://example.com/blog/first-post.html`, each with a
`lastmod` from its file date. The same two commands, plus the
bad-input check below, are saved in `examples/sample-output.txt`
and run by `examples/run-example.sh`.

A bad input fails, and nothing is written:

```sh
python3 src/sitemap_generator.py --urls-file examples/bad-urls.txt -o examples/sitemap-from-bad-urls.xml
```

Real output:

```text
examples/bad-urls.txt: line 4: example.com/no-scheme: no http:// or https:// scheme
examples/bad-urls.txt: line 4: example.com/no-scheme: no host name
examples/bad-urls.txt: line 6: https://example.com/page#section: has a #fragment (not allowed in a sitemap loc)
https://example.com/about.html: duplicate URL
4 problem(s), no sitemap written
```

The command exits 1. The `about.html` line is a duplicate
because the file lists it twice; the file itself is unchanged.

## Examples

### 1. URLs on the command line, printed, not written

```sh
python3 src/sitemap_generator.py https://example.com/ https://example.com/about.html --lastmod 2026-11-06 --stdout
```

Real output (the summary line goes to stderr, so stdout is
pure XML):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/</loc>
    <lastmod>2026-11-06</lastmod>
  </url>
  <url>
    <loc>https://example.com/about.html</loc>
    <lastmod>2026-11-06</lastmod>
  </url>
</urlset>
```

The exit code is 0.

### 2. One changefreq and priority for every URL

```sh
python3 src/sitemap_generator.py --urls-file examples/urls.txt --changefreq daily --priority 0.9 --stdout
```

Real output (first URL shown; all three get the same values):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/</loc>
    <changefreq>daily</changefreq>
    <priority>0.9</priority>
  </url>
  ...
</urlset>
```

A `--priority` outside 0.0 to 1.0, a `--changefreq` that is
not one of `always hourly daily weekly monthly yearly never`,
or a `--lastmod` that is not a real date is a usage error and
exits 2.

### 3. A folder with a subfolder, top folder only

`examples/site` has a `blog/` subfolder. With
`--no-recursive` only the top folder is read:

```sh
python3 src/sitemap_generator.py --dir examples/site --base-url https://example.com --no-recursive --stdout
```

Real output (summary on stderr):

```text
OK — 1 url(s)
```

Only `index.html` is in the top folder, so only
`https://example.com/` is in the sitemap. Without
`--no-recursive` the same command writes all 3 URLs.

## How it is tested

```sh
python3 tests/test_sitemap_generator.py
```

52 tests, standard library `unittest` only. They cover URL
checking (scheme, host, spaces, fragments, the 2048-character
limit, duplicates across inputs), folder collection (index
mapping, nested files, non-HTML files skipped, file dates as
lastmod), sitemap building (output parses back as XML with the
right namespace, order kept, optional fields, escaping), the
command line (exit codes 0, 1 and 2, `--stdout`, `--json`,
`--version`, `--no-recursive`, the 50,000-URL limit, input
files unchanged), the bundled examples, and the repo hygiene
checks (standard-library imports only, no placeholder text, no
secrets, no absolute paths).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Small, focused
improvements are welcome. Run the tests before opening a pull
request.

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The idea — a
small generator for one sitemap job — follows the same pattern
as the other single-job tools in this series; no code was
copied from any other project. The 50,000-URL and 2048-character
limits come from the sitemap protocol itself
(sitemaps.org/protocol.html).
