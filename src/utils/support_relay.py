"""
AbyssHub Live Support Relay
Bridges the website AI chat with Discord ticket channels.

Flow:
1. User clicks "Talk to Staff" on website chat
2. API creates a Discord ticket channel via the bot
3. User messages are forwarded from website → Discord channel
4. Staff messages in the channel are pushed to an in-memory buffer
5. Website polls for new staff messages

All state is in-memory — lost on restart (tickets persist in Discord though).
"""

import asyncio
import time
import secrets
from dataclasses import dataclass, field
from loguru import logger

# ── Retry helper ──────────────────────────────────────────────────────────────

async def _discord_retry(coro_fn, *args, retries=4, base_delay=5, **kwargs):
    """Call an async discord operation, retrying on 429 with exponential backoff."""
    import discord as _d
    delay = base_delay
    for attempt in range(retries):
        try:
            return await coro_fn(*args, **kwargs)
        except _d.errors.HTTPException as e:
            if e.status == 429 and attempt < retries - 1:
                logger.warning(f'[RELAY] Discord 429 on attempt {attempt+1}, retrying in {delay}s...')
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
            else:
                raise
    return None

# ── Types ─────────────────────────────────────────────────────────────────────

@dataclass
class WebTicket:
    ticket_id: str
    channel_id: int = 0
    username: str = 'Guest'           # website username or "Guest"
    category: str = 'website_chat'
    created_at: float = field(default_factory=time.time)
    closed: bool = False
    staff_messages: list = field(default_factory=list)   # [{id, author, text, ts}]
    _msg_counter: int = 0

# ── Global state ──────────────────────────────────────────────────────────────
_tickets: dict[str, WebTicket] = {}          # ticket_id → WebTicket
_channel_to_ticket: dict[int, str] = {}      # channel_id → ticket_id
_discord_client = None                       # set by main.py on ready

def set_discord_client(client):
    global _discord_client
    _discord_client = client

def get_ticket_by_channel(channel_id: int) -> WebTicket | None:
    tid = _channel_to_ticket.get(channel_id)
    return _tickets.get(tid) if tid else None

def get_ticket(ticket_id: str) -> WebTicket | None:
    return _tickets.get(ticket_id)

# ── Create ticket (called from API) ──────────────────────────────────────────

async def create_web_ticket(username: str = 'Guest') -> WebTicket | None:
    """Create a Discord ticket channel and return the WebTicket."""
    if not _discord_client:
        logger.error('[RELAY] Discord client not set')
        return None

    ticket_id = secrets.token_hex(6)
    ticket = WebTicket(ticket_id=ticket_id, username=username)
    _tickets[ticket_id] = ticket

    try:
        from utils.env_config import Config
        cfg = Config()
        guild = _discord_client.get_guild(cfg['discord_guild_id'])
        if not guild:
            logger.error('[RELAY] Guild not found')
            return None

        # Build overwrites — private to admins + bot
        overwrites = {
            guild.default_role: __import__('discord').PermissionOverwrite(view_channel=False),
            guild.me: __import__('discord').PermissionOverwrite(
                view_channel=True, send_messages=True,
                manage_channels=True, manage_messages=True,
                read_message_history=True,
            ),
        }
        for admin_id in cfg.get('admin_ids', []):
            member = guild.get_member(admin_id)
            if member:
                overwrites[member] = __import__('discord').PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    manage_channels=True, read_message_history=True,
                )

        ticket_category = guild.get_channel(1476294089703034900)

        channel_name = f"web-{username.lower()[:12]}-{ticket_id[:6]}"
        channel = await _discord_retry(
            guild.create_text_channel,
            name=channel_name,
            overwrites=overwrites,
            category=ticket_category,
            topic=f"Website Live Chat | {username} | Ticket {ticket_id}",
            reason=f"Website chat ticket opened by {username}",
        )

        ticket.channel_id = channel.id
        _channel_to_ticket[channel.id] = ticket_id

        # Send initial embed (matches Discord ticket style)
        import discord as _d
        from commands.tickets.views.ticket_channel_view import TicketChannelView
        embed = _d.Embed(color=0xFF9000, timestamp=__import__('datetime').datetime.utcnow())
        embed.set_author(name="\U0001f310  Website Live Chat")
        embed.title = "Website Support Ticket Opened"
        embed.description = (
            f"A user has connected via the website chat.\n"
            f"Reply here \u2014 your messages appear in their browser in real-time.\n"
            f"\u200b"
        )
        embed.add_field(name="Opened by", value=username, inline=True)
        embed.add_field(name="Source", value="\U0001f310\u2002Website Chat", inline=True)
        embed.add_field(name="Status", value="\U0001f7e2\u2002Open", inline=True)
        embed.add_field(name="Ticket ID", value=f"`{ticket_id}`", inline=True)
        embed.set_footer(text="xShadows Shop  \u2022  Website Live Chat Relay")
        await _discord_retry(channel.send, embed=embed, view=TicketChannelView(opener_id=0, category="website_chat"))

        logger.info(f'[RELAY] Web ticket {ticket_id} created → #{channel_name}')
        return ticket

    except Exception as e:
        logger.error(f'[RELAY] Failed to create web ticket: {e}')
        return None

