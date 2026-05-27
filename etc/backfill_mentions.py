"""One-shot backfill: rewrite raw Discord mention markup in stored message
content to readable @names / #channels, using the id->name pairs the bot has
already recorded on every row of the `messages` table.

Resolves what the table can supply:
    <@id> / <@!id>  -> @username   (latest display name that id authored under)
    <#id>           -> #channel    (latest name that channel_id was seen under)

Left untouched (no name source exists in the DB):
    <@&id>          role mentions  (roles never author a row)
    any id that was mentioned but never authored a message

This mirrors what `message.clean_content` now produces for new messages; the
difference is only the name source (this reads names back out of our own rows,
clean_content asks Discord live), which is why a few ids stay raw.

Usage:
    python etc/backfill_mentions.py --db cfmb.sqlite --dry-run   # preview only
    python etc/backfill_mentions.py --db cfmb.sqlite             # apply
"""
import argparse
import re
import sqlite3

USER_RE = re.compile(r"<@!?(\d+)>")
CHAN_RE = re.compile(r"<#(\d+)>")


def build_maps(conn: sqlite3.Connection) -> tuple[dict, dict]:
    """Builds {user_id: latest_username} and {channel_id: latest_channel_name}.

    `MAX(id)` per group = the most recent row that group authored / was seen on
    (id autoincrements), so renamed users resolve to their current name.
    """
    users = {
        r["user_id"]: r["username"]
        for r in conn.execute(
            "SELECT user_id, username FROM messages "
            "WHERE id IN (SELECT MAX(id) FROM messages GROUP BY user_id)"
        )
        if r["username"]
    }
    channels = {
        r["channel_id"]: r["channel_name"]
        for r in conn.execute(
            "SELECT channel_id, channel_name FROM messages WHERE id IN "
            "(SELECT MAX(id) FROM messages WHERE channel_id IS NOT NULL GROUP BY channel_id)"
        )
        if r["channel_name"]
    }
    return users, channels


def remap(content: str, users: dict, channels: dict) -> str:
    """Substitutes user/channel mentions; unknown ids and roles pass through."""
    if not content:
        return content

    def sub_user(m: re.Match) -> str:
        uid = m.group(1)
        return f"@{users[uid]}" if uid in users else m.group(0)

    def sub_chan(m: re.Match) -> str:
        cid = m.group(1)
        return f"#{channels[cid]}" if cid in channels else m.group(0)

    return CHAN_RE.sub(sub_chan, USER_RE.sub(sub_user, content))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--dry-run", action="store_true", help="preview without writing")
    ap.add_argument("--limit", type=int, default=12, help="rows to print in the preview")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    users, channels = build_maps(conn)
    print(f"maps built: {len(users)} users, {len(channels)} channels")

    changes = []
    for r in conn.execute(
        "SELECT id, content FROM messages WHERE content LIKE '%<@%' OR content LIKE '%<#%'"
    ):
        new = remap(r["content"], users, channels)
        if new != r["content"]:
            changes.append((r["id"], r["content"], new))

    print(f"{len(changes)} rows would change")
    for rid, old, new in changes[: args.limit]:
        print(f"--- row {rid}")
        print(f"  - {old[:160]}")
        print(f"  + {new[:160]}")

    if args.dry_run:
        print("dry-run: no writes made")
        return

    with conn:
        conn.executemany(
            "UPDATE messages SET content = ? WHERE id = ?",
            [(new, rid) for rid, _, new in changes],
        )
    print(f"updated {len(changes)} rows")


if __name__ == "__main__":
    main()
