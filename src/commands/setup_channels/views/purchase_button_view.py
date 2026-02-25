import discord
from datetime import datetime
from readsettings import ReadSettings
from utils.product_manager import linesInFile
from ..modals.payment_modal import PaymentModal


# ──── Shared embed builder ────────────────────────────────────────────

def build_store_embed():
    """Build the main store embed used by /setup and the stock-update loop."""
    products = ReadSettings('products.json')
    product_list = products.json()

    embed = discord.Embed(
        colour=0x5865F2,          # Discord blurple — stands out cleanly on dark mode
        timestamp=datetime.now()
    )
    embed.set_author(
        name="ᴘᴏɪsᴏɴ.xʏᴢ  ·  Store",
        icon_url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png"
    )
    embed.description = (
        "-# 〔 Browse the catalog below and select a product to purchase 〕\n"
        "\u200b"
    )

    for product in product_list:
        stock = linesInFile(product['product_file'])
        in_stock = stock >= product.get('min_order_amount', 1)
        status_icon = "🟢" if in_stock else "🔴"

        methods = []
        for m in product['payment_methods']:
            if m == 'CRYPTO':
                methods.append('🪙 Crypto')
            elif m == 'CREDITCARD':
                methods.append('💳 Card')
        methods_str = '  ╱  '.join(methods)

        embed.add_field(
            name=f"╔  {product['name']}",
            value=(
                f"╠  {product['description']}\n"
                f"╠\n"
                f"╠  💰 **Price** ── `${product['price']}`   •   📦 **Min** ── `{product['min_order_amount']}`\n"
                f"╠  {status_icon} **Stock** ── `{stock}`   •   {methods_str}\n"
                f"╚{'─' * 28}\n"
                f"\u200b"
            ),
            inline=False
        )

    embed.set_footer(text="ᴘᴏɪsᴏɴ.xʏᴢ  ·  Use the dropdown below to get started")
    return embed


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
            oos = discord.Embed(colour=0xed4245, timestamp=datetime.now())
            oos.set_author(name="Out of Stock", icon_url="https://cdn-icons-png.flaticon.com/512/753/753345.png")
            oos.description = (
                "```\n"
                "  ✗  This product is currently out of stock.\n"
                "```\n"
                "> Please check back later or wait for a restock.\n"
                "\u200b"
            )
            oos.set_footer(text="ᴘᴏɪsᴏɴ.xʏᴢ")
            return await interaction.response.send_message(embed=oos, ephemeral=True)

        # ── Product detail card ──
        in_stock = stock >= product.get('min_order_amount', 1)
        status_icon = "🟢" if in_stock else "🔴"

        methods = []
        for m in product['payment_methods']:
            if m == 'CRYPTO':
                methods.append('🪙 Crypto')
            elif m == 'CREDITCARD':
                methods.append('💳 Card')
        methods_str = '  ╱  '.join(methods)

        embed = discord.Embed(colour=0x5865F2, timestamp=datetime.now())
        embed.set_author(
            name="ᴘᴏɪsᴏɴ.xʏᴢ  ·  Product Details",
            icon_url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png"
        )
        embed.title = product['name']
        embed.description = (
            f"> {product['description']}\n"
            f"\u200b"
        )

        embed.add_field(name="💰  Price", value=f"`${product['price']}`", inline=True)
        embed.add_field(name="📦  Min Order", value=f"`{product['min_order_amount']}`", inline=True)
        embed.add_field(name=f"{status_icon}  Stock", value=f"`{stock}` available", inline=True)

        if product.get('requirements'):
            embed.add_field(
                name="🖥️  Requirements",
                value=f"```{product['requirements']}```",
                inline=False
            )

        embed.add_field(name="\u200b", value=methods_str, inline=False)

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
