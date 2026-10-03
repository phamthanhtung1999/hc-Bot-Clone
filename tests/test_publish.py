import unittest

from kbsync.publish import HISTORY, HISTORY_HEADER, publish_to_gist
from tests.fakes import FakeResponse


class FakeGitHub:
    def __init__(self, existing_history=None):
        files = {HISTORY: {"content": existing_history}} if existing_history else {}
        self.gist = {"files": files, "html_url": "https://gist.github.com/u/abc"}
        self.patched = None

    def get(self, url, headers=None, timeout=None):
        self.auth = headers["Authorization"]
        return FakeResponse(self.gist)

    def patch(self, url, headers=None, json=None, timeout=None):
        self.patched = json
        return FakeResponse(self.gist)


class PublishTest(unittest.TestCase):
    def test_writes_log_summary_and_starts_history(self):
        gh = FakeGitHub()
        url = publish_to_gist("abc", "tok", "line1\nline2", '{"added": 2}', "success",
                              {"scraped": 5, "added": 2, "updated": 0, "skipped": 3}, session=gh)
        self.assertEqual(url, "https://gist.github.com/u/abc")
        self.assertEqual(gh.auth, "Bearer tok")
        files = gh.patched["files"]
        self.assertEqual(files["run.log"]["content"], "line1\nline2")
        self.assertEqual(files["last_run.json"]["content"], '{"added": 2}')
        history = files[HISTORY]["content"]
        self.assertTrue(history.startswith(HISTORY_HEADER))
        self.assertIn("\tsuccess\t5\t2\t0\t3\t", history)

    def test_appends_to_existing_history(self):
        gh = FakeGitHub(existing_history=HISTORY_HEADER + "old-run\n")
        publish_to_gist("abc", "tok", "log", "{}", "failed", None, session=gh)
        lines = gh.patched["files"][HISTORY]["content"].splitlines()
        self.assertEqual(lines[1], "old-run")
        self.assertIn("\tfailed\t", lines[2])
        self.assertEqual(len(lines), 3)


if __name__ == "__main__":
    unittest.main()
