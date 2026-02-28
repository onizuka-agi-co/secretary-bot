#!/usr/bin/env python3
"""
Project Watcher - プロジェクトフォルダ監視とDiscordチャンネル自動作成

Usage:
    from project_watcher import ProjectWatcher
    
    watcher = ProjectWatcher(bot, projects_dir="/path/to/projects", guild_id=123456)
    await watcher.start()
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
import discord
from discord.errors import HTTPException, Forbidden

logger = logging.getLogger(__name__)


class ProjectWatcher:
    """プロジェクトフォルダを監視し、新規プロジェクト追加時にチャンネルを作成"""

    def __init__(
        self,
        bot: discord.Client,
        projects_dir: str,
        guild_id: int,
        category_id: Optional[int] = None,
        state_file: Optional[str] = None,
        check_interval: int = 300,  # 5分
    ):
        self.bot = bot
        self.projects_dir = Path(projects_dir)
        self.guild_id = guild_id
        self.category_id = category_id
        self.state_file = Path(state_file) if state_file else self.projects_dir / ".watcher_state.json"
        self.check_interval = check_interval
        self.known_projects: Set[str] = set()
        self._running = False

    def load_state(self) -> Set[str]:
        """保存された状態を読み込む"""
        try:
            if self.state_file.exists():
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data.get("known_projects", []))
        except Exception as e:
            logger.warning(f"Failed to load watcher state: {e}")
        return set()

    def save_state(self):
        """状態を保存"""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "known_projects": list(self.known_projects),
                    "last_check": datetime.now().isoformat(),
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save watcher state: {e}")

    def scan_projects(self) -> Set[str]:
        """プロジェクトディレクトリをスキャン"""
        projects = set()
        if not self.projects_dir.exists():
            logger.warning(f"Projects directory not found: {self.projects_dir}")
            return projects

        for item in self.projects_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                projects.add(item.name)
        
        return projects

    async def create_project_channel(self, project_name: str) -> Optional[discord.TextChannel]:
        """プロジェクト用のDiscordチャンネルを作成"""
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            logger.error(f"Guild not found: {self.guild_id}")
            return None

        channel_name = f"📂-{project_name.lower().replace(' ', '-').replace('_', '-')}"
        
        # 既存チャンネルチェック
        existing = discord.utils.get(guild.text_channels, name=channel_name)
        if existing:
            logger.info(f"Channel already exists: {channel_name}")
            return existing

        try:
            # カテゴリ取得
            category = None
            if self.category_id:
                category = guild.get_channel(self.category_id)
                if not isinstance(category, discord.CategoryChannel):
                    category = None

            # チャンネル作成
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                topic=f"プロジェクト: {project_name}",
                reason=f"Auto-created for project: {project_name}",
            )

            # ウェルカムメッセージ
            await channel.send(
                f"📂 **{project_name}** プロジェクトチャンネルを作成しました！\n"
                f"ここでプロジェクトの議論や開発を行ってください。"
            )

            logger.info(f"Created channel: {channel_name}")
            return channel

        except Forbidden as e:
            logger.error(f"Permission denied creating channel: {e}")
        except HTTPException as e:
            logger.error(f"Failed to create channel: {e}")
        
        return None

    async def check_for_new_projects(self):
        """新規プロジェクトをチェック"""
        current_projects = self.scan_projects()
        new_projects = current_projects - self.known_projects

        for project_name in new_projects:
            logger.info(f"New project detected: {project_name}")
            channel = await self.create_project_channel(project_name)
            if channel:
                self.known_projects.add(project_name)
        
        if new_projects:
            self.save_state()

    async def start(self):
        """監視を開始"""
        self.known_projects = self.load_state()
        self._running = True

        logger.info(f"Project watcher started. Monitoring: {self.projects_dir}")
        logger.info(f"Known projects: {len(self.known_projects)}")

        while self._running:
            try:
                await self.check_for_new_projects()
            except Exception as e:
                logger.error(f"Error checking projects: {e}")
            
            await asyncio.sleep(self.check_interval)

    def stop(self):
        """監視を停止"""
        self._running = False
        self.save_state()
        logger.info("Project watcher stopped")


# スラッシュコマンド用のユーティリティ関数
async def list_watched_projects(watcher: ProjectWatcher) -> List[str]:
    """監視中のプロジェクト一覧を返す"""
    return sorted(watcher.known_projects)


async def manually_create_channel(watcher: ProjectWatcher, project_name: str) -> Optional[str]:
    """手動でチャンネルを作成"""
    channel = await watcher.create_project_channel(project_name)
    if channel:
        watcher.known_projects.add(project_name)
        watcher.save_state()
        return channel.name
    return None
