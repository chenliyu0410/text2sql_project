"""Load, validate, and index the version-controlled retrieval corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ingest.validate import PROJECT_ROOT


def normalize_question(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def character_ngrams(value: str, *, minimum: int = 2, maximum: int = 4) -> tuple[str, ...]:
    normalized = normalize_question(value)
    return tuple(
        sorted(
            {
                normalized[index : index + size]
                for size in range(minimum, maximum + 1)
                for index in range(max(0, len(normalized) - size + 1))
            }
        )
    )


def load_corpus(path: Path) -> dict[str, Any]:
    corpus = json.loads(path.read_text(encoding="utf-8"))
    required = {"version", "ddl", "documentation", "examples"}
    missing = required - set(corpus)
    if missing:
        raise ValueError(f"語料缺少欄位：{sorted(missing)}")
    if not isinstance(corpus["examples"], list):
        raise ValueError("corpus.examples 必須是陣列")
    ids: set[str] = set()
    questions: set[str] = set()
    for example in corpus["examples"]:
        missing_example = {"id", "question", "sql", "intent"} - set(example)
        if missing_example:
            raise ValueError(f"語料 example 缺少欄位：{sorted(missing_example)}")
        normalized = normalize_question(example["question"])
        if example["id"] in ids or normalized in questions:
            raise ValueError(f"語料重複：{example['id']}")
        ids.add(example["id"])
        questions.add(normalized)
    return corpus


def corpus_checksum(corpus: dict[str, Any]) -> str:
    payload = json.dumps(corpus, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def build_index(corpus: dict[str, Any]) -> dict[str, Any]:
    documents = [
        {
            "id": example["id"],
            "question": example["question"],
            "normalized": normalize_question(example["question"]),
            "ngrams": character_ngrams(example["question"]),
        }
        for example in corpus["examples"]
    ]
    return {
        "corpus_version": corpus["version"],
        "corpus_checksum": corpus_checksum(corpus),
        "document_count": len(documents),
        "documents": documents,
    }


def benchmark_questions(paths: Iterable[Path]) -> set[str]:
    questions: set[str] = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload:
            if "question" in item:
                questions.add(normalize_question(item["question"]))
    return questions


def write_index(corpus_path: Path, index_path: Path) -> dict[str, Any]:
    corpus = load_corpus(corpus_path)
    index = build_index(corpus)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=PROJECT_ROOT / "corpus/training_corpus.json")
    parser.add_argument("--index", type=Path, default=PROJECT_ROOT / "corpus/index.json")
    args = parser.parse_args(argv)
    index = write_index(args.corpus, args.index)
    print(
        f"已建立語料索引：{index['document_count']} 份文件，"
        f"checksum={index['corpus_checksum'][:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
