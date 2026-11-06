#!/usr/bin/env python3
"""Tests for sitemap_generator. Standard library unittest only."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src" / "sitemap_generator.py"

sys.path.insert(0, str(ROOT / "src"))

import sitemap_generator as sg  # noqa: E402

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def run_cli(*args, cwd=None):
    """Run the CLI as a subprocess. Returns (exit code, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(SRC), *args],
        capture_output=True,
        text=True,
        cwd=cwd or str(ROOT),
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse_sitemap(text):
    """Parse sitemap XML text, return the list of url dicts."""
    root = ET.fromstring(text)
    assert root.tag == NS + "urlset"
    urls = []
    for url_el in root.findall(NS + "url"):
        entry = {}
        for child in url_el:
            entry[child.tag[len(NS):]] = child.text
        urls.append(entry)
    return urls


class TestCheckUrl(unittest.TestCase):
    def test_good_urls_pass(self):
        for url in [
            "https://example.com/",
            "http://example.com/about.html",
            "https://example.com/blog/first-post.html?ref=home",
            "https://sub.example.co.uk/a/b/c",
        ]:
            self.assertEqual(sg.check_url(url), [], url)

    def test_no_scheme(self):
        problems = sg.check_url("example.com/about")
        self.assertIn(sg.PROBLEM_NO_SCHEME, problems)

    def test_ftp_scheme(self):
        problems = sg.check_url("ftp://example.com/file")
        self.assertIn(sg.PROBLEM_NO_SCHEME, problems)

    def test_no_host(self):
        problems = sg.check_url("https:///about")
        self.assertIn(sg.PROBLEM_NO_HOST, problems)

    def test_space_in_url(self):
        problems = sg.check_url("https://example.com/my page.html")
        self.assertIn(sg.PROBLEM_SPACES, problems)

    def test_fragment(self):
        problems = sg.check_url("https://example.com/page#section")
        self.assertIn(sg.PROBLEM_FRAGMENT, problems)

    def test_too_long(self):
        problems = sg.check_url("https://example.com/" + "a" * 2040)
        self.assertIn(sg.PROBLEM_TOO_LONG, problems)

    def test_several_problems_at_once(self):
        problems = sg.check_url("example.com/my page#x")
        self.assertIn(sg.PROBLEM_NO_SCHEME, problems)
        self.assertIn(sg.PROBLEM_SPACES, problems)
        self.assertIn(sg.PROBLEM_FRAGMENT, problems)


class TestCollectFromUrls(unittest.TestCase):
    def test_comments_and_blanks_skipped(self):
        pages, problems = sg.collect_from_urls(
            [
                "# a comment",
                "",
                "   ",
                "https://example.com/",
                "https://example.com/about.html",
            ],
            "urls.txt",
        )
        self.assertEqual(problems, [])
        self.assertEqual(
            [p["loc"] for p in pages],
            ["https://example.com/", "https://example.com/about.html"],
        )

    def test_problem_names_file_and_line(self):
        _, problems = sg.collect_from_urls(
            ["https://example.com/", "example.com/bad"], "urls.txt"
        )
        self.assertEqual(len(problems), 2)
        self.assertTrue(problems[0].startswith("urls.txt: line 2: "))

    def test_empty_input(self):
        pages, problems = sg.collect_from_urls(["# only a comment"], "f")
        self.assertEqual(pages, [])
        self.assertEqual(problems, [])


class TestCollectFromDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.site = Path(self.tmp.name) / "site"
        (self.site / "blog").mkdir(parents=True)
        for rel in ["index.html", "about.html", "blog/post.html"]:
            (self.site / rel).write_text("<html></html>", encoding="utf-8")
        (self.site / "style.css").write_text("body {}", encoding="utf-8")
        (self.site / "photo.png").write_bytes(b"\x89PNG")
        fixed = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc).timestamp()
        for path in self.site.rglob("*"):
            if path.is_file():
                os.utime(path, (fixed, fixed))

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_maps_to_base_url(self):
        pages, problems = sg.collect_from_dir(
            self.site, "https://example.com"
        )
        self.assertEqual(problems, [])
        locs = [p["loc"] for p in pages]
        self.assertIn("https://example.com/", locs)
        self.assertIn("https://example.com/about.html", locs)
        self.assertIn("https://example.com/blog/post.html", locs)
        self.assertEqual(len(locs), 3)  # css and png are skipped

    def test_lastmod_comes_from_file_date(self):
        pages, _ = sg.collect_from_dir(self.site, "https://example.com")
        for page in pages:
            self.assertEqual(page["lastmod"], "2026-11-06")

    def test_base_url_trailing_slash_is_tolerated(self):
        pages, _ = sg.collect_from_dir(self.site, "https://example.com/")
        self.assertIn("https://example.com/", [p["loc"] for p in pages])
        self.assertNotIn(
            "https://example.com//about.html", [p["loc"] for p in pages]
        )

    def test_nested_index_keeps_its_path(self):
        (self.site / "blog" / "index.html").write_text(
            "<html></html>", encoding="utf-8"
        )
        pages, _ = sg.collect_from_dir(self.site, "https://example.com")
        self.assertIn(
            "https://example.com/blog/index.html", [p["loc"] for p in pages]
        )


