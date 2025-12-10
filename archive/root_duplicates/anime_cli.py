#!/usr/bin/env python3
"""
Anime Production CLI - Interactive Storyline Management
Command-line interface for the Tower Anime Production storyline system
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import click
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax

# Add the source directory to path for imports
sys.path.append(str(Path(__file__).parent / "src"))

console = Console()

# Configuration
API_BASE = "http://localhost:8328"
HEADERS = {"Content-Type": "application/json"}

class AnimeAPI:
    """API client for anime production system"""

    def __init__(self, base_url: str = API_BASE):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get(self, endpoint: str) -> requests.Response:
        """Make GET request to API"""
        return self.session.get(f"{self.base_url}{endpoint}")

    def post(self, endpoint: str, data: Dict = None) -> requests.Response:
        """Make POST request to API"""
        return self.session.post(f"{self.base_url}{endpoint}", json=data or {})

    def health_check(self) -> bool:
        """Check if API is healthy"""
        try:
            response = self.get("/api/health")
            return response.status_code == 200
        except:
            return False

api = AnimeAPI()

def handle_api_error(response: requests.Response, operation: str = "operation"):
    """Handle API errors with user-friendly messages"""
    if response.status_code == 404:
        console.print(f"❌ [red]Not found: {operation} failed[/red]")
    elif response.status_code >= 400:
        console.print(f"❌ [red]API error ({response.status_code}): {operation} failed[/red]")
        try:
            error_detail = response.json().get("detail", "Unknown error")
            console.print(f"   [dim]{error_detail}[/dim]")
        except:
            pass
    else:
        console.print(f"❌ [red]Unexpected error: {operation} failed[/red]")

def check_api_connection():
    """Ensure API is available before running commands"""
    if not api.health_check():
        console.print("❌ [red]Cannot connect to anime API at[/red] [cyan]http://localhost:8328[/cyan]")
        console.print("   [dim]Make sure the anime production service is running[/dim]")
        console.print("   [dim]Run: /opt/tower-anime-production/venv/bin/python secure_api.py[/dim]")
        raise click.Abort()

@click.group()
@click.version_option(version="1.0.0", prog_name="anime-cli")
def cli():
    """🎭 Anime Production CLI - Interactive Storyline Management

    Command-line interface for creating, managing, and collaborating on
    interactive anime storylines with AI assistance.
    """
    check_api_connection()

# ==================== STORY MANAGEMENT ====================

@cli.group()
def story():
    """📚 Story management commands"""
    pass

@story.command("list")
@click.option("--limit", "-l", default=20, help="Maximum number of stories to show")
def story_list(limit):
    """List all interactive stories"""
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Loading stories...", total=None)

        response = api.get("/api/stories")
        if response.status_code != 200:
            handle_api_error(response, "listing stories")
            return

        stories = response.json().get("stories", [])

    if not stories:
        console.print("📚 [yellow]No stories found[/yellow]")
        console.print("   Create your first story with: [cyan]anime-cli story create[/cyan]")
        return

    table = Table(title="Interactive Stories", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="bold")
    table.add_column("Author", style="green")
    table.add_column("Branch", style="magenta")
    table.add_column("Updated", style="dim")

    for story in stories[:limit]:
        table.add_row(
            story.get("story_id", "N/A"),
            story.get("title", "Untitled"),
            story.get("author", "Unknown"),
            story.get("current_branch", "main"),
            story.get("updated_at", "N/A")[:10] if story.get("updated_at") else "N/A"
        )

    console.print(table)

@story.command("create")
@click.option("--title", "-t", prompt="Story title", help="Title of the new story")
@click.option("--description", "-d", prompt="Description", help="Brief description of the story")
@click.option("--author", "-a", prompt="Author name", help="Author of the story")
@click.option("--genre", "-g", default="adventure", help="Story genre")
def story_create(title, description, author, genre):
    """Create a new interactive story"""
    story_data = {
        "title": title,
        "description": description,
        "author": author,
        "current_branch": "main",
        "head_commit": "initial",
        "working_story": {
            "title": title,
            "genre": genre,
            "chapters": [],
            "characters": {}
        },
        "metadata": {
            "genre": genre,
            "created_via": "cli"
        }
    }

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Creating story...", total=None)

        response = api.post("/api/stories", story_data)
        if response.status_code != 200:
            handle_api_error(response, "creating story")
            return

        result = response.json()

    console.print(f"✅ [green]Story created successfully![/green]")
    console.print(f"   [cyan]Story ID:[/cyan] {result['story_id']}")
    console.print(f"   [cyan]Title:[/cyan] {title}")
    console.print(f"   [dim]Use 'anime-cli story show {result['story_id']}' to view details[/dim]")

@story.command("show")
@click.argument("story_id")
def story_show(story_id):
    """Show detailed story information"""
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Loading story...", total=None)

        response = api.get(f"/api/stories/{story_id}")
        if response.status_code != 200:
            handle_api_error(response, f"loading story {story_id}")
            return

        story = response.json()

    # Main story info panel
    info_text = f"""[cyan]ID:[/cyan] {story.get('story_id', 'N/A')}
