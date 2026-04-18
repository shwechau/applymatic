#!/usr/bin/env python3
"""
applymatic chat — conversational job application agent
Run: python main_chat.py
"""
import os, sys, json
import anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.prompt import Prompt
    console = Console()
    def print_agent(text): console.print(f"\n[bold cyan]Agent[/bold cyan]"); console.print(Markdown(text))
    def print_tool(text): console.print(f"[dim]⚙ {text}[/dim]")
    def get_input(): return Prompt.ask("\n[bold purple]You[/bold purple]").strip()
except ImportError:
    def print_agent(text): print(f"\nAgent: {text}")
    def print_tool(text): print(f"  → {text}")
    def get_input(): return input("\nYou: ").strip()

WELCOME = """
╭──────────────────────────────────────╮
│        applymatic chat agent         │
│  Type what you want · Ctrl+C to quit │
╰──────────────────────────────────────╯

What I can do:
  • Find matching jobs in the Bay Area
  • Tailor your resume for each role (PDF)
  • Fill out ATS forms automatically
  • Show your application status
"""

def load_profile_text():
    try:
        from core.profile import load_profile
        p = load_profile()
        return f"\nUSER PROFILE:\n- Name: {p.name}\n- Title: {p.current_title}\n- Experience: {p.years_experience}+ years\n- Skills: {', '.join(p.skills[:12])}\n- Location: {p.location}\n"
    except Exception as e:
        return f"\nNo profile found ({e}). Run: python main.py setup\n"

def run_tool(name, args):
    try:
        if name == "search_jobs":
            from core.profile import load_profile
            from agents.agent1_discovery import run_discovery
            profile = load_profile()
            jobs = run_discovery(profile=profile, search_queries=[args.get("query","software engineer")],
                location=args.get("location","San Francisco Bay Area"),
                min_score=args.get("min_score",75), max_results=args.get("max_results",8))
            if not jobs: return "No matching jobs found."
            lines = [f"Found {len(jobs)} jobs:\n"]
            for j in jobs:
                lines.append(f"  [{j.id}] {j.company} — {j.title} (score: {j.match_score:.0f})")
            return "\n".join(lines)

        elif name == "tailor_resume":
            from core.profile import load_profile
            from core.tracker import load_tracker
            from agents.agent2_tailor import run_tailoring
            records = load_tracker()
            record = records.get(args["job_id"])
            if not record: return f"Job {args['job_id']} not found."
            tailored = run_tailoring(profile=load_profile(), job=record.job,
                                     approved_keywords=args.get("approved_keywords"))
            if not tailored: return "Tailoring failed."
            return f"Resume ready: {tailored.filename}\nKeywords: {', '.join(tailored.keyword_matches or [])}"

        elif name == "analyze_keywords":
            from core.profile import load_profile
            from core.tracker import load_tracker
            from agents.agent2_tailor import analyze_keywords_for_consent
            records = load_tracker()
            record = records.get(args["job_id"])
            if not record: return f"Job {args['job_id']} not found."
            result = analyze_keywords_for_consent(load_profile(), record.job)
            return result["consent_message"]

        elif name == "get_status":
            from core.tracker import load_tracker
            records = load_tracker()
            if not records: return "No applications yet."
            lines = [f"Total: {len(records)}\n"]
            for r in sorted(records.values(), key=lambda x: x.job.match_score or 0, reverse=True):
                lines.append(f"  [{r.job.id}] {r.job.company} — {r.job.title} ({r.status.value})")
            return "\n".join(lines)

        elif name == "submit_application":
            from core.tracker import load_tracker, add_or_update
            from agents.agent3_apply import run_application
            records = load_tracker()
            record = records.get(args["job_id"])
            if not record: return f"Job {args['job_id']} not found."
            if not record.resume: return "Tailor resume first."
            result = run_application(record=record, dry_run=args.get("dry_run", True), human_review=True)
            add_or_update(result)
            return f"{'Queued for review' if args.get('dry_run',True) else 'Submitted'}: {result.job.company}"

        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"

TOOLS = [
    {"name": "search_jobs", "description": "Search for matching jobs by role and location", "input_schema": {"type":"object","properties":{"query":{"type":"string"},"location":{"type":"string"},"min_score":{"type":"number"},"max_results":{"type":"integer"}},"required":["query"]}},
    {"name": "tailor_resume", "description": "Tailor resume for a job and generate PDF", "input_schema": {"type":"object","properties":{"job_id":{"type":"string"},"approved_keywords":{"type":"array","items":{"type":"string"}}},"required":["job_id"]}},
    {"name": "analyze_keywords", "description": "Analyze keyword gaps before tailoring resume", "input_schema": {"type":"object","properties":{"job_id":{"type":"string"}},"required":["job_id"]}},
    {"name": "get_status", "description": "Show all tracked applications and their status", "input_schema": {"type":"object","properties":{}}},
    {"name": "submit_application", "description": "Fill and submit ATS application form", "input_schema": {"type":"object","properties":{"job_id":{"type":"string"},"dry_run":{"type":"boolean"}},"required":["job_id"]}},
]

def chat():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    print(WELCOME)

    system = f"""You are the Applymatic job application agent running locally.
{load_profile_text()}
Be concise. Use tools to take real actions. Always analyze_keywords before tailor_resume.
Always confirm before submit_application. Include job IDs in your responses."""

    history = []

    while True:
        try:
            user_input = get_input()
            if not user_input: continue
            history.append({"role": "user", "content": user_input})

            while True:
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1024,
                    system=system,
                    tools=TOOLS,
                    messages=history,
                )

                text = "".join(b.text for b in response.content if b.type == "text")
                tool_uses = [b for b in response.content if b.type == "tool_use"]

                if text: print_agent(text)

                if not tool_uses or response.stop_reason == "end_turn":
                    history.append({"role": "assistant", "content": response.content})
                    break

                history.append({"role": "assistant", "content": response.content})
                tool_results = []
                for t in tool_uses:
                    print_tool(f"Running {t.name}...")
                    result = run_tool(t.name, t.input)
                    print_tool(result)
                    tool_results.append({"type":"tool_result","tool_use_id":t.id,"content":result})
                history.append({"role": "user", "content": tool_results})

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    chat()
