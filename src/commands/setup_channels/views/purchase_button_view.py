import discord
from datetime import datetime
from readsettings import ReadSettings
from utils.product_manager import linesInFile
from ..modals.payment_modal import PaymentModal


# ──── Shared embed builder ────────────────────────────────────────────

# One color per product slot — cycles if more than 6 products
_PRODUCT_COLORS = [0x5865F2, 0xEB459E, 0x57F287, 0xFEE75C, 0xED4245, 0xE67E22]


def build_store_embed():
    """Returns a list of embeds: one header + one per product (each with a unique color)."""
    products = ReadSettings('products.json')
    product_list = products.json()
    embeds = []

    # ── Header ──
    header = discord.Embed(colour=0x5865F2)
    header.set_author(
        name="ᴀʙʏss ʜᴜʙ",
        icon_url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png"
    )
    header.description = (
        "**Welcome to the store.**\n"
        "-# Pick a product from the dropdown below to get started.\n"
        "\u200b"
    )
    embeds.append(header)

    # ── One embed per product (with section separators) ──
    # Products 0-4 are Abyss Hub; 5+ are other brands (Xbox, Steam)
    _abyss_sep_added = False
    _other_sep_added = False

    for i, product in enumerate(product_list):
        tags = product.get('tags', [])
        is_abyss = 'abyss' in tags

        # Insert section separator before Abyss Hub block
        if is_abyss and not _abyss_sep_added:
            sep = discord.Embed(colour=0x2B2D31)
            sep.description = "─────────────────────────────────\n🎮  **Abyss Hub Steam Plugins**\n─────────────────────────────────"
            embeds.append(sep)
            _abyss_sep_added = True

        # Insert section separator before non-Abyss Hub block
        if not is_abyss and not _other_sep_added:
            sep = discord.Embed(colour=0x2B2D31)
            sep.description = "─────────────────────────────────\n🌐  **Other Products**\n─────────────────────────────────"
            embeds.append(sep)
            _other_sep_added = True

        stock       = linesInFile(product['product_file'])
        in_stock    = stock >= product.get('min_order_amount', 1)
        color       = _PRODUCT_COLORS[i % len(_PRODUCT_COLORS)]
        stock_badge = "🟢 In Stock" if in_stock else "🔴 Out of Stock"

        methods = []
        for m in product['payment_methods']:
            if m == 'CRYPTO':    methods.append('🪙 Crypto')
            elif m == 'CREDITCARD': methods.append('💳 Card')
        methods_str = '  ·  '.join(methods)

        req = product.get('requirements', '')

        emb = discord.Embed(colour=color)
        emb.title = product['name']
        emb.description = (
            f"*{product['description']}*\n"
            f"\u200b"
        )

        # ── Stats row ──
        emb.add_field(name="Price",     value=f"` ${product['price']} `",            inline=True)
        emb.add_field(name="Min Order", value=f"` {product['min_order_amount']} `",  inline=True)
        emb.add_field(name="Stock",     value=f"` {stock} `",                        inline=True)

        # ── Status + payment — with a blank-name spacer above for breathing room ──
        emb.add_field(name="\u200b",    value=f"{stock_badge}   ·   {methods_str}",  inline=False)

        if req:
            emb.add_field(name="Requirements", value=f"```{req}```", inline=False)

        thumbnail_url = product.get('thumbnail_url', 'https://cdn-icons-png.flaticon.com/512/1170/1170678.png')
        emb.set_thumbnail(url=thumbnail_url)
        embeds.append(emb)

    # Footer + timestamp only on the last embed
    embeds[-1].set_footer(text="ᴀʙʏss ʜᴜʙ  ·  Use the dropdown below to purchase")
    embeds[-1].timestamp = datetime.now()

    return embeds


# ──── Views / Dropdowns ───────────────────────────────────────────────

class PaymentMethodDropdown(discord.ui.Select):
    """Second dropdown: pick payment method for the selected product."""
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
        await interaction.response.send_modal(
            PaymentModal(custom_id='payment-modal', test=self.values[0], productInfo=self.productInfo)
        )


