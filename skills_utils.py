#!/usr/bin/env python3
"""
Skills Utilities - スキル一覧取得・表示用ユーティリティ
"""

from pathlib import Path
from typing import Optional
import re


# スキルディレクトリのパス
SKILLS_DIR = Path.home() / ".openclaw" / "workspace" / "skills"


def get_all_skills() -> list[dict]:
    """
    全スキルの一覧を取得

    Returns:
        list[dict]: スキル情報のリスト
            - name: スキル名
            - description: 説明
            - path: SKILL.mdのパス
    """
    skills = []

    if not SKILLS_DIR.exists():
        return skills

    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        skill_info = parse_skill_md(skill_md)
        skill_info["name"] = skill_dir.name
        skill_info["path"] = str(skill_md)
        skills.append(skill_info)

    # 名前順にソート
    skills.sort(key=lambda x: x["name"])
    return skills


def parse_skill_md(skill_md: Path) -> dict:
    """
    SKILL.mdをパースして情報を抽出

    Args:
        skill_md: SKILL.mdのパス

    Returns:
        dict: スキル情報
    """
    info = {
        "description": "",
        "has_scripts": False,
        "has_references": False,
    }

    try:
        content = skill_md.read_text(encoding="utf-8")

        # YAML frontmatterからdescriptionを抽出
        frontmatter_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            desc_match = re.search(r'^description:\s*["\']?(.+?)["\']?\s*$', frontmatter, re.MULTILINE)
            if desc_match:
                info["description"] = desc_match.group(1).strip().strip('"').strip("'")

        # scripts/, references/ ディレクトリの存在確認
        skill_dir = skill_md.parent
        info["has_scripts"] = (skill_dir / "scripts").exists()
        info["has_references"] = (skill_dir / "references").exists()

    except Exception as e:
        print(f"[ERROR] Failed to parse {skill_md}: {e}")

    return info


def get_skill_detail(skill_name: str) -> Optional[dict]:
    """
    特定のスキルの詳細情報を取得

    Args:
        skill_name: スキル名

    Returns:
        dict: スキル詳細情報（見つからない場合はNone）
    """
    skill_dir = SKILLS_DIR / skill_name
    if not skill_dir.exists():
        return None

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    info = parse_skill_md(skill_md)
    info["name"] = skill_name
    info["path"] = str(skill_md)

    # SKILL.mdの内容を取得（最初の50行）
    try:
        content = skill_md.read_text(encoding="utf-8")
        lines = content.split("\n")
        # frontmatterを除外
        in_frontmatter = False
        content_lines = []
        for line in lines[:50]:
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue
            if not in_frontmatter:
                content_lines.append(line)
        info["preview"] = "\n".join(content_lines[:30])
    except Exception:
        info["preview"] = ""

    # スクリプト一覧
    scripts_dir = skill_dir / "scripts"
    if scripts_dir.exists():
        info["scripts"] = [f.name for f in scripts_dir.iterdir() if f.is_file()]
    else:
        info["scripts"] = []

    # 参考ファイル一覧
    references_dir = skill_dir / "references"
    if references_dir.exists():
        info["references"] = [f.name for f in references_dir.iterdir() if f.is_file()]
    else:
        info["references"] = []

    return info


def format_skills_list(skills: list[dict]) -> str:
    """
    スキル一覧をDiscord用にフォーマット

    Args:
        skills: スキル情報のリスト

    Returns:
        str: フォーマットされたテキスト
    """
    lines = ["**🎋 スキル一覧**\n"]

    for skill in skills:
        name = skill.get("name", "unknown")
        desc = skill.get("description", "")
        # 説明を100文字に短縮
        if len(desc) > 100:
            desc = desc[:97] + "..."

        icons = ""
        if skill.get("has_scripts"):
            icons += "📜"
        if skill.get("has_references"):
            icons += "📚"

        lines.append(f"- **{name}** {icons}")
        if desc:
            lines.append(f"  {desc}")

    lines.append(f"\n**合計: {len(skills)}スキル**")
    lines.append("\n`/skills show <名前>` で詳細を表示")

    return "\n".join(lines)


def format_skill_detail(skill: dict) -> str:
    """
    スキル詳細をDiscord用にフォーマット

    Args:
        skill: スキル詳細情報

    Returns:
        str: フォーマットされたテキスト
    """
    lines = [f"**🎋 {skill.get('name', 'unknown')}**\n"]

    desc = skill.get("description", "")
    if desc:
        lines.append(f"> {desc}\n")

    # スクリプト
    scripts = skill.get("scripts", [])
    if scripts:
        lines.append("**📜 Scripts:**")
        for s in scripts[:10]:
            lines.append(f"- `{s}`")
        if len(scripts) > 10:
            lines.append(f"- ... and {len(scripts) - 10} more")
        lines.append("")

    # 参考ファイル
    refs = skill.get("references", [])
    if refs:
        lines.append("**📚 References:**")
        for r in refs[:10]:
            lines.append(f"- `{r}`")
        if len(refs) > 10:
            lines.append(f"- ... and {len(refs) - 10} more")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    # テスト
    skills = get_all_skills()
    print(f"Found {len(skills)} skills:")
    for s in skills:
        print(f"  - {s['name']}: {s['description'][:50]}...")

    print("\n--- Detail ---")
    detail = get_skill_detail("daily-memory")
    if detail:
        print(format_skill_detail(detail))
