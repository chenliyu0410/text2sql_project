from text2sql.retriever import TfidfRetriever


def test_tfidf_retrieval_is_relevant_and_deterministic() -> None:
    examples = [
        {"id": "unit", "question": "台中機組尖峰出力"},
        {"id": "reserve", "question": "備轉容量率最低日"},
        {"id": "outage", "question": "機組歲修排程"},
    ]
    retriever = TfidfRetriever(examples)
    first = retriever.retrieve("今年備轉容量率最低是哪天", top_k=2)
    second = retriever.retrieve("今年備轉容量率最低是哪天", top_k=2)
    assert first[0].example["id"] == "reserve"
    assert first == second
    assert first[0].score > first[1].score


def test_empty_retriever_returns_no_examples() -> None:
    assert TfidfRetriever([]).retrieve("任意問題") == []
