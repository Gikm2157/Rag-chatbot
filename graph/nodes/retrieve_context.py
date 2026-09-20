import logging

from config import get_settings
from db.vector import get_vectorstore

logger = logging.getLogger(__name__)


def retrieve_context(state):
    question = state["question"]
    threshold = get_settings().retrieval_score_threshold
    vs = get_vectorstore()

    # Step 1 — relevance gate: check the best-matching chunk's score.
    # If even the closest chunk is below the threshold the question is off-topic
    # and we return empty so the prompt triggers the "I don't have information"
    # fallback. This prevents the LLM from hallucinating against weak matches.
    top = vs.similarity_search_with_relevance_scores(question, k=1)
    if not top or top[0][1] < threshold:
        logger.info(
            "Best score %.3f is below threshold %.2f — returning no context",
            top[0][1] if top else 0.0,
            threshold,
        )
        return {"docs": "", "sources": []}

    # Step 2 — MMR retrieval: now that we know the question is on-topic,
    # fetch 10 candidates and pick the 3 that are both relevant AND diverse.
    # This avoids sending 3 near-identical paragraphs to the LLM.

     # What is MMR (Maximal Marginal Relevance)?
    # Normal similarity search returns the top-3 most similar chunks. Problem: if your policy doc repeats the same paragraph 3 times, you get 3 nearly identical chunks — wasted context.
    # MMR fetches 10 candidates then picks 3 that are both relevant AND different from each other. More information per token sent to the LLM.
    
    # MMR: fetch 10 candidates, return the 3 most relevant AND diverse
    # Without MMR: top-3 similarity can return 3 near-identical chunks (wasted context)
    # With MMR: picks chunks that cover different parts of the answer

    docs = vs.max_marginal_relevance_search(
        question,
        k=3, # how many chunks to return to the LLM
        fetch_k=10 # how many candidates to consider before picking
        )

    context = "\n\n".join(d.page_content for d in docs)
    # collect unique source file names so we know which docs answered this question
    sources = list({d.metadata.get("source_file", "unknown") for d in docs})

    logger.info(
        "Retrieved %d chunks via MMR from %s (best score: %.3f)",
        len(docs),
        sources,
        top[0][1],
    )
    return {"docs": context, "sources": sources}