class TestBuildSitemap(unittest.TestCase):
    def test_output_parses_back(self):
        xml_text = sg.build_sitemap(
            [{"loc": "https://example.com/"},
             {"loc": "https://example.com/about.html"}]
        )
        self.assertTrue(xml_text.startswith('<?xml version="1.0"'))
        urls = parse_sitemap(xml_text)
        self.assertEqual(
            [u["loc"] for u in urls],
            ["https://example.com/", "https://example.com/about.html"],
        )

    def test_order_is_kept(self):
        xml_text = sg.build_sitemap(
            [
                {"loc": "https://example.com/z.html"},
                {"loc": "https://example.com/a.html"},
            ]
        )
        urls = parse_sitemap(xml_text)
        self.assertEqual(
            [u["loc"] for u in urls],
            ["https://example.com/z.html", "https://example.com/a.html"],
        )

    def test_lastmod_changefreq_priority(self):
        xml_text = sg.build_sitemap(
            [{"loc": "https://example.com/", "lastmod": "2026-11-06"}],
            changefreq="weekly",
            priority=0.8,
        )
        urls = parse_sitemap(xml_text)
        self.assertEqual(urls[0]["lastmod"], "2026-11-06")
        self.assertEqual(urls[0]["changefreq"], "weekly")
        self.assertEqual(urls[0]["priority"], "0.8")

    def test_no_optional_fields_when_not_given(self):
        xml_text = sg.build_sitemap([{"loc": "https://example.com/"}])
        urls = parse_sitemap(xml_text)
        self.assertEqual(set(urls[0]), {"loc"})

    def test_lastmod_flag_applies_to_all(self):
        xml_text = sg.build_sitemap(
            [{"loc": "https://example.com/"},
             {"loc": "https://example.com/a.html"}],
            lastmod="2026-01-15",
        )
        urls = parse_sitemap(xml_text)
        self.assertEqual(urls[0]["lastmod"], "2026-01-15")
        self.assertEqual(urls[1]["lastmod"], "2026-01-15")

    def test_page_lastmod_beats_flag(self):
        xml_text = sg.build_sitemap(
            [{"loc": "https://example.com/", "lastmod": "2026-11-06"}],
            lastmod="2026-01-15",
        )
        urls = parse_sitemap(xml_text)
        self.assertEqual(urls[0]["lastmod"], "2026-11-06")

    def test_special_chars_are_escaped(self):
        xml_text = sg.build_sitemap(
            [{"loc": "https://example.com/a?x=1&y=2"}]
        )
        urls = parse_sitemap(xml_text)
        self.assertEqual(urls[0]["loc"], "https://example.com/a?x=1&y=2")


