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

def generate_session_id():
    return f"session_{int(time.time())}"

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
            "message_id": None
        }

        embed = build_embed(sessions[session_id], bot)
        view = AvailabilityView(session_id)

        msg = await interaction.channel.send(embed=embed, view=view)
        sessions[session_id]["message_id"] = str(msg.id)

        await interaction.response.send_message(
            " Availability session created.✅",
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

    # 🔔 FIXED REMINDER
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
        unsure_users = [
            channel.guild.get_member(int(uid))
            for uid, status in session["statuses"].items()
            if status == "unsure"
        ]

        targets = list({m for m in no_response + unsure_users if m})

        if not targets:
            return await interaction.response.send_message(
                " No one to remind.✅",
                ephemeral=True
            )

        await channel.send(
            " **Reminder 🔔:** Please confirm your availability!\n\n"
            + " ".join(m.mention for m in targets)
        )

        await interaction.response.send_message(" Reminder sent.🔔", ephemeral=True)

    @ui.button(label="🔄 Reset votes", style=ButtonStyle.secondary, row=1)
    async def reset(self, button, interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ Admins only.",
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
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ Admins only.",
                ephemeral=True
            )

        await interaction.response.send_modal(AvailabilityModal())

# ================= READY =================

@bot.event
async def on_ready():
    print(f" Logged in as {bot.user} ✅")

# ================= COMMAND =================

@bot.slash_command(name="send_availability_panel")
async def send_panel(ctx):
    embed = Embed(
        title="📝 Availability",
        description="Click the button below to create a new availability session.",
        color=0x3498db
    )

    await ctx.channel.send(embed=embed, view=CreatePanel())
    await ctx.respond(" Panel sent.✅", ephemeral=True)

# ================= RUN =================

bot.run(TOKEN)
