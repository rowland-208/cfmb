# CFMB — Cape Fear Makers Bot

A focused context bot for the Cape Fear Makers Guild Discord. When @mentioned (or replied-to), it assembles a system prompt from:

- A checked-in base persona (`etc/base_system.md`)
- Live meetup events (scraped per-request)
- Live handbook pages from the guild wiki (scraped per-request)
- The past 7 days of server activity from channels other than the current conversation chain

Then sends one chat completion through **OpenRouter** (primary) with a local **Ollama** fallback. No tools, no slash commands, no scheduled tasks.

## Deployment

### Prerequisites

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh        # uv (Python package manager)
curl -fsSL https://ollama.com/install.sh | sh          # Ollama (fallback backend)
ollama pull gemma3:4b                                   # default fallback model
```

You will also need:

- A Discord bot token + the bot user id ([Discord Developer Portal](https://discord.com/developers/applications))
- An [OpenRouter](https://openrouter.ai/) API key + a model id

### Configuration

Create `~/.cfmb` (dotenv format):

```ini
# Required
DISCORD_BOT_TOKEN=...
BOT_USER_ID=1234567890123456789
DB_NAME=/home/<user>/repos/cfmb/cfmb.sqlite
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free

# Optional
OLLAMA_MODEL=gemma3:4b
DEV_CHANNEL_ID=...
DEV_EXCLUDED_CHANNELS=...           # comma-separated channel IDs to skip
HANDBOOK_URLS=...                   # comma-separated; defaults to 6 standard wiki pages
```

All token-budget knobs default to 100K+ so the assembled prompt typically lands at ~30K tokens, well under most modern model context windows.

### Migrating from the old schema

If you're upgrading from a pre-redesign database (`messages` + `raw_messages` + `rag_chunks` + `user_profiles` + `summaries`), run the one-shot migration **before** starting the new bot:

```bash
python etc/migrate.py \
  --src cfmb_db.sqlite \
  --dst cfmb.sqlite \
  --bot-user-id <your bot user id>
```

The old file is left untouched. Point `DB_NAME` in `~/.cfmb` at the new file.

### Systemd user service

```ini
[Service]
WorkingDirectory=/home/<user>/repos/cfmb
EnvironmentFile=/home/<user>/.cfmb
ExecStart=/home/<user>/repos/cfmb/.venv/bin/python -m cfmb.bot
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

```bash
mkdir -p ~/.config/systemd/user/
# paste service file to ~/.config/systemd/user/cfmb.service
sudo loginctl enable-linger <user>
systemctl --user daemon-reload
systemctl --user enable cfmb
systemctl --user start cfmb
```

### Useful commands

```bash
systemctl --user status cfmb
systemctl --user restart cfmb
journalctl --user -u cfmb -f
```

### Auto-update via cron

`update.sh` pulls the latest code and restarts the service. It defers when the bot is mid-request (via `/tmp/cfmb_active`).

```cron
*/10 * * * * /home/<user>/repos/cfmb/update.sh >> /var/log/cfmb-update.log 2>&1
```

## Development

```bash
uv venv venv-test --python=python3
source venv-test/bin/activate
uv pip install -r requirements.txt -r requirements-test.txt
```

**Tests:**
```bash
./test.sh
```

**Iterate on prompt assembly against a real (or copied prod) sqlite, without an LLM:**
```bash
python etc/smoke_prompt.py
```

**With an LLM in the loop (Ollama):**
```bash
python etc/smoke_prompt.py --with-llm
```

**With an LLM via OpenRouter (e.g. for quality comparisons):**
```bash
python etc/smoke_prompt.py --with-llm --openrouter nvidia/nemotron-3-super-120b-a12b:free
```

## How it decides whether to respond

The bot responds when:
- The message @mentions the bot user, the bot's role, or @everyone, **or**
- The message is a reply to one of the bot's own previous messages.

Everything else is silently recorded to the `messages` table and used as context for future responses.
