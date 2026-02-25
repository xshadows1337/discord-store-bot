import discord
from datetime import datetime
from readsettings import ReadSettings
from utils.product_manager import linesInFile
from ..modals.payment_modal import PaymentModal


class PaymentMethodDropdown(discord.ui.Select):
    """Second dropdown: pick payment method for the selected product."""
    def __init__(self, productInfo):
        self.productInfo = productInfo
        options = []
        for method in productInfo['payment_methods']:
            if method == 'CRYPTO':
                options.append(discord.SelectOption(label="Crypto (LTC, BTC)", value="Crypto", emoji="💰"))
            elif method == 'CREDITCARD':
                options.append(discord.SelectOption(label="Credit Cards (Stripe)", value="CreditCard", emoji="💳"))
        super().__init__(placeholder="Select Payment Method", options=options)

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
            options.append(discord.SelectOption(
                label=product['name'][:100],
                description=f"${product['price']} • Stock: {stock}",
                value=product['name']
            ))
        super().__init__(
            placeholder="🛒 Select a product to purchase",
            options=options,
            custom_id="store-product-select"
        )

    async def callback(self, interaction: discord.Interaction):
        product = self.products_list[self.values[0]]
        stock = linesInFile(product['product_file'])

        if stock < product['min_order_amount']:
            embed = discord.Embed(
                title="Out Of Stock",
                description="We are currently out of stock for this product. Please wait for a restock.",
                colour=0xde2a2a,
                timestamp=datetime.now()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title=f"🎁 {product['name']}",
            colour=0x4900f5,
            timestamp=datetime.now()
        )
        embed.add_field(name="📝 Description", value=product['description'], inline=False)
        embed.add_field(
            name="💸 Price & Min Order",
            value=f"**${product['price']}** per • Min order: **{product['min_order_amount']}**",
            inline=True
        )
        if product.get('requirements'):
            embed.add_field(name="🖥️ Requirements", value=product['requirements'], inline=True)
        embed.add_field(name="📦 Stock", value=f"**{stock}** available", inline=True)

        thumbnail_url = product.get('thumbnail_url', 'https://cdn-icons-png.flaticon.com/512/1170/1170678.png')
        embed.set_thumbnail(url=thumbnail_url)
        embed.set_footer(text="Select a payment method below to continue")

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
