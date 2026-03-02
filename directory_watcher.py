#!/usr/bin/env python3
"""
Directory Watcher - 汎用ディレクトリ監視とDiscordチャンネル自動作成

複数のディレクトリを監視し、それぞれに対応するカテゴリのチャンネルを自動作成する。

Usage:
    from directory_watcher import DirectoryWatcher, WatchTarget
    
    targets = [
        WatchTarget(
            name="projects",
            directory="/path/to/projects",
            category_id=123456,
            channel_prefix="📂",
            github_org="onizuka-agi-co",
        ),
        WatchTarget(
            name="skills",
            directory="/path/to/skills",
            category_id=789012,
            channel_prefix="🎋",
            github_org="onizuka-agi-co",
        ),
    ]
    
    watcher = DirectoryWatcher(bot, targets=targets, guild_id=123456)
    await watcher.start()
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
import discord
from discord.errors import HTTPException, Forbidden

logger = logging.getLogger(__name__)


@dataclass
class WatchTarget:
    """監視対象のディレクトリ設定"""
    name: str                              # 識別名（例: "projects", "skills"）
    directory: str                         # 監視対象ディレクトリパス
    category_id: Optional[int] = None      # Discord カテゴリID
    channel_prefix: str = "📂"             # チャンネル名プレフィックス
    github_org: Optional[str] = None       # GitHub組織名（URL生成用）
    exclude_patterns: List[str] = field(default_factory=lambda: [".", "_", "__pycache__"])
    state_file: Optional[str] = None       # 状態保存ファイル（Noneなら自動生成）


class DirectoryWatcher:
    """複数ディレクトリを監視し、新規追加時にチャンネルを作成"""

    def __init__(
        self,
        bot: discord.Client,
        targets: List[WatchTarget],
        guild_id: int,
        check_interval: int = 300,  # 5分
        state_dir: Optional[str] = None,
    ):
        self.bot = bot
        self.targets = {t.name: t for t in targets}
        self.guild_id = guild_id
        self.check_interval = check_interval
        self.state_dir = Path(state_dir) if state_dir else Path(__file__).parent / ".cache"
        self.known_items: Dict[str, Set[str]] = {}  # {target_name: set of item names}
        self._running = False

    def load_state(self, target_name: str) -> Set[str]:
        """指定ターゲットの状態を読み込む"""
        target = self.targets.get(target_name)
        if not target:
            return set()
        
        state_file = self._get_state_file(target)
        try:
            if state_file.exists():
                with open(state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data.get("known_items", []))
        except Exception as e:
            logger.warning(f"Failed to load state for {target_name}: {e}")
        return set()

    def save_state(self, target_name: str):
        """指定ターゲットの状態を保存"""
        target = self.targets.get(target_name)
        if not target:
            return
        
        state_file = self._get_state_file(target)
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "known_items": list(self.known_items.get(target_name, [])),
                    "last_check": datetime.now().isoformat(),
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save state for {target_name}: {e}")

    def _get_state_file(self, target: WatchTarget) -> Path:
        """ターゲットの状態ファイルパスを取得"""
        if target.state_file:
            return Path(target.state_file)
        return self.state_dir / f".{target.name}_watcher_state.json"

    def scan_directory(self, target_name: str) -> Set[str]:
        """指定ターゲットのディレクトリをスキャン"""
        target = self.targets.get(target_name)
        if not target:
            return set()
        
        directory = Path(target.directory)
        if not directory.exists():
            logger.warning(f"Directory not found: {directory}")
            return set()

        items = set()
        for item in directory.iterdir():
            if item.is_dir() and not any(item.name.startswith(p) for p in target.exclude_patterns):
                items.add(item.name)
        
        return items

    async def create_channel(
        self,
        target: WatchTarget,
        item_name: str,
        item_path: Optional[Path] = None,
    ) -> Optional[discord.TextChannel]:
        """チャンネルを作成"""
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            logger.error(f"Guild not found: {self.guild_id}")
            return None

        # チャンネル名生成
        channel_name = f"{target.channel_prefix}-{item_name.lower().replace(' ', '-').replace('_', '-')}"
        
        # 既存チャンネルチェック
        existing = discord.utils.get(guild.text_channels, name=channel_name)
        if existing:
            logger.info(f"Channel already exists: {channel_name}")
            return existing

        try:
            # カテゴリ取得
            category = None
            if target.category_id:
                category = guild.get_channel(target.category_id)
                if not isinstance(category, discord.CategoryChannel):
                    category = None

            # チャンネル作成
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                topic=f"{target.name}: {item_name}",
                reason=f"Auto-created for {target.name}: {item_name}",
            )

            # ウェルカムメッセージ
            welcome_msg = f"{target.channel_prefix} **{item_name}** {target.name}チャンネルを作成しました！\n\n"
            
            if item_path:
                welcome_msg += f"📁 **パス:** `{item_path}`\n"
            
            if target.github_org:
                github_url = f"https://github.com/{target.github_org}/{item_name}"
                welcome_msg += f"🐙 **GitHub:** {github_url}\n"
            
            welcome_msg += f"\nここで{target.name}の議論や開発を行ってください。"
            
            await channel.send(welcome_msg)

            logger.info(f"Created channel: {channel_name}")
            return channel

        except Forbidden as e:
            logger.error(f"Permission denied creating channel: {e}")
        except HTTPException as e:
            logger.error(f"Failed to create channel: {e}")
        
        return None

    async def check_for_new_items(self, target_name: str):
        """新規アイテムをチェック"""
        target = self.targets.get(target_name)
        if not target:
            return
        
        current_items = self.scan_directory(target_name)
        known = self.known_items.get(target_name, set())
        new_items = current_items - known

        for item_name in new_items:
            logger.info(f"New {target_name} detected: {item_name}")
            item_path = Path(target.directory) / item_name
            channel = await self.create_channel(target, item_name, item_path=item_path)
            if channel:
                self.known_items.setdefault(target_name, set()).add(item_name)
        
        if new_items:
            self.save_state(target_name)

    async def create_channels_for_all(
        self,
        target_name: str,
    ) -> Dict[str, Optional[discord.TextChannel]]:
        """指定ターゲットの全アイテムにチャンネルを作成"""
        target = self.targets.get(target_name)
        if not target:
            return {}
        
        results = {}
        current_items = self.scan_directory(target_name)
        
        logger.info(f"Creating channels for {len(current_items)} {target_name} items...")
        
        for item_name in sorted(current_items):
            item_path = Path(target.directory) / item_name
            channel = await self.create_channel(target, item_name, item_path=item_path)
            results[item_name] = channel
            
            if channel:
                self.known_items.setdefault(target_name, set()).add(item_name)
                await asyncio.sleep(1)  # レート制限対策
        
        self.save_state(target_name)
        logger.info(f"Created channels for {len([c for c in results.values() if c])} {target_name} items")
        
        return results

    async def start(self):
        """監視を開始"""
        # 全ターゲットの状態を読み込む
        for target_name in self.targets:
            self.known_items[target_name] = self.load_state(target_name)
        
        self._running = True

        logger.info(f"Directory watcher started. Monitoring {len(self.targets)} targets")
        for name, target in self.targets.items():
            logger.info(f"  - {name}: {target.directory} (category: {target.category_id})")

        while self._running:
            try:
                for target_name in self.targets:
                    await self.check_for_new_items(target_name)
            except Exception as e:
                logger.error(f"Error checking directories: {e}")
            
            await asyncio.sleep(self.check_interval)

    def stop(self):
        """監視を停止"""
        self._running = False
        # 全ターゲットの状態を保存
        for target_name in self.targets:
            self.save_state(target_name)
        logger.info("Directory watcher stopped")


# ユーティリティ関数
async def list_watched_items(watcher: DirectoryWatcher, target_name: str) -> List[str]:
    """監視中のアイテム一覧を返す"""
    return sorted(watcher.known_items.get(target_name, set()))


async def manually_create_channel(
    watcher: DirectoryWatcher,
    target_name: str,
    item_name: str,
) -> Optional[str]:
    """手動でチャンネルを作成"""
    target = watcher.targets.get(target_name)
    if not target:
        return None
    
    item_path = Path(target.directory) / item_name
    channel = await watcher.create_channel(target, item_name, item_path=item_path)
    if channel:
        watcher.known_items.setdefault(target_name, set()).add(item_name)
        watcher.save_state(target_name)
        return channel.name
    return None


async def create_all_channels(
    watcher: DirectoryWatcher,
    target_name: str,
) -> Dict[str, Optional[str]]:
    """全アイテムのチャンネルを作成（コマンド用）"""
    results = await watcher.create_channels_for_all(target_name)
    return {
        name: channel.name if channel else None
        for name, channel in results.items()
    }
