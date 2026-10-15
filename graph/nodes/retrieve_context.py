import logging

from config import get_settings
from db.vector import get_vectorstore

logger = logging.getLogger(__name__)


def retrieve_context(state):
    question = state["question"]
    threshold = get_settings().retrieval_score_threshold
    vs = get_vectorstore()

    # 第 1 步：先取多个带分数的候选文本块。这样既能完成相关性门控，
    # 也能根据最高分文本块确定本次问题最匹配的文档。
    candidates = vs.similarity_search_with_relevance_scores(question, k=10)
    qualified = [(doc, score) for doc, score in candidates if score >= threshold]
    if not qualified:
        logger.info(
            "Best score %.3f is below threshold %.2f — returning no context",
            candidates[0][1] if candidates else 0.0,
            threshold,
        )
        return {"docs": "", "sources": []}

    # 第 2 步：锁定最高分候选所属的文档，再在该文档内部执行 MMR。
    # MMR 仍然负责兼顾相关性和内容多样性，但不会把其他文档的弱相关片段
    # 混入上下文，保证回答内容与界面显示的参考文档一致。
    best_doc, best_score = max(qualified, key=lambda item: item[1])
    best_doc_id = best_doc.metadata.get("doc_id")

    # 第 3 步：问题与知识库相关时执行 MMR（最大边际相关性）检索。
    # 普通相似度检索可能返回 3 个几乎相同的段落，浪费上下文窗口；
    # MMR 先找出 10 个候选，再挑选 3 个既相关又彼此不同的文本块。
    mmr_kwargs = {
        "k": 3,  # 最终传给大模型的文本块数量
        "fetch_k": 10,  # 进行筛选时考虑的候选文本块数量
    }
    # 旧数据或测试替身可能没有 doc_id；这种情况下保留兼容的无过滤检索。
    if best_doc_id:
        mmr_kwargs["filter"] = {"doc_id": best_doc_id}
    docs = vs.max_marginal_relevance_search(question, **mmr_kwargs)

    context = "\n\n".join(d.page_content for d in docs)
    # 收集去重后的源文件名，用于说明回答引用了哪些文档。
    sources = list({d.metadata.get("source_file", "unknown") for d in docs})

    logger.info(
        "Retrieved %d chunks via MMR from %s (best score: %.3f)",
        len(docs),
        sources,
        best_score,
    )
    return {"docs": context, "sources": sources}
