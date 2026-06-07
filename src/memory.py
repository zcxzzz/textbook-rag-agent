"""
长期记忆管理器 — SQLite 后端。
封装会话生命周期、消息持久化、学习追踪、薄弱点管理和学生画像。
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from src.memory_schema import SCHEMA

logger = logging.getLogger("memory")


class AgentMemory:
    """教材导师的长期记忆系统。

    所有数据存入 SQLite，跨会话持久化。
    通过 MEMORY_ENABLED 配置开关。
    """

    def __init__(self, db_path: str | Path, llm_factory=None):
        self.db_path = str(db_path)
        self._llm_factory = llm_factory
        self._conn: sqlite3.Connection | None = None

    # ── 连接管理 ──────────────────────────────────────────
    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(SCHEMA)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── 会话生命周期 ──────────────────────────────────────
    def create_session(self, book_name: str | None) -> str:
        """创建新会话，返回 session_id。自动清理之前的空会话。"""
        # 清理废弃的空活跃会话（创建了但从未发过消息）
        self.conn.execute(
            "DELETE FROM sessions WHERE closed_at IS NULL AND total_messages = 0"
        )
        self.conn.commit()

        session_id = uuid.uuid4().hex[:16]
        self.conn.execute(
            "INSERT INTO sessions (session_id, book_name) VALUES (?, ?)",
            (session_id, book_name),
        )
        self.conn.commit()
        logger.info("新会话: %s (教材: %s)", session_id, book_name or "全部")
        return session_id

    def close_session(self, session_id: str) -> str | None:
        """关闭会话，可选生成 LLM 摘要。返回摘要文本或 None。"""
        row = self.conn.execute(
            "SELECT book_name FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None

        # 统计消息数
        count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        total = count["cnt"]

        # 取最近 N 条消息用于摘要
        msgs = self.conn.execute(
            """SELECT role, content FROM messages
               WHERE session_id = ? AND role IN ('user','assistant')
               ORDER BY created_at DESC LIMIT 40""",
            (session_id,),
        ).fetchall()

        summary = None
        if msgs and self._llm_factory:
            summary = self._generate_summary(list(reversed(msgs)))

        self.conn.execute(
            """UPDATE sessions
               SET closed_at = datetime('now'), summary = ?,
                   total_messages = ?
               WHERE session_id = ?""",
            (summary, total, session_id),
        )
        self.conn.commit()
        logger.info("会话关闭: %s (共 %d 条消息)", session_id, total)
        return summary

    def reopen_session(self, session_id: str) -> dict | None:
        """重新打开一个已关闭的会话，返回会话信息。不存在或已活跃时返回 None。"""
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        row = dict(row)
        if row["closed_at"] is None:
            return row  # 已经是活跃状态，直接返回
        self.conn.execute(
            "UPDATE sessions SET closed_at = NULL, summary = NULL WHERE session_id = ?",
            (session_id,),
        )
        self.conn.commit()
        logger.info("会话重新打开: %s", session_id)
        return row

    def get_active_session(self) -> dict | None:
        """获取最近的活跃会话（未关闭的）。"""
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE closed_at IS NULL ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def get_last_session_summary(self, book_name: str | None = None) -> str | None:
        """获取最近一次已关闭会话的摘要。"""
        if book_name:
            row = self.conn.execute(
                """SELECT summary FROM sessions
                   WHERE closed_at IS NOT NULL AND book_name = ?
                   ORDER BY closed_at DESC LIMIT 1""",
                (book_name,),
            ).fetchone()
        else:
            row = self.conn.execute(
                """SELECT summary FROM sessions
                   WHERE closed_at IS NOT NULL
                   ORDER BY closed_at DESC LIMIT 1"""
            ).fetchone()
        return row["summary"] if row and row["summary"] else None

    def get_recent_sessions(self, limit: int = 5) -> list[dict]:
        """获取最近 N 个有实际内容的会话。隐藏空会话（total_messages = 0）。"""
        rows = self.conn.execute(
            "SELECT * FROM sessions WHERE total_messages > 0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _generate_summary(self, messages: list[dict]) -> str | None:
        """调用 LLM 生成会话摘要。"""
        try:
            llm = self._llm_factory()
            lines = []
            for m in messages:
                role = "学生" if m["role"] == "user" else "导师"
                # 截断长消息
                content = m["content"][:500]
                lines.append(f"{role}: {content}")
            transcript = "\n".join(lines)

            prompt = f"""基于以下学习对话，用中文总结学生学了哪些内容，提到具体概念和章节。
不超过 200 字。如果对话很短或没有实质内容，返回空字符串。

对话记录：
{transcript}