class PaymentMethodView(discord.ui.View):
    """Ephemeral view shown after product selection — contains payment method dropdown."""
    def __init__(self, productInfo):
        super().__init__()
        self.add_item(PaymentMethodDropdown(productInfo))


class ProductDropdown(discord.ui.Select):
    """Main dropdown on the store embed: pick a product."""
    def __init__(self, products_list):
        self.products_list = {p['name']: p for p in products_list}
        options = []
        for product in products_list:
            stock = linesInFile(product['product_file'])
            in_stock = stock >= product.get('min_order_amount', 1)
            emoji = "\u2705" if in_stock else "\u274c"   # ✅ / ❌
            options.append(discord.SelectOption(
                label=product['name'][:100],
                description=f"${product['price']}  ·  {stock} in stock",
                value=product['name'],
                emoji=emoji
            ))
        super().__init__(
            placeholder="Select a product …",
            options=options,
            custom_id="store-product-select"
        )

    async def callback(self, interaction: discord.Interaction):
        product = self.products_list[self.values[0]]
        stock = linesInFile(product['product_file'])

        # ── Out-of-stock ──
        if stock < product['min_order_amount']:
            oos = discord.Embed(colour=0xED4245, timestamp=datetime.now())
            oos.set_author(
                name="ᴘᴏɪsᴏɴ.xʏᴢ",
                icon_url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png"
            )
            oos.title = "Out of Stock"
            oos.description = (
                f"**{product['name']}** is currently unavailable.\n"
                "\u200b\n"
                "-# Check back later or wait for a restock notification."
            )
            oos.set_footer(text="ᴘᴏɪsᴏɴ.xʏᴢ")
            return await interaction.response.send_message(embed=oos, ephemeral=True)

        # ── Product detail card ──
        in_stock    = stock >= product.get('min_order_amount', 1)
        stock_badge = "🟢 In Stock" if in_stock else "🔴 Out of Stock"

        methods = []
        for m in product['payment_methods']:
            if m == 'CRYPTO':    methods.append('🪙 Crypto')
            elif m == 'CREDITCARD': methods.append('💳 Card')
        methods_str = '  ·  '.join(methods)

        products_list_all = ReadSettings('products.json').json()
        prod_index = next((j for j, p in enumerate(products_list_all) if p['name'] == product['name']), 0)
        color = _PRODUCT_COLORS[prod_index % len(_PRODUCT_COLORS)]

        embed = discord.Embed(colour=color, timestamp=datetime.now())
        embed.set_author(
            name="ᴘᴏɪsᴏɴ.xʏᴢ",
            icon_url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png"
        )
        embed.title = product['name']
        embed.description = (
            f"*{product['description']}*\n"
            "\u200b"
        )

        embed.add_field(name="Price",     value=f"` ${product['price']} `",           inline=True)
        embed.add_field(name="Min Order", value=f"` {product['min_order_amount']} `", inline=True)
        embed.add_field(name="Stock",     value=f"` {stock} `",                       inline=True)

        embed.add_field(name="\u200b",    value=f"{stock_badge}   ·   {methods_str}", inline=False)

        if product.get('requirements'):
            embed.add_field(
                name="Requirements",
                value=f"```{product['requirements']}```",
                inline=False
            )

        thumbnail_url = product.get('thumbnail_url', 'https://cdn-icons-png.flaticon.com/512/1170/1170678.png')
        embed.set_thumbnail(url=thumbnail_url)
        embed.set_footer(text="ᴘᴏɪsᴏɴ.xʏᴢ  ·  Choose a payment method below ↓")

        await interaction.response.send_message(
            embed=embed,
            view=PaymentMethodView(product),
            ephemeral=True
        )


class StoreView(discord.ui.View):
    """Persistent view on the store embed with the product dropdown."""
    def __init__(self):
        super().__init__(timeout=None)
        products = ReadSettings('products.json')
        self.add_item(ProductDropdown(products.json()))


# Keep backward compat name for imports
PaymentButtonView = StoreView
