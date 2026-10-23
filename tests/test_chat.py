import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from chat import CATALOG_TOOL, MARKER, SEARCH_TOOL, NATIVE_KB_TOOL, catalog_result, inject_rules, is_rhythm_message, search_result
from knowledge import KnowledgeBase


class ChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase(ROOT / "kb")

    def request(self, names=(SEARCH_TOOL, CATALOG_TOOL)):
        return SimpleNamespace(system_prompt="原始人格\n表情规则", prompt="GCP 历史及当前消息",
                               contexts=[{"role": "user", "content": "原有记忆"}],
                               func_tool=SimpleNamespace(tools=[SimpleNamespace(name=n, active=True) for n in names]))

    def test_query_json_and_bounds(self):
        result = json.loads(search_result(self.kb, "Malody 判定窗口"))
        self.assertTrue(result["ok"] and result["found"])
        self.assertEqual(result["entries"][0]["source_file"], "malody-official.json")
        self.assertLess(len(result["entries"]), 4)
        self.assertLess(len(search_result(self.kb, "判定", 5)), 15000)
        self.assertFalse(json.loads(search_result(self.kb, "xyzzy"))["found"])
        for query, limit in [("", 3), ("a" * 201, 3), (None, 3), ("定数", "3")]:
            self.assertFalse(json.loads(search_result(self.kb, query, limit))["ok"])

    def test_directory_json(self):
        data = json.loads(catalog_result(self.kb, "Malody", 2))
        self.assertTrue(data["ok"] and data["found"])
        self.assertEqual(data["page"], 2)
        self.assertLessEqual(len(data["entries"]), 12)
        self.assertFalse(json.loads(catalog_result(self.kb, "xyzzy"))["found"])
        self.assertFalse(json.loads(catalog_result(self.kb, "", 0))["ok"])
        self.assertFalse(json.loads(catalog_result(self.kb, "", 9999))["ok"])

    def test_policy_only_changes_system_prompt_once(self):
        event = SimpleNamespace(get_message_str=lambda: "Malody 判定是多少？")
        req = self.request()
        original_tools, original_contexts = req.func_tool, req.contexts
        self.assertTrue(inject_rules(event, req))
        self.assertTrue(req.system_prompt.startswith("原始人格\n表情规则"))
        self.assertEqual(req.prompt, "GCP 历史及当前消息")
        self.assertIs(req.contexts, original_contexts)
        self.assertIs(req.func_tool, original_tools)
        self.assertFalse(inject_rules(event, req))
        self.assertEqual(req.system_prompt.count(MARKER), 1)

    def test_unrelated_chat_and_disabled_tools_are_untouched(self):
        req = self.request()
        req.prompt = "历史上讨论过 Malody"
        self.assertFalse(inject_rules(SimpleNamespace(message_str="今天天气不错"), req))
        self.assertEqual(req.system_prompt, "原始人格\n表情规则")
        event = SimpleNamespace(message_str="音游判定是什么")
        req.func_tool.tools[0].active = False
        self.assertFalse(inject_rules(event, req))
        req.func_tool = None
        self.assertFalse(inject_rules(event, req))

    def test_only_describe_tools_present_in_request(self):
        req = self.request((SEARCH_TOOL,))
        self.assertTrue(inject_rules(SimpleNamespace(message_str="音游定数"), req))
        self.assertNotIn(CATALOG_TOOL, req.system_prompt)

    def test_domain_detection(self):
        for text in ["叠键和切换有什么区别", "Phigros 的 RKS", "音游目录", "osu!mania LN", "Malody 判定"]:
            self.assertTrue(is_rhythm_message(text))
        for text in ["我好困", "什么天气", "streaming the movie"]:
            self.assertFalse(is_rhythm_message(text))

    def test_iidx_routing_and_style(self):
        req = self.request((SEARCH_TOOL, CATALOG_TOOL, NATIVE_KB_TOOL))
        self.assertTrue(inject_rules(SimpleNamespace(message_str="IIDX SP12 怎么练？"), req))
        self.assertIn("先调用 astr_kb_search", req.system_prompt)
        self.assertNotIn("先调用 rhythm_search_knowledge", req.system_prompt)
        self.assertIn("2～3 句", req.system_prompt)
        self.assertIn("不使用标题、加粗", req.system_prompt)
        result = json.loads(search_result(self.kb, "SP12 推荐"))
        self.assertTrue(result["routed"])
        self.assertEqual(result["preferred_tool"], "astr_kb_search")
        result = json.loads(search_result(self.kb, "某曲攻略", current_message="IIDX 某曲怎么练"))
        self.assertTrue(result["routed"])
        self.assertFalse(json.loads(search_result(self.kb, "Malody 判定" )).get("routed", False))
