from __future__ import annotations

from aijurisdictionagents.llm import get_embedding_client
from services.document_processor.runtime import cosine_similarity


def main() -> None:
    client = get_embedding_client()
    query = "lease termination notice period"
    documents = [
        "Lease termination notice must be delivered 30 days before move-out.",
        "Deposit refund is processed after the final inspection.",
    ]

    batch = client.embed_texts([query, *documents])
    query_vector = batch.vectors[0]
    scored = [
        (cosine_similarity(query_vector, vector), text)
        for vector, text in zip(batch.vectors[1:], documents, strict=True)
    ]
    best_score, best_text = sorted(scored, key=lambda item: item[0], reverse=True)[0]

    print("Embedding model:", batch.model_name)
    print("Query:", query)
    print("Top match:", best_text)
    print("Score:", f"{best_score:.4f}")


if __name__ == "__main__":
    main()
