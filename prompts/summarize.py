def build_summarize_prompt(text: str, lang: str) -> str:
    return f"""Summarize this conversation in max 4 lines.
Focus only on: user intent, key questions, important answers.
YOU MUST write the summary in {lang} only. No exceptions.
If the selected language is Simplified Chinese, use natural Simplified Chinese throughout.

Conversation:
{text}
"""