# ── Send message from website → Discord ──────────────────────────────────────

async def send_user_message(ticket_id: str, text: str) -> bool:
    ticket = _tickets.get(ticket_id)
    if not ticket or ticket.closed or not ticket.channel_id or not _discord_client:
        return False
    try:
        channel = _discord_client.get_channel(ticket.channel_id)
        if not channel:
            return False
        import discord as _d
        embed = _d.Embed(color=0xFF9000, description=text)
        embed.set_author(name=f"\U0001f310 {ticket.username}")
        embed.set_footer(text="Website Chat")
        await _discord_retry(channel.send, embed=embed)
        return True
    except Exception as e:
        logger.error(f'[RELAY] Failed to send user message: {e}')
        return False

async def send_user_file_url(ticket_id: str, url: str, filename: str, text: str = '') -> bool:
    """Post an attachment URL to the Discord ticket channel."""
    ticket = _tickets.get(ticket_id)
    if not ticket or ticket.closed or not ticket.channel_id or not _discord_client:
        return False
    try:
        channel = _discord_client.get_channel(ticket.channel_id)
        if not channel:
            return False
        import discord as _d
        parts = []
        if text:
            parts.append(text)
        parts.append(f'📎 [{filename}]({url})')
        embed = _d.Embed(color=0xFF9000, description='\n'.join(parts))
        embed.set_author(name=f'\U0001f310 {ticket.username}')
        embed.set_footer(text='Website Chat \u2014 Attachment')
        await _discord_retry(channel.send, embed=embed)
        return True
    except Exception as e:
        logger.error(f'[RELAY] Failed to send file url: {e}')
        return False

# ── Receive staff message (called from bot on_message) ───────────────────────

def push_staff_message(channel_id: int, author: str, text: str):
    """Called from bot's on_message when a non-bot sends in a web-ticket channel."""
    ticket = get_ticket_by_channel(channel_id)
    if not ticket or ticket.closed:
        return
    ticket._msg_counter += 1
    ticket.staff_messages.append({
        'id': ticket._msg_counter,
        'author': author,
        'text': text,
        'ts': time.time(),
    })
    # Cap buffer at 200 messages
    if len(ticket.staff_messages) > 200:
        ticket.staff_messages = ticket.staff_messages[-200:]

# ── Poll for new staff messages (called from API) ────────────────────────────

def poll_staff_messages(ticket_id: str, since_id: int = 0) -> list[dict]:
    ticket = _tickets.get(ticket_id)
    if not ticket:
        return []
    return [m for m in ticket.staff_messages if m['id'] > since_id]

# ── Close ticket ──────────────────────────────────────────────────────────────

async def close_web_ticket(ticket_id: str):
    ticket = _tickets.get(ticket_id)
    if not ticket:
        return
    ticket.closed = True
    if ticket.channel_id and _discord_client:
        try:
            channel = _discord_client.get_channel(ticket.channel_id)
            if channel:
                await channel.delete(reason="Web live chat ended by user")
        except Exception:
            pass
    _channel_to_ticket.pop(ticket.channel_id, None)
    _tickets.pop(ticket_id, None)

# ── Cleanup old tickets (call periodically) ──────────────────────────────────

def cleanup_old_tickets(max_age: int = 7200):
    """Remove tickets older than max_age seconds."""
    cutoff = time.time() - max_age
    to_remove = [tid for tid, t in _tickets.items() if t.created_at < cutoff]
    for tid in to_remove:
        t = _tickets.pop(tid, None)
        if t:
            _channel_to_ticket.pop(t.channel_id, None)
