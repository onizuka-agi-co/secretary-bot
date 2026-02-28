#!/usr/bin/env python3
"""
Secretary Bot - 朱燈烏（Shutogarasu）
YAMLベース定期通知Bot - スラッシュコマンド対応
"""

import os
import sys
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands, tasks
import croniter

# 強制フラッシュ
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# 設定読み込み
env_path = Path(__file__).parent / "config" / ".env"
load_dotenv(env_path)

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
SCHEDULE_FILE = Path("/config/.openclaw/workspace/schedule-tasks.yaml")
TZ = ZoneInfo("Asia/Tokyo")
GUILD_ID = 1188045372526964796  # ONIZUKA Guild

# Bot設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 実行済みタスク管理
executed_tasks: Dict[str, str] = {}


def load_schedule() -> dict:
    """YAMLファイルからスケジュールを読み込む"""
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[ERROR] Failed to load schedule: {e}", flush=True)
        return {"tasks": [], "settings": {}}


def should_execute(task: dict, now: datetime) -> bool:
    """タスクを実行すべきか判定"""
    task_name = task.get("name", "unnamed")
    schedule = task.get("schedule", "")
    time_key = now.strftime("%Y-%m-%d %H:%M")

    if executed_tasks.get(task_name) == time_key:
        return False

    if schedule == "hourly":
        if now.minute == 0:
            executed_tasks[task_name] = time_key
            return True
        return False

    try:
        cron = croniter.croniter(schedule, now)
        prev_run = cron.get_prev(datetime)
        if (prev_run.year == now.year and prev_run.month == now.month and
            prev_run.day == now.day and prev_run.hour == now.hour and prev_run.minute == now.minute):
            executed_tasks[task_name] = time_key
            return True
    except Exception as e:
        print(f"[ERROR] Invalid cron: {schedule} - {e}", flush=True)

    return False


@bot.event
async def on_interaction(interaction: discord.Interaction):
    """インタラクション受信ログ"""
    print(f"[DEBUG] Interaction received: {interaction.type} - {interaction.data}", flush=True)
    # デフォルトの処理を継続
    await bot.process_application_commands(interaction)


@bot.event
async def on_ready():
    """起動時処理"""
    print(f"[INFO] 朱燈烏 Bot起動: {bot.user}", flush=True)
    print(f"[INFO] Bot ID: {bot.user.id}", flush=True)
    print(f"[INFO] スケジュールファイル: {SCHEDULE_FILE}", flush=True)

    schedule = load_schedule()
    task_count = len([t for t in schedule.get("tasks", []) if t.get("enabled", True)])
    print(f"[INFO] 有効なタスク数: {task_count}", flush=True)

    # スラッシュコマンド同期（Guild固有で即座に反映）
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"[INFO] Synced {len(synced)} command(s) to guild {GUILD_ID}", flush=True)
    except Exception as e:
        print(f"[ERROR] Failed to sync commands: {e}", flush=True)

    # 起動通知
    channel_id = int(os.getenv("CHANNEL_TASK", "0"))
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(f"🎋 朱燈烏起動しました\n📝 スケジュールタスク: {task_count}件")

    # 定期チェック開始
    schedule_check_loop.start()


@tasks.loop(seconds=60)
async def schedule_check_loop():
    """60秒ごとにスケジュールをチェック"""
    now = datetime.now(TZ)
    schedule = load_schedule()

    for task in schedule.get("tasks", []):
        if not task.get("enabled", True):
            continue
        if should_execute(task, now):
            await execute_task(task, now)


async def execute_task(task: dict, now: datetime):
    """タスクを実行"""
    task_name = task.get("name", "unnamed")
    channel_id = int(task.get("channel", "0"))
    mention = task.get("mention", "")
    prompt = task.get("prompt", "")
    use_thread = task.get("thread", False)
    thread_name_template = task.get("thread_name", "🔧 {date} {name}")

    channel = bot.get_channel(channel_id)
    if not channel:
        print(f"[ERROR] Channel not found: {channel_id}", flush=True)
        return

    # メッセージ構築
    message_parts = []
    if mention:
        message_parts.append(f"<@{mention}>")
    if prompt:
        message_parts.append(prompt)
    message = " ".join(message_parts)

    try:
        if use_thread:
            # スレッド名のプレースホルダーを置換
            thread_name = thread_name_template
            thread_name = thread_name.replace("{date}", now.strftime("%Y-%m-%d"))
            thread_name = thread_name.replace("{time}", now.strftime("%H:%M"))
            thread_name = thread_name.replace("{name}", task_name)

            # スレッドを作成
            thread = await channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.public_thread,
                auto_archive_duration=1440  # 1日でアーカイブ
            )

            # スレッド内でメッセージ送信
            await thread.send(message)
            print(f"[INFO] Task executed in thread: {task_name} at {now:%Y-%m-%d %H:%M}", flush=True)
        else:
            # 通常のチャンネル送信
            await channel.send(message)
            print(f"[INFO] Task executed: {task_name} at {now:%Y-%m-%d %H:%M}", flush=True)
    except Exception as e:
        print(f"[ERROR] Failed to execute task: {e}", flush=True)


@schedule_check_loop.before_loop
async def before_schedule_check():
    await bot.wait_until_ready()


# ============== スラッシュコマンド ==============

