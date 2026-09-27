import os
import threading
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
from discord.ext import commands


# =========================
# Render health-check server
# =========================

PORT = int(os.getenv("PORT", "10000"))


class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"NateSMP AntiCheat bot is online!")

    def log_message(self, format, *args):
        return


def start_web_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"Health server listening on port {PORT}")
    server.serve_forever()


# Start the web server in the background
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


@bot.event
async def on_ready():
    print(f"READY: {bot.user} connected")

    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="NateSMP AntiCheat")
    )

    print("PRESENCE: online set successfully")


@bot.command()
async def ping(ctx):
    await ctx.send("NateSMP AntiCheat is online! and not 67!")


print("STARTING NATESMP BOT...")
bot.run(TOKEN)
