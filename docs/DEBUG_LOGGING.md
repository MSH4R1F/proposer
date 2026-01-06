# Debug Logging Guide

## Overview

Comprehensive debug logging has been added throughout the FastAPI application to help you track the flow of requests, understand system behavior, and diagnose issues quickly.

## What is Structured Logging?

We use **structlog** for structured logging. Unlike traditional logging where you write messages like:
```python
logger.debug(f"Processing message for session {session_id}")
```

Structured logging uses key-value pairs:
```python
logger.debug("processing_message", session_id=session_id, message_length=len(message))
```

**Benefits:**
- Easy to search and filter logs by specific fields
- Machine-readable for log analysis tools
- Consistent format across the application
- Better for debugging production issues

## Log Levels

We use 4 log levels:

1. **DEBUG** (`logger.debug()`) - Detailed information for debugging
   - Function entry/exit
   - Intermediate calculations
   - Configuration values
   - Data transformations

2. **INFO** (`logger.info()`) - Important business events
   - Session created
   - Prediction generated
   - Evidence uploaded
   - Role set

3. **WARNING** (`logger.warning()`) - Potential issues
   - Session not found
   - Invalid file types
   - Missing data
   - Incomplete cases

4. **ERROR** (`logger.error()`) - Actual failures
   - API errors
   - Service failures
   - Exception details

## What's Been Added

### 1. Main Application (`main.py`)

**Startup Logging:**
```
DEBUG: environment_check - Shows which API keys are configured
DEBUG: ensuring_directories - Lists directories being created
DEBUG: configuring_cors - Shows allowed CORS origins
DEBUG: registering_routers - Lists routers being registered
```

**Request Logging:**
```
DEBUG: root_endpoint_accessed - Root "/" endpoint hit
DEBUG: health_check - Health check with service status
```

### 2. Chat Router (`routers/chat.py`)

**Session Start:**
```
DEBUG: start_session_request_received
DEBUG: start_session_success (session_id, stage, greeting_length)
ERROR: start_session_failed (error, error_type)
```

**Message Processing:**
```
DEBUG: send_message_request (session_id, message_length, message_preview)
DEBUG: send_message_success (session_id, stage, completeness, response_length)
ERROR: send_message_failed (session_id, error, error_type)
```

**Role Setting:**
```
DEBUG: set_role_request (session_id, role)
WARNING: invalid_role_attempted (if not tenant/landlord)
DEBUG: set_role_success (session_id, role, stage)
ERROR: set_role_failed (session_id, error)
```

**Session Management:**
```
DEBUG: get_session_request (session_id)
DEBUG: get_session_success (session_id, stage, message_count)
DEBUG: delete_session_request (session_id)
INFO: session_deleted (session_id)
DEBUG: list_sessions_request
DEBUG: list_sessions_success (session_count)
```

### 3. Intake Service (`services/intake_service.py`)

**Initialization:**
```
DEBUG: initializing_intake_service
DEBUG: llm_config_loaded (has_anthropic_key, primary_model, fallback_model)
DEBUG: claude_client_created
DEBUG: intake_agent_created
DEBUG: sessions_dir_ready (path)
INFO: intake_service_initialized
```

**Session Operations:**
```
DEBUG: starting_new_session
DEBUG: conversation_created (session_id, stage, greeting_length)
DEBUG: session_stored_in_memory (session_id, total_sessions)
DEBUG: session_saved_to_disk (session_id)
INFO: intake_session_started (session_id)
```

**Message Processing:**
```
DEBUG: processing_message (session_id, message_length)
DEBUG: session_retrieved (session_id, current_stage, message_count, user_role)
DEBUG: calling_agent_process_message (session_id)
DEBUG: agent_response_received (session_id, response_length, new_stage, completeness)
DEBUG: session_updated_in_memory (session_id)
DEBUG: session_saved_after_message (session_id)
```

**Role Setting:**
```
DEBUG: setting_role (session_id, role)
DEBUG: session_retrieved_for_role (session_id, current_stage)
DEBUG: party_role_created (session_id, party_role)
DEBUG: calling_agent_set_user_role (session_id)
DEBUG: agent_role_response_received (session_id, response_length, new_stage)
INFO: intake_role_set (session_id, role, stage)
```

**Session Persistence:**
```
DEBUG: attempting_load_session (session_id, path)
DEBUG: session_file_not_found (session_id, path)
DEBUG: reading_session_file (session_id)
DEBUG: validating_session_data (session_id)
DEBUG: session_loaded_successfully (session_id, stage, message_count)
ERROR: session_load_failed (session_id, error, error_type)
```

