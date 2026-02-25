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
                color=0x5865F2,
                timestamp=datetime.utcnow(),
            )
            embed.set_author(name="xShadows Shop  ·  Support")
            embed.title = "Open a Support Ticket"
            embed.description = (
                "Select a category from the dropdown below and\n"
                "a private channel will be created just for you.\n"
                "\u200b"
            )
            embed.add_field(
                name="💬\u2002General Support",
                value="General questions or issues",
                inline=True,
            )
            embed.add_field(
                name="🎮\u2002Steam Hub Support",
                value="Issues with Steam Hub products",
                inline=True,
            )
            embed.add_field(name="\u200b", value="\u200b", inline=False)
            embed.add_field(
                name="🎯\u2002Xbox Code Support",
                value="Help with Xbox Gamepass codes",
                inline=True,
            )
            embed.add_field(
                name="🔑\u2002Steam Account Support",
                value="Help with Steam FA accounts",
                inline=True,
            )
            embed.add_field(name="\u200b", value="\u200b", inline=False)
            embed.add_field(
                name="📩\u2002Other",
                value="Anything else — we'll help",
                inline=True,
            )
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            embed.set_footer(text="Response times may vary  •  xShadows Shop")

            await channel.send(embed=embed, view=TicketPanelView())
            await interaction.edit_original_response(
                content=f"✅ Ticket panel posted in {channel.mention}."
            )
