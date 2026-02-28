# 🎋 朱燈烏（Shutogarasu）- Secretary Bot

[![README in Japanese](https://img.shields.io/badge/README-日本語-white?style=flat-square)](README_JP.md)
[![README in English](https://img.shields.io/badge/README-English-blue?style=flat-square)](README.md)

> **YAMLベースのDiscord定期通知Bot** - 自動スレッド作成・スラッシュコマンド対応

A YAML-based Discord periodic notification bot with thread creation and slash command support.

## Features

- 📅 **YAML-based Schedule Management** - Define tasks using cron format or `hourly`
- 🧵 **Automatic Thread Creation** - Optionally create threads when executing tasks
- 💬 **Slash Commands** - `/status`, `/tasks`, `/add`, `/test`, and more
- 🔄 **Hot Reload** - Changes to YAML files are reflected immediately

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
cp config/.env.example config/.env
# Edit .env and set your bot token
```

### 3. Start the Bot

```bash
python3 bot.py
```

## Slash Commands

| Command | Description |
|---------|-------------|
| `/status` | Check bot status |
| `/tasks` | Display task list |
| `/reload` | Reload schedule |
| `/add` | Add a new task |
| `/enable` | Enable a task |
| `/disable` | Disable a task |
| `/test` | Test run a task |

## YAML Schedule Configuration

The bot reads `config/schedule-tasks.yaml` to define scheduled tasks.

### Task Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Task name (used in `/test` and logs) |
| `schedule` | string | ✅ | Cron format or `hourly` |
| `channel` | string | ✅ | Discord channel ID |
| `mention` | string | ❌ | User/role ID to mention |
| `prompt` | string | ❌ | Message content |
| `thread` | boolean | ❌ | Create thread (default: false) |
| `thread_name` | string | ❌ | Thread name template |
| `enabled` | boolean | ❌ | Enable/disable task |

### Schedule Format

- **Simple**: `hourly` - Run every hour at minute 0
- **Cron**: Standard cron format (e.g., `0 9 * * *` for 9:00 daily)

### Placeholders

- `{date}` - Date (YYYY-MM-DD)
- `{time}` - Time (HH:MM)
- `{name}` - Task name

### Example: Task Check (Hourly)

```yaml
tasks:
  - name: "タスク確認"
    schedule: "hourly"
    channel: "1475880463800205315"
    mention: "1475431819565469706"
    prompt: "🎋 TASK確認"
    thread: true
    thread_name: "🔧 {date} タスク確認"
    enabled: true

settings:
  timezone: "Asia/Tokyo"
  check_interval: 60
```

## Error Handling

The bot handles various error types:

- **Rate Limit (429)**: Automatic retry with exponential backoff
- **Server Error (5xx)**: Automatic retry up to 3 times
- **Permission Denied**: Logged and skipped
- **Not Found**: Logged and skipped
- **Timeout**: Automatic retry

Errors are logged to `logs/error.log`.

## Slash Commands

Each task is stored as an individual YAML file in `config/tasks/`:

```
config/tasks/
├── task-check.yaml       # Hourly task check
├── morning-idea.yaml     # Daily morning idea proposal (09:00)
└── evening-review.yaml   # Daily evening review (21:00)
```

## License

MIT
