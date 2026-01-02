"""
Pytest fixtures and configuration for RAG engine tests.

Provides common fixtures for:
- Sample documents and chunks
- Mock embeddings
- Temporary directories
- Test configurations
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add package path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from rag_engine.config import (
    CaseDocument,
    DocumentChunk,
    RAGConfig,
    RetrievalResult,
    SectionType,
)


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "embeddings").mkdir()
    return data_dir


@pytest.fixture
def test_config(temp_data_dir):
    """Create a test RAGConfig with temporary directories."""
    return RAGConfig(
        openai_api_key="test-api-key",
        data_dir=temp_data_dir,
        chroma_persist_dir=temp_data_dir / "embeddings",
        bm25_index_path=temp_data_dir / "embeddings" / "bm25_index.pkl",
        chunk_size=200,
        chunk_overlap=20,
        initial_retrieval_k=10,
        final_top_k=5,
        bm25_lite_mode=True,
    )


# ============================================================================
# Document Fixtures
# ============================================================================

@pytest.fixture
def sample_case_document():
    """Create a sample CaseDocument for testing."""
    return CaseDocument(
        case_reference="LON_00AB_HMF_2021_0001",
        year=2021,
        region="LON",
        region_name="London",
        case_type="HMF",
        case_type_name="HMO and other matters",
        title="Test Case v Test Landlord",
        decision_date="2021-06-15",
        full_text="""
        FIRST-TIER TRIBUNAL
        PROPERTY CHAMBER (RESIDENTIAL PROPERTY)

        Case Reference: LON/00AB/HMF/2021/0001

        DECISION

        1. The Applicant is a tenant of a property at 123 Test Street, London.

        2. The Respondent is the landlord of the property.

        BACKGROUND

        3. The tenancy began on 1 January 2020. The tenant paid a deposit of £1,200.

        4. The landlord did not protect the deposit within 30 days as required by
        section 213 of the Housing Act 2004.

        5. The tenant claims that the landlord failed to provide prescribed information
        about the deposit protection scheme.

        FINDINGS

        6. The tribunal finds that the deposit was not protected in accordance with
        the requirements of section 213 of the Housing Act 2004.

        7. The landlord admitted that they did not protect the deposit until after
        the tenant raised the issue.

        DECISION

        8. The tribunal awards the tenant £3,600 (3x the deposit amount) as compensation
        for the landlord's failure to protect the deposit.

        9. The landlord shall pay the tenant within 28 days of this decision.
        """,
        sections={
            "background": "The tenancy began on 1 January 2020...",
            "facts": "The tribunal finds that the deposit was not protected...",
            "decision": "The tribunal awards the tenant £3,600...",
        },
        source_path="/data/raw/bailii/deposit-cases/test_case.pdf",
        metadata={"scraped_date": "2024-01-15"},
    )


@pytest.fixture
def sample_case_document_cleaning():
    """Create a case document about cleaning disputes."""
    return CaseDocument(
        case_reference="LON_00BC_LSC_2022_0042",
        year=2022,
        region="LON",
        case_type="LSC",
        title="Service Charge Dispute",
        full_text="""
        FIRST-TIER TRIBUNAL
        PROPERTY CHAMBER

        Case Reference: LON/00BC/LSC/2022/0042

        DECISION

        1. This is an application under section 27A of the Landlord and Tenant Act 1985.

        2. The Applicant disputes the cleaning charges for the communal areas.

        FINDINGS

        3. The cleaning service was not provided to a reasonable standard.

        4. The invoices provided did not demonstrate that professional cleaning
        was carried out regularly.

        5. The tribunal finds that the cleaning costs charged were not reasonable.

        DECISION

        6. The cleaning charges are reduced by 50%.
        """,
        sections={},
        source_path="/data/raw/bailii/other-cases/cleaning.pdf",
    )


@pytest.fixture
def sample_chunks(sample_case_document) -> List[DocumentChunk]:
    """Create sample DocumentChunks for testing."""
    return [
        DocumentChunk(
            chunk_id="LON_00AB_HMF_2021_0001_0",
            case_reference="LON_00AB_HMF_2021_0001",
            chunk_index=0,
            text="The Applicant is a tenant of a property at 123 Test Street, London. The Respondent is the landlord of the property.",
            section_type=SectionType.BACKGROUND,
            year=2021,
            region="LON",
            case_type="HMF",
            token_count=25,
        ),
        DocumentChunk(
            chunk_id="LON_00AB_HMF_2021_0001_1",
            case_reference="LON_00AB_HMF_2021_0001",
            chunk_index=1,
            text="The tenancy began on 1 January 2020. The tenant paid a deposit of £1,200. The landlord did not protect the deposit within 30 days as required by section 213 of the Housing Act 2004.",
            section_type=SectionType.FACTS,
            year=2021,
            region="LON",
            case_type="HMF",
            token_count=45,
        ),
        DocumentChunk(
            chunk_id="LON_00AB_HMF_2021_0001_2",
            case_reference="LON_00AB_HMF_2021_0001",
            chunk_index=2,
            text="The tribunal finds that the deposit was not protected in accordance with the requirements of section 213 of the Housing Act 2004. The landlord admitted that they did not protect the deposit.",
            section_type=SectionType.REASONING,
            year=2021,
            region="LON",
            case_type="HMF",
            token_count=40,
        ),
        DocumentChunk(
            chunk_id="LON_00AB_HMF_2021_0001_3",
            case_reference="LON_00AB_HMF_2021_0001",
            chunk_index=3,
            text="The tribunal awards the tenant £3,600 (3x the deposit amount) as compensation for the landlord's failure to protect the deposit.",
            section_type=SectionType.DECISION,
            year=2021,
            region="LON",
            case_type="HMF",
            token_count=28,
        ),
    ]


@pytest.fixture
def sample_retrieval_results() -> List[RetrievalResult]:
    """Create sample RetrievalResults for testing."""
    return [
        RetrievalResult(
            chunk_id="LON_00AB_HMF_2021_0001_1",
            case_reference="LON_00AB_HMF_2021_0001",
            chunk_text="The tenant paid a deposit of £1,200. The landlord did not protect the deposit within 30 days as required by section 213.",
            section_type="facts",
            semantic_score=0.85,
            semantic_rank=1,
            bm25_score=15.5,
            bm25_rank=1,
            combined_score=0.025,
            year=2021,
            region="LON",
            case_type="HMF",
        ),
        RetrievalResult(
            chunk_id="LON_00BC_HMF_2022_0005_2",
            case_reference="LON_00BC_HMF_2022_0005",
            chunk_text="The deposit was not protected. Section 213 requires protection within 30 days.",
            section_type="reasoning",
            semantic_score=0.78,
            semantic_rank=2,
            bm25_score=12.3,
            bm25_rank=2,
            combined_score=0.020,
            year=2022,
            region="LON",
            case_type="HMF",
        ),
        RetrievalResult(
            chunk_id="CHI_00DE_HMF_2020_0012_1",
            case_reference="CHI_00DE_HMF_2020_0012",
            chunk_text="Failure to protect deposit under section 213 of the Housing Act 2004.",
            section_type="decision",
            semantic_score=0.72,
            semantic_rank=3,
            bm25_score=10.1,
            bm25_rank=4,
            combined_score=0.018,
            year=2020,
            region="CHI",
            case_type="HMF",
        ),
    ]


# ============================================================================
# Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_embeddings():
    """Create a mock embeddings service."""
    mock = MagicMock()

    async def embed_texts(texts: List[str]):
        # Return deterministic fake embeddings based on text length
        return [[0.1 * (i + 1)] * 1536 for i, _ in enumerate(texts)]

    async def embed_query(query: str):
        return [0.5] * 1536

    mock.embed_texts = AsyncMock(side_effect=embed_texts)
    mock.embed_query = AsyncMock(side_effect=embed_query)
    mock.get_stats = MagicMock(return_value={"total_tokens": 100, "api_calls": 1})

    return mock


@pytest.fixture
def mock_vectorstore(sample_chunks):
    """Create a mock vector store."""
    from rag_engine.vectorstore.base import VectorSearchResult

    mock = MagicMock()
    stored_chunks = {}

    async def add_chunks(chunks, embeddings):
        for chunk in chunks:
            stored_chunks[chunk.chunk_id] = chunk

    async def query(embedding, n_results=10, where=None):
        # Return mock results
        results = []
        for i, chunk in enumerate(list(stored_chunks.values())[:n_results]):
            results.append(VectorSearchResult(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                score=0.9 - (i * 0.05),
                metadata=chunk.to_chroma_metadata(),
            ))
        return results

    async def chunk_exists(chunk_id):
        return chunk_id in stored_chunks

    async def get_all_chunk_ids():
        return list(stored_chunks.keys())

    mock.add_chunks = AsyncMock(side_effect=add_chunks)
    mock.query = AsyncMock(side_effect=query)
    mock.chunk_exists = AsyncMock(side_effect=chunk_exists)
    mock.get_all_chunk_ids = AsyncMock(side_effect=get_all_chunk_ids)
    mock.get_collection_stats = AsyncMock(return_value={"total_chunks": len(stored_chunks)})

    return mock


# ============================================================================
# Sample Text Fixtures
# ============================================================================

@pytest.fixture
def sample_legal_text():
    """Sample legal text for cleaning/chunking tests."""
    return """
    FIRST-TIER TRIBUNAL
    PROPERTY CHAMBER (RESIDENTIAL PROPERTY)

    Case Reference: LON/00AB/HMF/2021/0001

    Property: 123 Test Street, London SW1A 1AA

    Applicant: Mr John Smith
    Representative: Not represented

    Respondent: ABC Properties Ltd
    Representative: Jane Doe, Solicitor

    DECISION

    1. The Applicant seeks a rent repayment order under section 41 of the
    Housing and Planning Act 2016 for the period from 1 January 2020 to
    31 December 2020.

    2. The property is an HMO which the Respondent failed to license under
    Part 2 of the Housing Act 2004.

    BACKGROUND

    3. The tenancy agreement was signed on 15 December 2019.

    4. The monthly rent was £1,200. Total rent paid was £14,400.

    FINDINGS OF FACT

    5. The tribunal is satisfied beyond reasonable doubt that the Respondent
    has committed an offence under section 72(1) of the Housing Act 2004
    by having control of or managing an HMO which is required to be
    licensed but is not licensed.

    6. The property had 5 occupiers, which exceeds the threshold requiring
    mandatory licensing.

    DECISION

    7. The tribunal makes a rent repayment order in the sum of £7,200
    (being 50% of the rent paid).

    8. This sum shall be payable within 28 days.

    Judge A. Tribunal
    15 June 2021
    """


@pytest.fixture
def sample_text_with_pii():
    """Sample text containing PII patterns."""
    return """
    The tenant's contact details are:
    - Email: john.smith@example.com
    - Phone: 07123456789
    - Address: 123 Test Street, London SW1A 1AA
    - Bank details for refund: 12-34-56 12345678

    The landlord can be contacted at landlord@property.co.uk or
    on 0207 123 4567.
    """


# ============================================================================
# Golden Dataset Fixtures (for retrieval quality testing)
# ============================================================================

@pytest.fixture
def golden_test_cases():
    """
    Golden test cases for retrieval quality evaluation.

    Each case has a query and expected relevant case types/topics.
    """
    return [
        {
            "query": "landlord didn't protect deposit",
            "expected_topics": ["deposit", "protection", "section 213"],
            "expected_case_types": ["HMF", "HTC"],
            "min_confidence": 0.5,
        },
        {
            "query": "cleaning costs disputed in service charge",
            "expected_topics": ["cleaning", "service charge", "cost"],
            "expected_case_types": ["LSC"],
            "min_confidence": 0.5,
        },
        {
            "query": "rent repayment order unlicensed HMO",
            "expected_topics": ["rent repayment", "HMO", "unlicensed", "section 41"],
            "expected_case_types": ["HMF", "HMG", "HNA"],
            "min_confidence": 0.5,
        },
        {
            "query": "fair wear and tear damage dispute",
            "expected_topics": ["wear", "tear", "damage"],
            "expected_case_types": ["HMF", "LDC", "LBC"],
            "min_confidence": 0.4,
        },
        {
            "query": "prescribed information not provided section 213",
            "expected_topics": ["prescribed information", "section 213", "deposit"],
            "expected_case_types": ["HMF", "HTC"],
            "min_confidence": 0.5,
        },
    ]


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "requires_api: marks tests that require external API access"
    )


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment for each test."""
    # Store original environment
    original_env = os.environ.copy()

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