class TestValidDate(unittest.TestCase):
    def test_good_date(self):
        self.assertEqual(sg.valid_date("2026-11-06"), "2026-11-06")

    def test_bad_shape(self):
        self.assertIsNone(sg.valid_date("06/11/2026"))
        self.assertIsNone(sg.valid_date("2026-11"))

    def test_impossible_date(self):
        self.assertIsNone(sg.valid_date("2026-02-30"))


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write_urls(self, name, text):
        path = self.work / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_positional_urls_exit_0(self):
        code, out, _ = run_cli(
            "https://example.com/",
            "https://example.com/about.html",
            "-o",
            str(self.work / "sitemap.xml"),
            cwd=str(self.work),
        )
        self.assertEqual(code, 0)
        self.assertIn("OK — wrote 2 url(s)", out)
        urls = parse_sitemap(
            (self.work / "sitemap.xml").read_text(encoding="utf-8")
        )
        self.assertEqual(len(urls), 2)

    def test_bad_url_exit_1_and_no_file(self):
        path = self.write_urls(
            "bad.txt",
            "https://example.com/\n"
            "example.com/no-scheme\n"
            "https://example.com/page#section\n",
        )
        code, _, err = run_cli(
            "--urls-file", str(path), "-o", str(self.work / "sitemap.xml")
        )
        self.assertEqual(code, 1)
        self.assertIn("no http:// or https:// scheme", err)
        self.assertIn("#fragment", err)
        self.assertIn("no sitemap written", err)
        self.assertFalse((self.work / "sitemap.xml").exists())

    def test_duplicate_url_exit_1(self):
        code, _, err = run_cli(
            "https://example.com/a.html",
            "https://example.com/a.html",
            "--stdout",
        )
        self.assertEqual(code, 1)
        self.assertIn("duplicate URL", err)

    def test_duplicate_across_inputs_exit_1(self):
        path = self.write_urls("u.txt", "https://example.com/a.html\n")
        code, _, err = run_cli(
            "https://example.com/a.html",
            "--urls-file",
            str(path),
            "--stdout",
        )
        self.assertEqual(code, 1)
        self.assertIn("duplicate URL", err)

    def test_no_input_exit_1(self):
        code, _, err = run_cli("--stdout")
        self.assertEqual(code, 1)
        self.assertIn("no pages given", err)

    def test_missing_urls_file_exit_2(self):
        code, _, err = run_cli(
            "--urls-file", str(self.work / "missing.txt"), "--stdout"
        )
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_dir_without_base_url_exit_2(self):
        code, _, err = run_cli("--dir", str(self.work), "--stdout")
        self.assertEqual(code, 2)
        self.assertIn("--base-url", err)

    def test_bad_changefreq_exit_2(self):
        code, _, err = run_cli(
            "https://example.com/", "--changefreq", "sometimes", "--stdout"
        )
        self.assertEqual(code, 2)

    def test_bad_priority_exit_2(self):
        code, _, err = run_cli(
            "https://example.com/", "--priority", "1.5", "--stdout"
        )
        self.assertEqual(code, 2)

    def test_bad_lastmod_exit_2(self):
        code, _, err = run_cli(
            "https://example.com/", "--lastmod", "2026-02-30", "--stdout"
        )
        self.assertEqual(code, 2)

    def test_bad_flag_exit_2(self):
        code, _, _ = run_cli("https://example.com/", "--nope")
        self.assertEqual(code, 2)

    def test_stdout_flag(self):
        code, out, err = run_cli("https://example.com/", "--stdout")
        self.assertEqual(code, 0)
        urls = parse_sitemap(out)
        self.assertEqual(urls[0]["loc"], "https://example.com/")
        self.assertIn("OK — 1 url(s)", err)

    def test_json_flag(self):
        code, _, err = run_cli(
            "https://example.com/", "--stdout", "--json"
        )
        self.assertEqual(code, 0)
        data = json.loads(err)
        self.assertTrue(data["ok"])
        self.assertEqual(data["urls"], 1)

    def test_json_flag_on_failure(self):
        code, _, err = run_cli("example.com/bad", "--stdout", "--json")
        self.assertEqual(code, 1)
        data = json.loads(err)
        self.assertFalse(data["ok"])
        self.assertTrue(data["problems"])

    def test_version(self):
        code, out, _ = run_cli("--version")
        self.assertEqual(code, 0)
        self.assertIn("1.0.0", out)

    def test_dir_mode(self):
        site = self.work / "site"
        (site / "blog").mkdir(parents=True)
        for rel in ["index.html", "about.html", "blog/post.html"]:
            (site / rel).write_text("<html></html>", encoding="utf-8")
        (site / "style.css").write_text("body {}", encoding="utf-8")
        code, out, _ = run_cli(
            "--dir",
            str(site),
            "--base-url",
            "https://example.com",
            "-o",
            str(self.work / "sitemap.xml"),
        )
        self.assertEqual(code, 0)
        self.assertIn("OK — wrote 3 url(s)", out)
        urls = parse_sitemap(
            (self.work / "sitemap.xml").read_text(encoding="utf-8")
        )
        self.assertEqual(
            sorted(u["loc"] for u in urls),
            [
                "https://example.com/",
                "https://example.com/about.html",
                "https://example.com/blog/post.html",
            ],
        )
        # lastmod comes from the file dates
        for url in urls:
            self.assertIn("lastmod", url)

    def test_dir_no_recursive(self):
        site = self.work / "site"
        (site / "blog").mkdir(parents=True)
        (site / "index.html").write_text("<html></html>", encoding="utf-8")
        (site / "blog" / "post.html").write_text(
            "<html></html>", encoding="utf-8"
        )
        code, out, err = run_cli(
            "--dir",
            str(site),
            "--base-url",
            "https://example.com",
            "--no-recursive",
            "--stdout",
        )
        self.assertEqual(code, 0)
        self.assertIn("OK — 1 url(s)", err)

    def test_missing_dir_exit_2(self):
        code, _, err = run_cli(
            "--dir",
            str(self.work / "nope"),
            "--base-url",
            "https://example.com",
            "--stdout",
        )
        self.assertEqual(code, 2)

    def test_input_file_is_not_changed(self):
        path = self.write_urls(
            "u.txt", "https://example.com/\nhttps://example.com/a.html\n"
        )
        before = path.read_bytes()
        code, _, _ = run_cli(
            "--urls-file", str(path), "-o", str(self.work / "sitemap.xml")
        )
        self.assertEqual(code, 0)
        self.assertEqual(path.read_bytes(), before)

    def test_over_50000_urls_exit_1(self):
        lines = [f"https://example.com/p{i}.html" for i in range(50001)]
        path = self.write_urls("many.txt", "\n".join(lines) + "\n")
        code, _, err = run_cli(
            "--urls-file", str(path), "-o", str(self.work / "sitemap.xml")
        )
        self.assertEqual(code, 1)
        self.assertIn("50000", err)
        self.assertFalse((self.work / "sitemap.xml").exists())


