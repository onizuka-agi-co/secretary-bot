#!/usr/bin/env python3
"""
Directory Channel Cog - Discord Bot用ディレクトリチャンネル管理Cog

複数のディレクトリ（projects, skills等）を監視し、それぞれのカテゴリにチャンネルを自動作成
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from pathlib import Path
from typing import Dict, List, Optional

from directory_watcher import (
    DirectoryWatcher,
    WatchTarget,
    list_watched_items,
    manually_create_channel,
    create_all_channels,
)

logger = logging.getLogger(__name__)


class DirectoryChannelCog(commands.Cog):
    """ディレクトリチャンネル管理Cog"""

    def __init__(
        self,
        bot: commands.Bot,
        targets: List[WatchTarget],
        guild_id: int,
        check_interval: int = 300,
    ):
        self.bot = bot
        self.watcher = DirectoryWatcher(
            bot=bot,
            targets=targets,
            guild_id=guild_id,
            check_interval=check_interval,
        )
        self._watcher_task = None

    async def cog_load(self):
        """Cog読み込み時に監視を開始"""
        self._watcher_task = self.bot.loop.create_task(self.watcher.start())
        logger.info("DirectoryChannelCog loaded")

    async def cog_unload(self):
        """Cogアンロード時に監視を停止"""
        self.watcher.stop()
        if self._watcher_task:
            self._watcher_task.cancel()
        logger.info("DirectoryChannelCog unloaded")

    # ========================================
    # プロジェクト関連コマンド
    # ========================================

    @app_commands.command(name="projects", description="監視中のプロジェクト一覧を表示")
    async def projects(self, interaction: discord.Interaction):
        """監視中のプロジェクト一覧を表示"""
        items = await list_watched_items(self.watcher, "projects")
        
        if not items:
            await interaction.response.send_message("📂 監視中のプロジェクトはありません", ephemeral=True)
            return

        embed = discord.Embed(
            title="📂 監視中のプロジェクト",
            description="\n".join(f"• {p}" for p in items),
            color=0x4CAF50,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="create-project", description="プロジェクトチャンネルを手動作成")
    @app_commands.describe(name="プロジェクト名")
    async def create_project(self, interaction: discord.Interaction, name: str):
        """プロジェクトチャンネルを手動作成"""
        await interaction.response.defer(ephemeral=True)
        
        channel_name = await manually_create_channel(self.watcher, "projects", name)
        
        if channel_name:
            await interaction.followup.send(f"✅ チャンネルを作成しました: `#{channel_name}`", ephemeral=True)
        else:
            await interaction.followup.send("❌ チャンネル作成に失敗しました", ephemeral=True)

    @app_commands.command(name="scan-projects", description="プロジェクトディレクトリを再スキャン")
    async def scan_projects(self, interaction: discord.Interaction):
        """プロジェクトディレクトリを再スキャン"""
        await interaction.response.defer(ephemeral=True)
        
        await self.watcher.check_for_new_items("projects")
        items = await list_watched_items(self.watcher, "projects")
        
        await interaction.followup.send(
            f"🔍 スキャン完了\n📂 プロジェクト数: {len(items)}",
            ephemeral=True,
        )

    @app_commands.command(name="sync-projects", description="全プロジェクトのチャンネルを作成・同期")
    async def sync_projects(self, interaction: discord.Interaction):
        """全プロジェクトフォルダのチャンネルを作成（既存はスキップ）"""
        await interaction.response.defer()
        
        results = await create_all_channels(self.watcher, "projects")
        
        created = [name for name, ch in results.items() if ch]
        skipped = [name for name, ch in results.items() if not ch]
        
        msg = f"📂 **プロジェクト同期完了**\n\n"
        if created:
            msg += f"✅ 作成: {len(created)}件\n" + "\n".join(f"  • {n}" for n in created) + "\n"
        if skipped:
            msg += f"⏭️ スキップ（既存）: {len(skipped)}件\n" + "\n".join(f"  • {n}" for n in skipped)
        
        await interaction.followup.send(msg)

    # ========================================
    # スキル関連コマンド
    # ========================================

    @app_commands.command(name="skills", description="監視中のスキル一覧を表示")
    async def skills(self, interaction: discord.Interaction):
        """監視中のスキル一覧を表示"""
        items = await list_watched_items(self.watcher, "skills")
        
        if not items:
            await interaction.response.send_message("🎋 監視中のスキルはありません", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎋 監視中のスキル",
            description="\n".join(f"• {s}" for s in items),
            color=0xC41E3A,  # 朱色
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="create-skill", description="スキルチャンネルを手動作成")
    @app_commands.describe(name="スキル名")
    async def create_skill(self, interaction: discord.Interaction, name: str):
        """スキルチャンネルを手動作成"""
        await interaction.response.defer(ephemeral=True)
        
        channel_name = await manually_create_channel(self.watcher, "skills", name)
        
        if channel_name:
            await interaction.followup.send(f"✅ チャンネルを作成しました: `#{channel_name}`", ephemeral=True)
        else:
            await interaction.followup.send("❌ チャンネル作成に失敗しました", ephemeral=True)

    @app_commands.command(name="scan-skills", description="スキルディレクトリを再スキャン")
    async def scan_skills(self, interaction: discord.Interaction):
        """スキルディレクトリを再スキャン"""
        await interaction.response.defer(ephemeral=True)
        
        await self.watcher.check_for_new_items("skills")
        items = await list_watched_items(self.watcher, "skills")
        
        await interaction.followup.send(
            f"🔍 スキャン完了\n🎋 スキル数: {len(items)}",
            ephemeral=True,
        )

    @app_commands.command(name="sync-skills", description="全スキルのチャンネルを作成・同期")
    async def sync_skills(self, interaction: discord.Interaction):
        """全スキルフォルダのチャンネルを作成（既存はスキップ）"""
        await interaction.response.defer()
        
        results = await create_all_channels(self.watcher, "skills")
        
        created = [name for name, ch in results.items() if ch]
        skipped = [name for name, ch in results.items() if not ch]
        
        msg = f"🎋 **スキル同期完了**\n\n"
        if created:
            msg += f"✅ 作成: {len(created)}件\n" + "\n".join(f"  • {n}" for n in created) + "\n"
        if skipped:
            msg += f"⏭️ スキップ（既存）: {len(skipped)}件\n" + "\n".join(f"  • {n}" for n in skipped)
        
        await interaction.followup.send(msg)

    # ========================================
    # 全体管理コマンド
    # ========================================

    @app_commands.command(name="scan-all", description="全ディレクトリを再スキャン")
    async def scan_all(self, interaction: discord.Interaction):
        """全ディレクトリを再スキャン"""
        await interaction.response.defer(ephemeral=True)
        
        for target_name in self.watcher.targets:
            await self.watcher.check_for_new_items(target_name)
        
        summary = []
        for target_name in self.watcher.targets:
            items = await list_watched_items(self.watcher, target_name)
            summary.append(f"{target_name}: {len(items)}件")
        
        await interaction.followup.send(
            f"🔍 全ディレクトリスキャン完了\n" + "\n".join(summary),
            ephemeral=True,
        )

    @app_commands.command(name="sync-all", description="全ディレクトリのチャンネルを作成・同期")
    async def sync_all(self, interaction: discord.Interaction):
        """全ディレクトリのチャンネルを作成"""
        await interaction.response.defer()
        
        results_summary = []
        
        for target_name in self.watcher.targets:
            results = await create_all_channels(self.watcher, target_name)
            created = len([c for c in results.values() if c])
            skipped = len([c for c in results.values() if not c])
            results_summary.append(f"{target_name}: 作成 {created}件 / スキップ {skipped}件")
        
        await interaction.followup.send(
            "🔄 **全ディレクトリ同期完了**\n\n" + "\n".join(results_summary)
        )


async def setup(
    bot: commands.Bot,
    targets: List[WatchTarget],
    guild_id: int,
    check_interval: int = 300,
):
    """Cogをセットアップ"""
    await bot.add_cog(DirectoryChannelCog(bot, targets, guild_id, check_interval))


# 後方互換性のためのエイリアス
ProjectChannelCog = DirectoryChannelCog
