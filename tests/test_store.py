from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from knowledge import KnowledgeBase
from store import KnowledgeStore


class StoreTests(unittest.TestCase):
    def test_review_visibility_persistence_and_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = KnowledgeStore(tmp)
            kb = KnowledgeBase(ROOT / "kb", store.approved)
            result = store.submit("独立测试词条", "仅用于验证持久化", "说明", "测试", "user", "group")
            self.assertEqual(result["status"], "pending")
            self.assertNotIn("独立测试词条", [e.title for e in kb.load()])
            total, rows = store.pending()
            self.assertEqual(total, 1)
            self.assertEqual(rows[0]["submitter"], "user")
            self.assertTrue(store.review(result["id"], True, "admin"))
            self.assertFalse(store.review(result["id"], True, "admin"))
            self.assertEqual(store.pending()[0], 0)
            restored = KnowledgeStore(tmp)
            self.assertEqual(restored.approved()[0]["title"], "独立测试词条")
            self.assertIn("独立测试词条", [e.title for e in kb.load()])
            self.assertTrue(list(Path(tmp, "backups").glob("*.sqlite3")))

    def test_duplicate_and_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = KnowledgeStore(tmp)
            a = store.submit("Test", "摘要", "", "补充", "u", "g")
            self.assertFalse(store.submit("test", "摘要", "", "补充", "u", "g")["ok"])
            self.assertTrue(store.review(a["id"], False, "admin"))
            self.assertEqual(store.approved(), [])
            self.assertTrue(store.submit("test", "摘要", "", "补充", "u", "g", admin=True)["ok"])
            self.assertEqual(len(store.approved()), 1)

    def test_builtin_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = KnowledgeStore(tmp)
            store.submit("定数", "错误的替代说明", "", "补充", "admin", "g", admin=True)
            kb = KnowledgeBase(ROOT / "kb", store.approved)
            entries = [e for e in kb.load() if e.title == "定数"]
            self.assertEqual(len(entries), 1)
            self.assertNotEqual(entries[0].summary, "错误的替代说明")
