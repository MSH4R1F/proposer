# LLM Orchestrator

Conversational intake agents and prediction engine for the legal mediation system.

## Architecture

```mermaid
flowchart TB
    subgraph Intake["Intake Agent"]
        Chat[User Message] --> Agent[IntakeAgent]
        Agent --> Extract[FactExtractor]
        Extract --> CaseFile[(CaseFile)]
    end

    subgraph Prediction["Prediction Engine"]
        CaseFile --> Query[Build Query]
        Query --> RAG[RAG Pipeline]
        RAG --> Similar[Similar Cases]
        Similar --> LLM[Claude API]
        LLM --> Result[PredictionResult]
    end
```

## Components

| Component | File | Purpose |
|-----------|------|---------|
| **IntakeAgent** | `agents/intake_agent.py` | 10-stage conversational intake |
| **PredictionEngine** | `agents/prediction_agent.py` | RAG + LLM synthesis |
| **ClaudeClient** | `clients/claude_client.py` | Anthropic API wrapper |
| **FactExtractor** | `extractors/fact_extractor.py` | Extract structured facts |

## Data Models

```mermaid
classDiagram
    class CaseFile {
        +str case_id
        +PartyRole user_role
        +PropertyDetails property
        +TenancyDetails tenancy
        +List~EvidenceItem~ evidence
        +List~ClaimedAmount~ claims
        +float completeness_score
    }

    class PredictionResult {
        +str prediction_id
        +OutcomeType overall_outcome
        +float overall_confidence
        +List~IssuePrediction~ issue_predictions
        +List~ReasoningStep~ reasoning_trace
    }
```

## Intake Flow

```mermaid
stateDiagram-v2
    [*] --> Greeting
    Greeting --> Role
    Role --> Property
    Property --> Tenancy
    Tenancy --> Deposit
    Deposit --> Issues
    Issues --> Evidence
    Evidence --> Claims
    Claims --> Narrative
    Narrative --> Confirmation
    Confirmation --> [*]
```

## Usage

### CLI
```bash
python scripts/intake.py chat
```

### Python
```python
from llm_orchestrator import IntakeAgent, ClaudeClient

client = ClaudeClient(api_key="sk-ant-...")
agent = IntakeAgent(llm_client=client, role="tenant")

response = await agent.process_message("I'm disputing my deposit")
print(response.message)
print(f"Stage: {response.state.current_stage}")
```

## Configuration

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key
export LLM_MODEL=claude-sonnet-4-20250514  # default
```
