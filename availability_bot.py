import os
import time
import discord
from discord import Embed, ButtonStyle, ui
from dotenv import load_dotenv

# ================= SETUP =================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
bot = discord.Bot(intents=intents)

sessions = {}

ROLE_NAME = "Availability Manager"   

def generate_session_id():
    return f"session_{int(time.time())}"

def has_permission(member: discord.Member):
    # Admin OR has Availability Manager role
    if member.guild_permissions.administrator:
        return True

    for role in member.roles:
        if role.name == ROLE_NAME:
            return True

    return False

# ================= EMBED =================

def build_embed(session, bot):
    channel = bot.get_channel(int(session["channel_id"]))
    if not channel:
        return None

    accepted, tentative, declined = [], [], []

    for uid, status in session["statuses"].items():
        member = channel.guild.get_member(int(uid))
        if not member:
            continue

        if status == "available":
            accepted.append(member.mention)
        elif status == "unsure":
            tentative.append(member.mention)
        elif status == "unavailable":
            declined.append(member.mention)

    embed = Embed(
        title=f"📅 **{session['title']}**",
        description=f"📝 {session['description']}",
        color=0x2ecc71
    )

    embed.add_field(
        name=f"✅ Accepted ({len(accepted)})",
        value="\n".join(accepted) if accepted else "—",
        inline=False
    )

    embed.add_field(
        name=f"❔ Tentative ({len(tentative)})",
        value="\n".join(tentative) if tentative else "—",
        inline=False
    )

    embed.add_field(
        name=f"❌ Declined ({len(declined)})",
        value="\n".join(declined) if declined else "—",
        inline=False
    )

    embed.set_footer(text="Click a button below to vote")

    return embed

# ================= MODAL =================

class AvailabilityModal(ui.Modal):
    def __init__(self):
        super().__init__(title="Create availability")

        self.title_input = ui.TextInput(
            label="Session title",
            placeholder="Pro Clubs Session"
        )

        self.desc_input = ui.TextInput(
            label="Description",
            placeholder="Vote if you will attend",
            required=False
        )

        self.add_item(self.title_input)
        self.add_item(self.desc_input)

    async def callback(self, interaction: discord.Interaction):
        session_id = generate_session_id()

        sessions[session_id] = {
            "channel_id": str(interaction.channel.id),
            "title": self.title_input.value,
            "description": self.desc_input.value or "Vote if you will attend",
            "statuses": {},
            "message_id": None
        }

        embed = build_embed(sessions[session_id], bot)
        view = AvailabilityView(session_id)

        msg = await interaction.channel.send(embed=embed, view=view)
        sessions[session_id]["message_id"] = str(msg.id)

        await interaction.response.send_message(
            "✅ Availability session created.",
            ephemeral=True
        )

# ================= AVAILABILITY VIEW =================

class AvailabilityView(ui.View):
    def __init__(self, session_id):
        super().__init__(timeout=None)
        self.session_id = session_id

    async def vote(self, interaction, status):
        session = sessions.get(self.session_id)
        session["statuses"][str(interaction.user.id)] = status

        embed = build_embed(session, bot)
        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.defer()

    @ui.button(label="✅ Available", style=ButtonStyle.success)
    async def available(self, button, interaction):
        await self.vote(interaction, "available")

    @ui.button(label="❔ Unsure", style=ButtonStyle.secondary)
    async def unsure(self, button, interaction):
        await self.vote(interaction, "unsure")

    @ui.button(label="❌ Unavailable", style=ButtonStyle.danger)
    async def unavailable(self, button, interaction):
        await self.vote(interaction, "unavailable")

    # 🔔 REMINDER
    @ui.button(label="🔔 Reminder", style=ButtonStyle.primary, row=1)
    async def reminder(self, button, interaction):
        if not has_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ You need Admin or Availability Manager role.",
                ephemeral=True
            )

        session = sessions.get(self.session_id)
        channel = interaction.channel
        members = [m for m in channel.members if not m.bot]

        no_response = [m for m in members if str(m.id) not in session["statuses"]]
        unsure_users = [
            channel.guild.get_member(int(uid))
            for uid, status in session["statuses"].items()
            if status == "unsure"
        ]

        targets = list({m for m in no_response + unsure_users if m})

        if not targets:
            return await interaction.response.send_message(
                "✅ No one to remind.",
                ephemeral=True
            )

        await channel.send(
            "🔔 **Reminder:** Please confirm your availability!\n\n"
            + " ".join(m.mention for m in targets)
        )

        await interaction.response.send_message("🔔 Reminder sent.", ephemeral=True)

    # 🔄 RESET
    @ui.button(label="🔄 Reset votes", style=ButtonStyle.secondary, row=1)
    async def reset(self, button, interaction):
        if not has_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ You need Admin or Availability Manager role.",
                ephemeral=True
            )

        session = sessions.get(self.session_id)
        session["statuses"].clear()

        embed = build_embed(session, bot)
        await interaction.message.edit(embed=embed, view=self)

        await interaction.response.send_message(
            "🔄 All votes have been reset.",
            ephemeral=True
        )

