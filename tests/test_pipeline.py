import copy
import json
import tempfile
import unittest
from pathlib import Path

from kbsync.config import Settings
from kbsync.pipeline import run
from kbsync.scraper import ZendeskClient
from tests.fakes import FakeOpenAI, FakeSession


class PipelineTest(unittest.TestCase):
    """End-to-end daily-job behaviour against in-memory fakes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.settings = Settings(
            api_key="test", output_dir=str(root / "articles"), summary_path=str(root / "last_run.json")
        )
        self.client = FakeOpenAI()
        self.session = FakeSession()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, **kw):
        zd = ZendeskClient("https://help.example", session=self.session)
        return run(self.settings, client=self.client, zendesk=zd, **kw)

    def test_first_run_uploads_everything(self):
        s = self._run()
        self.assertEqual((s.added, s.updated, s.skipped), (2, 0, 0))
        self.assertEqual(s.files_embedded, 2)
        self.assertGreaterEqual(s.chunks_embedded, 2)
        self.assertEqual(len(self.client.vs_files), 2)
        files = sorted(p.name for p in Path(self.settings.output_dir).glob("*.md"))
        self.assertEqual(files[0], "360016178374-How-to-add-a-YouTube-video.md")
        saved = json.loads(Path(self.settings.summary_path).read_text())
        self.assertEqual(saved["added"], 2)
        chunking = next(iter(self.client.vs_files.values()))["chunking"]
        self.assertEqual(chunking["static"]["max_chunk_size_tokens"], 1200)

    def test_second_run_skips_unchanged(self):
        self._run()
        s = self._run()
        self.assertEqual((s.added, s.updated, s.skipped), (0, 0, 2))
        self.assertEqual(s.files_embedded, 0)
        self.assertEqual(len(self.client.vs_files), 2)

    def test_edited_article_replaces_old_file(self):
        self._run()
        old_ids = set(self.client.vs_files)
        pages = copy.deepcopy(self.session.pages)
        pages[1]["articles"][0]["body"] += "<p>Step 4: Publish to screen.</p>"
        self.session = FakeSession(pages=pages)

        s = self._run()
        self.assertEqual((s.added, s.updated, s.skipped), (0, 1, 1))
        self.assertEqual(len(self.client.vs_files), 2)  # old copy removed
        self.assertEqual(len(old_ids - set(self.client.vs_files)), 1)
        self.assertEqual(len(self.client.deleted_files), 1)

    def test_dry_run_uploads_nothing(self):
        s = self._run(dry_run=True)
        self.assertEqual(s.added, 2)
        self.assertEqual(self.client.vs_files, {})

    def test_store_found_by_name_on_next_run(self):
        a = self._run().vector_store_id
        b = self._run().vector_store_id
        self.assertEqual(a, b)
        self.assertEqual(len(self.client.stores), 1)


if __name__ == "__main__":
    unittest.main()
