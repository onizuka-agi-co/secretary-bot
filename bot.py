#!/usr/bin/env python3
"""
Secretary Bot - 朱燈烏（Shutogarasu）
YAMLベース定期通知Bot - スラッシュコマンド対応
"""

import os
import sys
import yaml
import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.errors import HTTPException, Forbidden, NotFound
import croniter

# 強制フラッシュ
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# エラー種別定義
class ErrorTypes:
    NETWORK = "NETWORK_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    YAML_PARSE = "YAML_PARSE_ERROR"
    DISCORD_API = "DISCORD_API_ERROR"
    UNKNOWN = "UNKNOWN_ERROR"

# リトライ設定
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# 設定読み込み
env_path = Path(__file__).parent / "config" / ".env"
load_dotenv(env_path)

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TZ = ZoneInfo("Asia/Tokyo")
GUILD_ID = 1188045372526964796  # ONIZUKA Guild
TASKS_DIR = Path(__file__).parent / "config" / "tasks"
HISTORY_FILE = Path(__file__).parent / "config" / "history.json"

# Bot設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 実行済みタスク管理
executed_tasks: Dict[str, str] = {}

# エラーログ保存
error_log_file = Path(__file__).parent / "logs" / "errors.log"

# 履歴管理
def load_history() -> dict:
    """実行履歴を読み込む"""
    try:
        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load history: {e}", flush=True)
    return {"executions": []}


def save_history(history: dict):
    """実行履歴を保存"""
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        # 最新100件のみ保持
        history["executions"] = history["executions"][-100:]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR] Failed to save history: {e}", flush=True)


def log_execution(task_name: str, channel_id: int, success: bool, thread_id: int = None):
    """タスク実行をログに記録"""
    history = load_history()
    entry = {
        "task": task_name,
        "channel": channel_id,
        "thread": thread_id,
        "success": success,
        "timestamp": datetime.now(TZ).isoformat()
    }
    history["executions"].append(entry)
    save_history(history)




def log_error(error_type: str, task_name: str, error: Exception, context: str = ""):
    """エラーをログに記録"""
    error_dir = error_log_file.parent
    error_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    error_msg = f"[{timestamp}] [{error_type}] Task: {task_name} | Error: {type(error).__name__}: {error}"
    if context:
        error_msg += f" | Context: {context}"
    
    logger.error(error_msg)
    
    with open(error_log_file, "a", encoding="utf-8") as f:
        f.write(error_msg + "\n")


def load_schedule() -> dict:
    """tasksディレクトリ内の全YAMLファイルからタスクを読み込む"""
    tasks = []
    settings = {"timezone": "Asia/Tokyo", "check_interval": 60}

    try:
        if TASKS_DIR.exists():
            for yaml_file in TASKS_DIR.glob("*.yaml"):
                try:
                    with open(yaml_file, "r", encoding="utf-8") as f:
                        task = yaml.safe_load(f)
                        if task and "name" in task:
                            tasks.append(task)
                            logger.debug(f"Loaded task: {task.get('name')} from {yaml_file.name}")
                except yaml.YAMLError as e:
                    log_error(ErrorTypes.YAML_PARSE, yaml_file.stem, e, "YAML syntax error")
                except Exception as e:
                    log_error(ErrorTypes.UNKNOWN, yaml_file.stem, e, "Failed to load task file")
    except Exception as e:
        log_error(ErrorTypes.UNKNOWN, "scheduler", e, "Failed to load tasks directory")

    return {"tasks": tasks, "settings": settings}


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
    except (ValueError, croniter.CroniterBadCronError) as e:
        log_error(ErrorTypes.YAML_PARSE, task_name, e, f"Invalid cron: {schedule}")

    return False


@bot.event
async def on_interaction(interaction: discord.Interaction):
    """インタラクション受信ログ"""
    logger.debug(f"Interaction received: {interaction.type} - {interaction.data}")
    await bot.process_application_commands(interaction)


