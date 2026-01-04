"""
Knowledge Graph Builder Package

Provides knowledge graph construction and validation
for the legal mediation system.
"""

from .config import KGConfig
from .models.graph import KnowledgeGraph
from .models.nodes import NodeType, BaseNode
from .models.edges import EdgeType, Edge

__all__ = [
    "KGConfig",
    "KnowledgeGraph",
    "NodeType",
    "BaseNode",
    "EdgeType",
    "Edge",
]
