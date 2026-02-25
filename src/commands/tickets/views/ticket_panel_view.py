import discord
from datetime import datetime

TICKET_CATEGORIES = [
    discord.SelectOption(
        label="General Help",
        value="general",
        description="General questions or issues",
        emoji="💬",
    ),
    discord.SelectOption(
        label="Steam Hub",
        value="steam_hub",
        description="Issues related to Steam Hub products",
        emoji="🎮",
    ),
    discord.SelectOption(
        label="Xbox Code",
        value="xbox_code",
        description="Help with Xbox Gamepass codes",
        emoji="🎯",
    ),
    discord.SelectOption(
        label="Steam Account Help",
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
    "general":       "General Help",
    "steam_hub":     "Steam Hub",
    "xbox_code":     "Xbox Code",
    "steam_account": "Steam Account Help",
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
        guild = interaction.guild

        # Check if user already has an open ticket for this category
        channel_name = f"ticket-{interaction.user.name.lower().replace(' ', '-')}-{category}"
        existing = discord.utils.get(guild.text_channels, name=channel_name)
        if existing:
            await interaction.response.send_message(
                f"You already have an open ticket: {existing.mention}",
                ephemeral=True,
            )
            return

        # Build permission overwrites
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
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
        from utils.env_config import Config
        cfg = Config()
        for admin_id in cfg.get('admin_ids', []):
            member = guild.get_member(admin_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    read_message_history=True,
                )

        # Create the ticket channel
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                topic=f"Ticket | {CATEGORY_LABELS[category]} | {interaction.user} ({interaction.user.id})",
                reason=f"Ticket opened by {interaction.user} — {CATEGORY_LABELS[category]}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to create channels. Please contact an admin.",
                ephemeral=True,
            )
            return

        # Send ticket embed inside the new channel
        from commands.tickets.views.ticket_channel_view import TicketChannelView
        embed = discord.Embed(
            title=f"{CATEGORY_EMOJI[category]}  {CATEGORY_LABELS[category]} Ticket",
            description=(
                f"Hey {interaction.user.mention}, thanks for opening a ticket!\n\n"
                f"Please describe your issue and a staff member will be with you shortly."
            ),
            color=CATEGORY_COLORS[category],
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Category", value=f"{CATEGORY_EMOJI[category]} {CATEGORY_LABELS[category]}", inline=True)
        embed.add_field(name="Opened by", value=interaction.user.mention, inline=True)
        embed.set_footer(text=f"xShadows Shop  •  Ticket ID: {interaction.user.id}")

        await channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=TicketChannelView(opener_id=interaction.user.id, category=category),
        )

        await interaction.response.send_message(
            f"✅ Your ticket has been created: {channel.mention}",
            ephemeral=True,
        )


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())
