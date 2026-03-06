import io
import asyncio
import discord
from datetime import datetime
from loguru import logger

TRANSCRIPT_LOG_CHANNEL = 1476360741928833187
TICKET_LOG_CHANNEL_ID = 1476360741928833187


def _parse_custom_id(custom_id: str) -> tuple[int, str, int]:
    """Parse opener_id, category, ticket_number from a custom_id like 'ticket:action:opener:cat:num'."""
    parts = custom_id.split(":")
    opener_id = int(parts[2]) if len(parts) > 2 else 0
    category = parts[3] if len(parts) > 3 else "general"
    ticket_number = int(parts[4]) if len(parts) > 4 else 0
    return opener_id, category, ticket_number


async def _build_html_transcript(channel: discord.TextChannel, ticket_data: dict, closed_by: discord.Member) -> bytes:
    """Build an HTML transcript of the ticket channel."""
    category = ticket_data.get('category', 'unknown')
    ticket_num = ticket_data.get('number', 0)
    opener_id = ticket_data.get('opener_id', 0)
    topic = ticket_data.get('topic', '')

    messages_html = []
    msg_count = 0
    async for msg in channel.history(limit=1000, oldest_first=True):
        ts = msg.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')
        avatar_url = msg.author.display_avatar.url if hasattr(msg.author, 'display_avatar') else ''
        is_bot = msg.author.bot

        content_parts = []
        if msg.content:
            # Basic HTML escaping
            safe = msg.content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
            content_parts.append(safe)

        for emb in msg.embeds:
            if emb.title:
                content_parts.append(f'<div class="embed-title">{emb.title}</div>')
            if emb.description:
                safe_desc = emb.description.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
                content_parts.append(f'<div class="embed-desc">{safe_desc}</div>')
            for field in emb.fields:
                safe_name = field.name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                safe_val = str(field.value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
                content_parts.append(f'<div class="embed-field"><strong>{safe_name}:</strong> {safe_val}</div>')

        for att in msg.attachments:
            content_parts.append(f'<div class="attachment">📎 <a href="{att.url}">{att.filename}</a></div>')

        if not content_parts:
            continue

        msg_count += 1
        bot_class = ' bot' if is_bot else ''
        messages_html.append(f"""
        <div class="message{bot_class}">
            <div class="msg-header">
                <img class="avatar" src="{avatar_url}" alt="" />
                <span class="author">{msg.author.display_name}</span>
                <span class="timestamp">{ts}</span>
            </div>
            <div class="msg-content">{''.join(content_parts)}</div>
        </div>""")

    opener = channel.guild.get_member(opener_id)
    opener_name = str(opener) if opener else f"User {opener_id}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Transcript — Ticket #{ticket_num:04d}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; padding: 0; }}
  .header {{ background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 100%); padding: 2rem; border-bottom: 2px solid #5865F2; }}
  .header h1 {{ color: #5865F2; font-size: 1.5rem; margin-bottom: 0.5rem; }}
  .header .meta {{ color: #aaa; font-size: 0.9rem; line-height: 1.8; }}
  .header .meta strong {{ color: #ddd; }}
  .messages {{ padding: 1rem 2rem; }}
  .message {{ padding: 0.75rem 0; border-bottom: 1px solid #2a2a4a; }}
  .message.bot {{ opacity: 0.85; }}
  .msg-header {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem; }}
  .avatar {{ width: 28px; height: 28px; border-radius: 50%; }}
  .author {{ font-weight: 600; color: #fff; font-size: 0.95rem; }}
  .timestamp {{ color: #666; font-size: 0.78rem; margin-left: auto; }}
  .msg-content {{ padding-left: 2.3rem; color: #ddd; font-size: 0.92rem; line-height: 1.5; }}
  .embed-title {{ color: #5865F2; font-weight: 700; margin: 0.3rem 0 0.1rem; }}
  .embed-desc {{ color: #bbb; margin: 0.2rem 0; padding-left: 0.5rem; border-left: 3px solid #5865F2; }}
  .embed-field {{ margin: 0.2rem 0; }}
  .attachment {{ color: #5865F2; margin: 0.3rem 0; }}
  .attachment a {{ color: #5865F2; text-decoration: underline; }}
  .footer {{ text-align: center; padding: 2rem; color: #555; font-size: 0.8rem; border-top: 1px solid #2a2a4a; }}
</style>
</head>
<body>
<div class="header">
    <h1>Ticket #{ticket_num:04d} — Transcript</h1>
    <div class="meta">
        <strong>Channel:</strong> #{channel.name}<br>
        <strong>Category:</strong> {category.replace('_', ' ').title()}<br>
        <strong>Opened by:</strong> {opener_name}<br>
        <strong>Topic:</strong> {topic or 'N/A'}<br>
        <strong>Closed by:</strong> {closed_by} ({closed_by.id})<br>
        <strong>Date:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC<br>
        <strong>Messages:</strong> {msg_count}
    </div>
</div>
<div class="messages">
    {''.join(messages_html) if messages_html else '<p style="padding:2rem;color:#666;">No messages recorded.</p>'}
</div>
<div class="footer">
    xShadows Shop &bull; Ticket Transcript &bull; Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
</div>
</body>
</html>"""

    return html.encode('utf-8')


async def _build_and_send_transcript(channel: discord.TextChannel, ticket_data: dict, closed_by: discord.Member):
    """Build transcript, DM the opener, and log to the transcript channel."""
    opener_id = ticket_data.get('opener_id', 0)
    category = ticket_data.get('category', 'unknown')
    ticket_num = ticket_data.get('number', 0)
    topic = ticket_data.get('topic', '')

    html_bytes = await _build_html_transcript(channel, ticket_data, closed_by)
    filename = f"transcript-ticket-{ticket_num:04d}.html"

    embed = discord.Embed(
        color=0x5865F2,
        timestamp=datetime.utcnow(),
    )
    embed.set_author(name="Ticket Transcript")
    embed.description = (
        f"**Ticket:** #{ticket_num:04d}\n"
        f"**Channel:** #{channel.name}\n"
        f"**Category:** {category.replace('_', ' ').title()}\n"
        f"**Topic:** {topic or 'N/A'}\n"
        f"**Closed by:** {closed_by.mention}\n"
        f"\u200b"
    )
    embed.set_footer(text="xShadows Shop  \u2022  Support")

    # DM the opener
    opener = channel.guild.get_member(opener_id)
    if opener:
        try:
            await opener.send(
                embed=embed,
                file=discord.File(io.BytesIO(html_bytes), filename=filename),
            )
        except Exception:
            pass

    # Log to transcript channel
    log_channel = channel.guild.get_channel(TRANSCRIPT_LOG_CHANNEL)
    if log_channel:
        try:
            await log_channel.send(
                embed=embed,
                file=discord.File(io.BytesIO(html_bytes), filename=filename),
            )
        except Exception:
            pass


# ── Feedback Modal ───────────────────────────────────────────────────────────

class TicketFeedbackModal(discord.ui.Modal):
    def __init__(self, ticket_data: dict):
        super().__init__(title="Ticket Feedback")
        self.ticket_data = ticket_data

        self.rating_input = discord.ui.TextInput(
            label="Rating (1–5 stars)",
            style=discord.TextStyle.short,
            placeholder="Enter a number from 1 to 5",
            required=True,
            min_length=1,
            max_length=1,
            custom_id="feedback_rating",
        )
        self.comment_input = discord.ui.TextInput(
            label="Comments (optional)",
            style=discord.TextStyle.paragraph,
            placeholder="How was your experience? Any feedback for us?",
            required=False,
            max_length=1000,
            custom_id="feedback_comment",
        )
        self.add_item(self.rating_input)
        self.add_item(self.comment_input)

    async def on_submit(self, interaction: discord.Interaction):
        from utils.ticket_db import save_feedback, close_ticket, get_ticket_by_channel
        from utils.ticket_logging import log_ticket_event

        # Parse and clamp rating
        try:
            rating = int(self.rating_input.value)
        except ValueError:
            rating = 3
        rating = max(1, min(5, rating))
        comment = self.comment_input.value or None

        ticket_data = self.ticket_data
        ticket_id = ticket_data.get('id', 0)

        # Save feedback
        save_feedback(ticket_id, interaction.user.id, rating, comment)

        stars = "⭐" * rating + "☆" * (5 - rating)

        # Send feedback confirmation
        fb_embed = discord.Embed(color=0xEB459E, timestamp=datetime.utcnow())
        fb_embed.set_author(name="Feedback Received")
        fb_embed.description = (
            f"**Rating:** {stars} ({rating}/5)\n"
            f"**Comment:** {comment or 'No comment'}\n"
            f"\u200b"
        )
        fb_embed.set_footer(text="Thank you for your feedback!  •  xShadows Shop")
        await interaction.response.send_message(embed=fb_embed)

        # Log feedback
        await log_ticket_event(
            guild=interaction.guild,
            log_channel_id=TICKET_LOG_CHANNEL_ID,
            action='feedback',
            ticket_data=ticket_data,
            user=interaction.user,
            details=f"**Rating:** {stars} ({rating}/5)\n**Comment:** {comment or 'N/A'}",
        )

        # Now proceed with closing
        await asyncio.sleep(2)

        close_embed = discord.Embed(color=0xED4245, timestamp=datetime.utcnow())
        close_embed.set_author(name="Ticket Closing")
        close_embed.description = (
            f"Saving transcript and deleting channel in **5 seconds**.\n\u200b"
        )
        close_embed.set_footer(text="xShadows Shop  •  Support")
        await interaction.channel.send(embed=close_embed)

        await asyncio.sleep(5)

        # Close in DB
        close_ticket(interaction.channel.id, interaction.user.id, "Closed after feedback")

        # Build and send transcript
        try:
            fresh_data = get_ticket_by_channel(interaction.channel.id) or ticket_data
            await _build_and_send_transcript(
                channel=interaction.channel,
                ticket_data=fresh_data,
                closed_by=interaction.user,
            )
        except Exception:
            pass

        # Log close event
        await log_ticket_event(
            guild=interaction.guild,
            log_channel_id=TICKET_LOG_CHANNEL_ID,
            action='close',
            ticket_data=ticket_data,
            user=interaction.user,
        )

        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except Exception:
            pass

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.exception(f"TicketFeedbackModal error: {error}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send("Something went wrong. Please try again.", ephemeral=True)
            else:
                await interaction.response.send_message("Something went wrong. Please try again.", ephemeral=True)
        except Exception:
            pass


# ── Close Confirmation View ──────────────────────────────────────────────────

class CloseConfirmView(discord.ui.View):
    """Shown when someone clicks Close — gives Accept/Cancel and optionally asks the opener for feedback."""

    def __init__(self, ticket_data: dict, closer_id: int):
        super().__init__(timeout=120)
        self.ticket_data = ticket_data
        self.closer_id = closer_id
        opener_id = ticket_data.get('opener_id', 0)

        # Encode in custom IDs for persistence
        self.accept_btn.custom_id = f"ticket:close_accept:{opener_id}:{closer_id}"
        self.cancel_btn.custom_id = f"ticket:close_cancel:{opener_id}:{closer_id}"

    @discord.ui.button(label="Accept & Close", style=discord.ButtonStyle.danger, emoji="✅", custom_id="ticket:close_accept:0:0")
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from utils.env_config import Config
        cfg = Config()
        admin_ids = cfg.get('admin_ids', [])
        ticket_data = self.ticket_data
        opener_id = ticket_data.get('opener_id', 0)

        # Only the opener or staff can accept
        if interaction.user.id != opener_id and interaction.user.id not in admin_ids:
            await interaction.response.send_message(
                "Only the ticket opener or staff can accept the close request.",
                ephemeral=True,
            )
            return

        # If the opener is accepting, show feedback modal
        if interaction.user.id == opener_id:
            await interaction.response.send_modal(TicketFeedbackModal(ticket_data=ticket_data))
            return

        # Staff closing — skip feedback, close directly
        from utils.ticket_db import close_ticket, get_ticket_by_channel
        from utils.ticket_logging import log_ticket_event

        close_embed = discord.Embed(color=0xED4245, timestamp=datetime.utcnow())
        close_embed.set_author(name="Ticket Closing")
        close_embed.description = (
            f"{interaction.user.mention} is closing this ticket.\n"
            f"Saving transcript and deleting in **5 seconds**.\n\u200b"
        )
        close_embed.set_footer(text="xShadows Shop  •  Support")
        await interaction.response.send_message(embed=close_embed)

        await asyncio.sleep(5)

        close_ticket(interaction.channel.id, interaction.user.id)

        try:
            fresh_data = get_ticket_by_channel(interaction.channel.id) or ticket_data
            await _build_and_send_transcript(
                channel=interaction.channel,
                ticket_data=fresh_data,
                closed_by=interaction.user,
            )
        except Exception:
            pass

        await log_ticket_event(
            guild=interaction.guild,
            log_channel_id=TICKET_LOG_CHANNEL_ID,
            action='close',
            ticket_data=ticket_data,
            user=interaction.user,
        )

        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except Exception:
            pass

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌", custom_id="ticket:close_cancel:0:0")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        close_embed = discord.Embed(color=0x57F287, timestamp=datetime.utcnow())
        close_embed.set_author(name="Close Cancelled")
        close_embed.description = (
            f"{interaction.user.mention} cancelled the close request.\n\u200b"
        )
        close_embed.set_footer(text="xShadows Shop  •  Support")
        await interaction.response.edit_message(embed=close_embed, view=None)

    async def on_timeout(self):
        pass


# ── Main Ticket Channel View ────────────────────────────────────────────────

class TicketChannelView(discord.ui.View):
    def __init__(self, opener_id: int = 0, category: str = "general", ticket_number: int = 0):
        super().__init__(timeout=None)
        self.close_btn.custom_id = f"ticket:close:{opener_id}:{category}:{ticket_number}"
        self.claim_btn.custom_id = f"ticket:claim:{opener_id}:{category}:{ticket_number}"
        self.unclaim_btn.custom_id = f"ticket:unclaim:{opener_id}:{category}:{ticket_number}"
        self.lock_btn.custom_id = f"ticket:lock:{opener_id}:{category}:{ticket_number}"
        self.transcript_btn.custom_id = f"ticket:transcript:{opener_id}:{category}:{ticket_number}"

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        logger.exception(f'TicketChannelView error on {item}: {error}')
        try:
            if interaction.response.is_done():
                await interaction.followup.send('Something went wrong. Please try again.', ephemeral=True)
            else:
                await interaction.response.send_message('Something went wrong. Please try again.', ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", row=0, custom_id="ticket:close:0:general:0")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from utils.env_config import Config
        from utils.ticket_db import get_ticket_by_channel
        cfg = Config()
        admin_ids = cfg.get('admin_ids', [])
        opener_id, category, ticket_number = _parse_custom_id(button.custom_id)

        is_admin = interaction.user.id in admin_ids
        is_opener = interaction.user.id == opener_id

        if not (is_admin or is_opener):
            await interaction.response.send_message(
                "Only the ticket opener or staff can close this ticket.",
                ephemeral=True,
            )
            return

        ticket_data = get_ticket_by_channel(interaction.channel.id)
        if not ticket_data:
            ticket_data = {
                'id': 0, 'channel_id': interaction.channel.id,
                'opener_id': opener_id, 'category': category,
                'number': ticket_number, 'topic': '',
            }

        # Show close confirmation with accept/cancel
        confirm_embed = discord.Embed(color=0xFEE75C, timestamp=datetime.utcnow())
        confirm_embed.set_author(name="Close Request")
        confirm_embed.description = (
            f"{interaction.user.mention} wants to close this ticket.\n\n"
            f"Click **Accept & Close** to confirm, or **Cancel** to keep the ticket open.\n"
            f"\u200b"
        )
        confirm_embed.set_footer(text="xShadows Shop  •  Support")
        await interaction.response.send_message(
            embed=confirm_embed,
            view=CloseConfirmView(ticket_data=ticket_data, closer_id=interaction.user.id),
        )

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, emoji="🙋", row=0, custom_id="ticket:claim:0:general:0")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from utils.env_config import Config
        from utils.ticket_db import update_ticket, get_ticket_by_channel
        from utils.ticket_logging import log_ticket_event
        cfg = Config()
        admin_ids = cfg.get('admin_ids', [])

        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("Only staff can claim tickets.", ephemeral=True)
            return

        # Update claim button → disabled, show unclaim
        button.disabled = True
        button.label = f"Claimed by {interaction.user.display_name}"
        button.style = discord.ButtonStyle.secondary

        # Enable the unclaim button
        self.unclaim_btn.disabled = False

        await interaction.response.edit_message(view=self)

        # Update DB
        update_ticket(interaction.channel.id, claimed_by=interaction.user.id)

        embed = discord.Embed(color=0x57F287, timestamp=datetime.utcnow())
        embed.set_author(name="Ticket Claimed", icon_url=interaction.user.display_avatar.url)
        embed.description = (
            f"{interaction.user.mention} has claimed this ticket and will assist you shortly.\n\u200b"
        )
        embed.set_footer(text="xShadows Shop  •  Support")
        await interaction.channel.send(embed=embed)

        ticket_data = get_ticket_by_channel(interaction.channel.id) or {}
        await log_ticket_event(
            guild=interaction.guild,
            log_channel_id=TICKET_LOG_CHANNEL_ID,
            action='claim',
            ticket_data=ticket_data,
            user=interaction.user,
        )

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.secondary, emoji="↩️", row=0, disabled=True, custom_id="ticket:unclaim:0:general:0")
    async def unclaim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from utils.env_config import Config
        from utils.ticket_db import update_ticket, get_ticket_by_channel
        from utils.ticket_logging import log_ticket_event
        cfg = Config()
        admin_ids = cfg.get('admin_ids', [])

        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("Only staff can unclaim tickets.", ephemeral=True)
            return

        # Re-enable claim, disable unclaim
        self.claim_btn.disabled = False
        self.claim_btn.label = "Claim"
        self.claim_btn.style = discord.ButtonStyle.success
        button.disabled = True

        await interaction.response.edit_message(view=self)

        update_ticket(interaction.channel.id, claimed_by=None)

        embed = discord.Embed(color=0xFEE75C, timestamp=datetime.utcnow())
        embed.set_author(name="Ticket Unclaimed", icon_url=interaction.user.display_avatar.url)
        embed.description = (
            f"{interaction.user.mention} has released this ticket. It is now unassigned.\n\u200b"
        )
        embed.set_footer(text="xShadows Shop  •  Support")
        await interaction.channel.send(embed=embed)

        ticket_data = get_ticket_by_channel(interaction.channel.id) or {}
        await log_ticket_event(
            guild=interaction.guild,
            log_channel_id=TICKET_LOG_CHANNEL_ID,
            action='unclaim',
            ticket_data=ticket_data,
            user=interaction.user,
        )

    @discord.ui.button(label="Lock", style=discord.ButtonStyle.secondary, emoji="🔐", row=1, custom_id="ticket:lock:0:general:0")
    async def lock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from utils.env_config import Config
        from utils.ticket_db import update_ticket, get_ticket_by_channel
        from utils.ticket_logging import log_ticket_event
        cfg = Config()
        admin_ids = cfg.get('admin_ids', [])

        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("Only staff can lock/unlock tickets.", ephemeral=True)
            return

        opener_id, category, ticket_number = _parse_custom_id(button.custom_id)
        ticket_data = get_ticket_by_channel(interaction.channel.id) or {}
        is_locked = ticket_data.get('locked', 0)

        if not is_locked:
            # Lock: remove send_messages from the opener
            opener = interaction.guild.get_member(opener_id)
            if opener:
                await interaction.channel.set_permissions(
                    opener,
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True,
                    attach_files=False,
                )
            update_ticket(interaction.channel.id, locked=1)
            button.label = "Unlock"
            button.emoji = "🔓"
            await interaction.response.edit_message(view=self)

            embed = discord.Embed(color=0xF47B67, timestamp=datetime.utcnow())
            embed.set_author(name="Ticket Locked", icon_url=interaction.user.display_avatar.url)
            embed.description = (
                f"{interaction.user.mention} locked this ticket. Only staff can send messages.\n\u200b"
            )
            embed.set_footer(text="xShadows Shop  •  Support")
            await interaction.channel.send(embed=embed)

            await log_ticket_event(
                guild=interaction.guild,
                log_channel_id=TICKET_LOG_CHANNEL_ID,
                action='lock',
                ticket_data=get_ticket_by_channel(interaction.channel.id) or {},
                user=interaction.user,
            )
        else:
            # Unlock: restore send_messages for the opener
            opener = interaction.guild.get_member(opener_id)
            if opener:
                await interaction.channel.set_permissions(
                    opener,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                )
            update_ticket(interaction.channel.id, locked=0)
            button.label = "Lock"
            button.emoji = "🔐"
            await interaction.response.edit_message(view=self)

            embed = discord.Embed(color=0x57F287, timestamp=datetime.utcnow())
            embed.set_author(name="Ticket Unlocked", icon_url=interaction.user.display_avatar.url)
            embed.description = (
                f"{interaction.user.mention} unlocked this ticket. Everyone can send messages again.\n\u200b"
            )
            embed.set_footer(text="xShadows Shop  •  Support")
            await interaction.channel.send(embed=embed)

            await log_ticket_event(
                guild=interaction.guild,
                log_channel_id=TICKET_LOG_CHANNEL_ID,
                action='unlock',
                ticket_data=get_ticket_by_channel(interaction.channel.id) or {},
                user=interaction.user,
            )

    @discord.ui.button(label="Transcript", style=discord.ButtonStyle.secondary, emoji="📜", row=1, custom_id="ticket:transcript:0:general:0")
    async def transcript_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from utils.env_config import Config
        from utils.ticket_db import get_ticket_by_channel
        cfg = Config()
        admin_ids = cfg.get('admin_ids', [])

        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("Only staff can generate transcripts.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        ticket_data = get_ticket_by_channel(interaction.channel.id)
        if not ticket_data:
            opener_id, category, ticket_number = _parse_custom_id(button.custom_id)
            ticket_data = {
                'id': 0, 'channel_id': interaction.channel.id,
                'opener_id': opener_id, 'category': category,
                'number': ticket_number, 'topic': '',
            }

        html_bytes = await _build_html_transcript(interaction.channel, ticket_data, interaction.user)
        ticket_num = ticket_data.get('number', 0)
        filename = f"transcript-ticket-{ticket_num:04d}.html"

        await interaction.followup.send(
            content="Here's the current transcript:",
            file=discord.File(io.BytesIO(html_bytes), filename=filename),
            ephemeral=True,
        )
