"""
Ticket event logging — sends embeds to a configured log channel.
"""

import discord
from datetime import datetime
from loguru import logger
from utils.ticket_db import log_ticket_action


PRIORITY_EMOJI = {
    'HIGH': '🔴',
    'MEDIUM': '🟠',
    'LOW': '🟢',
}

ACTION_COLORS = {
    'create': 0x57F287,
    'close': 0xED4245,
    'claim': 0x5865F2,
    'unclaim': 0xFEE75C,
    'lock': 0xF47B67,
    'unlock': 0x57F287,
    'priority': 0xFF9000,
    'add_member': 0x5865F2,
    'remove_member': 0xED4245,
    'rename': 0xFF9000,
    'transfer': 0x5865F2,
    'feedback': 0xEB459E,
    'reopen': 0x57F287,
}

ACTION_LABELS = {
    'create': 'Ticket Created',
    'close': 'Ticket Closed',
    'claim': 'Ticket Claimed',
    'unclaim': 'Ticket Unclaimed',
    'lock': 'Ticket Locked',
    'unlock': 'Ticket Unlocked',
    'priority': 'Priority Changed',
    'add_member': 'Member Added',
    'remove_member': 'Member Removed',
    'rename': 'Ticket Renamed',
    'transfer': 'Ticket Transferred',
    'feedback': 'Feedback Received',
    'reopen': 'Ticket Reopened',
}


async def log_ticket_event(
    guild: discord.Guild,
    log_channel_id: int,
    action: str,
    ticket_data: dict,
    user: discord.User | discord.Member,
    details: str = None,
    extra_fields: list[tuple[str, str, bool]] = None,
):
    """
    Log a ticket event to the database and send an embed to the log channel.

    extra_fields: list of (name, value, inline) tuples for additional embed fields
    """
    # DB log
    try:
        log_ticket_action(
            ticket_id=ticket_data.get('id', 0),
            action=action,
            user_id=user.id,
            details=details,
        )
    except Exception as e:
        logger.error(f"[TICKET_LOG] DB log failed: {e}")

    # Discord log channel
    channel = guild.get_channel(log_channel_id)
    if not channel:
        return

    color = ACTION_COLORS.get(action, 0x5865F2)
    label = ACTION_LABELS.get(action, action.replace('_', ' ').title())

    embed = discord.Embed(
        color=color,
        timestamp=datetime.utcnow(),
    )
    embed.set_author(
        name=label,
        icon_url=user.display_avatar.url if hasattr(user, 'display_avatar') else None,
    )

    ticket_num = ticket_data.get('number', '?')
    category = ticket_data.get('category', 'unknown')
    channel_id = ticket_data.get('channel_id', 0)

    embed.add_field(name="Ticket", value=f"<#{channel_id}> (`#{ticket_num}`)", inline=True)
    embed.add_field(name="Category", value=category.replace('_', ' ').title(), inline=True)
    embed.add_field(name="By", value=user.mention, inline=True)

    if ticket_data.get('priority'):
        emoji = PRIORITY_EMOJI.get(ticket_data['priority'], '')
        embed.add_field(name="Priority", value=f"{emoji} {ticket_data['priority']}", inline=True)

    if details:
        embed.add_field(name="Details", value=details[:1024], inline=False)

    if extra_fields:
        for name, value, inline in extra_fields:
            embed.add_field(name=name, value=value[:1024], inline=inline)

    embed.set_footer(text=f"Ticket #{ticket_num}  •  xShadows Shop")

    try:
        await channel.send(embed=embed)
    except Exception as e:
        logger.error(f"[TICKET_LOG] Failed to send log embed: {e}")
