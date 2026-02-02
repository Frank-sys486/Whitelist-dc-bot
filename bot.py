import discord
from discord.ext import commands
import json
import os
import csv

# Load student data from CSV
STUDENT_FILE = "response.csv"
student_db = {}

if os.path.exists(STUDENT_FILE):
    with open(STUDENT_FILE, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Get Student Number and strip whitespace
            sid = row.get('Student Number', '').strip()
            if not sid: continue # Skip empty rows

            if sid not in student_db:
                student_db[sid] = {'name': row.get('Full Name', '').strip(), 'sports': set()}
            
            # Add sport to the set (handles duplicates automatically)
            sport = row.get('Column 7', '').strip()
            if sport:
                student_db[sid]['sports'].add(sport)
else:
    print(f"Warning: {STUDENT_FILE} not found!")

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
        await channel.send(f"Welcome {member.mention}! Please verify yourself by typing `!verify 20XX-XX-XXXXX`.", delete_after=60)

    # Automatically assign 'Unverified' role
    unverified_role = discord.utils.get(member.guild.roles, name="Unverified")
    if unverified_role:
        try:
            await member.add_roles(unverified_role)
            print(f"Assigned 'Unverified' role to {member.name}")
        except discord.Forbidden:
            print(f"Could not assign 'Unverified' role to {member.name} due to permission error.")

@bot.event
async def on_message(message):
    # Ignore bot's own messages
    if message.author.bot:
        return

    # Strict rules for 'verify' channel
    if message.channel.name == "verify":
        is_mod = discord.utils.get(message.author.roles, name="Moderator")
        
        # If user is NOT a moderator
        mod_log_channel = discord.utils.get(message.guild.text_channels, name="mod-logs")
        if not is_mod:
            # If it's NOT a verify command, delete it immediately
            if not message.content.startswith("!verify"):
                # Log the deleted message to mod-logs
                if mod_log_channel:
                    embed = discord.Embed(
                        title="Deleted Message",
                        description=f"**Author:** {message.author.mention}\n**Channel:** {message.channel.mention}\n**Content:** {message.content}",
                        color=discord.Color.red()
                    )
                    await mod_log_channel.send(embed=embed)

                # Delete the message and remind user of correct format
                await message.delete()
                await message.channel.send(f"{message.author.mention}, please verify using the format: `!verify 20XX-XX-XXXXX`", delete_after=5)                
                return

    # Process commands (like !verify)
    await bot.process_commands(message)

@bot.command()
async def verify(ctx, school_id: str = None):
    """User runs !verify <school_id> to check against whitelist"""
    # Delete the user's command message to keep channel clean
    try:
        await ctx.message.delete()
    except:
        pass

    # Ensure command is run in the correct channel
    if ctx.channel.name != "verify":
        await ctx.send("Please use the #verify channel.", delete_after=5)
        return

    if not school_id:
        await ctx.send(f"{ctx.author.mention}, please provide your Student Number (e.g., `!verify 2025-2-00228`).", delete_after=5)
        return

    clean_id = school_id.strip()
    user_id = str(ctx.author.id)

    # 1. Check if ID is in the CSV database
    if clean_id not in student_db:
        await ctx.send(f"{ctx.author.mention}, that ID number is not recognized.", delete_after=5)
        return

    # 2. Check if ID is already claimed by someone else
    if clean_id in claimed_ids:
        if claimed_ids[clean_id] != user_id:
            await ctx.send(f"{ctx.author.mention}, this ID has already been used by another user.", delete_after=5)
            return

    # 3. Get Student Info
    student_info = student_db[clean_id]
    
    # Change Nickname (First word of Full Name)
    # Example: "Ungco Josh Aiken O." -> "Ungco"
    new_nickname = student_info['name'].split()[0].replace(',', '')
    
    print(f"Attempting to change nickname for {ctx.author} to '{new_nickname}'...")

    if ctx.author.id == ctx.guild.owner_id:
        print("Error: Cannot change nickname because the user is the Server Owner.")
        await ctx.send("I cannot change the server owner's nickname.", delete_after=5)
    else:
        try:
            await ctx.author.edit(nick=new_nickname)
            print("Nickname changed successfully.")
        except discord.Forbidden as e:
            print(f"Error: Failed to change nickname. Permission denied. Details: {e}")
            print(f"Debug: Bot Top Role Position: {ctx.guild.me.top_role.position}, User Top Role Position: {ctx.author.top_role.position}")
            await ctx.send("I couldn't change your nickname. My role might be below yours in the server settings.", delete_after=5)
        except Exception as e:
            print(f"Error: An unexpected error occurred: {e}")

    # 4. Assign Roles based on Sports
    roles_added = []
    for sport_name in student_info['sports']:
        role = discord.utils.get(ctx.guild.roles, name=sport_name)
        if role:
            roles_added.append(role)

    # Add the base 'Verified' role
    verified_role = discord.utils.get(ctx.guild.roles, name="Verified")
    if verified_role:
        roles_added.append(verified_role)
    
    if roles_added:
        await ctx.author.add_roles(*roles_added)
    
    # Remove 'Unverified' role if the user has it
    unverified_role = discord.utils.get(ctx.guild.roles, name="Unverified")
    if unverified_role and unverified_role in ctx.author.roles:
        await ctx.author.remove_roles(unverified_role)

    # 5. Save Claim
    if clean_id not in claimed_ids:
        claimed_ids[clean_id] = user_id
        save_claimed_ids(claimed_ids)

    await ctx.send(f"{ctx.author.mention}, you have been verified as **{new_nickname}**!", delete_after=10)

# Run bot using token stored in environment variable
token = os.getenv("DISCORD_TOKEN")
if not token:
    print("Error: DISCORD_TOKEN environment variable not found.")
else:
    bot.run(token)