### 4. Evidence Router (`routers/evidence.py`)

```
DEBUG: upload_evidence_request (case_id, evidence_type, filename, content_type)
WARNING: invalid_file_type_rejected (case_id, content_type, filename)
DEBUG: uploading_to_storage (case_id, evidence_type)
INFO: evidence_uploaded (case_id, evidence_id, evidence_type, filename)
ERROR: evidence_upload_failed (case_id, error)

DEBUG: list_evidence_request (case_id)
DEBUG: list_evidence_success (case_id, evidence_count)

DEBUG: delete_evidence_request (case_id, evidence_id)
INFO: evidence_deleted (case_id, evidence_id)
```

### 5. Predictions Router (`routers/predictions.py`)

```
DEBUG: generate_prediction_request (case_id, include_reasoning)
DEBUG: checking_case_ready (case_id)
DEBUG: case_status_checked (exists, is_complete, completeness)
WARNING: case_incomplete_for_prediction (case_id, completeness, missing_info)
DEBUG: calling_prediction_service (case_id)
INFO: prediction_generated (case_id, prediction_id, outcome, confidence)
ERROR: generate_prediction_failed (case_id, error)

DEBUG: get_prediction_request (prediction_id)
WARNING: prediction_not_found (prediction_id)
DEBUG: prediction_retrieved (prediction_id)

DEBUG: list_predictions_for_case_request (case_id)
DEBUG: list_predictions_success (case_id, prediction_count)
```

### 6. Cases Router (`routers/cases.py`)

```
DEBUG: get_case_request (case_id)
WARNING: case_not_found (case_id)
DEBUG: case_retrieved (case_id, user_role, intake_complete, completeness)

DEBUG: get_case_full_request (case_id)
DEBUG: case_full_retrieved (case_id)

DEBUG: list_cases_request
DEBUG: list_cases_success (case_count)

DEBUG: delete_case_request (case_id)
INFO: case_deleted (case_id)
```

### 7. Configuration (`config.py`)

```
DEBUG: loading_config_from_env (debug, host, port, has_anthropic_key, has_openai_key)
DEBUG: creating_directories (data_dir, sessions_dir, kg_dir)
DEBUG: directories_created
```

## How to Use Debug Logs

### 1. Viewing Logs in Development

When you run your API with:
```bash
cd apps/api
python src/main.py
```

You'll see colored, structured logs in your terminal thanks to `structlog.dev.ConsoleRenderer`.

### 2. Filtering Logs

Since logs are structured, you can grep for specific events:

**Find all session operations:**
```bash
python src/main.py 2>&1 | grep "session_id"
```

**Find all errors:**
```bash
python src/main.py 2>&1 | grep "error"
```

**Track a specific session:**
```bash
python src/main.py 2>&1 | grep "session_id=abc-123"
```

### 3. Understanding the Flow

Let's trace a typical chat conversation:

```
1. DEBUG: start_session_request_received
2. DEBUG: starting_new_session
3. DEBUG: llm_config_loaded
4. DEBUG: conversation_created (session_id=xxx)
5. DEBUG: session_stored_in_memory (total_sessions=1)
6. DEBUG: session_saved_to_disk
7. INFO: intake_session_started (session_id=xxx)
8. DEBUG: start_session_success (session_id=xxx, stage=greeting)
```

Then when user sets role:
```
9. DEBUG: set_role_request (session_id=xxx, role=tenant)
10. DEBUG: setting_role (session_id=xxx, role=tenant)
11. DEBUG: session_retrieved_for_role (current_stage=greeting)
12. DEBUG: calling_agent_set_user_role
13. DEBUG: agent_role_response_received (new_stage=basic_facts)
14. INFO: intake_role_set (session_id=xxx, role=tenant, stage=basic_facts)
15. DEBUG: set_role_success (session_id=xxx, role=tenant, stage=basic_facts)
```

### 4. Debugging Issues

**Problem: Session not found error**

Look for:
```
DEBUG: get_session_request (session_id=xxx)
DEBUG: getting_session (session_id=xxx)
DEBUG: session_not_in_memory_trying_disk (session_id=xxx)
DEBUG: attempting_load_session (session_id=xxx, path=/path/to/file)
DEBUG: session_file_not_found (session_id=xxx)
ERROR: session_not_found_for_message (session_id=xxx)
```

This tells you: session wasn't in memory, tried disk, file doesn't exist.

**Problem: LLM call failing**

Look for:
```
DEBUG: calling_agent_process_message (session_id=xxx)
ERROR: send_message_failed (session_id=xxx, error=API key invalid, error_type=APIError)
```