@bot.event
async def on_error(event, *args, **kwargs):
    """グローバルエラーハンドラ"""
    logger.exception(f"Unhandled error in event {event}")


@bot.event
async def on_ready():
    """起動時処理"""
    logger.info(f"朱燈烏 Bot起動: {bot.user}")
    logger.info(f"Bot ID: {bot.user.id}")
    logger.info(f"タスクディレクトリ: {TASKS_DIR}")

    schedule = load_schedule()
    task_count = len([t for t in schedule.get("tasks", []) if t.get("enabled", True)])
    logger.info(f"有効なタスク数: {task_count}")

    # スラッシュコマンド同期（Guild固有で即座に反映）
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced)} command(s) to guild {GUILD_ID}")
    except HTTPException as e:
        log_error(ErrorTypes.DISCORD_API, "command_sync", e, f"Status: {e.status}")
    except Exception as e:
        log_error(ErrorTypes.UNKNOWN, "command_sync", e)

    # 起動通知
    channel_id = int(os.getenv("CHANNEL_TASK", "0"))
    if channel_id:
        try:
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(f"🎋 朱燈烏起動しました\n📝 スケジュールタスク: {task_count}件")
        except Exception as e:
            log_error(ErrorTypes.DISCORD_API, "startup_notification", e)

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
            await execute_task_with_retry(task, now)


async def execute_task_with_retry(task: dict, now: datetime, retry_count: int = 0):
    """タスクをリトライ付きで実行"""
    task_name = task.get("name", "unnamed")
    
    try:
        await execute_task(task, now)
    except HTTPException as e:
        if e.status == 429:  # Rate limit
            log_error(ErrorTypes.RATE_LIMIT, task_name, e, f"Retry: {retry_count}")
            if retry_count < MAX_RETRIES:
                retry_after = float(e.response.headers.get("Retry-After", RETRY_DELAY))
                logger.warning(f"Rate limited, retrying in {retry_after}s...")
                await asyncio.sleep(retry_after)
                await execute_task_with_retry(task, now, retry_count + 1)
            else:
                log_error(ErrorTypes.RATE_LIMIT, task_name, e, "Max retries exceeded")
        elif e.status >= 500:  # Server error
            log_error(ErrorTypes.NETWORK, task_name, e, f"Server error, retry: {retry_count}")
            if retry_count < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
                await execute_task_with_retry(task, now, retry_count + 1)
            else:
                log_error(ErrorTypes.NETWORK, task_name, e, "Max retries exceeded")
        else:
            log_error(ErrorTypes.DISCORD_API, task_name, e, f"HTTP {e.status}")
    except Forbidden as e:
        log_error(ErrorTypes.DISCORD_API, task_name, e, "Permission denied")
    except NotFound as e:
        log_error(ErrorTypes.DISCORD_API, task_name, e, "Resource not found")
    except asyncio.TimeoutError as e:
        log_error(ErrorTypes.NETWORK, task_name, e, f"Timeout, retry: {retry_count}")
        if retry_count < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY)
            await execute_task_with_retry(task, now, retry_count + 1)
    except Exception as e:
        log_error(ErrorTypes.UNKNOWN, task_name, e)


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
        log_error(ErrorTypes.DISCORD_API, task_name, Exception(f"Channel not found: {channel_id}"), "")
        return

    # メッセージ構築
    message_parts = []
    if mention:
        message_parts.append(f"<@{mention}>")
    if prompt:
        message_parts.append(prompt)
    message = " ".join(message_parts)

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
        logger.info(f"Task executed in thread: {task_name} at {now:%Y-%m-%d %H:%M}")
    else:
        # 通常のチャンネル送信
        await channel.send(message)
        logger.info(f"Task executed: {task_name} at {now:%Y-%m-%d %H:%M}")


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
    embed.add_field(name="タスクディレクトリ", value=f"`{TASKS_DIR}`", inline=False)

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
    # ファイル名を生成（タスク名から安全なファイル名を作成）
    import re
    safe_name = re.sub(r'[^\w\-]', '_', name.lower())
    task_file = TASKS_DIR / f"{safe_name}.yaml"

    new_task = {
        "name": name,
        "schedule": schedule,
        "channel": channel,
        "mention": mention,
        "prompt": prompt,
        "enabled": True
    }

    try:
        TASKS_DIR.mkdir(parents=True, exist_ok=True)
        with open(task_file, "w", encoding="utf-8") as f:
            yaml.dump(new_task, f, allow_unicode=True, default_flow_style=False)

        msg = f"🎋 タスクを追加しました\n**{name}** (`{schedule}`)\nチャンネル: <#{channel}>\nファイル: `{task_file.name}`"
        if mention:
            msg += f"\nメンション: <@{mention}>"
        await interaction.response.send_message(msg)
    except yaml.YAMLError as e:
        log_error(ErrorTypes.YAML_PARSE, name, e, "Failed to serialize task")
        await interaction.response.send_message(f"❌ YAML保存エラー: {e}")
    except Exception as e:
        log_error(ErrorTypes.UNKNOWN, name, e, "Failed to save task")
        await interaction.response.send_message(f"❌ 保存エラー: {e}")


