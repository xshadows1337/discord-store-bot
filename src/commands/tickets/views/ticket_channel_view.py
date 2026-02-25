import discord
from datetime import datetime


class TicketChannelView(discord.ui.View):
    def __init__(self, opener_id: int = 0, category: str = "general"):
        super().__init__(timeout=None)
        # Encode opener_id and category in the custom_ids so they survive restarts
        self.close_btn.custom_id  = f"ticket:close:{opener_id}:{category}"
        self.claim_btn.custom_id  = f"ticket:claim:{opener_id}:{category}"

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close:0:general")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from utils.env_config import Config
        cfg = Config()
        admin_ids = cfg.get('admin_ids', [])
        # Parse opener_id from custom_id
        parts = button.custom_id.split(":")
        opener_id = int(parts[2]) if len(parts) > 2 else 0

        is_admin = interaction.user.id in admin_ids
        is_opener = interaction.user.id == opener_id

        if not (is_admin or is_opener):
            await interaction.response.send_message(
                "Only the ticket opener or staff can close this ticket.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🔒  Ticket Closing",
            description=f"This ticket is being closed by {interaction.user.mention}.\nThe channel will be deleted in **5 seconds**.",
            color=0xED4245,
            timestamp=datetime.utcnow(),
        )
        await interaction.response.send_message(embed=embed)
        try:
            import asyncio
            await asyncio.sleep(5)
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
            description=f"✅ {interaction.user.mention} has claimed this ticket and will assist you shortly.",
            color=0x57F287,
            timestamp=datetime.utcnow(),
        )
        await interaction.channel.send(embed=embed)
