# 🎋 朱燈烏（Shutogarasu）- Secretary Bot

[![README in Japanese](https://img.shields.io/badge/README-日本語-white?style=flat-square)](README_JP.md)
[![README in English](https://img.shields.io/badge/README-English-blue?style=flat-square)](README.md)

YAMLベースのDiscord定期通知Bot。スレッド作成、スラッシュコマンド対応。

## 機能

- 📅 **YAMLベースのスケジュール管理** - cron形式または`hourly`でタスク定義
- 🧵 **スレッド自動作成** - オプションでタスク実行時にスレッドを作成
- 💬 **スラッシュコマンド** - `/status`, `/tasks`, `/add`, `/test` など
- 🔄 **ホットリロード** - YAMLファイルを編集して即座に反映

## セットアップ

### 1. 依存関係インストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数設定

```bash
cp config/.env.example config/.env
# .envを編集してBotトークンを設定
```

### 3. Bot起動

```bash
python3 bot.py
```

## スラッシュコマンド

| コマンド | 説明 |
|---------|------|
| `/status` | Botのステータス確認 |
| `/tasks` | タスク一覧表示 |
| `/reload` | スケジュール再読み込み |
| `/add` | 新しいタスク追加 |
| `/enable` | タスク有効化 |
| `/disable` | タスク無効化 |
| `/test` | タスクテスト実行 |

## YAML設定例

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

### プレースホルダー

- `{date}` - 日付 (YYYY-MM-DD)
- `{time}` - 時刻 (HH:MM)
- `{name}` - タスク名

## ライセンス

MIT
