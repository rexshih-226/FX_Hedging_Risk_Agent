"""Retrieval seam: keyword baseline; no automatic rule activation.

Put authorized .txt/.md source extracts here, with adjacent provenance metadata
managed by ingestion. A future hybrid retriever must return the same citations.
"""
from pathlib import Path
from typing import Protocol


class Retriever(Protocol):
    def search(self, query: str, limit: int = 5) -> list[dict]: ...


class LocalTextRetriever:
    def __init__(self, directory):
        self.directory = Path(directory)

    def search(self, query, limit=5):
        terms = query.lower().split()
        hits = []
        for path in self.directory.rglob("*"):
            if path.suffix not in {".txt", ".md"}:
                continue
            content = path.read_text(encoding="utf-8")
            score = sum(content.lower().count(term) for term in terms)
            if score:
                hits.append({"path": str(path), "score": score, "excerpt": content[:1500], "status": "UNVERIFIED_RETRIEVAL_ONLY"})
        return sorted(hits, key=lambda h: (-h["score"], h["path"]))[:limit]


class AgentPlanner(Protocol):
    """Future LLM adapter. May recommend tools; never changes approved policy.

    Controller must validate tool arguments and enforce mandatory checks.
    No LLM provider or API key is assumed in this scaffold.
    """
    def recommend(self, case_state: dict, available_tools: list[str]) -> dict: ...
