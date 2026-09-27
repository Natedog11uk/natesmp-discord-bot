import os
import threading
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
from discord.ext import commands
from discord import app_commands


# =========================
# Render health server
# =========================

PORT = int(os.getenv("PORT", "10000"))


class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(
            b"NateSMP AntiCheat bot is online!"
        )

    def do_POST(self):

        if self.path != "/anticheat/case":
            self.send_response(404)
            self.end_headers()
            return

        provided_key = self.headers.get(
            "X-AntiCheat-Key"
        )

        if provided_key != ANTICHEAT_API_KEY:
            self.send_response(401)
            self.end_headers()
            return

        try:
            length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            body = self.rfile.read(length)

            import json

            data = json.loads(
                body.decode("utf-8")
            )

            required = [
                "case_id",
                "player",
                "detection",
                "severity",
                "confidence",
                "evidence",
                "action"
            ]

            if not all(
                key in data
                for key in required
            ):
                self.send_response(400)
                self.end_headers()
                return

            future = asyncio.run_coroutine_threadsafe(
                create_anticheat_case(
                    case_id=str(data["case_id"]),
                    player=str(data["player"]),
                    detection=str(data["detection"]),
                    severity=str(data["severity"]),
                    confidence=int(data["confidence"]),
                    evidence=str(data["evidence"]),
                    action=str(data["action"])
                ),
                bot.loop
            )

            future.result(timeout=10)

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json"
            )
            self.end_headers()

            self.wfile.write(
                b'{"success":true}'
            )

        except Exception as e:

            print(
                f"Anti-cheat API error: {e}",
                flush=True
            )

            self.send_response(500)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def start_web_server():

    server = HTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler
    )

    print(
        f"Health server listening on port {PORT}",
        flush=True
    )

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
    raise RuntimeError(
        "DISCORD_TOKEN environment variable is missing."
    )


ANTICHEAT_CHANNEL_ID = 1553820612328300554

APPEAL_LINK = "https://discord.gg/P8HyYh5BbC"
ANTICHEAT_API_KEY = os.getenv("ANTICHEAT_API_KEY")


intents = discord.Intents.default()
intents.message_content = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# Anti-cheat case storage
# =========================

cases = {}


# =========================
# Ban modal
# =========================

class BanModal(discord.ui.Modal):

    def __init__(self, case_id):

        super().__init__(
            title="Ban Player"
        )

        self.case_id = case_id

        self.duration = discord.ui.TextInput(
            label="Ban duration",
            placeholder="Permanent / 7 days / 30 days",
            required=True,
            max_length=50
        )

        self.reason = discord.ui.TextInput(
            label="Ban reason",
            placeholder="Enter the reason for the punishment",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=500
        )

        self.add_item(self.duration)
        self.add_item(self.reason)


    async def on_submit(self, interaction):

        case = cases.get(self.case_id)

        if not case:

            await interaction.response.send_message(
                "That anti-cheat case no longer exists.",
                ephemeral=True
            )

            return


        case["ban_duration"] = self.duration.value
        case["ban_reason"] = self.reason.value
        case["handled_by"] = str(
            interaction.user
        )


        await interaction.response.send_message(
            f"Ban recorded for `{case['player']}`.\n"
            f"Duration: `{self.duration.value}`\n"
            f"Reason: `{self.reason.value}`",
            ephemeral=True
        )


        # Update the staff message.

        if case.get("message"):

            embed = case["message"].embeds[0]

            embed.add_field(
                name="Punishment",
                value=(
                    f"🔴 **BANNED**\n"
                    f"Duration: `{self.duration.value}`\n"
                    f"Reason: {self.reason.value}\n"
                    f"Staff: {interaction.user.mention}"
                ),
                inline=False
            )

            embed.set_footer(
                text=f"Case {self.case_id} • Punishment issued"
            )

            await case["message"].edit(
                embed=embed,
                view=None
            )


# =========================
# Case buttons
# =========================

