"""
共享常量：分隔线、帮助文本等 UI 元素。
"""

SEP = "─" * 60
DSEP = "═" * 60

HELP_TEXT = f"""
{DSEP}
📖 Textbook-RAG-Agent · 教材私人导师
{DSEP}

可用命令：
  /explain <概念>    — 详细讲解一个概念
  /summary <章节>    — 总结指定章节（如 /summary 第3章）
  /quiz [数量]题     — 出练习题（如 /quiz 10题）
  /review [范围]     — 快速复习模式
  /connect <知识点>  — 分析知识关联
  /progress          — 查看学习进度
  /weakpoints        — 查看知识薄弱点
  /resume            — 恢复上次学习会话
  /profile           — 查看学生画像
  /books             — 查看已索引的教材
  /clear             — 清空对话历史
  /help              — 显示此帮助
  /exit              — 退出程序

你也可以直接输入任何问题，导师会基于教材回答。

💡 提示：使用前请先运行 `python -m src.ingest` 索引教材 PDF。
{SEP}
"""
