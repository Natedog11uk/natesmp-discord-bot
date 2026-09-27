import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
from discord.ext import commands

PORT = int(os.getenv("PORT", "10000"))
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing.")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"NateSMP AntiCheat bot is online!")

    def log_message(self, format, *args):
        pass


def start_web_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()


threading.Thread(
    target=start_web_server,
    daemon=True
).start()


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print(f"READY: {bot.user} connected", flush=True)

    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="NateSMP AntiCheat")
    )

    print("PRESENCE: online set successfully", flush=True)


@bot.command()
async def ping(ctx):
    await ctx.send("NateSMP AntiCheat is online!")


print("STARTING DISCORD BOT...", flush=True)

bot.run(TOKEN)
```