@bot.tree.command(name="status", description="朱燈烏のステータスを確認")
async def cmd_status(interaction: discord.Interaction):
    """ステータス確認"""
    schedule = load_schedule()
    task_count = len([t for t in schedule.get("tasks", []) if t.get("enabled", True)])
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

    embed = discord.Embed(
        title="🎋 朱燈烏 ステータス",
        color=0xC41E3A
    )
    embed.add_field(name="状態", value="✅ 稼働中", inline=True)
    embed.add_field(name="タスク数", value=f"{task_count}件", inline=True)
    embed.add_field(name="現在時刻", value=now, inline=True)
    embed.add_field(name="スケジュールファイル", value=f"`{SCHEDULE_FILE}`", inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="tasks", description="スケジュールタスク一覧を表示")
async def cmd_tasks(interaction: discord.Interaction):
    """タスク一覧表示"""
    schedule = load_schedule()
    tasks = schedule.get("tasks", [])

    if not tasks:
        await interaction.response.send_message("🎋 登録されたタスクはありません")
        return

    embed = discord.Embed(
        title="🎋 スケジュールタスク一覧",
        color=0xC41E3A
    )

    for i, task in enumerate(tasks[:5]):  # 最大5件（詳細表示のため）
        status = "✅" if task.get("enabled", True) else "❌"
        name = task.get("name", "unnamed")
        sched = task.get("schedule", "N/A")
        channel_id = task.get("channel", "N/A")
        mention = task.get("mention", "")
        prompt = task.get("prompt", "")

        # 詳細情報を構築
        details = [f"スケジュール: `{sched}`"]
        if channel_id != "N/A":
            details.append(f"チャンネル: <#{channel_id}>")
        if mention:
            details.append(f"メンション: <@{mention}>")
        if prompt:
            # 長いプロンプトは短縮
            display_prompt = prompt if len(prompt) <= 50 else prompt[:47] + "..."
            details.append(f"メッセージ: {display_prompt}")
        # スレッド情報
        if task.get("thread", False):
            thread_icon = "🧵"
            thread_name = task.get("thread_name", "デフォルト")
            details.append(f"{thread_icon} スレッド: `{thread_name}`")

        embed.add_field(
            name=f"{status} {name}",
            value="\n".join(details),
            inline=False
        )

    if len(tasks) > 5:
        embed.set_footer(text=f"...他 {len(tasks) - 5} 件")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="reload", description="スケジュールを再読み込み")
async def cmd_reload(interaction: discord.Interaction):
    """スケジュール再読み込み"""
    schedule = load_schedule()
    task_count = len([t for t in schedule.get("tasks", []) if t.get("enabled", True)])

    await interaction.response.send_message(
        f"🎋 スケジュールを再読み込みしました\n📝 有効なタスク: {task_count}件"
    )


@bot.tree.command(name="add", description="新しいタスクを追加")
@app_commands.describe(
    name="タスク名",
    schedule="スケジュール（cron形式 または 'hourly'）",
    channel="チャンネルID",
    mention="メンション先のユーザー/ロールID",
    prompt="メッセージ内容"
)
async def cmd_add(
    interaction: discord.Interaction,
    name: str,
    schedule: str,
    channel: str,
    mention: str = "",
    prompt: str = ""
):
    """タスク追加"""
    schedule_data = load_schedule()

    new_task = {
        "name": name,
        "schedule": schedule,
        "channel": channel,
        "mention": mention,
        "prompt": prompt,
        "enabled": True
    }

    if "tasks" not in schedule_data:
        schedule_data["tasks"] = []
    schedule_data["tasks"].append(new_task)

    try:
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            yaml.dump(schedule_data, f, allow_unicode=True, default_flow_style=False)

        msg = f"🎋 タスクを追加しました\n**{name}** (`{schedule}`)\nチャンネル: <#{channel}>"
        if mention:
            msg += f"\nメンション: <@{mention}>"
        await interaction.response.send_message(msg)
    except Exception as e:
        await interaction.response.send_message(f"❌ 保存エラー: {e}")


@bot.tree.command(name="disable", description="タスクを無効化")
@app_commands.describe(name="タスク名")
async def cmd_disable(interaction: discord.Interaction, name: str):
    """タスク無効化"""
    schedule_data = load_schedule()

    for task in schedule_data.get("tasks", []):
        if task.get("name") == name:
            task["enabled"] = False
            break
    else:
        await interaction.response.send_message(f"❌ タスク '{name}' が見つかりません")
        return

    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        yaml.dump(schedule_data, f, allow_unicode=True, default_flow_style=False)

    await interaction.response.send_message(f"🎋 タスク '{name}' を無効化しました")


@bot.tree.command(name="enable", description="タスクを有効化")
@app_commands.describe(name="タスク名")
async def cmd_enable(interaction: discord.Interaction, name: str):
    """タスク有効化"""
    schedule_data = load_schedule()

    for task in schedule_data.get("tasks", []):
        if task.get("name") == name:
            task["enabled"] = True
            break
    else:
        await interaction.response.send_message(f"❌ タスク '{name}' が見つかりません")
        return

    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        yaml.dump(schedule_data, f, allow_unicode=True, default_flow_style=False)

    await interaction.response.send_message(f"🎋 タスク '{name}' を有効化しました")


@bot.tree.command(name="test", description="タスクをテスト実行")
@app_commands.describe(name="タスク名")
async def cmd_test(interaction: discord.Interaction, name: str):
    """タスクテスト実行"""
    schedule_data = load_schedule()

    for task in schedule_data.get("tasks", []):
        if task.get("name") == name:
            await interaction.response.send_message(f"🧪 タスク '{name}' をテスト実行中...")
            now = datetime.now(TZ)
            await execute_task(task, now)
            return

    await interaction.response.send_message(f"❌ タスク '{name}' が見つかりません")


# Bot起動
if __name__ == "__main__":
    print("[INFO] Bot起動中...", flush=True)
    bot.run(TOKEN)
