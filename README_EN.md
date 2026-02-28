# 🎋 朱燈烏（Shutogarasu）- Secretary Bot

[![README in Japanese](https://img.shields.io/badge/README-日本語-white?style=flat-square)](README.md)
[![README in English](https://img.shields.io/badge/README-English-blue?style=flat-square)](README_EN.md)

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

## YAML Configuration Example

```yaml
tasks:
  - name: "Task Check"
    schedule: "hourly"
    channel: "1475880463800205315"
    mention: "1475431819565469706"
    prompt: "🎋 TASK Check"
    thread: true
    thread_name: "🔧 {date} Task Check"
    enabled: true

settings:
  timezone: "Asia/Tokyo"
  check_interval: 60
```

### Placeholders

- `{date}` - Date (YYYY-MM-DD)
- `{time}` - Time (HH:MM)
- `{name}` - Task name

## Task File Structure

Each task is stored as an individual YAML file in `config/tasks/`:

```
config/tasks/
├── task-check.yaml       # Hourly task check
├── morning-idea.yaml     # Daily morning idea proposal (09:00)
└── evening-review.yaml   # Daily evening review (21:00)
```

## License

MIT
