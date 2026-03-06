import discord
from datetime import datetime
from loguru import logger

TICKET_CATEGORIES = [
    discord.SelectOption(
        label="General Support",
        value="general",
        description="General questions or issues",
        emoji="💬",
    ),
    discord.SelectOption(
        label="Steam Hub Support",
        value="steam_hub",
        description="Issues related to Steam Hub products",
        emoji="🎮",
    ),
    discord.SelectOption(
        label="Xbox Code Support",
        value="xbox_code",
        description="Help with Xbox Gamepass codes",
        emoji="🎯",
    ),
    discord.SelectOption(
        label="Steam Account Support",
        value="steam_account",
        description="Help with Steam FA accounts",
        emoji="🔑",
    ),
    discord.SelectOption(
        label="Other",
        value="other",
        description="Something else — we'll figure it out",
        emoji="📩",
    ),
]

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


class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select a category to open a ticket…",
            min_values=1,
            max_values=1,
            options=TICKET_CATEGORIES,
            custom_id="ticket:category_select",
        )

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]

        # Check if user already has an open ticket in this category (DB check)
        from utils.ticket_db import get_open_tickets_for_user
        existing = get_open_tickets_for_user(interaction.guild.id, interaction.user.id, category)
        if existing:
            existing_channel_id = existing[0]['channel_id']
            await interaction.response.send_message(
                f"You already have an open ticket in this category: <#{existing_channel_id}>",
                ephemeral=True,
            )
            return

        # Show the topic modal so the user describes their issue
        from commands.tickets.views.ticket_topic_modal import TicketTopicModal
        await interaction.response.send_modal(TicketTopicModal(category=category))


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        logger.exception(f'TicketPanelView error on {item}: {error}')
        try:
            if interaction.response.is_done():
                await interaction.followup.send('Something went wrong opening your ticket. Please try again.', ephemeral=True)
            else:
                await interaction.response.send_message('Something went wrong opening your ticket. Please try again.', ephemeral=True)
        except Exception:
            pass