[cyan]Author:[/cyan] {story.get('author', 'Unknown')}
[cyan]Branch:[/cyan] {story.get('current_branch', 'main')}
[cyan]Description:[/cyan] {story.get('description', 'No description')}"""

    console.print(Panel(info_text, title=f"📚 {story.get('title', 'Untitled')}", border_style="blue"))

    # Working story content
    working_story = story.get("working_story", {})

    # Characters
    characters = working_story.get("characters", {})
    if characters:
        char_table = Table(title="Characters", show_header=True)
        char_table.add_column("Name", style="bold yellow")
        char_table.add_column("Details", style="dim")

        for char_name, char_data in characters.items():
            details = []
            if char_data.get("hair_color"):
                details.append(f"Hair: {char_data['hair_color']}")
            if char_data.get("eye_color"):
                details.append(f"Eyes: {char_data['eye_color']}")
            if char_data.get("personality"):
                details.append(f"Traits: {', '.join(char_data['personality'][:3])}")

            char_table.add_row(char_name, " | ".join(details))

        console.print(char_table)

    # Chapters
    chapters = working_story.get("chapters", [])
    if chapters:
        console.print("\n[bold]📖 Chapters:[/bold]")
        for i, chapter in enumerate(chapters, 1):
            console.print(f"   {i}. {chapter.get('title', f'Chapter {i}')}")

    # Usage examples
    console.print(f"\n[dim]💡 Next steps:[/dim]")
    console.print(f"   [cyan]anime-cli branch create {story_id} alternative[/cyan] - Create story branch")
    console.print(f"   [cyan]anime-cli character evolve {story_id} <name>[/cyan] - Evolve character")
    console.print(f"   [cyan]anime-cli echo suggest {story_id}[/cyan] - Get AI suggestions")

# ==================== BRANCHING SYSTEM ====================

@cli.group()
def branch():
    """🌳 Story branching commands"""
    pass

@branch.command("create")
@click.argument("story_id")
@click.argument("branch_name")
@click.option("--description", "-d", prompt="Branch description", help="Description of the new branch")
def branch_create(story_id, branch_name, description):
    """Create a new story branch"""
    branch_data = {
        "name": branch_name,
        "description": description
    }

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Creating branch...", total=None)

        response = api.post(f"/api/stories/{story_id}/branches", branch_data)
        if response.status_code != 200:
            handle_api_error(response, f"creating branch {branch_name}")
            return

        result = response.json()

    console.print(f"✅ [green]Branch '{branch_name}' created successfully![/green]")
    console.print(f"   [dim]Use 'anime-cli branch switch {story_id} {branch_name}' to switch to it[/dim]")

@branch.command("list")
@click.argument("story_id")
def branch_list(story_id):
    """List all branches for a story"""
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Loading branches...", total=None)

        response = api.get(f"/api/stories/{story_id}/branches")
        if response.status_code != 200:
            handle_api_error(response, f"listing branches for story {story_id}")
            return

        branches = response.json().get("branches", [])

    if not branches:
        console.print("🌳 [yellow]No branches found[/yellow]")
        return

    table = Table(title=f"Story Branches - {story_id}", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="dim")
    table.add_column("Created", style="green")

    for branch in branches:
        table.add_row(
            branch.get("name", "N/A"),
            branch.get("description", "No description"),
            branch.get("created_at", "N/A")[:10] if branch.get("created_at") else "N/A"
        )

    console.print(table)

@branch.command("switch")
@click.argument("story_id")
@click.argument("branch_name")
def branch_switch(story_id, branch_name):
    """Switch to a different story branch"""
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task(f"Switching to {branch_name}...", total=None)

        response = api.post(f"/api/stories/{story_id}/branches/{branch_name}/switch")
        if response.status_code != 200:
            handle_api_error(response, f"switching to branch {branch_name}")
            return

        result = response.json()

    console.print(f"✅ [green]Switched to branch '{branch_name}'[/green]")
    console.print(f"   [cyan]Head commit:[/cyan] {result.get('head_commit', 'N/A')}")

# ==================== CHARACTER EVOLUTION ====================

@cli.group()
def character():
    """👥 Character management commands"""
    pass

@character.command("list")
def character_list():
    """List all characters from projects"""
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Loading characters...", total=None)

        response = api.get("/characters")
        if response.status_code != 200:
            handle_api_error(response, "listing characters")
            return

        characters = response.json().get("characters", [])

    if not characters:
        console.print("👥 [yellow]No characters found[/yellow]")
        return

    table = Table(title="Available Characters", show_header=True)
    table.add_column("Name", style="bold yellow")
    table.add_column("Project", style="cyan")
    table.add_column("Path", style="dim")

    for char in characters:
        table.add_row(
            char.get("name", "N/A"),
            char.get("project_id", "N/A"),
            char.get("path", "N/A")
        )

    console.print(table)

@character.command("evolve")
@click.argument("story_id")
@click.argument("character_name")
@click.option("--power", "-p", type=int, help="Power level (1-10)")
@click.option("--confidence", "-c", type=float, help="Confidence level (0.0-1.0)")
@click.option("--description", "-d", help="Evolution description")
def character_evolve(story_id, character_name, power, confidence, description):
    """Evolve a character based on story events"""
    evolution_data = {
        "evolution_state": {},
        "emotional_state": {},
        "relationships": {}
    }

    if power:
        evolution_data["evolution_state"]["power"] = power
    if confidence:
        evolution_data["emotional_state"]["confidence"] = confidence
    if description:
        evolution_data["description"] = description

    # Prompt for missing details interactively
    if not evolution_data["evolution_state"] and not evolution_data["emotional_state"]:
        console.print(f"🎭 [cyan]Evolving {character_name} in story {story_id}[/cyan]")

        power = click.prompt("Power level (1-10)", type=int, default=5)
        confidence = click.prompt("Confidence (0.0-1.0)", type=float, default=0.7)
        description = click.prompt("Evolution description", default="Character growth")

        evolution_data["evolution_state"]["power"] = power
        evolution_data["emotional_state"]["confidence"] = confidence
        evolution_data["description"] = description

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Evolving character...", total=None)

        response = api.post(f"/api/stories/{story_id}/characters/{character_name}/evolve", evolution_data)
        if response.status_code != 200:
            handle_api_error(response, f"evolving character {character_name}")
            return

        result = response.json()

    console.print(f"✅ [green]{character_name} evolved successfully![/green]")
    console.print(f"   [cyan]Power:[/cyan] {evolution_data['evolution_state'].get('power', 'N/A')}")
    console.print(f"   [cyan]Confidence:[/cyan] {evolution_data['emotional_state'].get('confidence', 'N/A')}")

@character.command("evolution")
@click.argument("story_id")
@click.argument("character_name")
def character_evolution(story_id, character_name):
    """Show character evolution history"""
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Loading evolution history...", total=None)

        response = api.get(f"/api/stories/{story_id}/characters/{character_name}/evolution")
        if response.status_code != 200:
            handle_api_error(response, f"loading evolution for {character_name}")
            return

        data = response.json()
        evolution = data.get("evolution", [])

    if not evolution:
        console.print(f"📈 [yellow]No evolution history for {character_name}[/yellow]")
        return

    console.print(f"📈 [bold]Evolution History: {character_name}[/bold]")

    for i, event in enumerate(evolution):
        timestamp = event.get("timestamp", "Unknown")[:16] if event.get("timestamp") else "Unknown"
        evolution_state = event.get("evolution_state", {})
        emotional_state = event.get("emotional_state", {})

        details = []
        if evolution_state.get("power"):
            details.append(f"Power: {evolution_state['power']}")
        if emotional_state.get("confidence"):
            details.append(f"Confidence: {emotional_state['confidence']}")

        console.print(f"   {i+1}. {timestamp} - {' | '.join(details)}")

# ==================== AI INTEGRATION ====================

@cli.group()
def echo():
    """🧠 Echo Brain AI integration commands"""
    pass

@echo.command("suggest")
@click.argument("story_id")
def echo_suggest(story_id):
    """Get AI suggestions for story progression"""
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Getting AI suggestions...", total=None)

        response = api.post(f"/api/stories/{story_id}/suggestions")
        if response.status_code != 200:
            handle_api_error(response, f"getting AI suggestions for story {story_id}")
            return

        result = response.json()
        suggestions = result.get("suggestions", [])

    if not suggestions:
        console.print("🧠 [yellow]No suggestions available[/yellow]")
        return

    console.print("🧠 [bold]Echo Brain Suggestions:[/bold]")
    for i, suggestion in enumerate(suggestions, 1):
        console.print(f"   {i}. {suggestion}")

@echo.command("intent")
@click.argument("story_id")
@click.argument("user_input")
def echo_intent(story_id, user_input):
    """Analyze user intent with Echo Brain"""
    intent_data = {"input": user_input}

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Analyzing intent...", total=None)

        response = api.post(f"/api/stories/{story_id}/intent", intent_data)
        if response.status_code != 200:
            handle_api_error(response, f"analyzing intent for '{user_input}'")
            return

        result = response.json()

    console.print("🧠 [bold]Intent Analysis:[/bold]")
    console.print(f"   [cyan]Action:[/cyan] {result.get('action', 'N/A')}")
    console.print(f"   [cyan]Target:[/cyan] {result.get('target', 'N/A')}")
    console.print(f"   [cyan]Confidence:[/cyan] {result.get('confidence', 'N/A')}")

    parameters = result.get("parameters", {})
    if parameters:
        console.print(f"   [cyan]Parameters:[/cyan]")
        for key, value in parameters.items():
            console.print(f"     {key}: {value}")

# ==================== GENERATION ====================

@cli.group()
def generate():
    """🎨 Content generation commands"""
    pass

@generate.command("image")
@click.argument("story_id")
@click.option("--prompt", "-p", prompt="Generation prompt", help="Image generation prompt")
@click.option("--character", "-c", help="Character name")
@click.option("--chapter", "-ch", default=0, help="Chapter index")
@click.option("--width", "-w", default=512, help="Image width")
@click.option("--height", "-h", default=768, help="Image height")
def generate_image(story_id, prompt, character, chapter, width, height):
    """Generate story-aware image"""
    generation_data = {
        "prompt": prompt,
        "character_name": character,
        "chapter_index": chapter,
        "width": width,
        "height": height
    }

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Generating image...", total=None)

        response = api.post(f"/api/stories/{story_id}/generate", generation_data)
        if response.status_code != 200:
            handle_api_error(response, "generating image")
            return

        result = response.json()

    console.print(f"✅ [green]Image generation started![/green]")
    console.print(f"   [cyan]Job ID:[/cyan] {result.get('job_id', 'N/A')}")
    console.print(f"   [cyan]Status:[/cyan] {result.get('status', 'N/A')}")
    console.print(f"   [dim]Monitor progress with API or check output directory[/dim]")

# ==================== SYSTEM COMMANDS ====================

@cli.group()
def system():
    """⚙️ System management commands"""
    pass

@system.command("health")
def system_health():
    """Check system health"""
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Checking system health...", total=None)

        # Check API health
        api_response = api.get("/api/health")

        # Check anime-specific health
        anime_response = api.get("/api/anime/health")

    console.print("⚙️ [bold]System Health Status:[/bold]")

    if api_response.status_code == 200:
        health_data = api_response.json()
        console.print(f"   ✅ [green]API Status:[/green] {health_data.get('status', 'unknown')}")
        console.print(f"   📊 [cyan]Queue Size:[/cyan] {health_data.get('queue_size', 'N/A')}")
        console.print(f"   🔗 [cyan]Active WebSockets:[/cyan] {health_data.get('active_websockets', 'N/A')}")
        console.print(f"   💾 [cyan]Jobs in Memory:[/cyan] {health_data.get('jobs_in_memory', 'N/A')}")
    else:
        console.print("   ❌ [red]API Status: Unhealthy[/red]")

    if anime_response.status_code == 200:
        console.print("   ✅ [green]Anime API: Healthy[/green]")
    else:
        console.print("   ❌ [red]Anime API: Unhealthy[/red]")

@system.command("projects")
def system_projects():
    """List available projects"""
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Loading projects...", total=None)

        response = api.get("/api/anime/projects")
        if response.status_code != 200:
            handle_api_error(response, "listing projects")
            return

        projects = response.json().get("projects", [])

    if not projects:
        console.print("📁 [yellow]No projects found[/yellow]")
        return

    table = Table(title="Available Projects", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Characters", style="yellow")
    table.add_column("Images", style="green")
    table.add_column("Path", style="dim")

    for project in projects:
        characters = project.get("characters", [])
        char_count = len(characters) if isinstance(characters, list) else 0

        table.add_row(
            project.get("id", "N/A"),
            project.get("name", "Untitled"),
            str(char_count),
            str(project.get("images", 0)),
            project.get("path", "N/A")
        )

    console.print(table)

@system.command("info")
def system_info():
    """Show system information"""
    console.print(Panel.fit(
        """[bold cyan]🎭 Anime Production CLI[/bold cyan]

[green]Features:[/green]
• Interactive storyline management
• Git-like story branching system
• Character evolution tracking
• Echo Brain AI integration
• Story-aware image generation

[green]API Endpoint:[/green] http://localhost:8328
[green]Documentation:[/green] Use --help with any command

[dim]For more info: https://tower.local/kb[/dim]""",
        title="System Information",
        border_style="blue"
    ))

if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n👋 [yellow]Goodbye![/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"❌ [red]Unexpected error:[/red] {str(e)}")
        sys.exit(1)