#!/usr/bin/env python3
"""
Telegram Bot for Anime Git Control
Simple bot that integrates with existing git_branching.py system
"""

import asyncio
import logging
import json
import sys
import os
from datetime import datetime

# Add project paths
sys.path.append('/opt/tower-anime-production')

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logging.warning("python-telegram-bot not installed")

from git_branching import GitBranchingSystem

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class AnimeGitBot:
    def __init__(self):
        self.git_system = GitBranchingSystem()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command"""
        welcome_text = """
🎬 **Anime Git Control Bot**

Available commands:
• `/status` - Show current git status
• `/commit <message>` - Commit current scene
• `/branch <name> <description>` - Create new branch
• `/branches` - List all branches
• `/switch <branch>` - Switch to branch
• `/merge <source_branch>` - Merge branch
• `/history` - Show recent commits
• `/budget` - Check render budget ($150/day)

Example: `/commit Add epic battle scene`
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show git status"""
        try:
            status = self.git_system.get_status()

            status_text = f"""
📊 **Project Status**

🌿 Branch: `{status.get('current_branch', 'main')}`
📝 Changes: {'✅ Clean' if not status.get('has_changes', False) else '⚠️ Modified'}
🔄 Total Branches: {len(status.get('branches', []))}
💾 Last Commit: `{status.get('last_commit', {}).get('hash', 'None')[:8]}`

Use `/branches` to see all branches
            """

            await update.message.reply_text(status_text, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"❌ Error getting status: {e}")

    async def commit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commit current scene"""
        if not context.args:
            await update.message.reply_text("❌ Please provide a commit message: `/commit Your message here`")
            return

        message = ' '.join(context.args)

        try:
            # Get current scene data (simplified for demo)
            scene_data = {
                "frames": 120,
                "duration": 5,
                "quality": "high",
                "timestamp": datetime.now().isoformat()
            }

            commit_hash = self.git_system.commit_scene(
                scene_data=scene_data,
                message=message,
                branch="main"  # Default to main branch
            )

            response_text = f"""
✅ **Scene Committed**

📝 Message: `{message}`
🔗 Hash: `{commit_hash[:8]}`
🌿 Branch: `main`
⏰ Time: {datetime.now().strftime('%H:%M:%S')}

Your scene is now saved! Use `/status` to see updated info.
            """

            await update.message.reply_text(response_text, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"❌ Commit failed: {e}")

    async def create_branch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Create new branch"""
        if len(context.args) < 2:
            await update.message.reply_text("❌ Usage: `/branch <name> <description>`\nExample: `/branch dark-ending Alternative darker conclusion`")
            return

        name = context.args[0]
        description = ' '.join(context.args[1:])

        try:
            branch_hash = self.git_system.create_branch(
                name=name,
                description=description,
                base_branch="main"
            )

            response_text = f"""
🌿 **Branch Created**

📛 Name: `{name}`
📖 Description: {description}
🔗 Hash: `{branch_hash[:8]}`
🌱 Based on: `main`

Use `/switch {name}` to switch to this branch
            """

            await update.message.reply_text(response_text, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"❌ Branch creation failed: {e}")

    async def list_branches(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all branches"""
        try:
            status = self.git_system.get_status()
            branches = status.get('branches', [])
            current = status.get('current_branch', 'main')

            if not branches:
                await update.message.reply_text("📝 No branches found. Use `/branch <name> <description>` to create one.")
                return

            branch_list = "🌿 **Project Branches**\n\n"
            for branch in branches:
                indicator = "👉" if branch.get('name') == current else "  "
                branch_list += f"{indicator} `{branch.get('name', 'unknown')}` - {branch.get('description', 'No description')}\n"

            branch_list += f"\nCurrent: `{current}`"

            await update.message.reply_text(branch_list, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"❌ Error listing branches: {e}")

    async def budget(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check render budget"""
        try:
            # This would integrate with actual budget tracking
            budget_info = {
                "limit": 150.00,
                "used": 23.45,
                "remaining": 126.55
            }

            used_percent = (budget_info["used"] / budget_info["limit"]) * 100
            status_emoji = "🟢" if used_percent < 50 else "🟡" if used_percent < 80 else "🔴"

            budget_text = f"""
💰 **Daily Render Budget**

{status_emoji} Used: ${budget_info["used"]:.2f} / ${budget_info["limit"]:.2f}
📊 Progress: {used_percent:.1f}%
💵 Remaining: ${budget_info["remaining"]:.2f}

🔥 Firebase renders available!
💻 Local GPU also available (free)
            """

            await update.message.reply_text(budget_text, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"❌ Error checking budget: {e}")

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show commit history"""
        try:
            status = self.git_system.get_status()
            commits = status.get('recent_commits', [])

            if not commits:
                await update.message.reply_text("📝 No commits found. Use `/commit <message>` to create your first commit.")
                return

            history_text = "📚 **Recent Commits**\n\n"
            for i, commit in enumerate(commits[:5]):  # Show last 5
                hash_short = commit.get('hash', 'unknown')[:8]
                message = commit.get('message', 'No message')
                timestamp = commit.get('timestamp', 'Unknown time')

                history_text += f"`{hash_short}` {message}\n"
                if i < len(commits) - 1:
                    history_text += "  ↓\n"

            await update.message.reply_text(history_text, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"❌ Error getting history: {e}")

def main():
    """Start the bot"""
    if not TELEGRAM_AVAILABLE:
        print("❌ python-telegram-bot not installed. Install with:")
        print("pip install python-telegram-bot")
        return

    # Bot token - would be stored in vault in production
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'your-bot-token-here')

    if BOT_TOKEN == 'your-bot-token-here':
        print("❌ Please set TELEGRAM_BOT_TOKEN environment variable")
        return

    # Create bot instance
    bot = AnimeGitBot()

    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("status", bot.status))
    application.add_handler(CommandHandler("commit", bot.commit))
    application.add_handler(CommandHandler("branch", bot.create_branch))
    application.add_handler(CommandHandler("branches", bot.list_branches))
    application.add_handler(CommandHandler("budget", bot.budget))
    application.add_handler(CommandHandler("history", bot.history))

    # Start bot
    print("🤖 Anime Git Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()