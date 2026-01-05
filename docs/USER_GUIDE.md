# User Guide

## Quick Start

```bash
# Set API keys
export OPENAI_API_KEY=sk-your-key
export ANTHROPIC_API_KEY=sk-ant-your-key

# Start the API
python scripts/api.py
# Visit http://localhost:8000/docs
```

## Ingesting Cases

```bash
# Ingest PDFs
python scripts/rag.py ingest --pdf-dir data/raw/bailii/adjacent-cases

# Check status
python scripts/rag.py stats
```

## Querying

```bash
# Basic query
python scripts/rag.py query "deposit not protected"

# With filters
python scripts/rag.py query "cleaning deduction" --region LON --year 2023
```

## Confidence Scores

| Level | Range | Meaning |
|-------|-------|---------|
| HIGH | 0.7-1.0 | Strong precedents exist |
| MEDIUM | 0.5-0.7 | Some relevant cases |
| LOW | 0.3-0.5 | Limited precedents |
| UNCERTAIN | <0.3 | Seek professional advice |

## Intake Agent

```bash
# Start chat
python scripts/intake.py chat
```

The agent guides you through 10 stages:
1. Greeting → 2. Role → 3. Property → 4. Tenancy → 5. Deposit → 6. Issues → 7. Evidence → 8. Claims → 9. Narrative → 10. Confirmation

## Generating Predictions

Via API:
```bash
curl -X POST http://localhost:8000/predictions/generate \
  -H "Content-Type: application/json" \
  -d '{"case_id": "abc123"}'
```

## Troubleshooting

- **No results**: Check `python scripts/rag.py stats` - index may be empty
- **Low confidence**: Normal for novel cases - seek professional advice
- **API errors**: Check API keys are set correctly
