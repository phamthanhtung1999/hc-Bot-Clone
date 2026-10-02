import unittest
from unittest import mock

from kbsync.chunks import chunks_for_tokens
from kbsync.cleaner import Doc
from kbsync.delta import RemoteFile, build_plan
from kbsync.scraper import ZendeskClient
from tests.fakes import FakeResponse, FakeSession


class ScraperTest(unittest.TestCase):
    def test_paginates_and_skips_drafts(self):
        session = FakeSession()
        arts = list(ZendeskClient("https://help.example", session=session).iter_articles())
        self.assertEqual([a.id for a in arts], [55906396437523, 360016178374])
        self.assertEqual(len(session.calls), 2)

    def test_limit_stops_early(self):
        session = FakeSession()
        arts = list(ZendeskClient("https://help.example", session=session).iter_articles(limit=1))
        self.assertEqual(len(arts), 1)
        self.assertEqual(len(session.calls), 1)

    @mock.patch("kbsync.scraper.time.sleep")
    def test_retries_rate_limit(self, sleep):
        session = FakeSession(errors=[FakeResponse(status=429, headers={"Retry-After": "1"})])
        arts = list(ZendeskClient("https://help.example", session=session).iter_articles())
        self.assertEqual(len(arts), 2)
        sleep.assert_called_once_with(1.0)


def doc(aid, content="x"):
    return Doc(article_id=aid, filename=f"{aid}.md", url="u", title="t", updated_at="", content=content)


class DeltaTest(unittest.TestCase):
    def test_classification(self):
        same, changed, new = doc("1", "a"), doc("2", "b-new"), doc("3", "c")
        remote = [
            RemoteFile("f1", "1", same.content_hash),
            RemoteFile("f2", "2", doc("2", "b-old").content_hash),
            RemoteFile("f9", "9", "zzz"),  # article removed upstream
        ]
        plan = build_plan([same, changed, new], remote)
        self.assertEqual(plan.counts(), {"added": 1, "updated": 1, "skipped": 1, "stale": 1})
        self.assertEqual(plan.updated[0][1][0].file_id, "f2")

    def test_failed_or_duplicate_copies_are_reuploaded(self):
        d = doc("1", "a")
        failed = build_plan([d], [RemoteFile("f1", "1", d.content_hash, status="failed")])
        dupes = build_plan([d], [RemoteFile("f1", "1", d.content_hash), RemoteFile("f2", "1", d.content_hash)])
        self.assertEqual(len(failed.updated), 1)
        self.assertEqual(len(dupes.updated[0][1]), 2)


class ChunkTest(unittest.TestCase):
    def test_static_window_math(self):
        self.assertEqual(chunks_for_tokens(0, 800, 400), 0)
        self.assertEqual(chunks_for_tokens(800, 800, 400), 1)
        self.assertEqual(chunks_for_tokens(801, 800, 400), 2)
        self.assertEqual(chunks_for_tokens(2000, 1200, 200), 2)
        self.assertEqual(chunks_for_tokens(2201, 1200, 200), 3)


if __name__ == "__main__":
    unittest.main()
