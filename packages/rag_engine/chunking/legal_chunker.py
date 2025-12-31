"""
Legal document chunking with section awareness.

Segments tribunal decisions into meaningful chunks while respecting
document structure (Background, Facts, Reasoning, Decision).
"""

import re
from typing import Dict, List, Optional, Tuple

import tiktoken
import structlog

from ..config import CaseDocument, DocumentChunk, SectionType

logger = structlog.get_logger()


class LegalChunker:
    """
    Chunk legal documents with awareness of document structure.

    Attempts to detect sections (Background, Facts, Reasoning, Decision)
    and chunks within those sections while preserving sentence boundaries.
    """

    # Section header patterns for tribunal decisions
    SECTION_PATTERNS = {
        SectionType.BACKGROUND: [
            re.compile(r"^\s*(?:BACKGROUND|INTRODUCTION|THE APPLICATION)\s*$", re.MULTILINE | re.IGNORECASE),
            re.compile(r"^\s*\d+\.\s*(?:BACKGROUND|INTRODUCTION)\s*$", re.MULTILINE | re.IGNORECASE),
        ],
        SectionType.FACTS: [
            re.compile(r"^\s*(?:THE FACTS|FACTS|EVIDENCE|THE EVIDENCE|FINDINGS OF FACT)\s*$", re.MULTILINE | re.IGNORECASE),
            re.compile(r"^\s*\d+\.\s*(?:FACTS|THE FACTS|EVIDENCE)\s*$", re.MULTILINE | re.IGNORECASE),
        ],
        SectionType.REASONING: [
            re.compile(r"^\s*(?:REASONS|THE REASONS|REASONING|THE TRIBUNAL'S REASONS|DISCUSSION)\s*$", re.MULTILINE | re.IGNORECASE),
            re.compile(r"^\s*\d+\.\s*(?:REASONS|REASONING|DISCUSSION)\s*$", re.MULTILINE | re.IGNORECASE),
        ],
        SectionType.DECISION: [
            re.compile(r"^\s*(?:DECISION|THE DECISION|DETERMINATION|ORDER|THE ORDER|CONCLUSION)\s*$", re.MULTILINE | re.IGNORECASE),
            re.compile(r"^\s*\d+\.\s*(?:DECISION|DETERMINATION|ORDER)\s*$", re.MULTILINE | re.IGNORECASE),
        ],
    }

    # Sentence boundary pattern
    SENTENCE_END = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        encoding_name: str = "cl100k_base"
    ) -> None:
        """
        Initialize the chunker.

        Args:
            chunk_size: Target chunk size in tokens
            chunk_overlap: Overlap between chunks in tokens
            encoding_name: Tiktoken encoding for token counting
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.tokenizer = tiktoken.get_encoding(encoding_name)

    def chunk_document(self, doc: CaseDocument) -> List[DocumentChunk]:
        """
        Chunk a case document into smaller pieces.

        Args:
            doc: CaseDocument to chunk

        Returns:
            List of DocumentChunk objects
        """
        # First, try to detect sections
        sections = self._detect_sections(doc.full_text)

        # Store sections in document
        doc.sections = {k.value: v for k, v in sections.items() if v}

        chunks = []
        chunk_index = 0

        for section_type, section_text in sections.items():
            if not section_text.strip():
                continue

            # Chunk this section
            section_chunks = self._chunk_text(
                section_text,
                section_type,
                doc,
                start_index=chunk_index
            )
            chunks.extend(section_chunks)
            chunk_index += len(section_chunks)

        # If no sections detected, chunk the whole document
        if not chunks:
            logger.debug(
                "no_sections_detected",
                case_reference=doc.case_reference,
                text_length=len(doc.full_text)
            )
            chunks = self._chunk_text(
                doc.full_text,
                SectionType.UNKNOWN,
                doc,
                start_index=0
            )

        logger.debug(
            "document_chunked",
            case_reference=doc.case_reference,
            num_chunks=len(chunks),
            sections_found=list(doc.sections.keys())
        )

        return chunks

    def _detect_sections(self, text: str) -> Dict[SectionType, str]:
        """
        Detect and extract sections from document text.

        Returns:
            Dict mapping section types to their text content
        """
        sections = {
            SectionType.BACKGROUND: "",
            SectionType.FACTS: "",
            SectionType.REASONING: "",
            SectionType.DECISION: "",
        }

        # Find all section boundaries
        boundaries: List[Tuple[int, SectionType]] = []

        for section_type, patterns in self.SECTION_PATTERNS.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    boundaries.append((match.start(), section_type))

        # Sort by position
        boundaries.sort(key=lambda x: x[0])

        if not boundaries:
            return sections

        # Extract text between boundaries
        for i, (start_pos, section_type) in enumerate(boundaries):
            # Find the actual start of content (after the header)
            header_match = None
            for pattern in self.SECTION_PATTERNS[section_type]:
                header_match = pattern.search(text[start_pos:start_pos + 200])
                if header_match:
                    break

            content_start = start_pos
            if header_match:
                content_start = start_pos + header_match.end()

            # End is either next boundary or end of text
            if i + 1 < len(boundaries):
                end_pos = boundaries[i + 1][0]
            else:
                end_pos = len(text)

            section_text = text[content_start:end_pos].strip()
            if section_text:
                sections[section_type] = section_text

        return sections

    def _chunk_text(
        self,
        text: str,
        section_type: SectionType,
        doc: CaseDocument,
        start_index: int = 0
    ) -> List[DocumentChunk]:
        """
        Chunk a section of text into overlapping chunks.

        Args:
            text: Text to chunk
            section_type: Type of section
            doc: Parent document
            start_index: Starting chunk index

        Returns:
            List of DocumentChunk objects
        """
        if not text.strip():
            return []

        # Split into sentences first
        sentences = self._split_into_sentences(text)

        chunks = []
        current_chunk_sentences: List[str] = []
        current_token_count = 0
        chunk_index = start_index

        for sentence in sentences:
            sentence_tokens = len(self.tokenizer.encode(sentence))

            # If single sentence exceeds chunk size, split it
            if sentence_tokens > self.chunk_size:
                # Flush current chunk if any
                if current_chunk_sentences:
                    chunk = self._create_chunk(
                        current_chunk_sentences,
                        section_type,
                        doc,
                        chunk_index
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                    current_chunk_sentences = []
                    current_token_count = 0

                # Split long sentence into smaller pieces
                sub_chunks = self._split_long_sentence(sentence, section_type, doc, chunk_index)
                chunks.extend(sub_chunks)
                chunk_index += len(sub_chunks)
                continue

            # Check if adding this sentence exceeds chunk size
            if current_token_count + sentence_tokens > self.chunk_size:
                # Create chunk from current sentences
                chunk = self._create_chunk(
                    current_chunk_sentences,
                    section_type,
                    doc,
                    chunk_index
                )
                chunks.append(chunk)
                chunk_index += 1

                # Start new chunk with overlap
                overlap_sentences = self._get_overlap_sentences(
                    current_chunk_sentences
                )
                current_chunk_sentences = overlap_sentences + [sentence]
                current_token_count = sum(
                    len(self.tokenizer.encode(s)) for s in current_chunk_sentences
                )
            else:
                current_chunk_sentences.append(sentence)
                current_token_count += sentence_tokens

        # Create final chunk
        if current_chunk_sentences:
            chunk = self._create_chunk(
                current_chunk_sentences,
                section_type,
                doc,
                chunk_index
            )
            chunks.append(chunk)

        return chunks

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences, preserving meaning."""
        # Simple sentence splitting
        sentences = self.SENTENCE_END.split(text)

        # Clean up each sentence
        cleaned = []
        for sent in sentences:
            sent = sent.strip()
            if sent:
                cleaned.append(sent)

        return cleaned

    def _get_overlap_sentences(self, sentences: List[str]) -> List[str]:
        """Get sentences to include as overlap in next chunk."""
        if not sentences:
            return []

        overlap_tokens = 0
        overlap_sentences = []

        # Take sentences from end until we hit overlap target
        for sent in reversed(sentences):
            sent_tokens = len(self.tokenizer.encode(sent))
            if overlap_tokens + sent_tokens > self.chunk_overlap:
                break
            overlap_sentences.insert(0, sent)
            overlap_tokens += sent_tokens

        return overlap_sentences

    def _split_long_sentence(
        self,
        sentence: str,
        section_type: SectionType,
        doc: CaseDocument,
        start_index: int
    ) -> List[DocumentChunk]:
        """Split a very long sentence into multiple chunks."""
        tokens = self.tokenizer.encode(sentence)
        chunks = []
        chunk_index = start_index

        for i in range(0, len(tokens), self.chunk_size - self.chunk_overlap):
            chunk_tokens = tokens[i:i + self.chunk_size]
            chunk_text = self.tokenizer.decode(chunk_tokens)

            chunk = DocumentChunk(
                chunk_id=f"{doc.case_reference}_{chunk_index}",
                case_reference=doc.case_reference,
                chunk_index=chunk_index,
                text=chunk_text,
                section_type=section_type,
                year=doc.year,
                region=doc.region,
                case_type=doc.case_type,
                token_count=len(chunk_tokens)
            )
            chunks.append(chunk)
            chunk_index += 1

        return chunks

    def _create_chunk(
        self,
        sentences: List[str],
        section_type: SectionType,
        doc: CaseDocument,
        chunk_index: int
    ) -> DocumentChunk:
        """Create a DocumentChunk from sentences."""
        text = " ".join(sentences)
        token_count = len(self.tokenizer.encode(text))

        return DocumentChunk(
            chunk_id=f"{doc.case_reference}_{chunk_index}",
            case_reference=doc.case_reference,
            chunk_index=chunk_index,
            text=text,
            section_type=section_type,
            year=doc.year,
            region=doc.region,
            case_type=doc.case_type,
            token_count=token_count
        )

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))


def chunk_document(
    doc: CaseDocument,
    chunk_size: int = 500,
    chunk_overlap: int = 50
) -> List[DocumentChunk]:
    """
    Convenience function to chunk a document.

    Args:
        doc: Document to chunk
        chunk_size: Target chunk size in tokens
        chunk_overlap: Overlap between chunks

    Returns:
        List of document chunks
    """
    chunker = LegalChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return chunker.chunk_document(doc)
