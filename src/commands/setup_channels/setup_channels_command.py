from typing import Optional
import discord
from discord import app_commands
from datetime import datetime
import asyncio
from readsettings import ReadSettings
from .views.purchase_button_view import StoreView
from utils.product_manager import linesInFile

class SetupCommand:
    
    def __init__(self, client, tree, config) -> None:
        print(config.data)
        @tree.command(guild = discord.Object(id=config['discord_guild_id']), name = 'setup', description='Setup Store in the current server.')
        async def setup(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True, thinking=True)
            if(interaction.user.id not in config['admin_ids']):
                embed = discord.Embed(title="Error", description="You are not an admin.", color=0xff0000)
                await interaction.edit_original_response(embed=embed)
                return

            await interaction.edit_original_response(content="Setting Up..")
            products = ReadSettings("products.json")
            
            # Build the store embed with all products listed
            embed = discord.Embed(
                title="🛒 Store",
                description="Browse our products below and select one from the dropdown to purchase.",
                colour=0x4900f5,
                timestamp=datetime.now()
            )

            for product in products.json():
                stock = linesInFile(product['product_file'])
                paymentMethods = []
                for method in product['payment_methods']:
                    if method == 'CRYPTO':
                        paymentMethods.append('💰 Crypto')
                    elif method == 'CREDITCARD':
                        paymentMethods.append('💳 Card')
                methods_str = ' • '.join(paymentMethods)
                
                embed.add_field(
                    name=f"🎁 {product['name']}",
                    value=(
                        f"{product['description']}\n"
                        f"**Price:** ${product['price']} • **Min:** {product['min_order_amount']} • **Stock:** {stock}\n"
                        f"**Payments:** {methods_str}"
                    ),
                    inline=False
                )

            embed.set_footer(text="🛒 Powered by ᴘᴏɪsᴏɴ.xʏᴢ")

            store_channel = interaction.guild.get_channel(config['store_channel_id'])
            store_msg = await store_channel.send(
                embed=embed,
                view=StoreView()
            )
            
            # Save the store message ID
            products.data = products.json()
            for index in range(len(products.data)):
                products[index]['message_id'] = store_msg.id
            products.save()
            
            await interaction.edit_original_response(content="✅ Store setup complete!")