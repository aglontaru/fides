"""Unit tests for semantic extractor."""

from __future__ import annotations

import pytest

from fides.ingestion.chunkers.legislation import LegislationChunk
from fides.ingestion.extractors.semantics import SemanticExtractor


@pytest.mark.unit
def test_semantic_extractor_roles():
    extractor = SemanticExtractor(short_name="MDR")
    result = extractor.extract([])
    role_names = [r.name for r in result.actor_roles]
    assert "Manufacturer" in role_names
    assert "Authorised Representative" in role_names
    assert "Importer" in role_names
    assert "Notified Body" in role_names


@pytest.mark.unit
def test_semantic_extractor_defined_terms():
    extractor = SemanticExtractor(short_name="MDR")
    chunks = [
        LegislationChunk(
            id="MDR:art:2",
            chunk_type="article",
            number="2",
            title="Definitions",
            text=(
                "For the purposes of this Regulation, the following definitions apply:\n"
                "1. 'medical device' means any instrument, apparatus, appliance;\n"
                "3. 'custom-made device' means any device specifically made in accordance with a written prescription;\n"
                "5. 'implantable device' means any device intended to be totally introduced into the human body;\n"
            ),
        ),
        LegislationChunk(
            id="MDR:art:21:para:1",
            chunk_type="paragraph",
            number="1",
            parent_id="MDR:art:21",
            text="Member States shall not create obstacles to custom-made device being made available.",
        ),
    ]
    result = extractor.extract(chunks)
    terms = {t.term: t for t in result.defined_terms}
    assert "custom-made device" in terms
    assert "implantable device" in terms
    assert "medical device" in terms

    # Check DEFINES
    defines_pairs = result.article_defines
    assert ("MDR:art:2", terms["custom-made device"].id) in defines_pairs

    # Check USES_TERM
    uses_pairs = result.paragraph_uses_term
    assert ("MDR:art:21:para:1", terms["custom-made device"].id) in uses_pairs


@pytest.mark.unit
def test_semantic_extractor_obligations_and_exemptions():
    extractor = SemanticExtractor(short_name="MDR")
    chunks = [
        LegislationChunk(
            id="MDR:art:11",
            chunk_type="article",
            number="11",
            title="Authorised representative",
            text="where the manufacturer is not established in a Member State and has not complied with obligations, the authorised representative shall be legally liable for defective devices on the same basis as, and jointly and severally with, the manufacturer.",
        ),
        LegislationChunk(
            id="MDR:art:21",
            chunk_type="article",
            number="21",
            title="Devices for special purposes",
            text="The devices referred to in the first subparagraph shall not bear the CE marking. Custom-made devices shall be accompanied by the statement referred to in Section 1 of Annex XIII.",
        ),
    ]
    result = extractor.extract(chunks)
    obl_ids = [o.id for o in result.obligations]
    assert "MDR:art:11:obl:joint_liability" in obl_ids
    assert "MDR:art:21:obl:ce_marking_exemption" in obl_ids
    assert "MDR:art:21:obl:annex_xiii_statement" in obl_ids

    # Check REFERENCES_ANNEX
    ref_annex = result.article_references_annex
    assert ("MDR:art:21", "MDR:annex:XIII") in ref_annex