请输出总结："""
            resp = llm.invoke(prompt)
            text = resp.content.strip() if hasattr(resp, "content") else str(resp).strip()
            return text if text else None
        except Exception:
            logger.exception("摘要生成失败")
            return None

    # ── 消息持久化 ────────────────────────────────────────
    def add_message(self, session_id: str, role: str, content: str,
                    sources: list[dict] | None = None):
        """持久化一条消息。"""
        sources_json = json.dumps(sources, ensure_ascii=False) if sources else None
        self.conn.execute(
            """INSERT INTO messages (session_id, role, content, sources_json)
               VALUES (?, ?, ?, ?)""",
            (session_id, role, content, sources_json),
        )
        self.conn.commit()

    def get_session_messages(self, session_id: str, limit: int = 100) -> list[dict]:
        """获取会话消息列表，适合重建 chat_history。"""
        rows = self.conn.execute(
            """SELECT role, content FROM messages
               WHERE session_id = ? AND role IN ('user','assistant')
               ORDER BY created_at ASC LIMIT ?""",
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 学习进度 ──────────────────────────────────────────
    def record_learning(self, session_id: str, book_name: str,
                        chapter: str, topic: str, mastered: int = 1):
        """记录一个学习项。mastered: 0=未知 1=接触 2=理解 3=掌握。"""
        self.conn.execute(
            """INSERT INTO learning_records (session_id, book_name, chapter, topic, mastered)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(book_name, chapter, topic) DO UPDATE SET
                 mastered = MAX(mastered, excluded.mastered),
                 last_reviewed = datetime('now'),
                 session_id = excluded.session_id""",
            (session_id, book_name, chapter, topic, mastered),
        )
        self.conn.commit()

    def get_chapter_progress(self, book_name: str) -> list[dict]:
        """按章节汇总学习进度。"""
        rows = self.conn.execute(
            """SELECT chapter, COUNT(*) as topics,
                      AVG(mastered) as avg_mastery,
                      MAX(last_reviewed) as last_reviewed
               FROM learning_records
               WHERE book_name = ?
               GROUP BY chapter
               ORDER BY chapter""",
            (book_name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_progress(self, book_name: str | None = None) -> list[dict]:
        """获取所有学习记录。"""
        if book_name:
            rows = self.conn.execute(
                """SELECT * FROM learning_records
                   WHERE book_name = ? ORDER BY chapter, topic""",
                (book_name,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM learning_records ORDER BY book_name, chapter, topic"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── 薄弱点 ────────────────────────────────────────────
    def add_weak_point(self, book_name: str, topic: str):
        """记录一个薄弱点（答错时调用）。"""
        self.conn.execute(
            """INSERT INTO weak_points (book_name, topic)
               VALUES (?, ?)
               ON CONFLICT(book_name, topic) DO UPDATE SET
                 error_count = error_count + 1,
                 last_error_at = datetime('now'),
                 resolved = 0""",
            (book_name, topic),
        )
        self.conn.commit()

    def resolve_weak_point(self, book_name: str, topic: str):
        """标记薄弱点为已解决。"""
        self.conn.execute(
            """UPDATE weak_points SET resolved = 1
               WHERE book_name = ? AND topic = ?""",
            (book_name, topic),
        )
        self.conn.commit()

    def get_weak_points(self, book_name: str | None = None,
                        active_only: bool = True) -> list[dict]:
        """获取薄弱点列表。"""
        sql = "SELECT * FROM weak_points"
        conditions = []
        params = []
        if active_only:
            conditions.append("resolved = 0")
        if book_name:
            conditions.append("book_name = ?")
            params.append(book_name)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY error_count DESC, last_error_at DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ── 测验 ──────────────────────────────────────────────
    def save_quiz(self, session_id: str, book_name: str,
                  questions: list, answers: list | None = None,
                  score: float | None = None):
        """保存一次测验记录。"""
        self.conn.execute(
            """INSERT INTO quiz_history (session_id, book_name, questions_json, answers_json, score)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, book_name,
             json.dumps(questions, ensure_ascii=False),
             json.dumps(answers, ensure_ascii=False) if answers else None,
             score),
        )
        self.conn.commit()

    def get_quiz_history(self, book_name: str | None = None,
                         limit: int = 10) -> list[dict]:
        """获取测验历史。"""
        if book_name:
            rows = self.conn.execute(
                """SELECT * FROM quiz_history WHERE book_name = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (book_name, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM quiz_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── 学生画像 ──────────────────────────────────────────
    def get_profile(self, book_name: str) -> dict | None:
        """获取某本书的学生画像。"""
        row = self.conn.execute(
            "SELECT * FROM student_profile WHERE book_name = ?",
            (book_name,),
        ).fetchone()
        return dict(row) if row else None

    def upsert_profile(self, book_name: str, **kwargs):
        """创建或更新学生画像。"""
        profile = self.get_profile(book_name)
        if profile:
            sets = []
            params = []
            for k, v in kwargs.items():
                if k in ("overall_level", "notes"):
                    sets.append(f"{k} = ?")
                    params.append(v)
            if sets:
                sets.append("updated_at = datetime('now')")
                params.append(book_name)
                self.conn.execute(
                    f"UPDATE student_profile SET {', '.join(sets)} WHERE book_name = ?",
                    params,
                )
        else:
            cols = ["book_name"] + list(kwargs.keys())
            placeholders = ["?"] * len(cols)
            vals = [book_name] + list(kwargs.values())
            self.conn.execute(
                f"INSERT INTO student_profile ({', '.join(cols)}) VALUES ({', '.join(placeholders)})",
                vals,
            )
        self.conn.commit()

    # ── 数据导出 / 统计 ───────────────────────────────────
    def get_stats(self, book_name: str | None = None) -> dict:
        """获取学习统计概览。"""
        sql_sessions = "SELECT COUNT(*) as cnt FROM sessions"
        sql_msgs = "SELECT COUNT(*) as cnt FROM messages"
        params = []
        if book_name:
            where = " WHERE book_name = ?"
            sql_sessions += where
            params.append(book_name)

        total_sessions = self.conn.execute(sql_sessions, params).fetchone()["cnt"]
        total_topics = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM learning_records"
            + (f" WHERE book_name = ?" if book_name else ""),
            params if book_name else [],
        ).fetchone()["cnt"]
        total_weak = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM weak_points WHERE resolved = 0"
            + (f" AND book_name = ?" if book_name else ""),
            params if book_name else [],
        ).fetchone()["cnt"]

        return {
            "total_sessions": total_sessions,
            "total_topics_learned": total_topics,
            "active_weak_points": total_weak,
        }