class CaseButtons(discord.ui.View):

    def __init__(self, case_id):

        super().__init__(
            timeout=None
        )

        self.case_id = case_id


    @discord.ui.button(
        label="Clear Review",
        style=discord.ButtonStyle.success,
        emoji="🟢"
    )
    async def clear_review(
        self,
        interaction,
        button
    ):

        case = cases.get(self.case_id)

        if not case:

            await interaction.response.send_message(
                "That case no longer exists.",
                ephemeral=True
            )

            return


        case["handled_by"] = str(
            interaction.user
        )

        case["decision"] = "CLEAR REVIEW"


        await interaction.response.send_message(
            f"Review cleared for `{case['player']}`.",
            ephemeral=True
        )


        if case.get("message"):

            embed = case["message"].embeds[0]

            embed.add_field(
                name="Resolution",
                value=(
                    f"🟢 **REVIEW CLEARED**\n"
                    f"Staff: {interaction.user.mention}"
                ),
                inline=False
            )

            embed.set_footer(
                text=f"Case {self.case_id} • Review cleared"
            )

            await case["message"].edit(
                embed=embed,
                view=None
            )


    @discord.ui.button(
        label="Ban",
        style=discord.ButtonStyle.danger,
        emoji="🔴"
    )
    async def ban(
        self,
        interaction,
        button
    ):

        await interaction.response.send_modal(
            BanModal(self.case_id)
        )


# =========================
# Create anti-cheat case
# =========================

async def create_anticheat_case(
    case_id,
    player,
    detection,
    severity,
    confidence,
    evidence,
    action
):

    channel = bot.get_channel(
        ANTICHEAT_CHANNEL_ID
    )

    if channel is None:

        print(
            "ERROR: Anti-cheat channel not found.",
            flush=True
        )

        return


    embed = discord.Embed(
        title="🛡️ NateAntiCheat — Review Required",
        description=(
            "An anti-cheat detection requires "
            "staff attention."
        ),
        color=discord.Color.orange()
    )


    embed.add_field(
        name="🆔 Case ID",
        value=f"`{case_id}`",
        inline=True
    )

    embed.add_field(
        name="👤 Player",
        value=f"`{player}`",
        inline=True
    )

    embed.add_field(
        name="🔎 Detection",
        value=detection,
        inline=False
    )

    embed.add_field(
        name="⚠️ Severity",
        value=severity,
        inline=True
    )

    embed.add_field(
        name="📊 Confidence",
        value=f"{confidence}%",
        inline=True
    )

    embed.add_field(
        name="🎯 Action",
        value=action,
        inline=False
    )

    embed.add_field(
        name="📋 Evidence",
        value=evidence,
        inline=False
    )

    embed.set_footer(
        text=f"Case {case_id}"
    )


    view = CaseButtons(
        case_id
    )


    message = await channel.send(
        embed=embed,
        view=view
    )


    cases[case_id] = {
        "player": player,
        "detection": detection,
        "severity": severity,
        "confidence": confidence,
        "evidence": evidence,
        "action": action,
        "message": message
    }


# =========================
# Bot ready
# =========================

@bot.event
async def on_ready():

    print(
        f"READY: {bot.user} connected",
        flush=True
    )

    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(
            name="NateSMP AntiCheat"
        )
    )

    print(
        "PRESENCE SENT",
        flush=True
    )

    print(
        f"BOT STATUS: {bot.status}",
        flush=True
    )


# =========================
# Ping
# =========================

@bot.command()
async def ping(ctx):

    await ctx.send(
        "NateSMP AntiCheat is online!"
    )


# =========================
# Status
# =========================

@bot.command()
async def status(ctx):

    await ctx.send(
        f"Bot status: `{bot.status}`\n"
        f"Activity: `{bot.activity}`"
    )


# =========================
# Test anti-cheat case
# =========================

@bot.command()
@commands.has_permissions(
    manage_guild=True
)
async def testcase(ctx):

    import random

    case_id = (
        "NAC-"
        + str(
            random.randint(
                100000,
                999999
            )
        )
    )

    await create_anticheat_case(
        case_id=case_id,
        player="TestPlayer",
        detection="Suspicious flight",
        severity="HIGH",
        confidence=96,
        evidence=(
            "Test detection generated "
            "by Discord bot."
        ),
        action="KICKED - REVIEW REQUIRED"
    )

    await ctx.send(
        f"Test case `{case_id}` created."
    )


# =========================
# Start
# =========================

print(
    "STARTING DISCORD BOT...",
    flush=True
)


bot.run(TOKEN)
