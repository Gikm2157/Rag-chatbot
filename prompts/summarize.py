def build_summarize_prompt(
    previous_summary: str,
    new_messages: str,
    lang: str,
) -> str:
    return f"""请根据旧摘要和本次新增消息更新对话摘要。

要求：
1. 保留旧摘要中的重要信息，并补充新消息中的用户意图、关键问题和重要回答。
2. 删除重复、过时或不重要的内容，不得编造对话中不存在的信息。
3. 摘要最多 4 行。
4. 必须使用 {lang}，不得混用其他语言。

【旧摘要】
{previous_summary or "（无）"}

【本次新增消息】
{new_messages}
"""