class TestExamples(unittest.TestCase):
    def test_sample_output_matches_fresh_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "repo"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(
                ".git", "__pycache__"
            ))
            proc = subprocess.run(
                ["sh", "examples/run-example.sh"],
                capture_output=True,
                text=True,
                cwd=str(copy),
            )
            self.assertEqual(proc.returncode, 0)
            fresh = (copy / "examples" / "sample-output.txt").read_text(
                encoding="utf-8"
            )
            committed = (
                ROOT / "examples" / "sample-output.txt"
            ).read_text(encoding="utf-8")
            self.assertEqual(fresh, committed)

    def test_committed_sitemaps_parse(self):
        for name in ("sitemap-from-urls.xml", "sitemap-from-folder.xml"):
            text = (ROOT / "examples" / name).read_text(encoding="utf-8")
            urls = parse_sitemap(text)
            self.assertEqual(len(urls), 3)
        folder_urls = parse_sitemap(
            (ROOT / "examples" / "sitemap-from-folder.xml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            sorted(u["loc"] for u in folder_urls),
            [
                "https://example.com/",
                "https://example.com/about.html",
                "https://example.com/blog/first-post.html",
            ],
        )
        for url in folder_urls:
            self.assertEqual(url["lastmod"], "2026-11-06")

    def test_readme_quoted_outputs(self):
        committed = (ROOT / "README.md").read_text(encoding="utf-8")
        # The README quotes the bad-urls run; those lines must match
        # the real output in sample-output.txt.
        sample = (ROOT / "examples" / "sample-output.txt").read_text(
            encoding="utf-8"
        )
        for line in [
            "OK — wrote 3 url(s) to examples/sitemap-from-urls.xml",
            "OK — wrote 3 url(s) to examples/sitemap-from-folder.xml",
            "4 problem(s), no sitemap written",
        ]:
            self.assertIn(line, sample)
            self.assertIn(line, committed)


class TestHygiene(unittest.TestCase):
    def test_stdlib_only(self):
        import ast

        allowed = {
            "argparse",
            "ast",
            "datetime",
            "json",
            "os",
            "shutil",
            "subprocess",
            "sys",
            "tempfile",
            "unittest",
            "urllib",
            "xml",
            "pathlib",
        }
        for path in [SRC, Path(__file__)]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(
                            alias.name.split(".")[0],
                            allowed | {"sitemap_generator"},
                            "%s imports %s" % (path, alias.name),
                        )
                elif isinstance(node, ast.ImportFrom):
                    self.assertIn(
                        (node.module or "").split(".")[0],
                        allowed | {"sitemap_generator"},
                        "%s imports %s" % (path, node.module),
                    )

    def test_no_placeholders_or_secrets(self):
        banned = ["TODO", "FIXME", "coming soon", "lorem", "API_KEY"]
        bad = []
        # The tests directory is excluded from this scan: the test
        # file itself names the banned words in its own check list.
        # The .git directory is excluded too: GitHub's checkout ships
        # sample hooks under .git/hooks/ that contain "TODO" (Day 21
        # CI failure), and those are git's own files, not this repo's.
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for word in banned:
                if word in text:
                    bad.append("%s: %s" % (path, word))
        self.assertEqual(bad, [])

    def test_no_absolute_paths(self):
        bad = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in ("/home/", "/tmp/", "C:\\"):
                if marker in text:
                    bad.append("%s: %s" % (path, marker))
        self.assertEqual(bad, [])

    def test_gitignore_lists_env_first(self):
        lines = (ROOT / ".gitignore").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(lines[0], ".env")


if __name__ == "__main__":
    unittest.main()
