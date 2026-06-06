"""
SQLite DDL 常量 — 6 张核心表。
与 AgentMemory 逻辑分离，便于审计和迁移。
"""

SCHEMA = """

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 会话表：一次程序启动到退出的完整对话
CREATE TABLE IF NOT EXISTS sessions (
    session_id     TEXT PRIMARY KEY,
    book_name      TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at      TEXT,
    summary        TEXT,
    total_messages INTEGER DEFAULT 0
);

-- 消息表：逐条持久化
CREATE TABLE IF NOT EXISTS messages (
    message_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role           TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content        TEXT NOT NULL,
    sources_json   TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id, created_at);

-- 学习进度：(book, chapter, topic) 粒度
CREATE TABLE IF NOT EXISTS learning_records (
    record_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    book_name      TEXT NOT NULL,
    chapter        TEXT NOT NULL,
    topic          TEXT NOT NULL,
    mastered       INTEGER NOT NULL DEFAULT 0,
    last_reviewed  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(book_name, chapter, topic)
);
CREATE INDEX IF NOT EXISTS idx_lr_book ON learning_records(book_name);

-- 知识薄弱点
CREATE TABLE IF NOT EXISTS weak_points (
    weak_point_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    book_name      TEXT NOT NULL,
    topic          TEXT NOT NULL,
    error_count    INTEGER NOT NULL DEFAULT 1,
    last_error_at  TEXT NOT NULL DEFAULT (datetime('now')),
    resolved       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(book_name, topic)
);
CREATE INDEX IF NOT EXISTS idx_wp_book ON weak_points(book_name);

-- 测验历史
CREATE TABLE IF NOT EXISTS quiz_history (
    quiz_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    book_name      TEXT NOT NULL,
    questions_json TEXT NOT NULL,
    answers_json   TEXT,
    score          REAL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 学生画像：每本书一份
CREATE TABLE IF NOT EXISTS student_profile (
    profile_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    book_name      TEXT NOT NULL UNIQUE,
    overall_level  TEXT DEFAULT 'beginner',
    notes          TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