This tells you: the agent call failed with an API key error.

## Best Practices

### 1. Always Include Context

Good logs include relevant identifiers:
```python
logger.debug("message_processed", 
             session_id=session_id,
             user_role=user_role,
             stage=stage)
```

### 2. Log Before and After Important Operations

```python
logger.debug("calling_prediction_service", case_id=case_id)
prediction = await prediction_service.generate()
logger.info("prediction_generated", case_id=case_id, prediction_id=prediction.id)
```

### 3. Log Errors with Full Context

```python
try:
    result = await do_something()
except Exception as e:
    logger.error("operation_failed",
                 context_id=context_id,
                 error=str(e),
                 error_type=type(e).__name__)
    raise
```

### 4. Use Meaningful Event Names

- Use `snake_case` for event names
- Make them searchable and descriptive
- Use verbs for actions: `processing_message`, `session_created`
- Use past tense for completion: `message_processed`, `session_created`

## Production Logging

In production, you might want to:

1. **Change the Renderer** - Switch from colored console to JSON:
```python
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),  # JSON instead of console
    ],
    # ... rest of config
)
```

2. **Filter by Log Level** - Only show INFO and above:
```python
import logging
logging.basicConfig(level=logging.INFO)
```

3. **Send to Log Aggregation** - Use services like:
   - **Datadog** - For comprehensive monitoring
   - **CloudWatch** - If hosting on AWS
   - **Railway Logs** - Built-in for Railway deployments

## Common Scenarios

### Debugging a Failed Chat Message

1. Check the request arrived: Look for `send_message_request`
2. Check session was found: Look for `session_retrieved` 
3. Check agent was called: Look for `calling_agent_process_message`
4. Check response: Look for `agent_response_received` or error
5. Check save: Look for `session_saved_after_message`

### Tracking Session Lifecycle

1. **Creation**: `start_session_request` → `conversation_created` → `intake_session_started`
2. **Usage**: Multiple `send_message_request` → `message_processed`
3. **Persistence**: `session_saved_to_disk` after each operation
4. **Loading**: `attempting_load_session` when retrieving from disk
5. **Deletion**: `delete_session_request` → `session_deleted`

### Understanding Performance

Look at the timestamp gaps between related events:
```
2026-01-06T11:33:20.606 [debug] calling_agent_process_message
2026-01-06T11:33:22.295 [debug] agent_response_received
```
This shows the LLM call took ~1.7 seconds.

## Tips for Development

1. **Keep terminal visible** while testing to see logs in real-time
2. **Use grep** to filter noise: `python main.py 2>&1 | grep "session_id=xxx"`
3. **Check error_type** to identify exception classes
4. **Follow session_id** through the entire flow to understand user journey
5. **Look for WARNING logs** to catch potential issues before they become errors

## Need Help?

If logs aren't showing what you expect:

1. Check log level is set to DEBUG
2. Verify structlog is configured in `main.py`
3. Check if the code path you're testing is actually being executed
4. Add temporary print statements if needed
5. Use Python debugger (`import pdb; pdb.set_trace()`) for interactive debugging

## Examples

### Example 1: Successful Chat Flow
```
2026-01-06T11:33:20.606 [info] api_starting host=0.0.0.0 port=8000
2026-01-06T11:33:20.607 [debug] environment_check anthropic_key_set=True openai_key_set=True
2026-01-06T11:33:20.608 [debug] routers_registered
2026-01-06T11:33:22.123 [debug] start_session_request_received
2026-01-06T11:33:22.125 [debug] conversation_created session_id=abc-123 stage=greeting
2026-01-06T11:33:22.127 [info] intake_session_started session_id=abc-123
2026-01-06T11:33:22.128 [debug] start_session_success session_id=abc-123
```

### Example 2: Error Flow
```
2026-01-06T11:35:10.123 [debug] send_message_request session_id=xyz-789 message_length=50
2026-01-06T11:35:10.124 [debug] getting_session session_id=xyz-789
2026-01-06T11:35:10.125 [debug] session_not_in_memory_trying_disk session_id=xyz-789
2026-01-06T11:35:10.126 [debug] session_file_not_found session_id=xyz-789
2026-01-06T11:35:10.127 [error] session_not_found_for_message session_id=xyz-789
2026-01-06T11:35:10.128 [error] send_message_failed session_id=xyz-789 error="Session not found: xyz-789" error_type=ValueError
```

---

**Remember**: Good logging is essential for understanding your system in production. These debug logs will help you diagnose issues quickly and understand how your application behaves under different conditions.

