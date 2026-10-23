"""Read-only, dependency-free retrieval for the bundled rhythm-kb dataset."""

import json
import logging
import math
import re
import threading
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)
NOISE = (
    "有什么区别", "有什么不同", "有什么差别", "是啥意思", "啥意思", "是什么意思",
    "是什么", "有哪些", "有那些", "怎么用", "怎么办", "怎么才能", "为什么",
    "怎么样", "是多少", "多少钱", "请问", "帮我", "一下", "这个", "那个", "如何",
)
STOP = set("怎么 什么 为什 么办 可以 是否 不是 没有 怎样 如何 多少 哪里 这个 那个 的话 还是 就是 应该 要不 不要 能不 不能 是不 一下 一点 有点 很多 有没 知道 请问 告诉 帮我 为啥 咋办 回事 是什 有什 是个 在哪 了吗 干嘛 哪个 几个".split())
TOKEN_SPLIT = re.compile(r"[\s\u3000,，、;；:：!！?？\"'“”‘’()（）\[\]【】{}/|\\+~*_-]+")


def norm(text):
    return re.sub(r"[\s\u3000]+", "", str(text).lower())


def to_list(value):
    if isinstance(value, list):
        return tuple(str(x).strip() for x in value if x is not None and str(x).strip())
    return tuple(x.strip() for x in re.split(r"[、,，/|]", str(value or "")) if x.strip())


def bigrams(text):
    text = norm(text)
    return {text[i:i + 2] for i in range(len(text) - 1)} if len(text) > 1 else {text} - {""}


@dataclass(frozen=True)
class Entry:
    title: str
    aliases: tuple
    tags: tuple
    category: str
    summary: str
    details: str
    tips: tuple
    source: str
    source_file: str


class KnowledgeBase:
    """Reload JSON on file changes; same-title records keep the first source."""

    def __init__(self, directory, extra_entries=None):
        self.directory = Path(directory)
        self._signature = None
        self._entries = ()
        self._lock = threading.RLock()
        self.errors = ()
        self.file_count = 0
        self.extra_entries = extra_entries

    def _load_builtin(self):
        with self._lock:
            files = sorted(self.directory.glob("*.json"))
            signature = tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in files)
            if signature == self._signature:
                return self._entries
            entries, errors, seen = [], [], set()
            for file in files:
                try:
                    data = json.loads(file.read_text(encoding="utf-8-sig"))
                    rows = data if isinstance(data, list) else data.get("entries", [])
                    if not isinstance(rows, list):
                        raise ValueError("entries 必须是数组")
                    for row in rows:
                        if not isinstance(row, dict) or not str(row.get("title") or "").strip():
                            continue
                        title = str(row["title"]).strip()
                        if title.lower() in seen:
                            continue
                        seen.add(title.lower())
                        entries.append(Entry(
                            title, to_list(row.get("aliases")), to_list(row.get("tags")),
                            str(row.get("category") or "未分类").strip(),
                            str(row.get("summary") or "").strip(),
                            str(row.get("details") or "").strip(), to_list(row.get("tips")),
                            str(row.get("source") or "").strip(), file.name,
                        ))
                except (OSError, ValueError, TypeError, AttributeError) as exc:
                    errors.append(f"{file.name}: {exc}")
                    log.warning("音游资料加载失败 %s: %s", file.name, exc)
            self._entries = tuple(entries)
            self._signature = signature
            self.errors = tuple(errors)
            self.file_count = len(files)
            return self._entries

    def load(self):
        entries = list(self._load_builtin())
        if self.extra_entries is None:
            return tuple(entries)
        seen = {e.title.casefold() for e in entries}
        for row in self.extra_entries():
            if row["title"].casefold() in seen:
                continue
            seen.add(row["title"].casefold())
            entries.append(Entry(row["title"], (), (), row["category"], row["summary"],
                                 row["details"], (), row["source"], row["source_file"]))
        return tuple(entries)

    def search(self, query, limit=3):
        entries = self.load()
        clean = str(query).strip()
        for noise in NOISE:
            clean = clean.replace(noise, " ")
        query_norm = norm(clean)
        if not query_norm:
            return []
        tokens = list(dict.fromkeys(t for t in TOKEN_SPLIT.split(clean) if t))
        for token in tuple(tokens):
            t = norm(token)
            if len(t) >= 4 and not any(ord(c) < 128 for c in t):
                for size in (4, 3):
                    tokens.extend(t[i:i + size] for i in range(len(t) - size + 1))
        tokens = tuple(dict.fromkeys(norm(t) for t in tokens))
        query_bigrams = {b for b in bigrams(query_norm) if b not in STOP and not any(ord(c) < 128 for c in b)}
        names = {e: ((norm(e.title), 6), *((norm(a), 5) for a in e.aliases)) for e in entries}
        idfs = {}

        def idf(term):
            if term not in idfs:
                count = sum(any(term in name for name, _ in names[e]) for e in entries)
                idfs[term] = math.log(1 + len(entries) / (1 + min(count, 61)))
            return idfs[term]

        scored = []
        for entry in entries:
            named = names[entry]
            fields = (*named, *((norm(t), 1) for t in entry.tags),
                      (norm(entry.category), 1), (norm(entry.summary), 2),
                      (norm(entry.details), 1), (norm("".join(entry.tips)), 1))
            score = 0.0
            for token in tokens:
                best = max((weight + (min(4, len(token)) if weight >= 4 else 0)
                            for text, weight in fields if token and token in text), default=0)
                score += best * idf(token)
            for name, weight in named:
                if len(name) >= 2 and name in query_norm:
                    score += (weight + 6) * idf(name)
                if len(name) >= 2:
                    score += sum(idf(b) for b in query_bigrams & bigrams(name)) * 1.2 * weight / 6
            exact = any(name == query_norm for name, _ in named)
            if exact:
                score += 8
            if score > 0:
                scored.append((exact, score, entry))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if not scored:
            return []
        floor = max(1, scored[0][1] * .25)
        return [entry for _, score, entry in scored if score >= floor][:max(1, min(5, int(limit)))]

    def catalog(self, keyword=""):
        keyword = norm(keyword)
        return sorted((e for e in self.load() if not keyword or
                       any(keyword in norm(t) for t in (e.title, *e.aliases, e.category))),
                      key=lambda e: (e.category, e.title))
