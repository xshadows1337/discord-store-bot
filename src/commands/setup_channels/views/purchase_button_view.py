import asyncio
import discord
from datetime import datetime
from readsettings import ReadSettings
from utils.product_manager import linesInFile
from ..modals.payment_modal import PaymentModal
from loguru import logger


# ──── Helpers ─────────────────────────────────────────────────────────────────

_PRODUCT_COLORS = [0x5865F2, 0xEB459E, 0x57F287, 0xFEE75C, 0xED4245, 0xE67E22]


def _get_products() -> list:
    return ReadSettings('products.json').json()


async def _get_products_async() -> list:
    """Non-blocking product read so we never stall the event loop."""
    return await asyncio.to_thread(_get_products)


def _build_product_embed(page: int) -> discord.Embed:
    """Build a single embed for the product at `page` (0-indexed), encoding state in footer."""
    products = _get_products()
    total   = len(products)
    product = products[page % total]

    stock       = linesInFile(product['product_file'])
    in_stock    = stock >= product.get('min_order_amount', 1)
    color       = _PRODUCT_COLORS[page % len(_PRODUCT_COLORS)]
    stock_badge = "🟢 In Stock" if in_stock else "🔴 Out of Stock"

    methods = []
    for m in product['payment_methods']:
        if m == 'CRYPTO':       methods.append('🪙 Crypto')
        elif m == 'CREDITCARD': methods.append('💳 Card')
    methods_str = '  ·  '.join(methods)

    emb = discord.Embed(colour=color, timestamp=datetime.now())
    emb.set_author(
        name="ᴀʙʏss ʜᴜʙ",
        icon_url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png"
    )
    emb.title = product['name']
    emb.description = f"*{product['description']}*\n\u200b"

    emb.add_field(name="Price",     value=f"` ${product['price']} `",           inline=True)
    emb.add_field(name="Min Order", value=f"` {product['min_order_amount']} `", inline=True)
    emb.add_field(name="Stock",     value=f"` {stock} `",                       inline=True)
    emb.add_field(name="\u200b",    value=f"{stock_badge}   ·   {methods_str}", inline=False)

    if product.get('requirements'):
        emb.add_field(name="Requirements", value=f"```{product['requirements']}```", inline=False)

    thumbnail = product.get('thumbnail_url', 'https://cdn-icons-png.flaticon.com/512/1170/1170678.png')
    emb.set_thumbnail(url=thumbnail)

    # Encode page state so we can recover it on button press (persists across restarts)
    emb.set_footer(text=f"page:{page}:{total}  ·  ᴀʙʏss ʜᴜʙ  ·  Page {page + 1} of {total}")
    return emb


def build_store_embed():
    """Entry point used by /setup and auto-update — returns a single embed for page 0."""
    return _build_product_embed(0)


def _parse_page(embed: discord.Embed) -> tuple[int, int]:
    """Extract (current_page, total) from footer 'page:N:T  ·  ...'."""
    try:
        part = embed.footer.text.split('  ·  ')[0]   # "page:N:T"
        _, p, t = part.split(':')
        return int(p), int(t)
    except Exception:
        return 0, len(_get_products())


async def _safe_reply(interaction: discord.Interaction, msg: str):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass


# ──── Payment method view (ephemeral) ─────────────────────────────────────────

