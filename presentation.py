"""Bounded command responses; no AI or AstrBot dependency."""

import math
import re

MAX_QUERY = 200
PAGE_SIZE = 12


def query_response(kb, query):
    query = query.strip()
    if not query:
        return "用法：音游查询 <关键词或问题>\n例如：音游查询 叠键和切换有什么区别"
    if len(query) > MAX_QUERY:
        return f"查询内容请控制在 {MAX_QUERY} 字以内。"
    if not kb.load():
        return "音游知识库暂不可用，请管理员检查 kb 目录和插件日志。"
    hits = kb.search(query)
    if not hits:
        return f"库里没有找到与「{query}」相关的条目。可用“音游目录”查看已有内容。"
    blocks = []
    for entry in hits:
        text = entry.summary + ("\n" + entry.details if entry.details else "")
        if entry.tips:
            text += "\n" + "\n".join("· " + tip for tip in entry.tips)
        body = text.strip()
        truncated = len(body) > 650
        body = body[:650] + ("…（内容较长，已截断）" if truncated else "")
        # Keep uncertainty visible even when it occurs after a long excerpt.
        if any(t in text.lower() for t in ("存疑", "未定稿", "wip")):
            body = "资料中包含存疑或未定稿说明，请勿视为定论。\n" + body
        source = entry.source or "原包本地整理，未注明外部来源"
        blocks.append(f"【{entry.title}】（{entry.category}）\n{body}\n来源：{source[:220]}\n资料文件：{entry.source_file}")
    return "找到以下相关条目（资料可能存在版本差异）：\n\n" + "\n\n".join(blocks)


def catalog_response(kb, arguments):
    arguments = arguments.strip()
    keyword, page = arguments, 1
    if arguments.isdecimal():
        keyword, page = "", int(arguments)
    else:
        match = re.fullmatch(r"(.*?)\s+([0-9]+)", arguments)
        if match:
            keyword, page = match[1].strip(), int(match[2])
    if len(keyword) > MAX_QUERY:
        return f"目录关键词请控制在 {MAX_QUERY} 字以内。"
    if not kb.load():
        return "音游知识库暂不可用，请管理员检查 kb 目录和插件日志。"
    entries = kb.catalog(keyword)
    if not entries:
        return f"目录中没有匹配「{keyword}」的条目。"
    pages = math.ceil(len(entries) / PAGE_SIZE)
    if not 1 <= page <= pages:
        return f"页码超出范围，请输入 1～{pages}。"
    rows = entries[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
    lines = [f"音游目录：{len(entries)} 条，第 {page}/{pages} 页"]
    lines.extend(f"· {e.title[:90]}（{e.category[:45]}）" for e in rows)
    if page < pages:
        lines.append(f"下一页：音游目录 {keyword + ' ' if keyword else ''}{page + 1}")
    lines.append("筛选：音游目录 <关键词> [页码]\n详情：音游查询 <标题或问题>")
    return "\n".join(lines)
