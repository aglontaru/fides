"""
Universal legal document chunker that understands statutory, regulatory, and contractual structure.
Supports provisions across any jurisdiction (US Code, EU acts, national statutes, contracts, codes).
"""

from __future__ import annotations

import re
from typing import Any

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

# Universal running header/footer patterns to strip across any legal document format
UNIVERSAL_HEADER_PATTERNS = [
    re.compile(r"^\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s*$"),  # Date formats e.g. 5.5.2017, 2024-01-15
    re.compile(r"^\s*(?:Page\s+)?\d+(?:\s*(?:of|/)\s*\d+)?\s*$", re.IGNORECASE),  # Page numbers e.g. "Page 1 of 50", "42"
    re.compile(r"^\s*L\s+\d+/\d+\s*$"),                      # Official gazette refs e.g. L 117/175
    re.compile(r"^\s*(?:Official Journal|Federal Register|Congressional Record|Statutes at Large).*", re.IGNORECASE),
    re.compile(r"^\s*(?:EN|FR|DE|ES|IT)\s*$"),               # Language codes
    re.compile(r"^\s*(?:CONFIDENTIAL|DRAFT|PROPRIETARY)\s*$", re.IGNORECASE),
]

# Keywords indicating statutory derogations, qualifications, or exemptions across any legal system
QUALIFICATION_KEYWORDS = [
    "other than",
    "shall not apply",
    "shall not",
    "exempt",
    "exemption",
    "derogation",
    "exception",
    "except as provided",
    "notwithstanding",
    "subject to",
    "provided that",
    "unless",
    "jointly and severally",
    "liable",
    "liability",
]


class LegislationChunk(BaseModel):
    """A structured provision chunk of a legal document."""

    id: str
    chunk_type: str  # article, section, clause, recital, annex, paragraph, preamble
    number: int | str
    title: str | None = None
    text: str
    parent_id: str | None = None
    children_ids: list[str] = []
    cross_references: list[str] = []
    metadata: dict[str, Any] = {}


class ChunkedLegislation(BaseModel):
    """The complete chunked legal document."""

    document_title: str
    short_name: str
    chunks: list[LegislationChunk]
    hierarchy: dict[str, list[str]]


