import discord
from datetime import datetime
from utils.product_manager import linesInFile
from ..modals.payment_modal import PaymentModal

class Dropdown(discord.ui.Select):
    def __init__(self, productInfo):
        self.productInfo = productInfo
        options = []
        
        for method in productInfo['payment_methods']:
            if(method == 'CRYPTO'):
                options.append(discord.SelectOption(label="Crypto (LTC, BTC)", value=str("Crypto")))
            elif(method == 'CREDITCARD'):
                options.append(discord.SelectOption(label="Credit Cards", value=str("CreditCard")))

        super().__init__(placeholder="Select Payment Option",options=options)
        
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PaymentModal(custom_id='12ax23', test=self.values[0], productInfo=self.productInfo))
        
class PaymentOptionView(discord.ui.View):
    def __init__(self, productInfo):
        super().__init__()
        self.add_item(Dropdown(productInfo))
        
        
class PaymentButtonView(discord.ui.View):
    def __init__(self, productInfo):
        self.productInfo = productInfo
        super().__init__(timeout=None)
        
        # Create the button dynamically with the correct custom_id
        self.purchase_button = discord.ui.Button(
            label='Purchase',
            style=discord.ButtonStyle.green,
            custom_id=f"payment-button-{self.productInfo['name']}",
            emoji="🛒"
        )
        self.purchase_button.callback = self.on_button_click
        self.add_item(self.purchase_button)

    async def on_button_click(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if linesInFile(self.productInfo['product_file']) < self.productInfo['min_order_amount']:
            print('Checked')
            embed = discord.Embed(
                title="Out Of Stock",
                description="We are currently out of stock for this product. Please wait for a restock.",
                colour=0x4900f5,
                timestamp=datetime.now()
            )
            return await interaction.followup.send(ephemeral=True, embed=embed)

        await interaction.followup.send(ephemeral=True, view=PaymentOptionView(self.productInfo))
