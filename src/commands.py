"""
命令处理器 — 从 chat.py 分离，扩展记忆相关命令。
"""

import logging

from src.constants import HELP_TEXT, SEP, DSEP

logger = logging.getLogger("commands")


def handle_command(cmd: str, chain, chat_history: list,
                   agent_memory=None, session_id: str = "",
                   book_name: str | None = None) -> tuple[bool, str]:
    """处理快捷命令。返回 (should_exit, output_text)。

    Args:
        cmd: 用户输入的原始命令
        chain: LangChain RAG 链
        chat_history: 会话聊天历史（会被原地修改）
        agent_memory: AgentMemory 实例（可为 None）
        session_id: 当前会话 ID
        book_name: 当前教材名
    """
    cmd = cmd.strip()
    parts = cmd.split(maxsplit=1)
    action = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    # ── 系统命令 ──────────────────────────────────────────
    if action in ("/exit", "/quit", "/q"):
        if agent_memory and session_id:
            _save_learning_snapshot(agent_memory, session_id, book_name, chat_history)
        return True, "👋 再见！祝你学习进步！"

    if action == "/clear":
        chat_history.clear()
        return False, "✅ 对话历史已清空，开始新的对话。"

    if action == "/help":
        return False, HELP_TEXT

    if action == "/books":
        return False, _cmd_books()

    # ── 记忆命令 ──────────────────────────────────────────
    if action == "/progress":
        return False, _cmd_progress(agent_memory, book_name)

    if action == "/weakpoints":
        return False, _cmd_weakpoints(agent_memory, book_name)

    if action == "/resume":
        return False, _cmd_resume(agent_memory, book_name, chat_history)

    if action == "/profile":
        return False, _cmd_profile(agent_memory, book_name, arg)

    # ── RAG 教学命令 ──────────────────────────────────────
    if action == "/summary":
        query = f"请总结以下内容的核心知识点、重点和难点，给出结构化的章节总结：{arg}"
    elif action == "/quiz":
        try:
            n = int(arg.replace("题", "").strip()) if arg else 5
        except ValueError:
            n = 5
        query = _build_quiz_query(n, arg)
    elif action == "/review":
        query = f"请用问答形式帮我快速回顾以下内容的关键知识点：{arg or '最近学的内容'}"
    elif action == "/connect":
        query = f"请帮我分析以下知识之间的关联，用概念图的方式呈现：{arg}"
    elif action == "/explain":
        query = f"请详细讲解以下概念，配合生活例子和类比：{arg}"
    else:
        return False, f"❓ 未知命令: {action}。输入 /help 查看可用命令。"

    # 执行 RAG 查询
    try:
        result = chain.invoke({
            "input": query,
            "chat_history": chat_history,
        })
        answer = result["answer"]
        chat_history.append({"role": "user", "content": query})
        chat_history.append({"role": "assistant", "content": answer})

        # 尝试自动记录学习主题
        if agent_memory and session_id and book_name:
            _auto_record_topic(agent_memory, session_id, book_name, action, arg)

        return False, answer
    except Exception:
        logger.exception("RAG 查询失败")
        return False, "❌ 查询出错，请重试。"


# ═══════════════════════════════════════════════════════════════
# 命令实现
# ═══════════════════════════════════════════════════════════════

