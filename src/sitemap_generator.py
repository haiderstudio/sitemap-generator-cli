#!/usr/bin/env python3
"""Generate a sitemap.xml from a URL list or a local folder of HTML files.

One job only: read pages (a plain-text file of URLs, URLs on the
command line, or a folder of .html/.htm files under a base URL) and
write a valid sitemap.xml. It never edits the input pages, never
fetches a live site, and needs no network at all.

Exit codes: 0 = sitemap written, 1 = a problem in the input (bad URL,
duplicate URL, no pages, more than 50,000 URLs), 2 = a usage error
(bad flags, missing input file, output cannot be written).

Standard library only.
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

VERSION = "1.0.0"

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
MAX_URLS = 50000  # the sitemap protocol limit per file
MAX_LOC_LENGTH = 2048  # the sitemap protocol limit per URL

CHANGEFREQS = (
    "always",
    "hourly",
    "daily",
    "weekly",
    "monthly",
    "yearly",
    "never",
)

# A loc must be an absolute http(s) URL with a host. Fragments are
# not allowed in a sitemap loc, so a URL with one is a problem.
PROBLEM_NO_SCHEME = "no http:// or https:// scheme"
PROBLEM_NO_HOST = "no host name"
PROBLEM_SPACES = "contains a space"
PROBLEM_FRAGMENT = "has a #fragment (not allowed in a sitemap loc)"
PROBLEM_TOO_LONG = "longer than 2048 characters"
PROBLEM_DUPLICATE = "duplicate URL"


def check_url(url):
    """Return a list of problems with one URL (empty list = fine)."""
    problems = []
    if " " in url or "\t" in url:
        problems.append(PROBLEM_SPACES)
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        problems.append(PROBLEM_NO_SCHEME)
    if not parsed.netloc:
        problems.append(PROBLEM_NO_HOST)
    if parsed.fragment:
        problems.append(PROBLEM_FRAGMENT)
    if len(url) > MAX_LOC_LENGTH:
        problems.append(PROBLEM_TOO_LONG)
    return problems


def collect_from_urls(text_lines, source_name):
    """Turn lines of a URL list into (pages, problems).

    A page is a dict with a "loc" key. Blank lines and lines starting
    with "#" are comments and are skipped. Each problem names the
    source and the line number.
    """
    pages = []
    problems = []
    for number, raw in enumerate(text_lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for problem in check_url(line):
            problems.append(f"{source_name}: line {number}: {line}: {problem}")
        pages.append({"loc": line})
    return pages, problems


def collect_from_dir(folder, base_url):
    """Walk a folder of HTML files into (pages, problems).

    index.html maps to the base URL itself; every other .html/.htm
    file maps to the base URL plus its path under the folder, keeping
    the .html ending. lastmod comes from the file's own date.
    Files that are not .html/.htm are skipped.
    """
    pages = []
    problems = []
    base = base_url.rstrip("/")
    files = sorted(
        p
        for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in (".html", ".htm")
    )
    for path in files:
        relative = path.relative_to(folder).as_posix()
        if path.name.lower() == "index.html" and path.parent == folder:
            loc = base + "/"
        else:
            loc = base + "/" + relative
        mtime = datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).date()
        pages.append({"loc": loc, "lastmod": mtime.isoformat()})
    return pages, problems


def build_sitemap(pages, changefreq=None, priority=None, lastmod=None):
    """Build the sitemap.xml text for a list of pages."""
    ET.register_namespace("", SITEMAP_NS)
    root = ET.Element(f"{{{SITEMAP_NS}}}urlset")
    for page in pages:
        url_el = ET.SubElement(root, f"{{{SITEMAP_NS}}}url")
        loc_el = ET.SubElement(url_el, f"{{{SITEMAP_NS}}}loc")
        loc_el.text = page["loc"]
        page_lastmod = page.get("lastmod") or lastmod
        if page_lastmod:
            lastmod_el = ET.SubElement(url_el, f"{{{SITEMAP_NS}}}lastmod")
            lastmod_el.text = page_lastmod
        if changefreq:
            freq_el = ET.SubElement(url_el, f"{{{SITEMAP_NS}}}changefreq")
            freq_el.text = changefreq
        if priority is not None:
            prio_el = ET.SubElement(url_el, f"{{{SITEMAP_NS}}}priority")
            prio_el.text = f"{priority:.1f}"
    ET.indent(root)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        + ET.tostring(root, encoding="unicode")
        + "\n"
    )


def valid_date(text):
    """Parse a YYYY-MM-DD date, or return None when it is not one."""
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    return parsed.isoformat()


def build_parser():
    parser = argparse.ArgumentParser(
        prog="sitemap_generator",
        description=(
            "Generate a sitemap.xml from a URL list or a folder of "
            "HTML files."
        ),
    )
    parser.add_argument(
        "urls",
        nargs="*",
        metavar="URL",
        help="one or more page URLs to include",
    )
    parser.add_argument(
        "--urls-file",
        metavar="FILE",
        help="text file with one URL per line (# starts a comment)",
    )
    parser.add_argument(
        "--dir",
        dest="directory",
        metavar="FOLDER",
        help="folder of .html/.htm files to turn into URLs",
    )
    parser.add_argument(
        "--base-url",
        metavar="URL",
        help="site address for --dir (needed with --dir)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="with --dir, stay in the top folder only",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        default="sitemap.xml",
        help="where to write the sitemap (default: sitemap.xml)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="print the sitemap instead of writing a file",
    )
    parser.add_argument(
        "--changefreq",
        metavar="FREQ",
        choices=CHANGEFREQS,
        help="changefreq for every URL: " + ", ".join(CHANGEFREQS),
    )
    parser.add_argument(
        "--priority",
        metavar="N",
        type=float,
        help="priority for every URL, 0.0 to 1.0",
    )
    parser.add_argument(
        "--lastmod",
        metavar="YYYY-MM-DD",
        help="lastmod date for every URL (folder mode uses file dates)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as JSON on stderr instead of plain text",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    problems = []

    # Flag values that are not usable are usage errors (exit 2).
    if args.priority is not None and not 0.0 <= args.priority <= 1.0:
        parser.error("--priority must be between 0.0 and 1.0")
    lastmod = None
    if args.lastmod is not None:
        lastmod = valid_date(args.lastmod)
        if lastmod is None:
            parser.error("--lastmod must be a real date, YYYY-MM-DD")
    if args.directory is not None and args.base_url is None:
        parser.error("--dir needs --base-url")
    if args.base_url is not None:
        for problem in check_url(args.base_url):
            parser.error(f"--base-url is not a usable site address: {problem}")

    pages = []

    if args.urls:
        new_pages, new_problems = collect_from_urls(args.urls, "<command line>")
        pages.extend(new_pages)
        problems.extend(new_problems)

    if args.urls_file:
        try:
            text = Path(args.urls_file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            parser.error(f"cannot read {args.urls_file}: {exc}")
        new_pages, new_problems = collect_from_urls(
            text.splitlines(), args.urls_file
        )
        pages.extend(new_pages)
        problems.extend(new_problems)

    if args.directory:
        folder = Path(args.directory)
        if not folder.is_dir():
            parser.error(f"{args.directory} is not a folder")
        if args.no_recursive:
            files = sorted(
                p
                for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() in (".html", ".htm")
            )
            base = args.base_url.rstrip("/")
            for path in files:
                if path.name.lower() == "index.html":
                    loc = base + "/"
                else:
                    loc = base + "/" + path.name
                mtime = datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).date()
                pages.append({"loc": loc, "lastmod": mtime.isoformat()})
        else:
            new_pages, new_problems = collect_from_dir(folder, args.base_url)
            pages.extend(new_pages)
            problems.extend(new_problems)

    # Duplicates are checked once, across every input, so the same
    # URL given twice (even from two different inputs) is one problem.
    seen = set()
    for page in pages:
        if page["loc"] in seen:
            problems.append(f"{page['loc']}: {PROBLEM_DUPLICATE}")
        seen.add(page["loc"])

    if not pages and not problems:
        problems.append("no pages given: pass URLs, --urls-file, or --dir")
    if len(pages) > MAX_URLS:
        problems.append(
            f"{len(pages)} URLs is more than the {MAX_URLS} a sitemap may hold"
        )

    if problems:
        report = "\n".join(problems)
        summary = f"{len(problems)} problem(s), no sitemap written"
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "problems": problems,
                        "urls": len(pages),
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
        else:
            print(report, file=sys.stderr)
            print(summary, file=sys.stderr)
        return 1

    xml_text = build_sitemap(
        pages,
        changefreq=args.changefreq,
        priority=args.priority,
        lastmod=lastmod,
    )

    if args.stdout:
        print(xml_text, end="")
    else:
        try:
            Path(args.output).write_text(xml_text, encoding="utf-8")
        except OSError as exc:
            parser.error(f"cannot write {args.output}: {exc}")

    summary = f"OK — wrote {len(pages)} url(s) to {args.output}"
    if args.stdout:
        summary = f"OK — {len(pages)} url(s)"
    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "urls": len(pages),
                    "output": None if args.stdout else args.output,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
    elif args.stdout:
        # The XML itself is on stdout, so the summary goes to stderr
        # to keep stdout parseable as XML.
        print(summary, file=sys.stderr)
    else:
        print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