def find_task_file(name: str) -> Optional[Path]:
    """タスク名からファイルを探す"""
    import re
    safe_name = re.sub(r'[^\w\-]', '_', name.lower())
    
    # 直接ファイル名で探す
    task_file = TASKS_DIR / f"{safe_name}.yaml"
    if task_file.exists():
        return task_file
    
    # 全ファイルから探す
    for yaml_file in TASKS_DIR.glob("*.yaml"):
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                task = yaml.safe_load(f)
                if task and task.get("name") == name:
                    return yaml_file
        except:
            pass
    return None


@bot.tree.command(name="disable", description="タスクを無効化")
@app_commands.describe(name="タスク名")
async def cmd_disable(interaction: discord.Interaction, name: str):
    """タスク無効化"""
    task_file = find_task_file(name)
    if not task_file:
        await interaction.response.send_message(f"❌ タスク '{name}' が見つかりません")
        return

    try:
        with open(task_file, "r", encoding="utf-8") as f:
            task = yaml.safe_load(f)
        
        task["enabled"] = False
        with open(task_file, "w", encoding="utf-8") as f:
            yaml.dump(task, f, allow_unicode=True, default_flow_style=False)

        await interaction.response.send_message(f"🎋 タスク '{name}' を無効化しました")
    except Exception as e:
        log_error(ErrorTypes.UNKNOWN, name, e, "Failed to disable task")
        await interaction.response.send_message(f"❌ エラー: {e}")


@bot.tree.command(name="enable", description="タスクを有効化")
@app_commands.describe(name="タスク名")
async def cmd_enable(interaction: discord.Interaction, name: str):
    """タスク有効化"""
    task_file = find_task_file(name)
    if not task_file:
        await interaction.response.send_message(f"❌ タスク '{name}' が見つかりません")
        return

    try:
        with open(task_file, "r", encoding="utf-8") as f:
            task = yaml.safe_load(f)
        
        task["enabled"] = True
        with open(task_file, "w", encoding="utf-8") as f:
            yaml.dump(task, f, allow_unicode=True, default_flow_style=False)

        await interaction.response.send_message(f"🎋 タスク '{name}' を有効化しました")
    except Exception as e:
        log_error(ErrorTypes.UNKNOWN, name, e, "Failed to enable task")
        await interaction.response.send_message(f"❌ エラー: {e}")


@bot.tree.command(name="test", description="タスクをテスト実行")
@app_commands.describe(name="タスク名")
async def cmd_test(interaction: discord.Interaction, name: str):
    """タスクテスト実行"""
    schedule_data = load_schedule()

    for task in schedule_data.get("tasks", []):
        if task.get("name") == name:
            await interaction.response.send_message(f"🧪 タスク '{name}' をテスト実行中...")
            now = datetime.now(TZ)
            await execute_task_with_retry(task, now)
            return

    await interaction.response.send_message(f"❌ タスク '{name}' が見つかりません")


