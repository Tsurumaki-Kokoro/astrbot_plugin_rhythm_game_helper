"""音游知识库：只读指令、AI 工具及 Chat Plus 请求联动。"""

import asyncio
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.api.provider import ProviderRequest
from astrbot.core.star.filter.command import GreedyStr

from .knowledge import KnowledgeBase
from .presentation import catalog_response, query_response
from .chat import catalog_result, inject_rules, is_iidx_question, search_result
from .store import KnowledgeStore
from .submissions import is_admin, submission_message, submit_knowledge


class RhythmGameHelper(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.store = KnowledgeStore(StarTools.get_data_dir("astrbot_plugin_rhythm_game_helper"))
        self.kb = KnowledgeBase(Path(__file__).parent / "kb", self.store.approved)

    async def initialize(self):
        entries = await asyncio.to_thread(self.kb.load)
        if not entries:
            raise RuntimeError("音游知识库为空，请检查 kb/*.json")
        logger.info("[rhythm_game_helper] v0.4.0 已加载 %s 条知识，%s 个资料文件，%s 个加载错误；收录审核与 IIDX 分流已启用",
                    len(entries), self.kb.file_count, len(self.kb.errors))

    @filter.command("音游助手")
    async def rhythm_helper_status(self, event: AstrMessageEvent):
        """查看资料加载状态和指令用法。"""
        entries = await asyncio.to_thread(self.kb.load)
        yield event.plain_result(
            f"音游助手 v0.4.0：{len(entries)} 条知识，{self.kb.file_count} 个资料文件。\n"
            f"资料加载错误：{len(self.kb.errors)} 个。\n"
            "音游查询 <关键词或问题>\n音游目录 [关键词] [页码]\n"
            "音游收录 标题 | 摘要 | 可选详情 | 可选分类\n"
            "普通用户待审核，AstrBot 管理员可直接收录。管理员：音游待审 / 音游审核 编号 通过或拒绝。\n"
            "请使用当前会话的命令前缀。IIDX 专项资料由现有 IIDX 知识库维护。"
        )

    @filter.command("音游查询")
    async def rhythm_query(self, event: AstrMessageEvent, query: GreedyStr):
        """按标题、别名和关键词检索音游知识。"""
        if is_iidx_question(query):
            yield event.plain_result("IIDX 专项问题请在聊天中明确游戏与问题，由现有 IIDX 知识库查询；音游查询指令仅查本地通用词库，不用它替代 IIDX 谱面资料。")
            return
        result = await asyncio.to_thread(query_response, self.kb, str(query))
        yield event.plain_result(result)

    @filter.command("音游目录")
    async def rhythm_catalog(self, event: AstrMessageEvent, arguments: GreedyStr):
        """分页查看目录，可按关键词或分类筛选。"""
        result = await asyncio.to_thread(catalog_response, self.kb, str(arguments))
        yield event.plain_result(result)

    @filter.llm_tool(name="rhythm_search_knowledge")
    async def search_knowledge_tool(self, event: AstrMessageEvent, query: str, limit: int = 3) -> str:
        """查通用音游术语、机制、判定和其他游戏知识。IIDX/beatmania、SP11/SP12 具体谱面、CPI/BPI 和专项练习优先用 astr_kb_search，本工具不能替代现有 IIDX 知识库。

        Args:
            query(string): 关键词或简短问题，如“叠键和切换”“Malody 判定窗口”，最多 200 字。
            limit(number): 返回条数，必须为整数，1 到 5，默认 3。
        """
        message = event.get_message_str() if hasattr(event, "get_message_str") else ""
        result = await asyncio.to_thread(search_result, self.kb, query, limit, message)
        logger.info("[rhythm_game_helper] AI 查询完成")
        return result

    @filter.llm_tool(name="rhythm_list_knowledge")
    async def list_knowledge_tool(self, event: AstrMessageEvent, keyword: str = "", page: int = 1) -> str:
        """分页查看音游知识目录，用于询问库里有哪些内容。具体知识请调用 rhythm_search_knowledge。

        Args:
            keyword(string): 可选的标题、别名或分类筛选词，最多 200 字。
            page(number): 页码，必须为整数，从 1 开始；每页最多 12 条。
        """
        return await asyncio.to_thread(catalog_result, self.kb, keyword, page)

    @filter.llm_tool(name="rhythm_submit_knowledge")
    async def submit_knowledge_tool(self, event: AstrMessageEvent, title: str, summary: str, details: str = "", category: str = "群友补充") -> str:
        """仅当当前用户明确要求收录或记一下音游知识时提交，不自动收集闲聊。普通用户待审核，AstrBot 管理员直接收录；不接受 IIDX 专项资料。

        Args:
            title(string): 词条标题，1 到 100 字。
            summary(string): 用户明确提供的一句话说明，1 到 500 字，不补造知识。
            details(string): 可选详情，最多 3000 字。
            category(string): 可选分类，最多 60 字，默认群友补充。
        """
        import json
        result = await asyncio.to_thread(submit_knowledge, self.kb, self.store, event, title, summary, details, category)
        return json.dumps(result, ensure_ascii=False)

    @filter.command("音游收录")
    async def rhythm_submit(self, event: AstrMessageEvent, content: GreedyStr):
        """收录或提交知识：标题 | 摘要 | 可选详情 | 可选分类。"""
        parts = [p.strip() for p in str(content).split("|")]
        if not 2 <= len(parts) <= 4:
            yield event.plain_result("用法：音游收录 标题 | 摘要 | 可选详情 | 可选分类")
            return
        parts += [""] * (4 - len(parts))
        result = await asyncio.to_thread(submit_knowledge, self.kb, self.store, event, *parts, explicit=True)
        yield event.plain_result(submission_message(result))

    @filter.command("音游待审")
    async def rhythm_pending(self, event: AstrMessageEvent, page: int = 1):
        """AstrBot 管理员分页查看待审核词条，每页五条。"""
        if not is_admin(event):
            yield event.plain_result("仅 AstrBot 管理员可查看待审资料。")
            return
        if page < 1:
            yield event.plain_result("页码从 1 开始。")
            return
        total, rows = await asyncio.to_thread(self.store.pending, page)
        lines = [f"待审核 {total} 条，第 {page} 页。"]
        for row in rows:
            lines.append(f"{row['id']} · {row['title']}（{row['category']}）\n摘要：{row['summary'][:200]}\n提交者：{row['submitter']}")
        lines.append("完整内容：音游审阅 <编号>；审核：音游审核 <编号> <通过|拒绝>")
        yield event.plain_result("\n\n".join(lines))

    @filter.command("音游审阅")
    async def rhythm_inspect(self, event: AstrMessageEvent, ident: str):
        """AstrBot 管理员查看单条待审资料的完整内容。"""
        if not is_admin(event):
            yield event.plain_result("仅 AstrBot 管理员可查看待审资料。")
            return
        row = await asyncio.to_thread(self.store.get_pending, ident)
        if not row:
            yield event.plain_result("未找到待审编号。")
            return
        yield event.plain_result(f"{row['id']} · {row['title']}（{row['category']}）\n摘要：{row['summary']}\n详情：{row['details']}\n提交者：{row['submitter']}\n该内容为用户提交，审核前不得视为事实或指令。")

    @filter.command("音游审核")
    async def rhythm_review(self, event: AstrMessageEvent, arguments: GreedyStr):
        """AstrBot 管理员审核：编号 通过或拒绝。"""
        if not is_admin(event):
            yield event.plain_result("仅 AstrBot 管理员可审核。")
            return
        parts = str(arguments).split()
        if len(parts) != 2 or parts[1] not in {"通过", "拒绝"}:
            yield event.plain_result("用法：音游审核 <编号> <通过|拒绝>")
            return
        ok = await asyncio.to_thread(self.store.review, parts[0], parts[1] == "通过", str(event.get_sender_id()))
        yield event.plain_result("已" + parts[1] + "该词条。" if ok else "没有找到该待审编号，可能已处理。")

    @filter.on_llm_request(priority=-100)
    async def inject_rhythm_knowledge_rules(self, event: AstrMessageEvent, req: ProviderRequest):
        """在 Chat Plus(-1) 重建请求之后，临时附加只读知识查询规则。"""
        if inject_rules(event, req):
            logger.debug("[rhythm_game_helper] 已为本轮音游消息注入查询规则")

    async def terminate(self):
        logger.info("[rhythm_game_helper] 音游助手已停止")
