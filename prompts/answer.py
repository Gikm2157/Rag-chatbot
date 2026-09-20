def build_answer_prompt(summary: str, history: str, docs: str, question: str, lang: str) -> str:
    context_block = docs.strip()
    return f"""You are a helpful assistant for our company.

Conversation Summary:
{summary}

Recent Chat:
{history}

Relevant Context:
{context_block if context_block else "(no relevant documents found)"}

User Question:
{question}

Rules:
- If Relevant Context is "(no relevant documents found)" AND the user message is a conversational
  follow-up (e.g. "i called", "they said", "ok", "thanks", "what do you mean") — respond naturally
  based on the Recent Chat history. Ask a follow-up like "What did they tell you?" or acknowledge
  what they said. Do NOT use general knowledge about unrelated topics.
- If Relevant Context is "(no relevant documents found)" AND the user is asking about a new topic
  not covered in the conversation — clearly state in {lang} that the knowledge base does not
  contain the requested information and suggest contacting support.
- Otherwise, answer ONLY from the Relevant Context. Do not add outside knowledge.
- Be concise (2-3 sentences max).
- Do not repeat history.
- YOU MUST respond in {lang} only. No exceptions.
- If the selected language is Simplified Chinese, use natural Simplified Chinese throughout.
- Do not translate Chinese names, company names, project names, or technical terms unnecessarily.
"""
