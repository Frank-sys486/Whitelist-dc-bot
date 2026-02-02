import discord
from discord.ext import commands
import json
import os

# Load whitelist of school IDs from ids.json
with open("ids.json", "r", encoding="utf-8") as f:
    # Load and strip whitespace from each ID to ensure clean matching
    valid_ids = [id_str.strip() for id_str in json.load(f)]

# File to track which ID belongs to which user
CLAIMED_FILE = "claimed_ids.json"

def load_claimed_ids():
    if os.path.exists(CLAIMED_FILE):
        with open(CLAIMED_FILE, "r") as f:
            return json.load(f)
    return {}

def save_claimed_ids(claimed):
    with open(CLAIMED_FILE, "w") as f:
        json.dump(claimed, f, indent=4)

claimed_ids = load_claimed_ids()

# Bot setup
intents = discord.Intents.default()
intents.members = True  # Needed to manage roles
intents.message_content = True # Needed to read commands like !verify
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"{bot.user} is now running!")
@bot.event
async def on_member_join(member):
    # Look for a channel named 'verify' or 'general' to send the message
    channel = discord.utils.get(member.guild.text_channels, name="verify")
    if not channel:
        channel = discord.utils.get(member.guild.text_channels, name="general")
    
    if channel:
        await channel.send(f"Welcome {member.mention}! Please verify yourself by typing `!verify <school_id>`.")

@bot.command()
async def verify(ctx, school_id: str):
    """User runs !verify <school_id> to check against whitelist"""
    clean_id = school_id.strip()
    user_id = str(ctx.author.id)

    # 1. Check if ID is in the whitelist
    if clean_id not in valid_ids:
        await ctx.send("That ID number is not recognized. Please contact a moderator.")
        return

    # 2. Check if ID is already claimed by someone else
    if clean_id in claimed_ids:
        if claimed_ids[clean_id] != user_id:
            await ctx.send("This ID has already been used by another user.")
            return

    # 3. Assign Role and Save
    role = discord.utils.get(ctx.guild.roles, name="Verified")
    if role:
        await ctx.author.add_roles(role)
        
        # Save the claim if it's new
        if clean_id not in claimed_ids:
            claimed_ids[clean_id] = user_id
            save_claimed_ids(claimed_ids)
            
        await ctx.send(f"{ctx.author.mention}, you’ve been verified!")
    else:
        await ctx.send("Verified role not found. Please ask a moderator to create it.")

# Run bot using token stored in environment variable
token = os.getenv("DISCORD_TOKEN")
if not token:
    print("Error: DISCORD_TOKEN environment variable not found.")
else:
    bot.run(token)