class LegislationChunker:
    """Universal legal document chunker supporting statutes, regulations, codes, and contracts."""

    # Document division patterns
    TITLE_PATTERN = re.compile(
        r"^\s*TITLE\s+([IVXLCDM0-9]+)\b(?:\s+(.*))?$", re.IGNORECASE
    )
    CHAPTER_PATTERN = re.compile(
        r"^\s*CHAPTER\s+([IVXLCDM0-9]+)\b(?:\s+(.*))?$", re.IGNORECASE
    )
    PART_PATTERN = re.compile(
        r"^\s*PART\s+([IVXLCDM0-9]+)\b(?:\s+(.*))?$", re.IGNORECASE
    )
    SECTION_DIV_PATTERN = re.compile(
        r"^\s*SECTION\s+([IVXLCDM0-9]+)\b(?:\s+(.*))?$", re.IGNORECASE
    )

    # Operative provision patterns (Articles, Sections, Clauses, Rules)
    ARTICLE_HEADING_PATTERN = re.compile(
        r"^\s*(?:Article|Art\.)\s+([0-9]+[a-z]?)\s*$", re.IGNORECASE
    )
    ARTICLE_INLINE_PATTERN = re.compile(
        r"^\s*(?:Article|Art\.)\s+([0-9]+[a-z]?)\s+([A-Z][a-z].*)$"
    )

    SECTION_HEADING_PATTERN = re.compile(
        r"^\s*(?:Section|Sec\.|§|§§)\s*([0-9]+[a-z]?|[IVXLCDM]+)\s*$", re.IGNORECASE
    )
    SECTION_INLINE_PATTERN = re.compile(
        r"^\s*(?:Section|Sec\.|§|§§)\s*([0-9]+[a-z]?|[IVXLCDM]+)\s+([A-Z].*)$"
    )

    CLAUSE_HEADING_PATTERN = re.compile(
        r"^\s*Clause\s+([0-9]+(?:\.[0-9]+)*)\s*$", re.IGNORECASE
    )
    CLAUSE_INLINE_PATTERN = re.compile(
        r"^\s*Clause\s+([0-9]+(?:\.[0-9]+)*)\s+([A-Z].*)$"
    )

    # Annexes, Schedules, Exhibits, Appendices
    SUPPLEMENT_PATTERN = re.compile(
        r"^\s*(?:ANNEX|SCHEDULE|EXHIBIT|APPENDIX)\s+([IVXLCDM0-9]+|[A-Z])\s*$", re.IGNORECASE
    )

    # Sub-provisions
    PARAGRAPH_PATTERN = re.compile(r"^\s*(?:(\d+)\.|(\(\d+\)))\s*(.*)$")
    POINT_PATTERN = re.compile(r"^\s*\(([a-z0-9]+)\)\s+(.*)$")
    RECITAL_PATTERN = re.compile(r"^\s*(?:\((\d+)\)|Whereas\s+)\s*(.*)$", re.IGNORECASE)

    # Universal cross-reference pattern
    CROSS_REF_PATTERN = re.compile(
        r"(?:Article|Art\.|Section|Sec\.|§|Clause|Rule)\s+([0-9]+[a-z]?(?:\s*(?:and|,)\s*[0-9]+[a-z]?)*)",
        re.IGNORECASE,
    )

    def __init__(self, short_name: str, document_title: str) -> None:
        self.short_name = short_name
        self.document_title = document_title

    def extract_cross_references(self, text: str) -> list[str]:
        """Extract cross-references to other provisions from text."""
        refs: list[str] = []
        for match in self.CROSS_REF_PATTERN.finditer(text):
            ref_str = match.group(1).strip()
            parts = re.split(r"\s*(?:and|,)\s*", ref_str)
            for part in parts:
                part = part.strip()
                if part and not part.startswith("("):
                    refs.append(f"{self.short_name}:art:{part}")
        return refs

    def _is_running_header(self, line: str) -> bool:
        """Check if a line matches running header/footer patterns."""
        return any(pattern.match(line) for pattern in UNIVERSAL_HEADER_PATTERNS)

    def _extract_qualification_metadata(self, text: str) -> dict[str, Any]:
        """Tag provisions containing statutory qualifications, exemptions, or liabilities."""
        lower = text.lower()
        matched = [k for k in QUALIFICATION_KEYWORDS if k in lower]
        if matched:
            return {"has_qualifications": True, "qualification_terms": matched}
        return {}

    async def chunk(self, text: str) -> ChunkedLegislation:
        """Chunk any legal document text into a clean hierarchical provision structure."""
        logger.info(f"Chunking universal legal document: {self.short_name}")
        chunks: list[LegislationChunk] = []
        hierarchy: dict[str, list[str]] = {}

        raw_lines = text.split("\n")
        lines = [
            line.strip()
            for line in raw_lines
            if line.strip() and not self._is_running_header(line)
        ]

        current_article: str | None = None
        current_paragraph: str | None = None
        current_supplement: str | None = None

        current_buffer: list[str] = []
        current_node_id: str | None = None
        current_node_type: str | None = None
        current_node_number: str | int = ""
        current_node_title: str | None = None

        root_id = f"{self.short_name}:root"
        hierarchy[root_id] = []

        seen_first_provision = False
        in_supplement_mode = False
        recital_count = 0

        def save_buffer(parent_id: str | None = None) -> None:
            nonlocal current_buffer, current_node_id, current_node_type, current_node_number, current_node_title
            if current_node_id:
                chunk_text = "\n".join(current_buffer).strip()
                if not chunk_text and current_node_type == "article" and current_node_title:
                    chunk_text = current_node_title

                if chunk_text or current_node_type == "article":
                    refs = self.extract_cross_references(chunk_text)
                    meta = self._extract_qualification_metadata(chunk_text)
                    chunk = LegislationChunk(
                        id=current_node_id,
                        chunk_type=current_node_type or "unknown",
                        number=current_node_number,
                        title=current_node_title,
                        text=chunk_text,
                        parent_id=parent_id,
                        cross_references=refs,
                        metadata=meta,
                    )
                    chunks.append(chunk)
                    if parent_id:
                        if parent_id not in hierarchy:
                            hierarchy[parent_id] = []
                        hierarchy[parent_id].append(current_node_id)
            current_buffer = []

        idx = 0
        total_lines = len(lines)

        while idx < total_lines:
            line = lines[idx]

            # 1. Detect Supplement / Annex / Schedule boundary
            supp_match = self.SUPPLEMENT_PATTERN.match(line)
            if supp_match:
                save_buffer(current_article or root_id)
                in_supplement_mode = True
                supp_num = supp_match.group(1).strip()
                current_supplement = f"{self.short_name}:annex:{supp_num}"
                current_article = None
                current_paragraph = None

                supp_title = f"Annex {supp_num}"
                if idx + 1 < total_lines:
                    next_l = lines[idx + 1]
                    if not self.SUPPLEMENT_PATTERN.match(next_l) and not self.ARTICLE_HEADING_PATTERN.match(next_l):
                        supp_title = next_l
                        idx += 1

                current_node_id = current_supplement
                current_node_type = "annex"
                current_node_number = supp_num
                current_node_title = supp_title
                idx += 1
                continue

            # 2. In supplement mode, keep content within supplement
            if in_supplement_mode:
                if current_node_id:
                    current_buffer.append(line)
                idx += 1
                continue

            # 3. Detect Operative Provisions (Articles, Sections, Clauses)
            art_h = self.ARTICLE_HEADING_PATTERN.match(line)
            art_i = self.ARTICLE_INLINE_PATTERN.match(line) if not art_h else None
            sec_h = self.SECTION_HEADING_PATTERN.match(line) if not art_h and not art_i else None
            sec_i = self.SECTION_INLINE_PATTERN.match(line) if not art_h and not art_i and not sec_h else None
            cla_h = self.CLAUSE_HEADING_PATTERN.match(line) if not any([art_h, art_i, sec_h, sec_i]) else None
            cla_i = self.CLAUSE_INLINE_PATTERN.match(line) if not any([art_h, art_i, sec_h, sec_i, cla_h]) else None

            prov_match = art_h or art_i or sec_h or sec_i or cla_h or cla_i
            if prov_match:
                prov_num = prov_match.group(1).strip()
                is_inline = bool(art_i or sec_i or cla_i)

                # Avoid false positives in preambles before the first provision
                if not seen_first_provision and prov_num not in ("1", "101", "1.1", "I"):
                    if current_node_id:
                        current_buffer.append(line)
                    idx += 1
                    continue

                prov_title: str | None = None
                if is_inline:
                    candidate_title = prov_match.group(2).strip()
                    if not candidate_title.endswith(".") and not re.match(
                        r"^(of\s+(the\s+)?(Directive|Regulation|Charter|Treaty|Act|Code)|thereof)",
                        candidate_title,
                        re.IGNORECASE,
                    ):
                        prov_title = candidate_title
                    else:
                        if current_node_id:
                            current_buffer.append(line)
                        idx += 1
                        continue
                else:
                    # Look ahead to next non-heading line for title
                    if idx + 1 < total_lines:
                        next_l = lines[idx + 1]
                        if (
                            not self.ARTICLE_HEADING_PATTERN.match(next_l)
                            and not self.SECTION_HEADING_PATTERN.match(next_l)
                            and not self.CLAUSE_HEADING_PATTERN.match(next_l)
                            and not self.SUPPLEMENT_PATTERN.match(next_l)
                            and not self.PARAGRAPH_PATTERN.match(next_l)
                            and not re.match(
                                r"^(of\s+(the\s+)?(Directive|Regulation|Charter|Treaty|Act|Code)|thereof)",
                                next_l,
                                re.IGNORECASE,
                            )
                        ):
                            prov_title = next_l
                            idx += 1

                seen_first_provision = True
                save_buffer(current_article or root_id)

                current_article = f"{self.short_name}:art:{prov_num}"
                current_node_id = current_article
                current_node_type = "article"
                current_node_number = prov_num
                current_node_title = prov_title or f"Provision {prov_num}"
                current_paragraph = None
                idx += 1
                continue

            # 4. Detect Recitals or Preamble statements (before first provision)
            if not seen_first_provision:
                recital_match = self.RECITAL_PATTERN.match(line)
                if recital_match:
                    r_num_str = recital_match.group(1)
                    r_num = int(r_num_str) if r_num_str and r_num_str.isdigit() else recital_count + 1
                    if r_num == recital_count + 1 or recital_count == 0:
                        save_buffer(root_id)
                        recital_count = r_num
                        text_part = recital_match.group(2).strip()
                        current_node_id = f"{self.short_name}:recital:{r_num}"
                        current_node_type = "recital"
                        current_node_number = r_num
                        current_node_title = f"Recital ({r_num})"
                        current_paragraph = None
                        if text_part:
                            current_buffer.append(text_part)
                        idx += 1
                        continue

            # 5. Detect Paragraphs / Sub-provisions within an operative provision
            para_match = self.PARAGRAPH_PATTERN.match(line)
            if para_match and current_article:
                save_buffer(current_article)
                num = para_match.group(1) or para_match.group(2).strip("()")
                current_paragraph = f"{current_article}:para:{num}"
                current_node_id = current_paragraph
                current_node_type = "paragraph"
                current_node_number = num
                current_node_title = f"Paragraph {num}"
                rest_of_line = para_match.group(3).strip()
                if rest_of_line:
                    current_buffer.append(rest_of_line)
                idx += 1
                continue

            # 6. Regular content lines
            if current_node_id:
                current_buffer.append(line)
            else:
                current_node_id = f"{self.short_name}:preamble"
                current_node_type = "preamble"
                current_node_number = ""
                current_buffer.append(line)

            idx += 1

        # Save final buffer
        save_buffer(current_supplement or current_article or root_id)

        # 7. Aggregate paragraphs into operative provision full_text
        paragraphs_by_article: dict[str, list[LegislationChunk]] = {}
        for c in chunks:
            if c.chunk_type == "paragraph" and c.parent_id:
                paragraphs_by_article.setdefault(c.parent_id, []).append(c)

        for c in chunks:
            if c.chunk_type == "article":
                paras = paragraphs_by_article.get(c.id, [])
                if paras:
                    para_blocks: list[str] = []
                    for p in paras:
                        p_prefix = f"{p.number}."
                        p_text = p.text.strip()
                        if not p_text.startswith(p_prefix):
                            para_blocks.append(f"{p_prefix} {p_text}")
                        else:
                            para_blocks.append(p_text)

                    intro = c.text.strip()
                    title_part = c.title or ""
                    full_parts: list[str] = []
                    if title_part and title_part not in intro:
                        full_parts.append(title_part)
                    if intro and intro != title_part:
                        full_parts.append(intro)
                    full_parts.extend(para_blocks)

                    c.text = "\n\n".join(full_parts).strip()
                    c.children_ids = [p.id for p in paras]
                    c.metadata.update(self._extract_qualification_metadata(c.text))
                else:
                    if c.title and c.title not in c.text:
                        c.text = f"{c.title}\n\n{c.text}".strip()
                    c.metadata.update(self._extract_qualification_metadata(c.text))

        return ChunkedLegislation(
            document_title=self.document_title,
            short_name=self.short_name,
            chunks=chunks,
            hierarchy=hierarchy,
        )


__all__ = [
    "ChunkedLegislation",
    "LegislationChunk",
    "LegislationChunker",
]
