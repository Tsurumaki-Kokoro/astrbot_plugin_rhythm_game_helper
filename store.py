"""Transactional submissions and reviewed knowledge, separate from bundled JSON."""

from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
import uuid


class KnowledgeStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "knowledge.sqlite3"
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, title_key TEXT NOT NULL,
                summary TEXT NOT NULL, details TEXT NOT NULL, category TEXT NOT NULL,
                submitter TEXT NOT NULL, session TEXT NOT NULL, status TEXT NOT NULL,
                reviewer TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, reviewed_at TEXT)""")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS unique_live_title ON submissions(title_key) WHERE status IN ('pending','approved')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def backup(self):
        folder = self.directory / "backups"
        folder.mkdir(exist_ok=True)
        target = folder / (uuid.uuid4().hex + ".sqlite3")
        with self.connect() as source, closing(sqlite3.connect(target)) as dest:
            source.backup(dest)
        # Keep the latest 20 successful pre-change snapshots.
        for old in sorted(folder.glob("*.sqlite3"), key=lambda p: p.stat().st_mtime_ns, reverse=True)[20:]:
            old.unlink()

    def submit(self, title, summary, details, category, user, session, admin=False):
        self.backup()
        ident = uuid.uuid4().hex[:12]
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                count = db.execute("SELECT count(*) FROM submissions WHERE status IN ('pending','approved')").fetchone()[0]
                if count >= 1500:
                    return {"ok": False, "error": "补充资料已达 1500 条上限，请管理员整理"}
                if not admin:
                    pending = db.execute("SELECT count(*) FROM submissions WHERE submitter=? AND status='pending'", (user,)).fetchone()[0]
                    if pending >= 20:
                        return {"ok": False, "error": "你已有 20 条待审核，请等待管理员处理"}
                db.execute("INSERT INTO submissions(id,title,title_key,summary,details,category,submitter,session,status,reviewer) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (ident, title, title.casefold(), summary, details, category, user, session,
                            "approved" if admin else "pending", user if admin else None))
        except sqlite3.IntegrityError:
            return {"ok": False, "error": "相同标题已收录或正在审核，不重复提交"}
        return {"ok": True, "id": ident, "status": "approved" if admin else "pending"}

    def pending(self, page=1):
        with self.connect() as db:
            total = db.execute("SELECT count(*) FROM submissions WHERE status='pending'").fetchone()[0]
            rows = db.execute("SELECT * FROM submissions WHERE status='pending' ORDER BY created_at,id LIMIT 5 OFFSET ?", ((page - 1) * 5,)).fetchall()
        return total, [dict(row) for row in rows]

    def get_pending(self, ident):
        with self.connect() as db:
            row = db.execute("SELECT * FROM submissions WHERE id=? AND status='pending'", (ident,)).fetchone()
        return dict(row) if row else None

    def review(self, ident, approve, reviewer):
        self.backup()
        with self.connect() as db:
            result = db.execute("UPDATE submissions SET status=?,reviewer=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",
                                ("approved" if approve else "rejected", reviewer, ident))
        return result.rowcount == 1

    def approved(self):
        with self.connect() as db:
            rows = db.execute("SELECT title,summary,details,category FROM submissions WHERE status='approved' ORDER BY created_at,id").fetchall()
        return [{**dict(row), "source": "群友补充，经 AstrBot 管理员收录或审核；非官方资料", "source_file": "reviewed-user-knowledge"} for row in rows]
