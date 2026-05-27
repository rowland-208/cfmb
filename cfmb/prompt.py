def render_discord_content(rows: list[dict]) -> str:
    """Renders oldest-first rows as markdown grouped by channel then by day.

    Layout:
        ### {channel}
        **{YYYY-MM-DD}**
        - {username}: {content}

    Multi-line content is collapsed to a single line. Channels appear in the
    order they first occur in the input.
    """
    if not rows:
        return ""
    by_channel: dict[str, list[dict]] = {}
    for row in rows:
        channel = row.get("channel_name") or "unknown"
        by_channel.setdefault(channel, []).append(row)

    lines: list[str] = []
    for channel, ch_rows in by_channel.items():
        lines.append(f"### {channel}")
        current_day: str | None = None
        for r in ch_rows:
            day = _date_from_timestamp(r.get("timestamp", ""))
            if day != current_day:
                lines.append(f"**{day}**")
                current_day = day
            content_oneline = " ".join((r.get("content") or "").split())
            username = r.get("username") or "unknown"
            lines.append(f"- {username}: {content_oneline}")
    return "\n".join(lines)


def build_system_prompt(*, base: str, meetup: str, handbook: str, discord: str) -> str:
    """Concatenates base + (meetup, handbook, discord) with H2 section headings.

    Sections are separated by a horizontal rule (`---`). Empty sections are
    omitted entirely (no heading, no rule). Base is rendered as-is (it
    manages its own structure).
    """
    parts = [base.rstrip()]
    if meetup.strip():
        parts.append("## Upcoming events\n" + meetup.rstrip())
    if handbook.strip():
        parts.append("## Handbook\n" + handbook.rstrip())
    if discord.strip():
        parts.append("## Recent guild activity\n" + discord.rstrip())
    return "\n\n---\n\n".join(parts)


def build_chain_messages(rows: list[dict], bot_user_id: str) -> list[dict]:
    """Maps oldest-first chain rows to {'role', 'content'} dicts.

    Role is derived from user_id: bot_user_id → 'assistant', else 'user'. User
    turns are prefixed with the speaker's username (`username: content`) so the
    model can tell who is talking and answer questions like "who am I"; the
    bot's own turns are left unprefixed.
    """
    messages: list[dict] = []
    for r in rows:
        content = r.get("content") or ""
        if str(r["user_id"]) == str(bot_user_id):
            messages.append({"role": "assistant", "content": content})
        else:
            username = r.get("username") or "unknown"
            messages.append({"role": "user", "content": f"{username}: {content}"})
    return messages


def _date_from_timestamp(ts: str) -> str:
    """Extracts YYYY-MM-DD from a SQLite-style timestamp string."""
    if not ts:
        return "unknown-date"
    return ts.split(" ", 1)[0].split("T", 1)[0]
