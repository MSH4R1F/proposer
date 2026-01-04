"""
CLI for testing the LLM orchestrator.

Provides interactive chat interface and testing commands.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

import click
import structlog

from .config import LLMConfig
from .clients.claude_client import ClaudeClient
from .agents.intake_agent import IntakeAgent
from .models.case_file import PartyRole
from .models.conversation import ConversationState

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def run_async(coro):
    """Run an async function synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, verbose):
    """LLM Orchestrator CLI - Test intake agents and prediction engine."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config"] = LLMConfig.from_env()


@cli.command()
@click.option("--role", type=click.Choice(["tenant", "landlord"]), help="Pre-set user role")
@click.option("--save", type=click.Path(), help="Save conversation to file")
@click.pass_context
def chat(ctx, role: Optional[str], save: Optional[str]):
    """
    Start an interactive intake chat session.

    Chat with the intake agent to test the conversation flow.
    Type 'quit' or 'exit' to end the session.
    Type 'status' to see current case file state.
    Type 'save' to save the case file.
    """
    config = ctx.obj["config"]

    if not config.anthropic_api_key:
        click.echo("Error: ANTHROPIC_API_KEY not set in environment", err=True)
        return

    # Initialize components
    llm_client = ClaudeClient(api_key=config.anthropic_api_key)
    agent = IntakeAgent(llm_client)

    # Pre-set role if provided
    user_role = PartyRole(role) if role else None

    click.echo("\n" + "=" * 60)
    click.echo("  Tenancy Deposit Dispute - Intake Agent")
    click.echo("=" * 60)
    click.echo("\nCommands: 'quit', 'status', 'save', 'export'")
    click.echo("-" * 60 + "\n")

    # Start conversation
    greeting, conversation = run_async(agent.start_conversation(user_role))
    click.echo(f"Agent: {greeting}\n")

    # Chat loop
    while True:
        try:
            user_input = click.prompt("You", default="", show_default=False)

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() in ("quit", "exit", "q"):
                click.echo("\nEnding session...")
                break

            if user_input.lower() == "status":
                _print_status(conversation)
                continue

            if user_input.lower() == "save":
                _save_case_file(conversation, save)
                continue

            if user_input.lower() == "export":
                _export_conversation(conversation)
                continue

            # Process message
            response, conversation = run_async(
                agent.process_message(conversation, user_input)
            )

            click.echo(f"\nAgent: {response}\n")

            # Check if complete
            if conversation.is_complete:
                click.echo("\n" + "=" * 60)
                click.echo("  Intake Complete!")
                click.echo("=" * 60)
                _print_status(conversation)

                if click.confirm("\nWould you like to save the case file?"):
                    _save_case_file(conversation, save)

                break

        except KeyboardInterrupt:
            click.echo("\n\nSession interrupted.")
            break
        except Exception as e:
            logger.error("chat_error", error=str(e))
            click.echo(f"\nError: {e}\n", err=True)

    # Print final stats
    click.echo("\nSession Stats:")
    stats = agent.get_stats()
    click.echo(f"  Messages processed: {stats['messages_processed']}")
    if "llm_stats" in stats and stats["llm_stats"]:
        llm_stats = stats["llm_stats"]
        click.echo(f"  LLM calls: {llm_stats.get('calls', 0)}")
        click.echo(f"  Tokens: {llm_stats.get('tokens_in', 0)} in, {llm_stats.get('tokens_out', 0)} out")
        if llm_stats.get("estimated_cost_usd"):
            click.echo(f"  Estimated cost: ${llm_stats['estimated_cost_usd']:.4f}")


@cli.command()
@click.argument("case_file", type=click.Path(exists=True))
@click.pass_context
def analyze(ctx, case_file: str):
    """
    Analyze a saved case file.

    Loads a case file and shows its analysis.
    """
    try:
        with open(case_file) as f:
            data = json.load(f)

        from .models.case_file import CaseFile
        cf = CaseFile.model_validate(data)

        click.echo("\n" + "=" * 60)
        click.echo(f"  Case Analysis: {cf.case_id}")
        click.echo("=" * 60)

        click.echo(f"\nRole: {cf.user_role.value}")
        click.echo(f"Property: {cf.property.address or 'Not provided'}")
        click.echo(f"Tenancy: {cf.tenancy.start_date} - {cf.tenancy.end_date or 'ongoing'}")
        click.echo(f"Deposit: £{cf.tenancy.deposit_amount or 'N/A'}")

        if cf.tenancy.deposit_protected is not None:
            status = "Protected" if cf.tenancy.deposit_protected else "NOT PROTECTED"
            click.echo(f"Protection Status: {status}")

        if cf.issues:
            click.echo(f"\nDispute Issues:")
            for issue in cf.issues:
                click.echo(f"  - {issue.value}")

        if cf.evidence:
            click.echo(f"\nEvidence:")
            for ev in cf.evidence:
                click.echo(f"  - {ev.type.value}: {ev.description}")

        click.echo(f"\nCompleteness: {cf.completeness_score:.0%}")

        missing = cf.get_missing_required_info()
        if missing:
            click.echo(f"Missing Info: {', '.join(missing)}")

        # Show query string for RAG
        query = cf.to_query_string()
        click.echo(f"\nRAG Query Preview:")
        click.echo(f"  {query[:200]}...")

    except Exception as e:
        click.echo(f"Error loading case file: {e}", err=True)


@cli.command()
@click.pass_context
def test_connection(ctx):
    """Test connection to Claude API."""
    config = ctx.obj["config"]

    if not config.anthropic_api_key:
        click.echo("Error: ANTHROPIC_API_KEY not set", err=True)
        return

    click.echo("Testing Claude API connection...")

    try:
        client = ClaudeClient(api_key=config.anthropic_api_key)
        response = run_async(client.generate(
            messages=[{"role": "user", "content": "Hello, please respond with 'Connection successful!'"}],
            system_prompt="You are a helpful assistant. Respond briefly.",
            max_tokens=50,
        ))

        click.echo(f"Response: {response}")
        click.echo("\nConnection successful!")

        stats = client.get_stats()
        click.echo(f"Tokens used: {stats['tokens_in']} in, {stats['tokens_out']} out")

    except Exception as e:
        click.echo(f"Connection failed: {e}", err=True)


def _print_status(conversation: ConversationState):
    """Print current conversation status."""
    cf = conversation.case_file

    click.echo("\n" + "-" * 40)
    click.echo("Current Case Status")
    click.echo("-" * 40)

    click.echo(f"Session ID: {conversation.session_id}")
    click.echo(f"Stage: {conversation.current_stage.value}")
    click.echo(f"Messages: {len(conversation.messages)}")
    click.echo(f"Completeness: {cf.completeness_score:.0%}")

    click.echo(f"\nRole: {cf.user_role.value}")

    if cf.property.address:
        click.echo(f"Property: {cf.property.address}")

    if cf.tenancy.deposit_amount:
        click.echo(f"Deposit: £{cf.tenancy.deposit_amount}")

    if cf.tenancy.deposit_protected is not None:
        status = "Yes" if cf.tenancy.deposit_protected else "NO"
        click.echo(f"Protected: {status}")

    if cf.issues:
        click.echo(f"Issues: {', '.join(i.value for i in cf.issues)}")

    if cf.evidence:
        click.echo(f"Evidence: {len(cf.evidence)} items")

    missing = cf.get_missing_required_info()
    if missing:
        click.echo(f"\nMissing: {', '.join(missing)}")

    click.echo("-" * 40 + "\n")


def _save_case_file(conversation: ConversationState, filepath: Optional[str]):
    """Save the case file to a JSON file."""
    cf = conversation.case_file

    if filepath:
        path = Path(filepath)
    else:
        path = Path(f"case_{cf.case_id}.json")

    data = cf.model_dump(mode="json")

    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    click.echo(f"Case file saved to: {path}")


def _export_conversation(conversation: ConversationState):
    """Export the full conversation to JSON."""
    path = Path(f"conversation_{conversation.session_id}.json")

    data = conversation.model_dump(mode="json")

    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    click.echo(f"Conversation exported to: {path}")


if __name__ == "__main__":
    cli()
