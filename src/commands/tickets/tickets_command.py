import discord
from discord import app_commands
from datetime import datetime
from loguru import logger
from .views.ticket_panel_view import TicketPanelView

TICKET_PANEL_CHANNEL_ID = 1476279123147100210
TICKET_LOG_CHANNEL_ID = 1476360741928833187

PRIORITY_EMOJI = {'HIGH': '🔴', 'MEDIUM': '🟠', 'LOW': '🟢'}


def _staff_check(interaction: discord.Interaction, config: dict) -> bool:
    return interaction.user.id in config.get('admin_ids', [])


def _denied_embed() -> discord.Embed:
    embed = discord.Embed(colour=0xED4245)
    embed.set_author(
        name="Access Denied",
        icon_url="https://cdn-icons-png.flaticon.com/512/753/753345.png",
    )
    embed.description = "You do not have permission to run this command."
    return embed


def _not_ticket_embed() -> discord.Embed:
    embed = discord.Embed(colour=0xED4245)
    embed.set_author(name="Not a Ticket Channel")
    embed.description = "This command can only be used inside a ticket channel."
    return embed


class TicketsCommand:
    def __init__(self, client, tree, config) -> None:

        # ── /setup-tickets ───────────────────────────────────────────────

        @tree.command(
            guild=discord.Object(id=config['discord_guild_id']),
            name="setup-tickets",
            description="Post the ticket panel in the support channel.",
        )
        async def setup_tickets(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True, thinking=True)

            if not _staff_check(interaction, config):
                await interaction.edit_original_response(embed=_denied_embed())
                return

            channel = interaction.guild.get_channel(TICKET_PANEL_CHANNEL_ID)
            if channel is None:
                await interaction.edit_original_response(
                    content=f"Could not find channel <#{TICKET_PANEL_CHANNEL_ID}>. Make sure I have access to it."
                )
                return

            embed = discord.Embed(
                color=0x5865F2,
                timestamp=datetime.utcnow(),
            )
            embed.set_author(name="xShadows Shop  ·  Support")
            embed.title = "Open a Support Ticket"
            embed.description = (
                "Select a category from the dropdown below.\n"
                "You'll be asked to describe your issue, then a\n"
                "private channel will be created just for you.\n"
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
            embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)

            await channel.send(embed=embed, view=TicketPanelView())
            await interaction.edit_original_response(
                content=f"Ticket panel posted in {channel.mention}."
            )

        # ── /ticket-add ──────────────────────────────────────────────────

        @tree.command(
            guild=discord.Object(id=config['discord_guild_id']),
            name="ticket-add",
            description="Add a member to the current ticket.",
        )
        @app_commands.describe(member="The member to add to this ticket")
        async def ticket_add(interaction: discord.Interaction, member: discord.Member):
            from utils.ticket_db import get_ticket_by_channel
            from utils.ticket_logging import log_ticket_event

            await interaction.response.defer(ephemeral=True, thinking=True)

            ticket = get_ticket_by_channel(interaction.channel.id)
            if not ticket:
                await interaction.edit_original_response(embed=_not_ticket_embed())
                return

            is_staff = _staff_check(interaction, config)
            is_opener = interaction.user.id == ticket['opener_id']
            if not (is_staff or is_opener):
                await interaction.edit_original_response(embed=_denied_embed())
                return

            await interaction.channel.set_permissions(
                member,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                reason=f"{interaction.user} added {member} to ticket #{ticket['number']:04d}",
            )

            embed = discord.Embed(color=0x5865F2, timestamp=datetime.utcnow())
            embed.description = f"{member.mention} has been added to this ticket by {interaction.user.mention}."
            embed.set_footer(text="xShadows Shop  •  Support")
            await interaction.channel.send(embed=embed)

            await interaction.edit_original_response(
                content=f"Added {member.mention} to this ticket."
            )

            await log_ticket_event(
                guild=interaction.guild,
                log_channel_id=TICKET_LOG_CHANNEL_ID,
                action='add_member',
                ticket_data=ticket,
                user=interaction.user,
                details=f"Added {member} ({member.id})",
            )

        # ── /ticket-remove ───────────────────────────────────────────────

        @tree.command(
            guild=discord.Object(id=config['discord_guild_id']),
            name="ticket-remove",
            description="Remove a member from the current ticket.",
        )
        @app_commands.describe(member="The member to remove from this ticket")
        async def ticket_remove(interaction: discord.Interaction, member: discord.Member):
            from utils.ticket_db import get_ticket_by_channel
            from utils.ticket_logging import log_ticket_event

            await interaction.response.defer(ephemeral=True, thinking=True)

            ticket = get_ticket_by_channel(interaction.channel.id)
            if not ticket:
                await interaction.edit_original_response(embed=_not_ticket_embed())
                return

            is_staff = _staff_check(interaction, config)
            is_opener = interaction.user.id == ticket['opener_id']
            if not (is_staff or is_opener):
                await interaction.edit_original_response(embed=_denied_embed())
                return

            await interaction.channel.set_permissions(
                member,
                overwrite=None,
                reason=f"{interaction.user} removed {member} from ticket #{ticket['number']:04d}",
            )

            embed = discord.Embed(color=0xED4245, timestamp=datetime.utcnow())
            embed.description = f"{member.mention} has been removed from this ticket by {interaction.user.mention}."
            embed.set_footer(text="xShadows Shop  •  Support")
            await interaction.channel.send(embed=embed)

            await interaction.edit_original_response(
                content=f"Removed {member.mention} from this ticket."
            )

            await log_ticket_event(
                guild=interaction.guild,
                log_channel_id=TICKET_LOG_CHANNEL_ID,
                action='remove_member',
                ticket_data=ticket,
                user=interaction.user,
                details=f"Removed {member} ({member.id})",
            )

        # ── /ticket-rename ───────────────────────────────────────────────

        @tree.command(
            guild=discord.Object(id=config['discord_guild_id']),
            name="ticket-rename",
            description="Rename the current ticket channel.",
        )
        @app_commands.describe(name="New name for the ticket channel")
        async def ticket_rename(interaction: discord.Interaction, name: str):
            from utils.ticket_db import get_ticket_by_channel
            from utils.ticket_logging import log_ticket_event

            await interaction.response.defer(ephemeral=True, thinking=True)

            ticket = get_ticket_by_channel(interaction.channel.id)
            if not ticket:
                await interaction.edit_original_response(embed=_not_ticket_embed())
                return

            if not _staff_check(interaction, config):
                await interaction.edit_original_response(embed=_denied_embed())
                return

            if len(name) < 1 or len(name) > 100:
                embed = discord.Embed(colour=0xED4245)
                embed.description = "Channel name must be between 1 and 100 characters."
                await interaction.edit_original_response(embed=embed)
                return

            old_name = interaction.channel.name
            await interaction.channel.edit(name=name, reason=f"Renamed by {interaction.user}")

            embed = discord.Embed(color=0xFF9000, timestamp=datetime.utcnow())
            embed.description = f"{interaction.user.mention} renamed this ticket: `{old_name}` → `{name}`"
            embed.set_footer(text="xShadows Shop  •  Support")
            await interaction.channel.send(embed=embed)

            await interaction.edit_original_response(content=f"Channel renamed to `{name}`.")

            await log_ticket_event(
                guild=interaction.guild,
                log_channel_id=TICKET_LOG_CHANNEL_ID,
                action='rename',
                ticket_data=ticket,
                user=interaction.user,
                details=f"`{old_name}` → `{name}`",
            )

        # ── /ticket-priority ─────────────────────────────────────────────

        @tree.command(
            guild=discord.Object(id=config['discord_guild_id']),
            name="ticket-priority",
            description="Set the priority level of the current ticket.",
        )
        @app_commands.describe(level="Priority level")
        @app_commands.choices(level=[
            app_commands.Choice(name="🔴 High", value="HIGH"),
            app_commands.Choice(name="🟠 Medium", value="MEDIUM"),
            app_commands.Choice(name="🟢 Low", value="LOW"),
        ])
        async def ticket_priority(interaction: discord.Interaction, level: app_commands.Choice[str]):
            from utils.ticket_db import get_ticket_by_channel, update_ticket
            from utils.ticket_logging import log_ticket_event

            await interaction.response.defer(ephemeral=True, thinking=True)

            ticket = get_ticket_by_channel(interaction.channel.id)
            if not ticket:
                await interaction.edit_original_response(embed=_not_ticket_embed())
                return

            if not _staff_check(interaction, config):
                await interaction.edit_original_response(embed=_denied_embed())
                return

            priority = level.value
            old_priority = ticket.get('priority')

            # Update channel name with priority emoji prefix
            channel_name = interaction.channel.name
            # Remove old priority emoji if present
            if old_priority and old_priority in PRIORITY_EMOJI:
                channel_name = channel_name.replace(PRIORITY_EMOJI[old_priority], '', 1)
            # Add new priority emoji
            new_name = PRIORITY_EMOJI[priority] + channel_name
            await interaction.channel.edit(name=new_name, reason=f"Priority set to {priority} by {interaction.user}")

            update_ticket(interaction.channel.id, priority=priority)

            emoji = PRIORITY_EMOJI[priority]
            embed = discord.Embed(color=0xFF9000, timestamp=datetime.utcnow())
            embed.description = (
                f"{interaction.user.mention} set the priority to {emoji} **{priority}**"
            )
            embed.set_footer(text="xShadows Shop  •  Support")
            await interaction.channel.send(embed=embed)

            await interaction.edit_original_response(
                content=f"Priority set to {emoji} **{priority}**."
            )

            await log_ticket_event(
                guild=interaction.guild,
                log_channel_id=TICKET_LOG_CHANNEL_ID,
                action='priority',
                ticket_data=update_ticket(interaction.channel.id) or ticket,
                user=interaction.user,
                details=f"{old_priority or 'None'} → {priority}",
            )

        # ── /ticket-transfer ─────────────────────────────────────────────

        @tree.command(
            guild=discord.Object(id=config['discord_guild_id']),
            name="ticket-transfer",
            description="Transfer ticket ownership to another member.",
        )
        @app_commands.describe(member="The member to transfer the ticket to")
        async def ticket_transfer(interaction: discord.Interaction, member: discord.Member):
            from utils.ticket_db import get_ticket_by_channel, update_ticket
            from utils.ticket_logging import log_ticket_event

            await interaction.response.defer(thinking=True)

            ticket = get_ticket_by_channel(interaction.channel.id)
            if not ticket:
                await interaction.edit_original_response(embed=_not_ticket_embed())
                return

            is_staff = _staff_check(interaction, config)
            is_opener = interaction.user.id == ticket['opener_id']
            if not (is_staff or is_opener):
                await interaction.edit_original_response(embed=_denied_embed())
                return

            old_opener_id = ticket['opener_id']

            # Give new owner permissions
            await interaction.channel.set_permissions(
                member,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                reason=f"Ticket transferred to {member} by {interaction.user}",
            )

            # Update channel topic
            topic = ticket.get('topic', '')
            await interaction.channel.edit(
                topic=f"{member.mention} | {topic[:100]}" if topic else f"{member.mention}",
                reason=f"Ticket transferred by {interaction.user}",
            )

            # Update DB
            update_ticket(interaction.channel.id, opener_id=member.id)

            embed = discord.Embed(color=0x5865F2, timestamp=datetime.utcnow())
            embed.set_author(name="Ticket Transferred", icon_url=member.display_avatar.url)
            embed.description = (
                f"Ticket ownership transferred from <@{old_opener_id}> to {member.mention} "
                f"by {interaction.user.mention}.\n\u200b"
            )
            embed.set_footer(text="xShadows Shop  •  Support")
            await interaction.edit_original_response(embed=embed)

            await log_ticket_event(
                guild=interaction.guild,
                log_channel_id=TICKET_LOG_CHANNEL_ID,
                action='transfer',
                ticket_data=get_ticket_by_channel(interaction.channel.id) or ticket,
                user=interaction.user,
                details=f"<@{old_opener_id}> → {member.mention}",
            )

        # ── /ticket-close ────────────────────────────────────────────────

        @tree.command(
            guild=discord.Object(id=config['discord_guild_id']),
            name="ticket-close",
            description="Close the current ticket with an optional reason.",
        )
        @app_commands.describe(reason="Reason for closing the ticket")
        async def ticket_close(interaction: discord.Interaction, reason: str = None):
            from utils.ticket_db import get_ticket_by_channel
            from commands.tickets.views.ticket_channel_view import CloseConfirmView

            ticket = get_ticket_by_channel(interaction.channel.id)
            if not ticket:
                await interaction.response.send_message(embed=_not_ticket_embed(), ephemeral=True)
                return

            is_staff = _staff_check(interaction, config)
            is_opener = interaction.user.id == ticket['opener_id']
            if not (is_staff or is_opener):
                await interaction.response.send_message(embed=_denied_embed(), ephemeral=True)
                return

            confirm_embed = discord.Embed(color=0xFEE75C, timestamp=datetime.utcnow())
            confirm_embed.set_author(name="Close Request")
            desc = f"{interaction.user.mention} wants to close this ticket.\n"
            if reason:
                desc += f"**Reason:** {reason}\n"
            desc += f"\nClick **Accept & Close** to confirm, or **Cancel** to keep the ticket open.\n\u200b"
            confirm_embed.description = desc
            confirm_embed.set_footer(text="xShadows Shop  •  Support")

            await interaction.response.send_message(
                embed=confirm_embed,
                view=CloseConfirmView(ticket_data=ticket, closer_id=interaction.user.id),
            )

        # ── /ticket-stats ────────────────────────────────────────────────

        @tree.command(
            guild=discord.Object(id=config['discord_guild_id']),
            name="ticket-stats",
            description="View ticket statistics for this server.",
        )
        async def ticket_stats(interaction: discord.Interaction):
            from utils.ticket_db import get_ticket_stats

            await interaction.response.defer(ephemeral=True, thinking=True)

            if not _staff_check(interaction, config):
                await interaction.edit_original_response(embed=_denied_embed())
                return

            stats = get_ticket_stats(interaction.guild.id)

            embed = discord.Embed(color=0x5865F2, timestamp=datetime.utcnow())
            embed.set_author(name="Ticket Statistics", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            embed.add_field(name="Total Tickets", value=f"```{stats['total']}```", inline=True)
            embed.add_field(name="Open", value=f"```{stats['open']}```", inline=True)
            embed.add_field(name="Closed", value=f"```{stats['closed']}```", inline=True)
            avg = stats['avg_rating']
            if avg:
                stars = round(avg)
                star_display = "⭐" * stars + "☆" * (5 - stars)
                embed.add_field(name="Avg Rating", value=f"{star_display} ({avg}/5)", inline=False)
            else:
                embed.add_field(name="Avg Rating", value="No feedback yet", inline=False)
            embed.set_footer(text="xShadows Shop  •  Support")

            await interaction.edit_original_response(embed=embed)
