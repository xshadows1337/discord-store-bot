from typing import Optional
import discord
from discord import app_commands
from datetime import datetime
import asyncio
from readsettings import ReadSettings
from .views.purchase_button_view import StoreView, build_store_embed
from utils.product_manager import linesInFile

class SetupCommand:
    
    def __init__(self, client, tree, config) -> None:
        print(config.data)
        @tree.command(guild = discord.Object(id=config['discord_guild_id']), name = 'setup', description='Setup Store in the current server.')
        async def setup(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True, thinking=True)
            if(interaction.user.id not in config['admin_ids']):
                embed = discord.Embed(colour=0xed4245)
                embed.set_author(name="Access Denied", icon_url="https://cdn-icons-png.flaticon.com/512/753/753345.png")
                embed.description = "You do not have permission to run this command."
                await interaction.edit_original_response(embed=embed)
                return

            await interaction.edit_original_response(content="Setting up store …")
            products = ReadSettings("products.json")

            store_channel = interaction.guild.get_channel(config['store_channel_id'])
            store_msg = await store_channel.send(
                embeds=build_store_embed(),
                view=StoreView()
            )
            
            # Save the store message ID
            products.data = products.json()
            for index in range(len(products.data)):
                products[index]['message_id'] = store_msg.id
            products.save()
            
            await interaction.edit_original_response(content="✅ Store embed created successfully.")