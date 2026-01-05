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

# session_id -> session data
sessions = {}

def generate_session_id():
    return f"session_{int(time.time())}"

# ================= EMBED =================

def build_embed(session, bot, closed=False):
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

    title = session["title"]
    if closed:
        title += " 🔒 (Closed)"

    embed = Embed(
        title=title,
        description=session["description"] or " ",
        color=0xe74c3c if closed else 0x2ecc71
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

    if closed:
        embed.set_footer(text="This session is closed. Voting disabled.")

    return embed

# ================= MODAL =================

class AvailabilityModal(ui.Modal):
    def __init__(self):
        super().__init__(title="Create availability")

        self.title_input = ui.InputText(
            label="Session title",
            placeholder="Pro Clubs Session"
        )

        self.desc_input = ui.InputText(
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
            "closed": False,
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
        if session["closed"]:
            return await interaction.response.send_message(
                "❌ This session is closed.",
                ephemeral=True
            )

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

    @ui.button(label="🔔 Reminder", style=ButtonStyle.primary, row=1)
    async def reminder(self, button, interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ Admins only.",
                ephemeral=True
            )

        session = sessions.get(self.session_id)
        channel = interaction.channel

        members = [m for m in channel.members if not m.bot]
        no_response = [m for m in members if str(m.id) not in session["statuses"]]

        if not no_response:
            return await interaction.response.send_message(
                "✅ Everyone already voted.",
                ephemeral=True
            )

        msg = (
            "🔔 **Reminder:** Please vote if you'll be present!\n\n"
            + " ".join(m.mention for m in no_response)
        )

        await channel.send(msg)
        await interaction.response.send_message("🔔 Reminder sent.", ephemeral=True)

    @ui.button(label="🔒 Close session", style=ButtonStyle.secondary, row=1)
    async def close(self, button, interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ Admins only.",
                ephemeral=True
            )

        session = sessions.get(self.session_id)
        session["closed"] = True

        embed = build_embed(session, bot, closed=True)

        for child in self.children:
            child.disabled = True

        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message(
            "🔒 Session closed.",
            ephemeral=True
        )

# ================= CONTEXT MENU EDIT =================

class EditAvailabilityModal(ui.Modal):
    def __init__(self, session):
        super().__init__(title="Edit availability")

        self.session = session

        self.title_input = ui.InputText(
            label="Session title",
            value=session["title"]
        )

        self.desc_input = ui.InputText(
            label="Description",
            value=session["description"],
            required=False
        )

        self.add_item(self.title_input)
        self.add_item(self.desc_input)

    async def callback(self, interaction: discord.Interaction):
        self.session["title"] = self.title_input.value
        self.session["description"] = self.desc_input.value or " "

        channel = interaction.channel
        message = await channel.fetch_message(int(self.session["message_id"]))

        embed = build_embed(self.session, bot, closed=self.session["closed"])
        await message.edit(embed=embed)

        await interaction.response.send_message(
            "✅ Availability updated.",
            ephemeral=True
        )

@bot.message_command(name="Edit availability")
async def edit_availability(interaction: discord.Interaction, message: discord.Message):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ Admins only.",
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

# ================= PANEL =================

class CreatePanel(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📝 Create availability", style=ButtonStyle.primary)
    async def create(self, button, interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ Admins only.",
                ephemeral=True
            )

        await interaction.response.send_modal(AvailabilityModal())

# ================= READY =================

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# ================= SLASH COMMAND =================

@bot.slash_command(name="send_availability_panel")
async def send_panel(ctx):
    embed = Embed(
        title="📝 Availability",
        description="Click the button below to create a new availability session.",
        color=0x3498db
    )

    await ctx.channel.send(embed=embed, view=CreatePanel())
    await ctx.respond("✅ Panel sent.", ephemeral=True)

# ================= RUN =================

bot.run(TOKEN)
