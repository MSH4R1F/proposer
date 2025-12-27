# Changelog

All notable changes to the Proposer legal mediation system will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **BAILII Scraper** - Production-ready async Python scraper for UK First-tier Tribunal decisions
  - Scrapes Property Chamber cases from https://www.bailii.org/uk/cases/UKFTT/PC/
  - Downloads both HTML and PDF for each case
  - Keyword-based categorization (deposit, adjacent, other)
  - SQLite progress tracking with resume capability
  - Rate limiting (1 req/sec) with exponential backoff retries
  - CLI with flexible year selection (`--years`, `--year-range`)

### New Files
- `scripts/scrapers/` - BAILII scraper package
  - `config.py` - Keywords, settings, rate limits
  - `models.py` - Pydantic data models for cases
  - `parsers.py` - HTML parsing for year index and case pages
  - `downloader.py` - Async HTTP client with retries
  - `progress.py` - SQLite progress tracking
  - `bailii_scraper.py` - Main CLI orchestrator
- `scripts/requirements.txt` - Scraper dependencies
- `data/raw/bailii/` - Output directory structure

### Planned Features
- RAG pipeline for tribunal decision retrieval
- Knowledge Graph extraction from case facts
- Hybrid RAG + KG prediction engine
- Shadow mediator for real-time negotiation
- ZOPA (Zone of Possible Agreement) calculation
- Interactive intake chat interface
- Case dashboard with reasoning trace visualization

---

## [0.1.0] - 2024-12-24

### Added
- Initial project structure and repository setup
- Project documentation (README.md, CLAUDE.md, .cursorrules)
- Monorepo architecture with apps/ and packages/ structure
- Development guidelines and coding standards
- Legal safety and compliance guidelines
- .gitignore configuration for Python, Node.js, and sensitive data
- CHANGELOG.md for tracking project updates

### Project Structure
- `apps/api/` - FastAPI backend application
- `apps/web/` - Next.js 14 frontend application
- `apps/workers/` - Background workers for data processing
- `packages/rag-engine/` - RAG pipeline for case retrieval
- `packages/kg-builder/` - Knowledge Graph construction
- `packages/llm-orchestrator/` - LLM agent coordination
- `packages/legal-db/` - Database schemas and migrations
- `packages/shared/` - Shared utilities and types
- `data/` - Data storage (raw, processed, embeddings, test cases)
- `docs/` - Additional documentation
- `scripts/` - Utility scripts for development

### Documentation
- Comprehensive README with project overview and architecture
- CLAUDE.md with technical specifications
- .cursorrules with development guidelines and legal compliance rules

---

## Version History

### Version Numbering Guide
- **MAJOR** version for incompatible API changes or significant architectural shifts
- **MINOR** version for new features in a backward-compatible manner
- **PATCH** version for backward-compatible bug fixes

### Categories
- **Added** - New features
- **Changed** - Changes in existing functionality
- **Deprecated** - Soon-to-be removed features
- **Removed** - Removed features
- **Fixed** - Bug fixes
- **Security** - Vulnerability fixes

---

## Development Phases

### Phase 1: Foundation (Current)
- [ ] Complete project setup and infrastructure
- [ ] Set up development environment
- [ ] Initialize databases (PostgreSQL, ChromaDB, Neo4j)
- [ ] Configure authentication (Supabase Auth)

### Phase 2: Data Pipeline (Sprint 1-2)
- [x] Implement BAILII scraper for tribunal decisions
- [ ] Implement PDF parsing and text extraction
- [ ] Build RAG pipeline with ChromaDB/Pinecone
- [ ] Implement hybrid search (keyword + semantic)
- [ ] Add PII redaction system
- [ ] Create basic prediction engine

### Phase 3: Knowledge Graph (Sprint 3-4)
- [ ] Design and implement KG ontology (Neo4j)
- [ ] Build NLP-based fact extraction
- [ ] Implement constraint validation
- [ ] Integrate hybrid RAG + KG prediction
- [ ] Set up evaluation framework

### Phase 4: Frontend & UX (Sprint 5-6)
- [ ] Build authentication flows
- [ ] Create case dashboard
- [ ] Implement intake chat interface
- [ ] Design reasoning trace visualization
- [ ] Add case status tracking

### Phase 5: Mediation Features (Sprint 7-8)
- [ ] Implement shadow mediator agent
- [ ] Build ZOPA calculation engine
- [ ] Create real-time negotiation interface
- [ ] Add nudge generation system
- [ ] Implement settlement tracking

### Phase 6: Production Readiness
- [ ] Comprehensive testing suite
- [ ] Security audit and penetration testing
- [ ] Performance optimization
- [ ] Legal compliance review
- [ ] User acceptance testing
- [ ] Deployment to Railway

---

## Notes for Developers

### How to Update This Changelog

1. **During Development**: Add unreleased changes under `[Unreleased]` section
2. **On Release**: 
   - Move unreleased changes to a new version section
   - Update the version number and date
   - Add a link to the version comparison at the bottom
3. **Always Include**:
   - Date in YYYY-MM-DD format
   - Clear description of what changed
   - Migration notes if breaking changes
   - Security notes if relevant

### Example Entry
```markdown
## [1.2.0] - 2024-03-15

### Added
- New prediction confidence calibration using Brier Score
- Support for Housing Ombudsman case data in RAG pipeline

### Changed
- Improved LLM prompt for better citation accuracy (breaking: update prompts in config)

### Fixed
- Knowledge Graph extraction failing on cases with missing dates (#42)
- Frontend crash when displaying cases with no evidence (#45)

### Security
- Updated dependencies to patch CVE-2024-12345 in FastAPI
```

---

## Contact & Contributions

For questions about changes or to report issues:
- Check the [README.md](./README.md) for project overview
- Review [CLAUDE.md](./CLAUDE.md) for technical details
- Follow the development guidelines in [.cursorrules](./.cursorrules)

---

**Remember**: This changelog tracks **user-facing changes** and **significant technical milestones**. For detailed commit history, use `git log`.

