"""Embedding generation utilities."""

from .base import BaseEmbeddings
from .openai_embeddings import OpenAIEmbeddings

__all__ = ["BaseEmbeddings", "OpenAIEmbeddings"]
