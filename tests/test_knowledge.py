import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from knowledge import KnowledgeBase
from presentation import catalog_response, query_response


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase(ROOT / "kb")

    def test_bundled_data_and_sources(self):
        entries = self.kb.load()
        self.assertEqual(len(entries), 711)
        self.assertEqual(self.kb.errors, ())
        official = self.kb.search("Malody 的判定窗口是多少毫秒")[0]
        self.assertIn("判定窗口", official.title)
        self.assertIn("Malody", official.source)
        self.assertEqual(official.source_file, "malody-official.json")

    def test_relevant_answers(self):
        self.assertEqual(self.kb.search("定数")[0].title, "定数")
        titles = [e.title for e in self.kb.search("叠键和切换有什么区别")]
        self.assertIn("叠键", titles)
        self.assertIn("切换", titles)
        self.assertIn("手部健康", self.kb.search("手疼")[0].title)
        self.assertEqual(self.kb.search("LN")[0].title, "面")
        self.assertIn("Phigros", self.kb.search("Phigros RKS怎么才能涨")[0].title)

    def test_no_false_ascii_or_unrelated_results(self):
        for query in ("", "请问", "xyzzy", "今天天气怎么样", "!!!!"):
            with self.subTest(query=query):
                self.assertEqual(self.kb.search(query), [])

    def test_limits_and_output(self):
        self.assertLessEqual(len(self.kb.search("判定", 999)), 5)
        response = query_response(self.kb, "Malody 判定窗口")
        self.assertIn("来源：", response)
        self.assertIn("malody-official.json", response)
        self.assertLess(len(response), 3500)
        self.assertIn("用法", query_response(self.kb, ""))
        self.assertIn("200", query_response(self.kb, "a" * 201))
        self.assertIn("没有找到", query_response(self.kb, "xyzzy"))

    def test_catalog_pagination_and_filter(self):
        first = catalog_response(self.kb, "")
        second = catalog_response(self.kb, "2")
        self.assertIn("第 1/", first)
        self.assertIn("第 2/", second)
        self.assertNotEqual(first, second)
        self.assertLess(len(first), 2000)
        self.assertIn("超出范围", catalog_response(self.kb, "0"))
        self.assertIn("超出范围", catalog_response(self.kb, "99999"))
        self.assertIn("没有匹配", catalog_response(self.kb, "xyzzy"))
        self.assertIn("第 2/", catalog_response(self.kb, "Malody 2"))

    def test_load_bom_dedup_invalid_and_hot_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            a = path / "a.json"
            a.write_text(json.dumps({"entries": [{"title": "TEST", "aliases": "别名、别称", "source": "原始出处"}, {}]}), encoding="utf-8-sig")
            (path / "b.json").write_text('[{"title":"test"}]', encoding="utf-8")
            (path / "broken.json").write_text("{", encoding="utf-8")
            kb = KnowledgeBase(path)
            self.assertEqual(len(kb.load()), 1)
            self.assertEqual(kb.search("别称")[0].source, "原始出处")
            self.assertEqual(len(kb.errors), 1)
            a.write_text('[{"title":"更新后的词条"}]', encoding="utf-8")
            self.assertEqual(kb.search("更新后的词条")[0].title, "更新后的词条")
            (path / "broken.json").unlink()
            self.assertEqual(len(kb.load()), 2)
            self.assertEqual(kb.errors, ())

    def test_uncertainty_not_lost_to_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "x.json").write_text(json.dumps([{"title": "测试", "details": "长" * 700 + "存疑"}]), encoding="utf-8")
            self.assertIn("存疑或未定稿", query_response(KnowledgeBase(tmp), "测试"))


if __name__ == "__main__":
    unittest.main()
