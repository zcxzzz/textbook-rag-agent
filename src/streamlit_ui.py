"""
Streamlit UI 渲染组件。
纯 UI 层——所有状态变更通过 st.session_state 标志传递，由 app.py 处理。
"""
import streamlit as st

from src.chat import list_available_books


# ═══════════════════════════════════════════════════════════════
# Loading Screen
# ═══════════════════════════════════════════════════════════════

def render_loading_screen():
    """初始加载中的等待画面。"""
    st.markdown("""
    <div style="text-align: center; padding-top: 15vh;">
        <h1>📖 Textbook RAG Tutor</h1>
        <p style="font-size: 1.2em; color: #888;">正在加载 AI 模型和教材数据库...</p>
        <p style="color: #aaa;">首次加载需要 1-2 分钟，后续启动将秒开</p>
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# Sidebar
# ═══════════════════════════════════════════════════════════════

def render_sidebar():
    """渲染侧边栏。设置 st.session_state 标志供 app.py 处理：
    - _sidebar_action: "book_change" | "new_session" | "resume" | None
    - _sidebar_action_data: 附带数据（新书名 / session_id 等）
    """
    books = list_available_books()

    with st.sidebar:
        st.markdown("## 📖 Textbook RAG Tutor")
        sid_short = st.session_state.session_id[:12] if st.session_state.session_id else "..."
        st.caption(f"会话: `{sid_short}...`")

        # ── 教材选择 ──
        st.markdown("### 📚 教材")
        book_labels = ["全部教材"] + books
        current_book = st.session_state.book_name
        try:
            idx = books.index(current_book) + 1 if current_book else 0
        except ValueError:
            idx = 0

        selected_label = st.selectbox(
            "选择教材",
            book_labels,
            index=idx,
            key="_sidebar_book_select_label",
        )
        selected_book = None if selected_label == "全部教材" else selected_label

        # 使用 _prev_book_label 避免初始加载误触发 book_change
        if "_prev_book_label" not in st.session_state:
            st.session_state._prev_book_label = selected_label

        if selected_label != st.session_state._prev_book_label:
            st.session_state._prev_book_label = selected_label
            if "_sidebar_action" not in st.session_state:
                st.session_state._sidebar_action = "book_change"
                st.session_state._sidebar_action_data = selected_book

        st.divider()

        # ── 会话管理 ──
        st.markdown("### 🔄 会话")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("新会话", use_container_width=True):
                st.session_state._sidebar_action = "new_session"
                st.session_state._sidebar_action_data = None
                st.rerun()
        with col2:
            st.text_input(
                "Session ID", placeholder="输入 ID 恢复",
                key="_sidebar_resume_input",
                label_visibility="collapsed",
            )

        if st.button("恢复会话", use_container_width=True):
            target = (st.session_state.get("_sidebar_resume_input") or "").strip()
            if target:
                st.session_state._sidebar_action = "resume"
                st.session_state._sidebar_action_data = target
                st.rerun()
            else:
                st.warning("请输入 Session ID")

        if st.session_state.session_id:
            st.code(st.session_state.session_id, language=None)

        st.divider()

        # ── 快捷命令 ──
        st.markdown("### ⚡ 快捷命令")
        shortcuts = [
            ("/progress", "📊 学习进度"),
            ("/weakpoints", "🎯 薄弱点"),
            ("/quiz 3", "✏️ 出题 (3)"),
            ("/quiz 5", "✏️ 出题 (5)"),
            ("/profile", "👤 学生画像"),
            ("/clear", "🧹 清空对话"),
        ]
        for cmd, label in shortcuts:
            if st.button(label, use_container_width=True, key=f"sc_{cmd}"):
                if cmd == "/clear":
                    st.session_state.chat_history.clear()
                    st.session_state.messages_to_render.clear()
                    st.session_state.round_count = 0
                else:
                    st.session_state.pending_command = cmd
                st.rerun()

        st.divider()

        # ── 统计 ──
        st.markdown("### 📈 统计")
        round_count = st.session_state.round_count
        msg_count = len(st.session_state.chat_history)
        next_compression = 20 - (round_count % 20) if round_count > 0 else 20
        st.caption(f"对话轮次: {round_count}")
        st.caption(f"消息数: {msg_count}")
        st.caption(f"距下次压缩: {next_compression} 轮")
        if round_count > 0:
            st.progress(
                min(round_count % 20 / 20, 1.0),
                text=f"压缩进度 ({round_count % 20}/20)",
            )


# ═══════════════════════════════════════════════════════════════
# Chat Area
# ═══════════════════════════════════════════════════════════════

def render_chat_area(messages: list[dict]):
    """渲染聊天消息列表。"""
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")
        sources = msg.get("sources", [])
        avatar = "🧑‍🎓" if role == "user" else "🤖"

        with st.chat_message(role, avatar=avatar):
            st.markdown(content)

            if sources and role == "assistant":
                with st.expander(f"📚 参考来源 ({len(sources)})", expanded=False):
                    for s in sources:
                        parts = [f"**{s.get('file', '未知')}**"]
                        if s.get("page"):
                            parts.append(s["page"])
                        if s.get("heading"):
                            parts.append(f"→ {s['heading']}")
                        st.caption(" · ".join(parts))


# ═══════════════════════════════════════════════════════════════
# Input Area
# ═══════════════════════════════════════════════════════════════

def render_input_area() -> str | None:
    """渲染输入区域。返回用户输入的文本，或 None。"""
    return st.chat_input("在这里输入你的问题，或使用 / 命令...")


# ═══════════════════════════════════════════════════════════════
# Exit Screen
# ═══════════════════════════════════════════════════════════════

def render_exit_screen():
    """退出后的总结画面。通过标志触发新会话。"""
    sid = st.session_state.session_id

    st.markdown("""
    <div style="text-align: center; padding-top: 10vh;">
        <h1>👋 学习结束</h1>
    </div>
    """, unsafe_allow_html=True)

    if sid:
        st.success("会话已保存")
        st.code(sid, language=None)
        st.info(f"下次恢复: `python -m src.chat --session {sid}`\n\n"
                f"或访问: `?session={sid}`")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 开始新会话", use_container_width=True):
            st.session_state._sidebar_action = "new_session"
            st.session_state._sidebar_action_data = None
            st.rerun()
    with col2:
        if st.button("📋 复制 Session ID", use_container_width=True):
            st.toast("Session ID 已显示在上方", icon="📋")
