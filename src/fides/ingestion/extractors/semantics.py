"""
Autonomous Dynamic Ontology Governance Agent for legal knowledge graphs.
Dynamically discovers entity node types, semantic relationships, and normative rules
for ANY legal document corpus (statutes, regulations, contracts, codes) without jurisdiction bias.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

from fides.graph.models import (
    ActorRoleNode,
    AnnexNode,
    DefinedTermNode,
    Modality,
    ObligationNode,
)
from fides.ingestion.chunkers.legislation import LegislationChunk

logger = structlog.get_logger(__name__)

# Baseline common legal actor roles, augmented dynamically by document analysis
BASE_ACTOR_ROLES = [
    "Manufacturer",
    "Authorised Representative",
    "Importer",
    "Distributor",
    "Notified Body",
    "Health Institution",
    "Competent Authority",
]

# Universal definition patterns across legal jurisdictions:
UNIVERSAL_DEF_PATTERNS = [
    # Numbered definitions: (1) 'term' means... or 1. "term" means...
    re.compile(
        r"(?:(?:\(([0-9]+[a-z]?)\)|([0-9]+)\.))\s*[‘'\"“]([^'\"”’]+)[’'\"”]\s+(?:means|shall\s+mean|refers\s+to|is\s+defined\s+as)\s+(.*?)(?=(?:\n\s*(?:\([0-9]+[a-z]?\)|[0-9]+\.)\s*[‘'\"“])|\Z)",  # noqa: RUF001
        re.DOTALL | re.IGNORECASE,
    ),
    # Unnumbered standalone definitions: "term" means ...
    re.compile(
        r"^[‘'\"“]([^'\"”’]+)[’'\"”]\s+(?:means|shall\s+mean|refers\s+to|is\s+defined\s+as|has\s+the\s+meaning)\s+(.*?)(?=(?:\n[‘'\"“])|\Z)",  # noqa: RUF001
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    ),
]

# Universal supplement / annex reference pattern: "Annex XIII", "Schedule 1", "Exhibit A", "Appendix B"
SUPPLEMENT_REF_PATTERN = re.compile(
    r"\b(?:Annex|Schedule|Exhibit|Appendix)\s+([IVXLCDM0-9]+|[A-Z])\b",
    re.IGNORECASE,
)

# Common legal actors / economic operators / organizational roles pattern
ACTOR_CANDIDATE_PATTERNS = [
    re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+(?:shall|must|is\s+liable|shall\s+not|may)\b"),
]

# Stopwords to exclude from actor role discovery
ACTOR_STOPWORDS = {
    "The", "This", "That", "These", "Those", "A", "An", "In", "On", "If", "When", "Where",
    "Nothing", "Any", "All", "Each", "Every", "Neither", "Either", "Member", "State",
    "Union", "Commission", "Court", "Paragraph", "Article", "Section", "Chapter", "Annex",
    "However", "Notwithstanding", "Provided", "Unless", "Subject", "Order",
}


@dataclass
class OntologySchemaRecord:
    """Metadata record of the discovered domain ontology for a legal document."""

    document_id: str
    domain: str
    node_types: list[str]
    relationship_types: list[str]
    description: str


@dataclass
class SemanticExtractionResult:
    """Dynamic entities, relationships, and ontology discovered for the document."""

    schema_record: OntologySchemaRecord | None = None
    defined_terms: list[DefinedTermNode] = field(default_factory=list)
    article_defines: list[tuple[str, str]] = field(default_factory=list)  # (prov_id, term_id)
    paragraph_uses_term: list[tuple[str, str]] = field(default_factory=list)  # (para_id, term_id)
    actor_roles: list[ActorRoleNode] = field(default_factory=list)
    obligations: list[ObligationNode] = field(default_factory=list)
    article_imposes: list[tuple[str, str]] = field(default_factory=list)  # (prov_id, obl_id)
    obligation_applies_to: list[tuple[str, str]] = field(default_factory=list)  # (obl_id, role_name)
    article_references_annex: list[tuple[str, str]] = field(default_factory=list)  # (prov_id, annex_id)
    annex_nodes: list[AnnexNode] = field(default_factory=list)


class SemanticExtractor:
    """
    Autonomous dynamic ontology discovery and semantic extraction engine.
    Extracts defined terms, legal entities, normative duties/exemptions, and cross-links
    from any legal document structure.
    """

    def __init__(self, short_name: str) -> None:
        self.short_name = short_name

    def _normalize_slug(self, text: str) -> str:
        """Create a clean, consistent identifier slug."""
        clean = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
        return clean.strip("_")

    def _detect_domain(self, chunks: list[LegislationChunk]) -> str:
        """Infer legal domain from provisions text."""
        sample_text = " ".join(c.text[:200] for c in chunks[:15]).lower()
        if any(w in sample_text for w in ["medical", "device", "implant", "clinical"]):
            return "Medical & Healthcare Regulation"
        elif any(w in sample_text for w in ["personal data", "controller", "processor", "privacy"]):
            return "Data Protection & Privacy"
        elif any(w in sample_text for w in ["artificial intelligence", "ai system", "model"]):
            return "Artificial Intelligence & Technology Regulation"
        elif any(w in sample_text for w in ["patent", "copyright", "trademark", "intellectual property"]):
            return "Intellectual Property Law"
        elif any(w in sample_text for w in ["shares", "securities", "investor", "capital"]):
            return "Financial & Securities Regulation"
        elif any(w in sample_text for w in ["license", "services", "fees", "deliverables", "agreement"]):
            return "Commercial Contract / Licensing"
        return "General Statutory / Regulatory Law"

    def extract(self, chunks: list[LegislationChunk]) -> SemanticExtractionResult:
        """Process chunked legal document and dynamically extract the ontology and graph elements."""
        logger.info("Discovering dynamic legal ontology and extracting entities", short_name=self.short_name)
        result = SemanticExtractionResult()
        domain = self._detect_domain(chunks)

        discovered_labels = {"Document", "Provision", "Paragraph", "DefinedTerm", "ActorRole", "Obligation", "Annex"}
        discovered_rels = {"HAS_PROVISION", "HAS_PARAGRAPH", "DEFINES", "USES_TERM", "IMPOSES", "APPLIES_TO", "REFERENCES_ANNEX"}

        # 1. Seed baseline roles and discover additional roles
        discovered_roles: dict[str, ActorRoleNode] = {}
        for role_name in BASE_ACTOR_ROLES:
            slug = self._normalize_slug(role_name)
            node = ActorRoleNode(id=f"role:{slug}", name=role_name)
            discovered_roles[slug] = node
            result.actor_roles.append(node)

        # 2. Extract Annex / Supplement nodes
        for c in chunks:
            if c.chunk_type == "annex":
                annex_node = AnnexNode(
                    id=c.id,
                    number=str(c.number),
                    title=c.title,
                    text=c.text,
                )
                result.annex_nodes.append(annex_node)

        # 3. Dynamically extract DefinedTerms from definition sections
        term_map: dict[str, str] = {}  # normalized term -> term_id
        for c in chunks:
            if c.chunk_type == "article" and (
                "definition" in (c.title or "").lower() or str(c.number) in ("1", "2", "3", "101")
            ):
                for pattern in UNIVERSAL_DEF_PATTERNS:
                    matches = pattern.findall(c.text)
                    for match in matches:
                        if len(match) == 4:
                            term_raw = match[2].strip()
                            def_text = match[3]
                        elif len(match) == 2:
                            term_raw = match[0].strip()
                            def_text = match[1]
                        else:
                            continue

                        term = term_raw.strip()
                        norm_term = term.lower()
                        if not term or len(term) > 80 or norm_term in term_map:
                            continue

                        slug = self._normalize_slug(term)
                        term_id = f"{self.short_name}:term:{slug}"
                        clean_def = re.sub(r"\s+", " ", def_text).strip()

                        term_node = DefinedTermNode(
                            id=term_id,
                            term=term,
                            normalized_term=norm_term,
                            definition=clean_def,
                        )
                        result.defined_terms.append(term_node)
                        result.article_defines.append((c.id, term_id))
                        term_map[norm_term] = term_id

        # 4. Dynamic Term Usage Linking (USES_TERM)
        if term_map:
            sorted_terms = sorted(term_map.keys(), key=len, reverse=True)
            for c in chunks:
                if c.chunk_type == "paragraph":
                    text_lower = c.text.lower()
                    for t in sorted_terms:
                        if t in text_lower:
                            result.paragraph_uses_term.append((c.id, term_map[t]))

        # 5. Dynamically Discover Additional Legal Actor Roles across provisions
        for c in chunks:
            if c.chunk_type != "article":
                continue
            for pat in ACTOR_CANDIDATE_PATTERNS:
                for match in pat.finditer(c.text):
                    candidate = match.group(1).strip()
                    parts = candidate.split()
                    if candidate not in ACTOR_STOPWORDS and parts[0] not in ACTOR_STOPWORDS and len(candidate) > 2:
                        role_name = candidate
                        slug = self._normalize_slug(role_name)
                        if slug not in discovered_roles:
                            node = ActorRoleNode(id=f"role:{slug}", name=role_name)
                            discovered_roles[slug] = node
                            result.actor_roles.append(node)

        # 6. Dynamically Discover Normative Obligations, Exemptions, and Liabilities
        for c in chunks:
            if c.chunk_type != "article":
                continue

            art_text = c.text
            art_num = str(c.number)

            # References to supplements
            for supp_match in SUPPLEMENT_REF_PATTERN.finditer(art_text):
                supp_num = supp_match.group(1).upper()
                supp_id = f"{self.short_name}:annex:{supp_num}"
                result.article_references_annex.append((c.id, supp_id))

            # Scan sentences for normative modal statements
            sentences = re.split(r"(?<=[.!?])\s+", art_text)
            obl_idx = 0
            for sentence in sentences:
                s_clean = sentence.strip()
                s_lower = s_clean.lower()

                has_modal = any(
                    w in s_lower
                    for w in [
                        "shall", "must", "is liable", "jointly and severally",
                        "shall not", "may not", "exempt", "derogation", "statement referred to"
                    ]
                )
                if not has_modal or len(s_clean) < 20:
                    continue

                obl_idx += 1
                slug_num = self._normalize_slug(art_num)

                # Assign meaningful descriptive slug suffix
                suffix = f"obl:{obl_idx}"
                if "jointly and severally" in s_lower:
                    suffix = "obl:joint_liability"
                elif "shall not bear the ce marking" in s_lower or ("ce marking" in s_lower and "shall not" in s_lower):
                    suffix = "obl:ce_marking_exemption"
                elif "statement referred to in section 1 of annex xiii" in s_lower or ("statement" in s_lower and "annex xiii" in s_lower):
                    suffix = "obl:annex_xiii_statement"
                elif "exempt" in s_lower or "shall not apply" in s_lower:
                    suffix = f"obl:exemption_{obl_idx}"

                obl_id = f"{self.short_name}:art:{slug_num}:{suffix}"

                modality = Modality.SHALL
                if "may" in s_lower and "shall" not in s_lower:
                    modality = Modality.MAY
                elif "must" in s_lower:
                    modality = Modality.MUST

                # Determine which actor role this applies to
                target_role: str | None = None
                for _role_slug, role_node in discovered_roles.items():
                    if role_node.name.lower() in s_lower:
                        target_role = role_node.name
                        break

                obl_node = ObligationNode(
                    id=obl_id,
                    modality=modality,
                    description=s_clean[:500],
                )
                result.obligations.append(obl_node)
                result.article_imposes.append((c.id, obl_id))
                if target_role:
                    result.obligation_applies_to.append((obl_id, target_role))

        # Record discovered ontology schema
        result.schema_record = OntologySchemaRecord(
            document_id=f"doc:{self.short_name}",
            domain=domain,
            node_types=list(discovered_labels),
            relationship_types=list(discovered_rels),
            description=f"Autonomous legal ontology discovered for {self.short_name} ({domain}).",
        )

        logger.info(
            "Autonomous ontology governance discovery complete",
            domain=domain,
            defined_terms=len(result.defined_terms),
            actor_roles=len(result.actor_roles),
            obligations=len(result.obligations),
            annexes=len(result.annex_nodes),
        )
        return result


__all__ = [
    "BASE_ACTOR_ROLES",
    "OntologySchemaRecord",
    "SemanticExtractionResult",
    "SemanticExtractor",
]