def _cmd_books() -> str:
    """列出已索引的教材。"""
    from src.config import INDEXES_DIR
    if not INDEXES_DIR.exists():
        return "📭 暂无已索引的教材。"
    books = sorted(
        d.name for d in INDEXES_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    if books:
        return "📚 已索引的教材：\n" + "\n".join(f"  · {b}" for b in books)
    return "📭 暂无已索引的教材。"


def _cmd_progress(agent_memory, book_name: str | None) -> str:
    """展示学习进度。"""
    if not agent_memory:
        return "⚠️ 长期记忆功能未启用。请在 .env 中设置 MEMORY_ENABLED=true"

    records = agent_memory.get_all_progress(book_name)
    if not records:
        return "📝 暂无学习记录。开始提问或使用 /quiz 出题练习吧！"

    # 按章节分组
    by_chapter: dict[str, list] = {}
    for r in records:
        ch = r.get("chapter", "未知")
        by_chapter.setdefault(ch, []).append(r)

    lines = [f"\n{DSEP}", "📊 学习进度", f"{DSEP}"]
    for ch, topics in sorted(by_chapter.items()):
        mastered_count = sum(1 for t in topics if t.get("mastered", 0) >= 2)
        lines.append(f"\n  📖 {ch} ({mastered_count}/{len(topics)} 掌握)")
        for t in topics:
            level_mark = ["❓", "👀", "📖", "✅"][min(t.get("mastered", 0), 3)]
            lines.append(f"     {level_mark} {t.get('topic', '未知')}")

    stats = agent_memory.get_stats(book_name)
    lines.append(f"\n{SEP}")
    lines.append(f"📈 总计: {stats['total_sessions']} 次学习, "
                 f"{stats['total_topics_learned']} 个知识点, "
                 f"{stats['active_weak_points']} 个薄弱点")
    lines.append(SEP)
    return "\n".join(lines)


def _cmd_weakpoints(agent_memory, book_name: str | None) -> str:
    """列出薄弱点。"""
    if not agent_memory:
        return "⚠️ 长期记忆功能未启用。"

    points = agent_memory.get_weak_points(book_name, active_only=True)
    if not points:
        return "🎉 太棒了！暂未发现薄弱知识点。继续保持！"

    lines = [f"\n📌 知识薄弱点（需加强复习）", SEP]
    for i, wp in enumerate(points, 1):
        lines.append(
            f"  {i}. {wp['topic']} — 错过 {wp['error_count']} 次"
            f"（上次出错: {wp['last_error_at']}）"
        )
    lines.append(f"{SEP}\n💡 试试用 /explain 或 /review 来针对性地复习这些知识点。")
    return "\n".join(lines)


def _cmd_resume(agent_memory, book_name: str | None, chat_history: list) -> str:
    """恢复上次会话上下文。"""
    if not agent_memory:
        return "⚠️ 长期记忆功能未启用。"

    # 查找最后一个已关闭且有消息的 session（排除当前活跃 session）
    rows = agent_memory.conn.execute(
        """SELECT * FROM sessions
           WHERE closed_at IS NOT NULL AND total_messages > 0
             AND (? IS NULL OR book_name = ?)
           ORDER BY closed_at DESC LIMIT 1""",
        (book_name, book_name),
    ).fetchall()
    last_closed = rows[0] if rows else None

    if not last_closed:
        return "📝 没有找到上次学习的记录。开始新的学习吧！"

    summary = last_closed["summary"]

    # 加载该 session 的消息到 chat_history
    msgs = agent_memory.get_session_messages(last_closed["session_id"], limit=30)
    if msgs:
        chat_history.extend(msgs)

    return f"""📝 上次学习回顾（{last_closed['created_at']}）：

{summary or '（无摘要）'}

{SEP}
💡 已恢复上次对话上下文（{len(msgs)} 条消息）。
你可以继续提问，或用 /progress 查看整体进度。"""


def _cmd_profile(agent_memory, book_name: str | None, arg: str) -> str:
    """查看或编辑学生画像。"""
    if not agent_memory:
        return "⚠️ 长期记忆功能未启用。"

    if not book_name:
        return "⚠️ 请先选择一本教材。"

    if arg:
        # 更新画像
        parts = arg.split("=", 1)
        if len(parts) == 2:
            key, value = parts[0].strip(), parts[1].strip()
            if key in ("level", "overall_level"):
                valid = ("beginner", "intermediate", "advanced")
                if value not in valid:
                    return f"⚠️ 水平只能为: {', '.join(valid)}"
                agent_memory.upsert_profile(book_name, overall_level=value)
            elif key == "notes":
                agent_memory.upsert_profile(book_name, notes=value)
            else:
                return "⚠️ 可用设置: level=beginner|intermediate|advanced, notes=..."
            return f"✅ 画像已更新: {key} = {value}"
        return "⚠️ 格式: /profile level=intermediate 或 /profile notes=..."

    # 查看画像
    profile = agent_memory.get_profile(book_name)
    if not profile:
        # 自动创建
        agent_memory.upsert_profile(book_name, overall_level="beginner")
        profile = agent_memory.get_profile(book_name)

    return f"""
📋 学生画像 — {book_name}
{SEP}
  水平: {profile.get('overall_level', 'beginner')}
  笔记: {profile.get('notes', '（无）')}
  创建: {profile.get('created_at', '-')}
  更新: {profile.get('updated_at', '-')}
{SEP}
💡 修改画像: /profile level=intermediate 或 /profile notes=我喜欢画图理解
"""


# ═══════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════

QUIZ_TEMPLATES = {
    3: "请基于教材内容出 3 道练习题（2道选择题+1道简答题），每道题后面附上详细解析。",
    5: "请基于教材内容出 5 道练习题，难度递进，包含：3道选择题、1道简答题和1道思考题。每道题后面附上详细解析。",
    10: "请基于教材内容出 10 道综合练习题。包含：4道选择题、3道填空题、2道简答题和1道综合应用题。难度递进，每道题后面附上详细解析和答案。",
}


def _build_quiz_query(n: int, arg: str) -> str:
    """构建出题查询。"""
    template = QUIZ_TEMPLATES.get(n)
    if template:
        return template
    return (f"请基于教材内容出 {n} 道练习题，难度递进，"
            f"包含选择题、简答题和思考题。每道题后面附上详细解析。")


def _auto_record_topic(agent_memory, session_id: str, book_name: str,
                       action: str, arg: str):
    """自动记录学习主题到数据库。"""
    if not arg:
        return
    try:
        topic = arg.strip()[:80]
        chapter = "自动记录"
        # 尝试从 arg 中提取章节号
        import re
        m = re.search(r'第\s*(\d+)\s*章', arg)
        if m:
            chapter = f"第{m.group(1)}章"

        if action in ("/explain", "/summary", "/review"):
            agent_memory.record_learning(session_id, book_name, chapter, topic, 1)
    except Exception:
        pass  # 静默失败，不影响主流程


def _save_learning_snapshot(agent_memory, session_id: str,
                            book_name: str | None, chat_history: list):
    """在退出前保存学习快照。"""
    if not book_name or not chat_history:
        return
    try:
        # 记录最后讨论的主题
        recent_topics = set()
        for msg in reversed(chat_history[-20:]):
            if msg["role"] == "user":
                content = msg["content"][:100]
                if len(content) > 10 and not content.startswith("/"):
                    recent_topics.add(content[:50])
        for topic in list(recent_topics)[:5]:
            agent_memory.record_learning(session_id, book_name, "本次会话", topic, 1)
    except Exception:
        pass
