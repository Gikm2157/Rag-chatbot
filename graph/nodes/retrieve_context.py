import logging

from config import get_settings
from db.vector import get_vectorstore

logger = logging.getLogger(__name__)


def retrieve_context(state):
    question = state["question"]
    threshold = get_settings().retrieval_score_threshold
    vs = get_vectorstore()

    # 第 1 步：相关性门控，检查最匹配文本块的分数。
    # 如果最相近的文本块仍低于阈值，就认为问题与知识库无关并返回空上下文，
    # 让提示词触发“知识库中没有相关信息”的兜底回答，避免模型根据弱匹配产生幻觉。
    top = vs.similarity_search_with_relevance_scores(question, k=1)
    if not top or top[0][1] < threshold:
        logger.info(
            "Best score %.3f is below threshold %.2f — returning no context",
            top[0][1] if top else 0.0,
            threshold,
        )
        return {"docs": "", "sources": []}

    # 第 2 步：问题与知识库相关时执行 MMR（最大边际相关性）检索。
    # 普通相似度检索可能返回 3 个几乎相同的段落，浪费上下文窗口；
    # MMR 先找出 10 个候选，再挑选 3 个既相关又彼此不同的文本块。

    docs = vs.max_marginal_relevance_search(
        question,
        k=3,  # 最终传给大模型的文本块数量
        fetch_k=10  # 进行筛选时考虑的候选文本块数量
        )

    context = "\n\n".join(d.page_content for d in docs)
    # 收集去重后的源文件名，用于说明回答引用了哪些文档。
    sources = list({d.metadata.get("source_file", "unknown") for d in docs})

    logger.info(
        "Retrieved %d chunks via MMR from %s (best score: %.3f)",
        len(docs),
        sources,
        top[0][1],
    )
    return {"docs": context, "sources": sources}