class PaymentMethodDropdown(discord.ui.Select):
    def __init__(self, productInfo):
        self.productInfo = productInfo
        options = []
        for method in productInfo['payment_methods']:
            if method == 'CRYPTO':
                options.append(discord.SelectOption(label="Crypto  (LTC / BTC)", value="Crypto", emoji="\U0001fa99"))
            elif method == 'CREDITCARD':
                options.append(discord.SelectOption(label="Credit Card  (Stripe)", value="CreditCard", emoji="\U0001f4b3"))
        super().__init__(placeholder="Choose a payment method", options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(
                PaymentModal(custom_id='payment-modal', test=self.values[0], productInfo=self.productInfo)
            )
        except Exception as e:
            logger.exception(f'PaymentMethodDropdown error: {e}')
            try:
                await _safe_reply(interaction, 'Something went wrong. Please try again.')
            except Exception:
                pass


class PaymentMethodView(discord.ui.View):
    def __init__(self, productInfo):
        super().__init__()
        self.add_item(PaymentMethodDropdown(productInfo))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        logger.exception(f'PaymentMethodView error on {item}: {error}')
        try:
            await _safe_reply(interaction, 'Something went wrong. Please try again.')
        except Exception:
            pass


# ──── Paginated store view ─────────────────────────────────────────────────────

class StoreView(discord.ui.View):
    """
    Persistent paginated store with navigation buttons.
    State is stored in the embed footer as 'page:N:T' so it survives restarts.
    """
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary,
                       custom_id="store:prev", row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()   # ack instantly
            page, total = _parse_page(interaction.message.embeds[0])
            emb = await asyncio.to_thread(_build_product_embed, (page - 1) % total)
            await interaction.edit_original_response(embed=emb)
        except Exception as e:
            logger.exception(f'store:prev error: {e}')
            try:
                await _safe_reply(interaction, 'Something went wrong. Please try again.')
            except Exception:
                pass

    @discord.ui.button(label="·", style=discord.ButtonStyle.secondary,
                       custom_id="store:page", disabled=True, row=0)
    async def page_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass  # disabled — never fires

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary,
                       custom_id="store:next", row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()   # ack instantly
            page, total = _parse_page(interaction.message.embeds[0])
            emb = await asyncio.to_thread(_build_product_embed, (page + 1) % total)
            await interaction.edit_original_response(embed=emb)
        except Exception as e:
            logger.exception(f'store:next error: {e}')
            try:
                await _safe_reply(interaction, 'Something went wrong. Please try again.')
            except Exception:
                pass

    @discord.ui.button(label="🛒  Buy", style=discord.ButtonStyle.success,
                       custom_id="store:buy", row=0)
    async def buy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)   # ack instantly
            page, total = _parse_page(interaction.message.embeds[0])
            products = await _get_products_async()
            product  = products[page % total]
            stock    = await asyncio.to_thread(linesInFile, product['product_file'])

            if stock < product.get('min_order_amount', 1):
                oos = discord.Embed(colour=0xED4245, timestamp=datetime.now())
                oos.set_author(name="ᴀʙʏss ʜᴜʙ",
                               icon_url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png")
                oos.title = "Out of Stock"
                oos.description = (
                    f"**{product['name']}** is currently unavailable.\n\u200b\n"
                    "-# Check back later or wait for a restock notification."
                )
                return await interaction.followup.send(embed=oos, ephemeral=True)

            # Detail card + payment method selection
            detail = _build_detail_embed(product, page)
            await interaction.followup.send(
                embed=detail,
                view=PaymentMethodView(product),
                ephemeral=True
            )
        except Exception as e:
            logger.exception(f'store:buy error: {e}')
            try:
                await _safe_reply(interaction, 'Something went wrong. Please try again.')
            except Exception:
                pass

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        logger.exception(f'StoreView error on {item}: {error}')
        try:
            await _safe_reply(interaction, 'Something went wrong. Please try again.')
        except Exception:
            pass


def _build_detail_embed(product: dict, page: int) -> discord.Embed:
    """Ephemeral detail card shown after pressing Buy."""
    stock       = linesInFile(product['product_file'])
    in_stock    = stock >= product.get('min_order_amount', 1)
    color       = _PRODUCT_COLORS[page % len(_PRODUCT_COLORS)]
    stock_badge = "🟢 In Stock" if in_stock else "🔴 Out of Stock"

    methods = []
    for m in product['payment_methods']:
        if m == 'CRYPTO':       methods.append('🪙 Crypto')
        elif m == 'CREDITCARD': methods.append('💳 Card')
    methods_str = '  ·  '.join(methods)

    emb = discord.Embed(colour=color, timestamp=datetime.now())
    emb.set_author(name="ᴀʙʏss ʜᴜʙ",
                   icon_url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png")
    emb.title = product['name']
    emb.description = f"*{product['description']}*\n\u200b"

    emb.add_field(name="Price",     value=f"` ${product['price']} `",           inline=True)
    emb.add_field(name="Min Order", value=f"` {product['min_order_amount']} `", inline=True)
    emb.add_field(name="Stock",     value=f"` {stock} `",                       inline=True)
    emb.add_field(name="\u200b",    value=f"{stock_badge}   ·   {methods_str}", inline=False)

    if product.get('requirements'):
        emb.add_field(name="Requirements", value=f"```{product['requirements']}```", inline=False)

    thumbnail = product.get('thumbnail_url', 'https://cdn-icons-png.flaticon.com/512/1170/1170678.png')
    emb.set_thumbnail(url=thumbnail)
    emb.set_footer(text="ᴀʙʏss ʜᴜʙ  ·  Choose a payment method below ↓")
    return emb


# Keep backward compat name for imports
PaymentButtonView = StoreView