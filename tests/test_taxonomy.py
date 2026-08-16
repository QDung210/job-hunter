from src.config import get_config
from src.taxonomy import Taxonomy


def make_taxonomy():
    config = get_config()
    return Taxonomy(
        config.keywords["categories"], config.known_terms,
        fuzzy_enabled=True, fuzzy_threshold=90,
    )


def test_crewai_transferable_from_langgraph():
    tax = make_taxonomy()
    result = tax.match("We are looking for an engineer to build autonomous LLM workflows using CrewAI.")
    assert any(t.startswith("crewai") for t in result.transferable_matches)
    assert "crewai" not in result.technical_matches


def test_pinecone_transferable_from_qdrant():
    tax = make_taxonomy()
    result = tax.match("Experience with Pinecone vector database required.")
    assert any(t.startswith("pinecone") for t in result.transferable_matches)


def test_azure_partial_transferable_from_aws():
    tax = make_taxonomy()
    result = tax.match("Must have Azure cloud experience.")
    assert any(t.startswith("azure") for t in result.transferable_matches)


def test_known_terms_are_technical_matches():
    tax = make_taxonomy()
    result = tax.match("You will use LangGraph and MCP to build agents.")
    assert "langgraph" in result.technical_matches
    assert "mcp" in result.technical_matches


def test_hard_requirement_missing_detection():
    tax = make_taxonomy()
    result = tax.match("Kubernetes experience is required for this role.")
    assert "kubernetes" in result.missing_skills
    assert "kubernetes" in result.hard_requirements_missing


def test_soft_missing_skill_not_flagged_as_hard():
    tax = make_taxonomy()
    result = tax.match("Kubernetes experience is a nice to have.")
    assert "kubernetes" in result.missing_skills
    assert "kubernetes" not in result.hard_requirements_missing
