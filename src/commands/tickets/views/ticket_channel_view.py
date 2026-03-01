import io
import asyncio
import discord
from datetime import datetime
from loguru import logger

TRANSCRIPT_LOG_CHANNEL = 1476360741928833187


async def _build_and_send_transcript(channel: discord.TextChannel, opener_id: int, closed_by: discord.Member, category: str):
    """Collect all messages, build a .txt transcript, DM the opener and log to channel."""
    lines = []
    lines.append(f"═══════════════════════════════════════════════")
    lines.append(f"  xShadows Shop — Ticket Transcript")
    lines.append(f"  Channel : #{channel.name}")
    lines.append(f"  Category: {category}")
    lines.append(f"  Closed by: {closed_by} ({closed_by.id})")
    lines.append(f"  Date    : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    lines.append(f"═══════════════════════════════════════════════\n")

    messages = []
    async for msg in channel.history(limit=500, oldest_first=True):
        if msg.author.bot and not msg.embeds:
            continue
        ts = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
        content = msg.content or ""
        if msg.embeds:
            for emb in msg.embeds:
                if emb.title:
                    content += f"[Embed: {emb.title}]"
                if emb.description:
                    content += f" — {emb.description[:120]}"
        if content.strip():
            messages.append(f"[{ts}] {msg.author} : {content.strip()}")

    lines += messages if messages else ["(no messages)"]
    lines.append(f"\n═══════════════════════════════════════════════")

    transcript_text = "\n".join(lines)
    file_bytes = transcript_text.encode("utf-8")

    embed = discord.Embed(
        color=0x5865F2,
        timestamp=datetime.utcnow(),
    )
    embed.set_author(name="Ticket Transcript")
    embed.description = (
        f"**Channel:** #{channel.name}\n"
        f"**Category:** {category}\n"
        f"**Closed by:** {closed_by.mention}\n"
        f"**Messages:** {len(messages)}\n"
        f"\u200b"
    )
    embed.set_footer(text="xShadows Shop  \u2022  Support")

    # DM the opener
    opener = channel.guild.get_member(opener_id)
    if opener:
        try:
            await opener.send(
                embed=embed,
                file=discord.File(io.BytesIO(file_bytes), filename=f"transcript-{channel.name}.txt"),
            )
        except Exception:
            pass

    # Log to transcript channel
    log_channel = channel.guild.get_channel(TRANSCRIPT_LOG_CHANNEL)
    if log_channel:
        try:
            await log_channel.send(
                embed=embed,
                file=discord.File(io.BytesIO(file_bytes), filename=f"transcript-{channel.name}.txt"),
            )
        except Exception:
            pass


class TicketChannelView(discord.ui.View):
    def __init__(self, opener_id: int = 0, category: str = "general"):
        super().__init__(timeout=None)
        # Encode opener_id and category in the custom_ids so they survive restarts
        self.close_btn.custom_id = f"ticket:close:{opener_id}:{category}"
        self.claim_btn.custom_id = f"ticket:claim:{opener_id}:{category}"

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        logger.exception(f'TicketChannelView error on {item}: {error}')
        try:
            if interaction.response.is_done():
                await interaction.followup.send('Something went wrong. Please try again.', ephemeral=True)
            else:
                await interaction.response.send_message('Something went wrong. Please try again.', ephemeral=True)
        except Exception:
            pass
        # Encode opener_id and category in the custom_ids so they survive restarts
        self.close_btn.custom_id  = f"ticket:close:{opener_id}:{category}"
        self.claim_btn.custom_id  = f"ticket:claim:{opener_id}:{category}"

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close:0:general")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from utils.env_config import Config
        cfg = Config()
        admin_ids = cfg.get('admin_ids', [])
        # Parse opener_id and category from custom_id
        parts = button.custom_id.split(":")
        opener_id = int(parts[2]) if len(parts) > 2 else 0
        category  = parts[3] if len(parts) > 3 else "general"

        is_admin = interaction.user.id in admin_ids
        is_opener = interaction.user.id == opener_id

        if not (is_admin or is_opener):
            await interaction.response.send_message(
                "Only the ticket opener or staff can close this ticket.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            color=0xED4245,
            timestamp=datetime.utcnow(),
        )
        embed.set_author(name="Ticket Closing")
        embed.description = (
            f"{interaction.user.mention} is closing this ticket.\n"
            f"Saving transcript and deleting in **5 seconds**.\n"
            f"\u200b"
        )
        embed.set_footer(text="xShadows Shop  \u2022  Support")
        await interaction.response.send_message(embed=embed)

        await asyncio.sleep(5)

        # Build and send transcript before deleting
        try:
            await _build_and_send_transcript(
                channel=interaction.channel,
                opener_id=opener_id,
                closed_by=interaction.user,
                category=category,
            )
        except Exception:
            pass

        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.Forbidden:
            await interaction.channel.send("⚠️ I don't have permission to delete this channel.")
        except Exception:
            pass

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.secondary, emoji="🙋", custom_id="ticket:claim:0:general")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from utils.env_config import Config
        cfg = Config()
        admin_ids = cfg.get('admin_ids', [])

        if interaction.user.id not in admin_ids:
            await interaction.response.send_message(
                "Only staff can claim tickets.",
                ephemeral=True,
            )
            return

        # Disable the claim button so no one else can claim
        button.disabled = True
        button.label = f"Claimed by {interaction.user.display_name}"
        await interaction.response.edit_message(view=self)

        embed = discord.Embed(
            color=0x57F287,
            timestamp=datetime.utcnow(),
        )
        embed.set_author(
            name="Ticket Claimed",
            icon_url=interaction.user.display_avatar.url,
        )
        embed.description = (
            f"{interaction.user.mention} has claimed this ticket and will assist you shortly.\n"
            f"\u200b"
        )
        embed.set_footer(text="xShadows Shop  \u2022  Support")
        await interaction.channel.send(embed=embed)
