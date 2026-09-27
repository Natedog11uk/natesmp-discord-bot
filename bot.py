import os
import threading
import asyncio
import json
import random
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
from discord.ext import commands


# =========================
# Render health / API server
# =========================

PORT = int(os.getenv("PORT", "10000"))

TOKEN = os.getenv("DISCORD_TOKEN")
ANTICHEAT_API_KEY = os.getenv("ANTICHEAT_API_KEY")

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN environment variable is missing."
    )

if not ANTICHEAT_API_KEY:
    raise RuntimeError(
        "ANTICHEAT_API_KEY environment variable is missing."
    )


ANTICHEAT_CHANNEL_ID = 1553820612328300554

APPEAL_LINK = "https://discord.gg/P8HyYh5BbC"


# Pending actions waiting for Minecraft
pending_actions = []


# =========================
# HTTP API
# =========================

class HealthHandler(BaseHTTPRequestHandler):

    def send_json(self, status, data):

        body = json.dumps(data).encode("utf-8")

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.end_headers()

        self.wfile.write(body)


    def authorised(self):

        provided_key = self.headers.get(
            "X-AntiCheat-Key"
        )

        return provided_key == ANTICHEAT_API_KEY


    def do_GET(self):

        # Normal Render health check
        if self.path == "/":

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/plain"
            )

            self.end_headers()

            self.wfile.write(
                b"NateSMP AntiCheat bot is online!"
            )

            return


        # Minecraft polls this endpoint
        if self.path == "/anticheat/actions":

            if not self.authorised():

                self.send_response(401)
                self.end_headers()
                return


            # Copy the queue so Minecraft gets a stable response.
            actions = list(pending_actions)

            self.send_json(
                200,
                {
                    "success": True,
                    "actions": actions
                }
            )

            return


        self.send_response(404)
        self.end_headers()


    def do_POST(self):

        # Minecraft sends new Discord cases here
        if self.path == "/anticheat/case":

            if not self.authorised():

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

                data = json.loads(
                    body.decode("utf-8")
                )

                required = [
                    "case_id",
                    "player",
                    "player_uuid",
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

                    self.send_json(
                        400,
                        {
                            "success": False,
                            "error": "Missing required field"
                        }
                    )

                    return


                future = asyncio.run_coroutine_threadsafe(

                    create_anticheat_case(
                        case_id=str(
                            data["case_id"]
                        ),
                        player=str(
                            data["player"]
                        ),
                        player_uuid=str(
                            data["player_uuid"]
                        ),
                        detection=str(
                            data["detection"]
                        ),
                        severity=str(
                            data["severity"]
                        ),
                        confidence=int(
                            data["confidence"]
                        ),
                        evidence=str(
                            data["evidence"]
                        ),
                        action=str(
                            data["action"]
                        )
                    ),

                    bot.loop
                )


                future.result(
                    timeout=10
                )


                self.send_json(
                    200,
                    {
                        "success": True
                    }
                )


            except Exception as e:

                print(
                    f"Anti-cheat API error: {e}",
                    flush=True
                )

                self.send_json(
                    500,
                    {
                        "success": False,
                        "error": str(e)
                    }
                )

            return


        # Minecraft acknowledges an action
        if self.path == "/anticheat/action-ack":

            if not self.authorised():

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

                data = json.loads(
                    body.decode("utf-8")
                )

                action_id = str(
                    data.get(
                        "action_id",
                        ""
                    )
                )


                if not action_id:

                    self.send_json(
                        400,
                        {
                            "success": False
                        }
                    )

                    return


                global pending_actions

                before = len(
                    pending_actions
                )


                pending_actions = [
                    action
                    for action in pending_actions
                    if action["action_id"]
                    != action_id
                ]


                removed = (
                    before
                    != len(pending_actions)
                )


                self.send_json(
                    200,
                    {
                        "success": True,
                        "removed": removed
                    }
                )


            except Exception as e:

                print(
                    f"Action acknowledgement error: {e}",
                    flush=True
                )

                self.send_json(
                    500,
                    {
                        "success": False,
                        "error": str(e)
                    }
                )

            return


        self.send_response(404)
        self.end_headers()


    def log_message(
        self,
        format,
        *args
    ):
        pass


def start_web_server():

    server = HTTPServer(
        (
            "0.0.0.0",
            PORT
        ),
        HealthHandler
    )

    print(
        f"Health/API server listening on port {PORT}",
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

intents = discord.Intents.default()

intents.message_content = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# Case storage
# =========================

cases = {}


# =========================
# Queue Minecraft action
# =========================

def queue_action(
    action_type,
    case
):

    action_id = (
        "ACT-"
        + str(
            random.randint(
                100000,
                999999
            )
        )
    )


    action = {

        "action_id": action_id,

        "type": action_type,

        "case_id": case["case_id"],

        "player": case["player"],

        "player_uuid": case["player_uuid"]

    }


    if action_type == "BAN":

        action["duration"] = (
            case.get(
                "ban_duration",
                "Permanent"
            )
        )

        action["reason"] = (
            case.get(
                "ban_reason",
                "NateAntiCheat violation"
            )
        )

        action["staff"] = (
            case.get(
                "handled_by",
                "Unknown"
            )
        )


    pending_actions.append(
        action
    )


    print(
        f"QUEUED MINECRAFT ACTION: {action}",
        flush=True
    )


    return action_id


# =========================
# Ban modal
# =========================

class BanModal(discord.ui.Modal):

    def __init__(
        self,
        case_id
    ):

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


        self.add_item(
            self.duration
        )

        self.add_item(
            self.reason
        )


    async def on_submit(
        self,
        interaction
    ):

        case = cases.get(
            self.case_id
        )


        if not case:

            await interaction.response.send_message(
                "That anti-cheat case no longer exists.",
                ephemeral=True
            )

            return


        case["ban_duration"] = (
            self.duration.value
        )

        case["ban_reason"] = (
            self.reason.value
        )

        case["handled_by"] = str(
            interaction.user
        )

        case["decision"] = "BAN"


        action_id = queue_action(
            "BAN",
            case
        )


        await interaction.response.send_message(

            f"🔴 Ban queued for `{case['player']}`.\n"
            f"Duration: `{self.duration.value}`\n"
            f"Reason: `{self.reason.value}`\n"
            f"Action ID: `{action_id}`",

            ephemeral=True
        )


        if case.get("message"):

            embed = (
                case["message"]
                .embeds[0]
            )


            embed.add_field(

                name="Punishment",

                value=(

                    f"🔴 **BAN QUEUED**\n"

                    f"Duration: `{self.duration.value}`\n"

                    f"Reason: {self.reason.value}\n"

                    f"Staff: {interaction.user.mention}\n"

                    f"Action ID: `{action_id}`"

                ),

                inline=False
            )


            embed.set_footer(

                text=(
                    f"Case {self.case_id}"
                    " • Ban queued"
                )

            )


            await case["message"].edit(
                embed=embed,
                view=None
            )


# =========================
# Case buttons
# =========================

class CaseButtons(
    discord.ui.View
):

    def __init__(
        self,
        case_id
    ):

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

        case = cases.get(
            self.case_id
        )


        if not case:

            await interaction.response.send_message(
                "That case no longer exists.",
                ephemeral=True
            )

            return


        case["handled_by"] = str(
            interaction.user
        )

        case["decision"] = (
            "CLEAR REVIEW"
        )


        action_id = queue_action(
            "CLEAR",
            case
        )


        await interaction.response.send_message(

            f"🟢 Review-clear action queued for "
            f"`{case['player']}`.\n"
            f"Action ID: `{action_id}`",

            ephemeral=True
        )


        if case.get("message"):

            embed = (
                case["message"]
                .embeds[0]
            )


            embed.add_field(

                name="Resolution",

                value=(

                    f"🟢 **CLEAR QUEUED**\n"

                    f"Staff: {interaction.user.mention}\n"

                    f"Action ID: `{action_id}`"

                ),

                inline=False
            )


            embed.set_footer(

                text=(
                    f"Case {self.case_id}"
                    " • Clear queued"
                )

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
            BanModal(
                self.case_id
            )
        )


# =========================
# Create anti-cheat case
# =========================

async def create_anticheat_case(
    case_id,
    player,
    player_uuid,
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

        title=(
            "🛡️ NateAntiCheat — "
            "Review Required"
        ),

        description=(
            "An anti-cheat detection "
            "requires staff attention."
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

        "case_id": case_id,

        "player": player,

        "player_uuid": player_uuid,

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

        f"Activity: `{bot.activity}`\n"

        f"Pending Minecraft actions: "
        f"`{len(pending_actions)}`"

    )


# =========================
# Test anti-cheat case
# =========================

@bot.command()
@commands.has_permissions(
    manage_guild=True
)
async def testcase(ctx):

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

        player_uuid=(
            "00000000-0000-0000-0000-000000000000"
        ),

        detection="Suspicious flight",

        severity="HIGH",

        confidence=96,

        evidence=(
            "Test detection generated "
            "by Discord bot."
        ),

        action=(
            "KICKED - REVIEW REQUIRED"
        )

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


bot.run(
    TOKEN
)
