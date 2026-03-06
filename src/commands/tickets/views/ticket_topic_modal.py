"""
Modal shown when a user selects a ticket category.
Collects a topic/description before creating the channel.
"""

import discord
from datetime import datetime
from loguru import logger

from utils.env_config import Config
from utils.ticket_db import (
    create_ticket,
    get_open_tickets_for_user,
    next_ticket_number,
)
from utils.ticket_logging import log_ticket_event, PRIORITY_EMOJI
from commands.tickets.views.ticket_channel_view import TicketChannelView

TICKET_CATEGORY_CHANNEL_ID = 1476294089703034900
TICKET_LOG_CHANNEL_ID = 1476360741928833187

CATEGORY_COLORS = {
    "general":       0x5865F2,
    "steam_hub":     0x1b2838,
    "xbox_code":     0x107c10,
    "steam_account": 0x1b2838,
    "other":         0xEB459E,
}

CATEGORY_LABELS = {
    "general":       "General Support",
    "steam_hub":     "Steam Hub Support",
    "xbox_code":     "Xbox Code Support",
    "steam_account": "Steam Account Support",
    "other":         "Other",
}

CATEGORY_EMOJI = {
    "general":       "💬",
    "steam_hub":     "🎮",
    "xbox_code":     "🎯",
    "steam_account": "🔑",
    "other":         "📩",
}


class TicketTopicModal(discord.ui.Modal):
    def __init__(self, category: str):
        self.category = category
        label = CATEGORY_LABELS.get(category, "Support")
        super().__init__(title=f"{label} — Open Ticket")

        self.topic_input = discord.ui.TextInput(
            label="What do you need help with?",
            style=discord.TextStyle.paragraph,
            placeholder="Briefly describe your issue or question…",
            required=True,
            min_length=5,
            max_length=500,
            custom_id="ticket_topic_input",
        )
        self.add_item(self.topic_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        topic = self.topic_input.value
        category = self.category
        guild = interaction.guild
        cfg = Config()

        # Check if user already has an open ticket in this category
        existing = get_open_tickets_for_user(guild.id, interaction.user.id, category)
        if existing:
            existing_channel_id = existing[0]['channel_id']
            await interaction.followup.send(
                f"You already have an open ticket in this category: <#{existing_channel_id}>",
                ephemeral=True,
            )
            return

        # Get the next ticket number
        ticket_num = next_ticket_number(guild.id)

        # Build permission overwrites
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
            ),
        }

        # Give admins access
        for admin_id in cfg.get('admin_ids', []):
            member = guild.get_member(admin_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True,
                    read_message_history=True,
                )

        # Create channel
        ticket_category_obj = guild.get_channel(TICKET_CATEGORY_CHANNEL_ID)
        channel_name = f"ticket-{ticket_num:04d}-{interaction.user.name.lower()[:12]}"

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=ticket_category_obj,
                topic=f"{interaction.user.mention} | {CATEGORY_LABELS.get(category, category)} | {topic[:100]}",
                reason=f"Ticket #{ticket_num} opened by {interaction.user} — {CATEGORY_LABELS.get(category, category)}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to create channels. Please contact an admin.",
                ephemeral=True,
            )
            return

        # Save to database
        ticket_data = create_ticket(
            channel_id=channel.id,
            guild_id=guild.id,
            opener_id=interaction.user.id,
            category=category,
            topic=topic,
            number=ticket_num,
        )

        # Build the opening embed
        cat_color = CATEGORY_COLORS.get(category, 0x5865F2)
        cat_emoji = CATEGORY_EMOJI.get(category, "🎫")
        cat_label = CATEGORY_LABELS.get(category, category)

        embed = discord.Embed(
            color=cat_color,
            timestamp=datetime.utcnow(),
        )
        embed.set_author(
            name=f"{cat_emoji}  {cat_label}",
            icon_url=interaction.user.display_avatar.url,
        )
        embed.title = f"Ticket #{ticket_num:04d}"
        embed.description = (
            f"Welcome {interaction.user.mention}! A staff member will be with you shortly.\n"
            f"\u200b"
        )
        embed.add_field(name="Opened by", value=interaction.user.mention, inline=True)
        embed.add_field(name="Category", value=f"{cat_emoji}\u2002{cat_label}", inline=True)
        embed.add_field(name="Status", value="🟢\u2002Open", inline=True)

        # Topic embed (second embed, like discord-tickets)
        topic_embed = discord.Embed(
            color=cat_color,
        )
        topic_embed.add_field(name="Topic", value=topic, inline=False)

        view = TicketChannelView(
            opener_id=interaction.user.id,
            category=category,
            ticket_number=ticket_num,
        )

        await channel.send(
            content=interaction.user.mention,
            embeds=[embed, topic_embed],
            view=view,
        )

        await interaction.followup.send(
            f"✅ Your ticket has been created: {channel.mention}",
            ephemeral=True,
        )

        # Log the event
        await log_ticket_event(
            guild=guild,
            log_channel_id=TICKET_LOG_CHANNEL_ID,
            action='create',
            ticket_data=ticket_data,
            user=interaction.user,
            details=f"**Category:** {cat_label}\n**Topic:** {topic[:200]}",
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.exception(f"TicketTopicModal error: {error}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send("Something went wrong creating your ticket. Please try again.", ephemeral=True)
            else:
                await interaction.response.send_message("Something went wrong creating your ticket. Please try again.", ephemeral=True)
        except Exception:
            pass
