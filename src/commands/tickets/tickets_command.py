import discord
from datetime import datetime
from .views.ticket_panel_view import TicketPanelView

TICKET_PANEL_CHANNEL_ID = 1476279123147100210


class TicketsCommand:
    def __init__(self, client, tree, config) -> None:

        @tree.command(
            guild=discord.Object(id=config['discord_guild_id']),
            name="setup-tickets",
            description="Post the ticket panel in the support channel.",
        )
        async def setup_tickets(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True, thinking=True)

            if interaction.user.id not in config['admin_ids']:
                embed = discord.Embed(colour=0xED4245)
                embed.set_author(
                    name="Access Denied",
                    icon_url="https://cdn-icons-png.flaticon.com/512/753/753345.png",
                )
                embed.description = "You do not have permission to run this command."
                await interaction.edit_original_response(embed=embed)
                return

            channel = interaction.guild.get_channel(TICKET_PANEL_CHANNEL_ID)
            if channel is None:
                await interaction.edit_original_response(
                    content=f"⚠️ Could not find channel <#{TICKET_PANEL_CHANNEL_ID}>. Make sure I have access to it."
                )
                return

            embed = discord.Embed(
                title="🎫  Support Tickets",
                description=(
                    "Need help? Open a ticket by selecting a category below.\n\n"
                    "**Categories**\n"
                    "💬 **General Support** — General questions or issues\n"
                    "🎮 **Steam Hub Support** — Issues with Steam Hub products\n"
                    "🎯 **Xbox Code Support** — Help with Xbox Gamepass codes\n"
                    "🔑 **Steam Account Support** — Help with Steam FA accounts\n"
                    "📩 **Other** — Anything else\n\n"
                    "*Our team will respond as soon as possible.*"
                ),
                color=0x5865F2,
                timestamp=datetime.utcnow(),
            )
            embed.set_footer(text="xShadows Shop  •  Support")

            await channel.send(embed=embed, view=TicketPanelView())
            await interaction.edit_original_response(
                content=f"✅ Ticket panel posted in {channel.mention}."
            )
