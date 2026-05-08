#!/usr/bin/env python3
"""
X Post History Tracker & Visualizer
X（Twitter）の投稿履歴を追跡・可視化するスクリプト
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import Counter

import httpx

# Timezone
JST = timezone(timedelta(hours=9))

# Paths
WORKSPACE = Path.home() / ".openclaw" / "workspace"
TOKEN_FILE = WORKSPACE / "x-tokens.json"
HISTORY_FILE = WORKSPACE / ".local" / "state" / "x-post-history.json"
DATA_DIR = HISTORY_FILE.parent
DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_tokens():
    """Load X OAuth2 tokens"""
    if not TOKEN_FILE.exists():
        print(f"Token file not found: {TOKEN_FILE}", file=sys.stderr)
        sys.exit(1)
    with open(TOKEN_FILE) as f:
        return json.load(f)


def get_user_id(access_token: str) -> str:
    """Get authenticated user ID"""
    resp = httpx.get(
        "https://api.x.com/2/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if resp.status_code != 200:
        print(f"Failed to get user info: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()["data"]["id"]


def fetch_recent_tweets(access_token: str, user_id: str, max_results: int = 100):
    """Fetch recent tweets from user"""
    tweets = []
    pagination_token = None

    while len(tweets) < max_results:
        params = {
            "max_results": min(100, max_results - len(tweets)),
            "tweet.fields": "created_at,public_metrics,text,referenced_tweets",
            "exclude": "replies",
        }
        if pagination_token:
            params["pagination_token"] = pagination_token

        resp = httpx.get(
            f"https://api.x.com/2/users/{user_id}/tweets",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )

        if resp.status_code != 200:
            print(f"API error: {resp.status_code} {resp.text}", file=sys.stderr)
            break

        data = resp.json()
        if "data" in data:
            tweets.extend(data["data"])
        if "meta" in data and data["meta"].get("next_token"):
            pagination_token = data["meta"]["next_token"]
        else:
            break

    return tweets[:max_results]


def save_history(tweets: list):
    """Save tweet history to JSON"""
    history = {
        "last_updated": datetime.now(JST).isoformat(),
        "total_tweets": len(tweets),
        "tweets": tweets,
    }
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(tweets)} tweets to {HISTORY_FILE}")


def load_history() -> dict:
    """Load existing history"""
    if not HISTORY_FILE.exists():
        return {"tweets": [], "last_updated": None, "total_tweets": 0}
    with open(HISTORY_FILE) as f:
        return json.load(f)


def generate_stats(tweets: list) -> dict:
    """Generate statistics from tweets"""
    if not tweets:
        return {}

    # Parse dates
    now = datetime.now(JST)
    day_counts = Counter()
    hour_counts = Counter()
    type_counts = Counter()  # tweet, retweet, quote
    total_likes = 0
    total_rt = 0
    total_replies = 0
    total_views = 0
    daily_metrics = {}

    for t in tweets:
        created = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00")).astimezone(JST)
        day_key = created.strftime("%Y-%m-%d")
        hour_key = str(created.hour)
        day_counts[day_key] += 1
        hour_counts[hour_key] += 1

        # Type
        refs = t.get("referenced_tweets", [])
        if refs:
            rt_type = refs[0].get("type", "tweet")
            type_counts[rt_type] += 1
        else:
            type_counts["original"] += 1

        # Metrics
        metrics = t.get("public_metrics", {})
        total_likes += metrics.get("like_count", 0)
        total_rt += metrics.get("retweet_count", 0)
        total_replies += metrics.get("reply_count", 0)
        total_views += metrics.get("impression_count", 0)

        if day_key not in daily_metrics:
            daily_metrics[day_key] = {"likes": 0, "rt": 0, "replies": 0, "views": 0, "count": 0}
        daily_metrics[day_key]["likes"] += metrics.get("like_count", 0)
        daily_metrics[day_key]["rt"] += metrics.get("retweet_count", 0)
        daily_metrics[day_key]["replies"] += metrics.get("reply_count", 0)
        daily_metrics[day_key]["views"] += metrics.get("impression_count", 0)
        daily_metrics[day_key]["count"] += 1

    # Recent 7 days
    recent_7d = 0
    for i in range(7):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        recent_7d += day_counts.get(day, 0)

    # Recent 30 days
    recent_30d = 0
    for i in range(30):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        recent_30d += day_counts.get(day, 0)

    # Best performing tweet
    best_tweet = max(tweets, key=lambda t: t.get("public_metrics", {}).get("like_count", 0), default=None)

    return {
        "total": len(tweets),
        "recent_7d": recent_7d,
        "recent_30d": recent_30d,
        "total_likes": total_likes,
        "total_retweets": total_rt,
        "total_replies": total_replies,
        "total_views": total_views,
        "avg_likes": round(total_likes / len(tweets), 1) if tweets else 0,
        "type_distribution": dict(type_counts),
        "daily_metrics": daily_metrics,
        "best_tweet": {
            "text": best_tweet.get("text", "")[:100] if best_tweet else "",
            "likes": best_tweet.get("public_metrics", {}).get("like_count", 0) if best_tweet else 0,
            "created_at": best_tweet.get("created_at", "") if best_tweet else "",
        } if best_tweet else None,
        "busiest_hour": max(hour_counts, key=hour_counts.get) if hour_counts else None,
        "active_days": len(day_counts),
    }


def send_discord_report(stats: dict, webhook_url: str):
    """Send stats to Discord via webhook as embed"""
    if not stats:
        return

    embed = {
        "title": "📊 X投稿統計レポート",
        "color": 0x4CAF50,
        "fields": [
            {"name": "📝 総投稿数", "value": str(stats["total"]), "inline": True},
            {"name": "📅 7日間", "value": f"{stats['recent_7d']}件", "inline": True},
            {"name": "📅 30日間", "value": f"{stats['recent_30d']}件", "inline": True},
            {"name": "❤️ いいね", "value": f"{stats['total_likes']} (avg: {stats['avg_likes']})", "inline": True},
            {"name": "🔁 RT", "value": str(stats["total_retweets"]), "inline": True},
            {"name": "👁️ IMP", "value": f"{stats['total_views']:,}", "inline": True},
        ],
        "footer": {"text": f"🔥 アクティブ日数: {stats['active_days']}日 | ⏰ 最頻投稿時間: {stats.get('busiest_hour','?')}時台"},
    }

    if stats.get("best_tweet"):
        embed["fields"].append({
            "name": "🏆 最多いいね",
            "value": f"「{stats['best_tweet']['text'][:80]}...」\n❤️ {stats['best_tweet']['likes']}",
            "inline": False,
        })

    resp = httpx.post(webhook_url, json={
        "username": "Renji ONIZUKA 🎋",
        "embeds": [embed],
    })
    if resp.status_code in (200, 204):
        print("Discord report sent!")
    else:
        print(f"Discord error: {resp.status_code} {resp.text}", file=sys.stderr)


def format_discord_report(stats: dict) -> str:
    """Format stats for Discord embed"""
    if not stats:
        return "📊 投稿データなし"

    lines = [
        "**📊 X投稿統計レポート**",
        "",
        f"📝 **総投稿数:** {stats['total']}",
        f"📅 **7日間:** {stats['recent_7d']}件",
        f"📅 **30日間:** {stats['recent_30d']}件",
        f"🔥 **アクティブ日数:** {stats['active_days']}日",
        "",
        "**📈 エンゲージメント:**",
        f"  ❤️ いいね: {stats['total_likes']} (avg: {stats['avg_likes']})",
        f"  🔁 リツイート: {stats['total_retweets']}",
        f"  💬 リプライ: {stats['total_replies']}",
        f"  👁️ インプレッション: {stats['total_views']:,}",
    ]

    if stats.get("type_distribution"):
        lines.append("")
        lines.append("**📋 投稿タイプ:**")
        for t, c in stats["type_distribution"].items():
            lines.append(f"  {t}: {c}")

    if stats.get("best_tweet"):
        lines.append("")
        lines.append("**🏆 最多いいね投稿:**")
        lines.append(f"  「{stats['best_tweet']['text']}...」")
        lines.append(f"  ❤️ {stats['best_tweet']['likes']}")

    if stats.get("busiest_hour"):
        lines.append("")
        lines.append(f"⏰ **最も投稿する時間:** {stats['busiest_hour']}時台")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="X Post History Tracker")
    parser.add_argument("command", choices=["fetch", "stats", "report", "history", "notify"])
    parser.add_argument("--max", type=int, default=100, help="Max tweets to fetch")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.command == "fetch":
        tokens = load_tokens()
        user_id = get_user_id(tokens["access_token"])
        print(f"Fetching tweets for user {user_id}...")
        tweets = fetch_recent_tweets(tokens["access_token"], user_id, args.max)
        save_history(tweets)
        print(f"Fetched {len(tweets)} tweets")

    elif args.command == "stats":
        history = load_history()
        tweets = history.get("tweets", [])
        stats = generate_stats(tweets)
        if args.json:
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            print(format_discord_report(stats))

    elif args.command == "report":
        history = load_history()
        tweets = history.get("tweets", [])
        stats = generate_stats(tweets)
        print(format_discord_report(stats))

    elif args.command == "history":
        history = load_history()
        tweets = history.get("tweets", [])
        if args.json:
            print(json.dumps(history, ensure_ascii=False, indent=2))
        else:
            print(f"Last updated: {history.get('last_updated', 'N/A')}")
            print(f"Total: {len(tweets)} tweets")
            for t in tweets[:20]:
                created = t.get("created_at", "")[:16]
                text = t.get("text", "")[:60]
                likes = t.get("public_metrics", {}).get("like_count", 0)
                print(f"  [{created}] {text}... (❤️{likes})")

    elif args.command == "notify":
        # Fetch + stats + Discord notify
        tokens = load_tokens()
        user_id = get_user_id(tokens["access_token"])
        tweets = fetch_recent_tweets(tokens["access_token"], user_id, args.max)
        save_history(tweets)
        stats = generate_stats(tweets)
        webhook_file = WORKSPACE / "data" / "x" / "x-discord-webhook.json"
        if webhook_file.exists():
            webhook_url = json.load(open(webhook_file))["webhook_url"]
            send_discord_report(stats, webhook_url)
        else:
            print(format_discord_report(stats))


if __name__ == "__main__":
    main()
