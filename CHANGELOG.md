# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project structure with modular architecture
- CRAG workflow implementation with LangGraph
- Dual retrieval system (Vector + Graph)
- Reranker integration with FlagEmbedding
- Multi-turn conversation memory
- Web search fallback with Tavily API

## [1.0.0] - 2024-01-01

### Added
- Core CRAG implementation
- Neo4j graph query service
- FAISS vector store integration
- Grader node for retrieval quality assessment
- Query rewrite node for insufficient results
- Generate node for answer synthesis
- Memory nodes for conversation context
- Web search node as fallback mechanism
- Complete project documentation
