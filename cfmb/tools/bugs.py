import io
import pathlib

import discord
from PIL import Image, ImageDraw, ImageFont

from cfmb.tools.base import Tool

BUGS_IMAGE = pathlib.Path(__file__).resolve().parent.parent.parent / "static" / "communist_bugs_bunny.jpg"
MEME_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class BugsTool(Tool):
    name = "bugs_meme"
    description = (
        "Send the Communist Bugs Bunny meme image to the channel for humorous effect. "
        "Use this tool rarely, only when the user is discussing equipment, supplies, or guild events."
    )
    parameters = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {
                "type": "string",
                "description": "A simple noun, must be guild equipment, supplies, or the word guild, e.g., 'filament', 'laser cutter', 'guild'",
            },
        },
    }

    async def run(self, args: dict, context: dict) -> str:
        text = f"OUR {args.get('text', '').upper()}"
        message = context.get("message")
        if not message:
            return "No message context available."

        img = Image.open(BUGS_IMAGE).convert("RGB")
        draw = ImageDraw.Draw(img)
        font_size = max(12, int(img.height * 0.10))
        font = ImageFont.truetype(MEME_FONT, font_size)

        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (img.width - text_w) // 2
        y = int(img.height * 0.90) - text_h // 2

        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                draw.text((x + dx, y + dy), text, font=font, fill="black")
        draw.text((x, y), text, font=font, fill="white")

        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        await message.channel.send(file=discord.File(buf, filename="bugs.jpg"))
        return "Sent the Communist Bugs Bunny meme to the channel."