@bot.tree.command(name="errors", description="最近のエラーログを表示")
@app_commands.describe(count="表示するエラー数（デフォルト: 5）")
async def cmd_errors(interaction: discord.Interaction, count: int = 5):
    """エラーログ表示"""
    if not error_log_file.exists():
        await interaction.response.send_message("🎋 エラーログはありません")
        return

    try:
        with open(error_log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        recent_errors = lines[-count:] if len(lines) > count else lines
        
        if not recent_errors:
            await interaction.response.send_message("🎋 エラーログはありません")
            return
        
        embed = discord.Embed(
            title="⚠️ 最近のエラーログ",
            color=0xFF6B6B
        )
        
        for line in recent_errors[:10]:  # 最大10件
            line = line.strip()
            if line:
                # 長い行は短縮
                display = line if len(line) <= 100 else line[:97] + "..."
                embed.add_field(name="━━━", value=f"`{display}`", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ ログ読み込みエラー: {e}", ephemeral=True)



@bot.tree.command(name="history", description="実行履歴を表示")
@app_commands.describe(limit="表示件数（最大20）")
async def cmd_history(interaction: discord.Interaction, limit: int = 10):
    """実行履歴表示"""
    history = load_history()
    executions = history.get("executions", [])

    if not executions:
        await interaction.response.send_message("🎋 実行履歴はありません")
        return

    # 最新の指定件数を取得
    recent = executions[-limit:][::-1]

    embed = discord.Embed(
        title="🔔 実行履歴",
        color=0xC41E3A
    )

    for entry in recent[:10]:  # 最大10件表示
        task_name = entry.get("task", "unknown")
        ts = entry.get("timestamp", "")
        success = "✅" if entry.get("success") else "❌"
        thread_info = " 🧵" if entry.get("thread") else ""

        # タイムスタンプを読みやすく
        try:
            dt = datetime.fromisoformat(ts)
            time_str = dt.strftime("%m/%d %H:%M")
        except:
            time_str = ts[:16] if len(ts) > 16 else ts

        embed.add_field(
            name=f"{success} {task_name}{thread_info}",
            value=f"📅 {time_str}",
            inline=False
        )

    if len(recent) > 10:
        embed.set_footer(text=f"...他 {len(recent) - 10} 件")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="streaks", description="タスク別の実行統計を表示")
async def cmd_streaks(interaction: discord.Interaction):
    """タスク別統計表示"""
    history = load_history()
    executions = history.get("executions", [])

    if not executions:
        await interaction.response.send_message("🎋 実行履歴はありません")
        return

    # タスク別に集計
    task_stats = {}
    for entry in executions:
        task_name = entry.get("task", "unknown")
        if task_name not in task_stats:
            task_stats[task_name] = {"total": 0, "success": 0, "last": None}
        task_stats[task_name]["total"] += 1
        if entry.get("success"):
            task_stats[task_name]["success"] += 1
        task_stats[task_name]["last"] = entry.get("timestamp")

    embed = discord.Embed(
        title="📊 タスク統計",
        color=0xC41E3A
    )

    for task_name, stats in sorted(task_stats.items(), key=lambda x: x[1]["total"], reverse=True)[:10]:
        total = stats["total"]
        success = stats["success"]
        rate = (success / total * 100) if total > 0 else 0

        last = stats["last"]
        try:
            dt = datetime.fromisoformat(last)
            last_str = dt.strftime("%m/%d %H:%M")
        except:
            last_str = "N/A"

        embed.add_field(
            name=f"📌 {task_name}",
            value=f"実行: {total}回 | 成功率: {rate:.0f}%
最終: {last_str}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)


# Bot起動
if __name__ == "__main__":
    logger.info("Bot起動中...")
    bot.run(TOKEN)
