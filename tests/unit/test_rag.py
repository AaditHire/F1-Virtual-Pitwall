from pathlib import Path

from f1_pitwall.rag import LocalKnowledgeIndex


def test_local_knowledge_index_replaces_and_searches(tmp_path: Path) -> None:
    index = LocalKnowledgeIndex(tmp_path / "knowledge.db")
    index.add_document(
        source="guide", title="Undercut", content="Fresh tyres create an undercut.", season=2024
    )
    index.add_document(
        source="guide", title="Undercut", content="An undercut gains track position.", season=2024
    )
    results = index.search("undercut", season=2024, available_before="2025-01-01")
    assert len(results) == 1
    assert "track position" in results[0].content
    assert index.search("!!!") == ()
