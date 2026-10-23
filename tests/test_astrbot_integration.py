"""Run inside AstrBot's Python environment; never send external messages."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

HAS_ASTRBOT = importlib.util.find_spec("astrbot") is not None


@unittest.skipUnless(HAS_ASTRBOT, "Requires AstrBot's Python environment")
class CommandIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from astrbot.core.star.filter.command import CommandFilter
        root = Path(__file__).resolve().parents[1]
        package = "rhythm_helper_integration"
        spec = importlib.util.spec_from_file_location(package, root / "main.py", submodule_search_locations=[str(root)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[package] = module
        spec.loader.exec_module(module)
        cls.module = module
        cls.command_filter_class = CommandFilter

    def parsed(self, method_name, params):
        command_filter = self.command_filter_class("test")
        handler = getattr(self.module.RhythmGameHelper, method_name)
        command_filter.init_handler_md(SimpleNamespace(handler=handler))
        return command_filter.validate_and_convert_params(params, command_filter.handler_params)

    async def test_query_preserves_all_words(self):
        params = self.parsed("rhythm_query", ["Malody", "判定窗口"])
        self.assertEqual(params, {"query": "Malody 判定窗口"})
        helper = object.__new__(self.module.RhythmGameHelper)
        helper.kb = self.module.KnowledgeBase(Path(__file__).resolve().parents[1] / "kb")
        event = SimpleNamespace(plain_result=lambda text: text)
        results = [r async for r in helper.rhythm_query(event, **params)]
        self.assertIn("毫秒表", results[0])
        self.assertIn("来源：", results[0])

    async def test_empty_parameters_and_paging(self):
        self.assertEqual(self.parsed("rhythm_query", []), {"query": ""})
        params = self.parsed("rhythm_catalog", ["Malody", "2"])
        self.assertEqual(params, {"arguments": "Malody 2"})
        helper = object.__new__(self.module.RhythmGameHelper)
        helper.kb = self.module.KnowledgeBase(Path(__file__).resolve().parents[1] / "kb")
        event = SimpleNamespace(plain_result=lambda text: text)
        results = [r async for r in helper.rhythm_catalog(event, **params)]
        self.assertIn("第 2/", results[0])
        results = [r async for r in helper.rhythm_query(event, query="")]
        self.assertIn("用法", results[0])

    async def test_native_tool_registration_and_execution(self):
        import json
        from astrbot.core.star.register.star_handler import llm_tools
        search = llm_tools.get_func("rhythm_search_knowledge")
        listing = llm_tools.get_func("rhythm_list_knowledge")
        self.assertIsNotNone(search)
        self.assertIsNotNone(listing)
        self.assertEqual(search.parameters["properties"]["query"]["type"], "string")
        self.assertEqual(search.parameters["properties"]["limit"]["type"], "number")
        helper = object.__new__(self.module.RhythmGameHelper)
        helper.kb = self.module.KnowledgeBase(Path(__file__).resolve().parents[1] / "kb")
        # Invoke the actual registered handler. Event has no send method by design.
        data = json.loads(await search.handler(helper, SimpleNamespace(), query="Malody 判定窗口", limit=3))
        self.assertTrue(data["found"])
        data = json.loads(await listing.handler(helper, SimpleNamespace(), keyword="Malody", page=1))
        self.assertTrue(data["found"])

    async def test_request_hook_with_native_request_and_tools(self):
        from astrbot.api.provider import ProviderRequest
        from astrbot.core.agent.tool import ToolSet
        from astrbot.core.star.register.star_handler import llm_tools
        helper = object.__new__(self.module.RhythmGameHelper)
        toolset = ToolSet([llm_tools.get_func("rhythm_search_knowledge"), llm_tools.get_func("rhythm_list_knowledge")])
        request = ProviderRequest(prompt="Chat Plus 重建的当前请求", system_prompt="薄绿人格\n记忆\n表情规则", func_tool=toolset)
        event = SimpleNamespace(get_message_str=lambda: "叠键和切换有什么区别？")
        await helper.inject_rhythm_knowledge_rules(event, request)
        self.assertTrue(request.system_prompt.startswith("薄绿人格\n记忆\n表情规则"))
        self.assertIn("rhythm_search_knowledge", request.system_prompt)
        self.assertIs(request.func_tool, toolset)
        self.assertEqual(request.prompt, "Chat Plus 重建的当前请求")

    async def test_submission_permissions_and_iidx_boundary(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            helper = object.__new__(self.module.RhythmGameHelper)
            helper.store = self.module.KnowledgeStore(tmp)
            helper.kb = self.module.KnowledgeBase(Path(__file__).resolve().parents[1] / "kb", helper.store.approved)
            event = SimpleNamespace(is_admin=lambda: False, get_sender_id=lambda: "user",
                                    unified_msg_origin="test:group:1", plain_result=lambda text: text,
                                    get_message_str=lambda: "记一下这个音游知识")
            result = json.loads(await helper.submit_knowledge_tool(event, "测试补充甲", "摘要甲"))
            self.assertEqual(result["status"], "pending")
            self.assertNotIn("测试补充甲", [e.title for e in helper.kb.load()])
            responses = [r async for r in helper.rhythm_review(event, result["id"] + " 通过")]
            self.assertIn("仅 AstrBot 管理员", responses[0])
            event.is_admin = lambda: True
            responses = [r async for r in helper.rhythm_review(event, result["id"] + " 通过")]
            self.assertIn("已通过", responses[0])
            self.assertIn("测试补充甲", [e.title for e in helper.kb.load()])
            result = json.loads(await helper.submit_knowledge_tool(event, "测试补充乙", "摘要乙"))
            self.assertEqual(result["status"], "approved")
            result = json.loads(await helper.submit_knowledge_tool(event, "定数", "覆盖内置资料"))
            self.assertFalse(result["ok"])
            result = json.loads(await helper.submit_knowledge_tool(event, "IIDX SP12 攻略", "说明"))
            self.assertFalse(result["ok"])
            self.assertIn("IIDX", result["error"])
            event.get_message_str = lambda: "只是普通聊天"
            result = json.loads(await helper.submit_knowledge_tool(event, "测试补充丙", "说明"))
            self.assertFalse(result["ok"])
            responses = [r async for r in helper.rhythm_submit(event, "测试补充丁 | 摘要丁")]
            self.assertIn("已收录", responses[0])
