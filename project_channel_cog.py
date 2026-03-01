#!/usr/bin/env python3
"""
Project Channel Cog - Discord Bot用プロジェクトチャンネル管理Cog
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging

from project_watcher import ProjectWatcher, list_watched_projects, manually_create_channel

logger = logging.getLogger(__name__)


class ProjectChannelCog(commands.Cog):
    """プロジェクトチャンネル管理Cog"""

    def __init__(self, bot: commands.Bot, projects_dir: str, guild_id: int, category_id: int = None):
        self.bot = bot
        self.watcher = ProjectWatcher(
            bot=bot,
            projects_dir=projects_dir,
            guild_id=guild_id,
            category_id=category_id,
        )
        self._watcher_task = None

    async def cog_load(self):
        """Cog読み込み時に監視を開始"""
        self._watcher_task = self.bot.loop.create_task(self.watcher.start())
        logger.info("ProjectChannelCog loaded")

    async def cog_unload(self):
        """Cogアンロード時に監視を停止"""
        self.watcher.stop()
        if self._watcher_task:
            self._watcher_task.cancel()
        logger.info("ProjectChannelCog unloaded")

    @app_commands.command(name="projects", description="監視中のプロジェクト一覧を表示")
    async def projects(self, interaction: discord.Interaction):
        """監視中のプロジェクト一覧を表示"""
        projects = await list_watched_projects(self.watcher)
        
        if not projects:
            await interaction.response.send_message("📂 監視中のプロジェクトはありません", ephemeral=True)
            return

        embed = discord.Embed(
            title="📂 監視中のプロジェクト",
            description="\n".join(f"• {p}" for p in projects),
            color=0x4CAF50,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="create-project", description="プロジェクトチャンネルを手動作成")
    @app_commands.describe(name="プロジェクト名")
    async def create_project(self, interaction: discord.Interaction, name: str):
        """プロジェクトチャンネルを手動作成"""
        await interaction.response.defer(ephemeral=True)
        
        channel_name = await manually_create_channel(self.watcher, name)
        
        if channel_name:
            await interaction.followup.send(f"✅ チャンネルを作成しました: `#{channel_name}`", ephemeral=True)
        else:
            await interaction.followup.send("❌ チャンネル作成に失敗しました", ephemeral=True)

    @app_commands.command(name="scan-projects", description="プロジェクトディレクトリを再スキャン")
    async def scan_projects(self, interaction: discord.Interaction):
        """プロジェクトディレクトリを再スキャン"""
        await interaction.response.defer(ephemeral=True)
        
        await self.watcher.check_for_new_projects()
        projects = await list_watched_projects(self.watcher)
        
        await interaction.followup.send(
            f"🔍 スキャン完了\n📂 プロジェクト数: {len(projects)}",
            ephemeral=True,
        )

    @app_commands.command(name="sync-projects", description="全プロジェクトのチャンネルを作成・同期")
    async def sync_projects(self, interaction: discord.Interaction):
        """全プロジェクトフォルダのチャンネルを作成（既存はスキップ）"""
        await interaction.response.defer()
        
        from project_watcher import create_all_project_channels
        
        results = await create_all_project_channels(
            self.watcher,
            github_org="onizuka-agi-co",
        )
        
        created = [name for name, ch in results.items() if ch]
        skipped = [name for name, ch in results.items() if not ch]
        
        msg = f"📂 **プロジェクト同期完了**\n\n"
        if created:
            msg += f"✅ 作成: {len(created)}件\n" + "\n".join(f"  • {n}" for n in created) + "\n"
        if skipped:
            msg += f"⏭️ スキップ（既存）: {len(skipped)}件\n" + "\n".join(f"  • {n}" for n in skipped)
        
        await interaction.followup.send(msg)


async def setup(bot: commands.Bot, projects_dir: str, guild_id: int, category_id: int = None):
    """Cogをセットアップ"""
    await bot.add_cog(ProjectChannelCog(bot, projects_dir, guild_id, category_id))
