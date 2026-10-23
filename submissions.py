"""Validation and permissions shared by command and AI submission paths."""

import re

from .chat import is_iidx_question


def is_admin(event):
    checker = getattr(event, "is_admin", None)
    return bool(checker()) if callable(checker) else False


def submit_knowledge(kb, store, event, title, summary, details="", category="群友补充", explicit=False):
    text_getter = getattr(event, "get_message_str", None)
    text = text_getter() if callable(text_getter) else getattr(event, "message_str", "")
    if not explicit and not re.search(r"收录|记一下|记进库|提交.*知识|以后记住", str(text)):
        return {"ok": False, "error": "当前用户没有明确要求收录，不写入资料"}
    values = (title, summary, details, category)
    if not all(isinstance(x, str) for x in values):
        return {"ok": False, "error": "标题、摘要、详情和分类必须是文本"}
    title, summary, details, category = (x.strip() for x in values)
    if not title or not summary or len(title) > 100 or len(summary) > 500 or len(details) > 3000 or len(category) > 60:
        return {"ok": False, "error": "标题 1～100 字，摘要 1～500 字，详情最多 3000 字，分类最多 60 字"}
    if is_iidx_question(" ".join((title, summary, details, category))) or is_iidx_question(text):
        return {"ok": False, "error": "IIDX 专项资料由现有 IIDX 知识库维护，本插件不重复收录或覆盖；请管理员更新原生知识库文档"}
    key = title.casefold()
    if any(key in {e.title.casefold(), *(a.casefold() for a in e.aliases)} for e in kb.load()):
        return {"ok": False, "error": "已有同名或同别名词条，不能覆盖内置或已收录资料"}
    user = str(event.get_sender_id())
    session = str(getattr(event, "unified_msg_origin", ""))
    return store.submit(title, summary, details, category or "群友补充", user, session, is_admin(event))


def submission_message(result):
    if not result.get("ok"):
        return "未收录：" + result["error"]
    if result["status"] == "approved":
        return f"已收录「{result['id']}」，下次查询即可检索；标注为经管理员确认的群友补充。"
    return f"已提交，编号 {result['id']}。等待 AstrBot 管理员审核，通过前不会进入查询结果。"
