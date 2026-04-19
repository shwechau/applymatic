"""
Preferences setup wizard for Applymatic CLI.
Run: python main.py preferences
"""
from rich.console import Console
from rich.prompt import Prompt, Confirm
from recommendations import load_prefs, save_prefs, UserPreferences

console = Console()


def run_preferences_wizard():
    """Interactive wizard to configure user preferences."""
    prefs = load_prefs()

    console.print("\n[bold]Applymatic preferences[/bold]\n")

    # Recommendation mode
    console.print("[cyan]1. Job recommendations[/cyan]")
    console.print("   [dim]on_request[/dim] — only when you ask (default)")
    console.print("   [dim]daily[/dim]      — suggest new jobs automatically each morning\n")
    mode = Prompt.ask("Mode", choices=["on_request", "daily"], default=prefs.recommend_mode)
    prefs.recommend_mode = mode

    if mode == "daily":
        time = Prompt.ask("What time should I send daily recommendations?", default=prefs.recommend_time)
        prefs.recommend_time = time

    # Auto-apply
    console.print(f"\n[cyan]2. Auto-apply[/cyan]")
    console.print("   If ON, I'll apply to jobs automatically without asking each time.")
    console.print("   You can set a minimum score threshold so I only apply to strong matches.\n")
    auto = Confirm.ask("Enable auto-apply?", default=prefs.auto_apply)
    prefs.auto_apply = auto

    if auto:
        score = Prompt.ask("Minimum match score to auto-apply (0-100)", default=str(int(prefs.auto_apply_min_score)))
        prefs.auto_apply_min_score = float(score)
        limit = Prompt.ask("Max applications per day", default=str(prefs.auto_apply_limit_per_day))
        prefs.auto_apply_limit_per_day = int(limit)
        console.print("[yellow]Note: I'll still open the form for your review before submitting.[/yellow]")

    # Excluded companies
    console.print(f"\n[cyan]3. Excluded companies[/cyan]")
    console.print(f"   Currently excluded: {prefs.excluded_companies or 'none'}")
    if Confirm.ask("Add companies to never apply to?", default=False):
        companies = Prompt.ask("Enter company names (comma-separated)")
        new_excl = [c.strip() for c in companies.split(",") if c.strip()]
        prefs.excluded_companies = list(set(prefs.excluded_companies + new_excl))

    # Excluded keywords
    console.print(f"\n[cyan]4. Excluded job title keywords[/cyan]")
    console.print(f"   Currently excluded: {prefs.excluded_keywords or 'none'}")
    console.print("   Example: 'manager, director, ML, intern'")
    if Confirm.ask("Add keywords to exclude from job titles?", default=False):
        keywords = Prompt.ask("Enter keywords (comma-separated)")
        new_kw = [k.strip() for k in keywords.split(",") if k.strip()]
        prefs.excluded_keywords = list(set(prefs.excluded_keywords + new_kw))

    save_prefs(prefs)
    console.print("\n[green]✓ Preferences saved.[/green]")
    console.print(f"  Mode: {prefs.recommend_mode}")
    console.print(f"  Auto-apply: {'ON (score ≥ ' + str(prefs.auto_apply_min_score) + ')' if prefs.auto_apply else 'OFF'}")
    if prefs.excluded_companies:
        console.print(f"  Excluded companies: {', '.join(prefs.excluded_companies)}")
    if prefs.excluded_keywords:
        console.print(f"  Excluded keywords: {', '.join(prefs.excluded_keywords)}")
