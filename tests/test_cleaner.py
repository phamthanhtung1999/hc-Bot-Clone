import json
import unittest

from kbsync.cleaner import html_to_markdown, render, slug_for
from kbsync.scraper import Article
from tests.fakes import FIXTURES


def weather_article() -> Article:
    raw = json.loads((FIXTURES / "articles_page1.json").read_text())["articles"][0]
    return Article.from_api(raw)


class CleanerTest(unittest.TestCase):
    def setUp(self):
        self.md = html_to_markdown(weather_article().body)

    def test_headings_are_atx(self):
        self.assertIn("\n## What You'll Need\n", self.md)
        self.assertIn("## How It Works", self.md)

    def test_in_page_anchor_links_still_resolve(self):
        self.assertIn("[What You'll Need](#WhatYoullNeed)", self.md)
        self.assertIn('<a id="WhatYoullNeed"></a>', self.md)

    def test_relative_and_absolute_links_preserved(self):
        self.assertIn("[Screen setup](/hc/en-us/articles/360016178374)", self.md)
        self.assertIn("(https://support.optisigns.com/hc/en-us/articles/360017964153)", self.md)

    def test_code_block_fenced_with_language(self):
        self.assertIn('```json\n{"location": "New_York", "forecast": true}\n```', self.md)

    def test_noise_removed(self):
        for junk in ("trackPageView", "Upgrade now", "<span", "style=", "data-list-item-id"):
            self.assertNotIn(junk, self.md)

    def test_callout_table_becomes_blockquote_and_real_table_kept(self):
        self.assertIn("> **IMPORTANT**", self.md)
        self.assertIn("| Plan | Radar |\n| --- | --- |", self.md)

    def test_media(self):
        self.assertIn("![Radar map](https://support.optisigns.com/hc/article_attachments/1/radar.png)", self.md)
        self.assertIn("(https://www.youtube.com/embed/abc123)", self.md)

    def test_no_runaway_blank_lines(self):
        self.assertNotIn("\n\n\n", self.md)


class RenderTest(unittest.TestCase):
    def test_filename_and_citation_lines(self):
        doc = render(weather_article())
        self.assertEqual(doc.filename, "55906396437523-How-to-Use-the-Weather-Radar-App.md")
        self.assertTrue(doc.content.startswith("# How to Use the Weather Radar App\n\nArticle URL: https://"))
        self.assertEqual(doc.content.count("Article URL: "), 2)

    def test_hash_is_stable_and_content_sensitive(self):
        a = weather_article()
        self.assertEqual(render(a).content_hash, render(a).content_hash)
        changed = Article(**{**a.__dict__, "body": a.body + "<p>new line</p>"})
        self.assertNotEqual(render(a).content_hash, render(changed).content_hash)

    def test_slug_fallback_when_url_odd(self):
        a = Article(id=7, title="Hello World / FAQ?", html_url="https://x/y", body="")
        self.assertEqual(slug_for(a), "7-Hello-World-FAQ")


if __name__ == "__main__":
    unittest.main()
