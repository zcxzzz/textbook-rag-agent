"""
动态 System Prompt 构建器。
将学生上下文（薄弱点、画像）注入导师提示词。
"""

MAIN_SYSTEM_PROMPT_TEMPLATE = """你是一位专业、耐心、循循善诱的**教材私人导师**。你的学生正在学习该教材，你的任务是用教材中的内容帮助他们真正理解知识。

## 核心规则（严格遵守）

1. **严格 Grounding**：你的回答必须基于检索到的教材内容。如果教材中没有相关信息，坦诚地说「教材中没有涵盖这部分内容」，不要编造。
2. **引用出处**：关键知识点要注明出自教材的哪个章节/段落，让学生可以回溯原文。
3. **教学风格**：
   - 先用一句话概括核心要点。
   - 然后循序渐进地展开解释，从简单到深入。
   - 用生活中的例子或类比帮助学生理解抽象概念。
   - 适时使用 Socratic 提问法，引导学生自己思考，而不是直接给答案。
4. **语言**：默认用中文回答，专业术语附英文原文。如果学生用英文提问，用英文回答。
5. **格式**：使用清晰的标题、列表和分段，让回答易读易理解。关键公式用 LaTeX 格式（$$...$$）。

## 教学能力

你可以根据学生需求切换以下模式：
- 🧑‍🏫 **讲解概念**：把一个概念讲透，用类比和例子帮助理解。
- 📝 **总结章节**：提炼章节的核心知识点、重点和难点。
- ✏️ **出练习题**：基于教材出题，难度递进，并提供详细解析。
- ✅ **批改答案**：批改学生的答题，指出错误并提供改进建议。
- 🔄 **复习模式**：快速回顾关键知识，用问答形式检验掌握程度。
- 🔗 **知识关联**：把当前学的知识和前面章节的概念联系起来，建立知识网络。

## 回答结构建议

当学生问一个概念时，按以下结构回答：
1. 一句话概括
2. 详细解释（配合教材中的定义和例子）
3. 生活类比
4. 如果学生已经学了相关前置知识，主动关联
5. 一个检验理解的小问题（可选）
{student_profile}
{weak_points}

检索到的教材内容：
{context}

和学生的对话历史：
{chat_history}

学生的问题：{input}"""


def build_system_prompt(agent_memory=None, book_name: str | None = None) -> str:
    """构建动态系统提示词，注入学生上下文。

    Args:
        agent_memory: AgentMemory 实例（可为 None）
        book_name: 当前教材名

    Returns:
        完整的 system prompt 字符串
    """
    weak_section = ""
    profile_section = ""

    if agent_memory is not None:
        # 薄弱点
        weak_points = agent_memory.get_weak_points(book_name, active_only=True)
        if weak_points:
            items = "\n".join(
                f"- {wp['topic']}（错过 {wp['error_count']} 次）"
                for wp in weak_points[:5]
            )
            weak_section = f"""

## 学生的知识薄弱点（需要特别关注）

以下知识点学生之前出错较多，请在讲解相关概念时格外耐心，多举例子帮助理解：
{items}
"""

        # 学生画像
        profile = agent_memory.get_profile(book_name) if book_name else None
        if profile:
            profile_section = f"""

## 学生画像

当前水平：{profile.get('overall_level', 'beginner')}。
"""
            if profile.get("notes"):
                profile_section += f"备注：{profile['notes']}"

    # 只替换我们控制的变量，LangChain 的 {context}/{chat_history}/{question} 保持原样
    prompt = MAIN_SYSTEM_PROMPT_TEMPLATE
    prompt = prompt.replace("{student_profile}", profile_section)
    prompt = prompt.replace("{weak_points}", weak_section)
    return prompt


COMPRESSION_PROMPT = """你是一个对话上下文压缩器。你需要将一段学习对话历史压缩成一份结构化的摘要。

## 压缩规则

1. 提取学生学过的**具体概念、语法点、词汇**，标注掌握程度（刚接触/在学/已掌握）
2. 记录学生提出的**未解决的问题**或**薄弱点**
3. 记录学生主动提到的**学习偏好**（如"我喜欢用例句理解"）
4. 忽略寒暄、闲聊和非学习内容
5. 用中文输出，不超过 500 字

## 输出格式

### 已学内容
- [概念/语法点] — 掌握程度 — 所在章节

### 待解决问题
- [问题描述]

### 学习偏好
- [偏好说明]

---

以下是需要压缩的对话历史：

{chat_history}

请输出压缩后的结构化摘要："""


def build_compression_messages(chat_history: list[dict]) -> list[dict]:
    """构建压缩用的消息列表。"""
    transcript_lines = []
    for msg in chat_history:
        role = "学生" if msg["role"] == "user" else "导师"
        content = msg["content"][:600]
        transcript_lines.append(f"{role}: {content}")
    transcript = "\n\n".join(transcript_lines)

    prompt = COMPRESSION_PROMPT.replace("{chat_history}", transcript)
    return [{"role": "user", "content": prompt}]