# ================= PANEL =================

class CreatePanel(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📝 Create availability", style=ButtonStyle.primary)
    async def create(self, button, interaction):
        if not has_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ You need Admin or Availability Manager role.",
                ephemeral=True
            )

        await interaction.response.send_modal(AvailabilityModal())

# ================= RIGHT CLICK EDIT =================

class EditAvailabilityModal(ui.Modal):
    def __init__(self, session):
        super().__init__(title="Edit availability")

        self.session = session

        self.title_input = ui.TextInput(
            label="Session title",
            value=session["title"]
        )

        self.desc_input = ui.TextInput(
            label="Description",
            value=session["description"],
            required=False
        )

        self.add_item(self.title_input)
        self.add_item(self.desc_input)

    async def callback(self, interaction: discord.Interaction):
        self.session["title"] = self.title_input.value
        self.session["description"] = self.desc_input.value or "Vote if you will attend"  # Fixed: Default to the same as creation if empty

        channel = interaction.channel
        message = await channel.fetch_message(int(self.session["message_id"]))

        embed = build_embed(self.session, bot)
        await message.edit(embed=embed)

        await interaction.response.send_message(
            "✅ Availability updated.",
            ephemeral=True
        )

@bot.message_command(name="Edit availability", guild_ids=[1456061431119347715, 812723567686320168])  # Keep for now, but slash is alternative
async def edit_availability(interaction: discord.Interaction, message: discord.Message):
    if not has_permission(interaction.user):
        return await interaction.response.send_message(
            "❌ You need Admin or Availability Manager role.",
            ephemeral=True
        )

    session = None
    for s in sessions.values():
        if s.get("message_id") == str(message.id):
            session = s
            break

    if not session:
        return await interaction.response.send_message(
            "❌ This is not an availability message.",
            ephemeral=True
        )

    await interaction.response.send_modal(EditAvailabilityModal(session))

# ================= READY =================

@bot.event
async def on_ready():
    await bot.sync_commands()
    print(f"✅ Logged in as {bot.user}")

# ================= COMMANDS =================

@bot.slash_command(name="send_availability_panel")
async def send_panel(ctx):
    if not has_permission(ctx.user):
        return await ctx.respond(
            "❌ You need Admin or Availability Manager role.",
            ephemeral=True
        )

    # Respond immediately to the interaction (fixed: avoids timeout)
    await ctx.respond("✅ Panel sent.", ephemeral=True)

    # Then send the embed to the channel
    embed = Embed(
        title="📝 Availability",
        description="Click the button below to create a new availability session.",
        color=0x3498db
    )

    await ctx.channel.send(embed=embed, view=CreatePanel())

@bot.slash_command(name="edit_availability")
async def slash_edit_availability(ctx, message_id: str):
    if not has_permission(ctx.user):
        return await ctx.respond(
            "❌ You need Admin or Availability Manager role.",
            ephemeral=True
        )

    # Find the session by message ID
    session = None
    for s in sessions.values():
        if s.get("message_id") == message_id:
            session = s
            break

    if not session:
        return await ctx.respond(
            "❌ No availability session found for that message ID. Ensure it's a valid embed from this bot.",
            ephemeral=True
        )

    # Defer and send modal
    await ctx.defer(ephemeral=True)
    await ctx.followup.send_modal(EditAvailabilityModal(session))

# ================= RUN =================

bot.run(TOKEN)
