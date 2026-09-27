
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
from discord.ext import commands


# =========================
# Render health server
# =========================

PORT = int(os.getenv("PORT", "10000"))


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
    print(f"Health server listening on port {PORT}", flush=True)
    server.serve_forever()


threading.Thread(
    target=start_web_server,
    daemon=True
).start()


# =========================
# Discord bot
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing.")


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# Bot ready
# =========================

@bot.event
async def on_ready():
    print(f"READY: {bot.user} connected", flush=True)

    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="NateSMP AntiCheat")
    )

    print("PRESENCE SENT", flush=True)
    print(f"BOT STATUS: {bot.status}", flush=True)
    print(f"BOT ACTIVITY: {bot.activity}", flush=True)


# =========================
# Ping command
# =========================

@bot.command()
async def ping(ctx):
    await ctx.send("NateSMP AntiCheat is online!")


# =========================
# Status command
# =========================

@bot.command()
async def status(ctx):
    await ctx.send(
        f"Bot status: `{bot.status}`\n"
        f"Activity: `{bot.activity}`"
    )


# =========================
# Start
# =========================

print("STARTING DISCORD BOT...", flush=True)

bot.run(TOKEN)

