from typing import Optional
import discord
from discord import app_commands
from datetime import datetime
from setuptools import Command
import asyncio
from discord.ext.commands import cooldown, BucketType
from datetime import timedelta
import math
import time
from readsettings import ReadSettings
from .views.purchase_button_view import PaymentButtonView
from utils.product_manager import getAccounts, linesInFile

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
            for index, product in enumerate(products.json()):
                embed = discord.Embed(
                    title=f"🎁 {product['name']}",
                    colour=0x4900f5,
                    timestamp=datetime.now()
                )

                embed.add_field(
                    name="📝 Description",
                    value=product['description'],
                    inline=False
                )
                embed.add_field(
                    name="💸 Price & Min Order",
                    value=f"**${product['price']}** per • Min order: **{product['min_order_amount']}**",
                    inline=True
                )
                if product['requirements']:
                    embed.add_field(
                        name="🖥️ Requirements",
                        value=product['requirements'],
                        inline=True
                    )
                paymentMethods = []
                for paymentMethod in product['payment_methods']:
                    if paymentMethod == 'CRYPTO':
                        paymentMethods.append('💰 Crypto (BTC, LTC)')
                    elif paymentMethod == 'CREDITCARD':
                        paymentMethods.append('💳 Credit Card (Stripe)')
                formattedMethods = '\n'.join(paymentMethods)
                embed.add_field(
                    name="💵 Payment Methods",
                    value=formattedMethods,
                    inline=False
                )

                embed.set_footer(text="🛒 Powered by ᴘᴏɪsᴏɴ.xʏᴢ")

                # Thumbnail support: use product['thumbnail_url'] if present, else default
                thumbnail_url = product.get('thumbnail_url', 'https://cdn-icons-png.flaticon.com/512/1170/1170678.png')
                embed.set_thumbnail(url=thumbnail_url)

                store_channel = interaction.guild.get_channel(config['store_channel_id'])
                stock_msg = await store_channel.send(
                    content=f'Stock: {linesInFile(product["product_file"])}',
                    embed=embed,
                    view=PaymentButtonView(productInfo=product)
                )
                products[index]['message_id'] = stock_msg.id
                products[index]['channel_id'] = store_channel.id
            products.save()