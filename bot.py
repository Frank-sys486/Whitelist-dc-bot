import discord
from discord.ext import commands
import json
import os
import csv
import datetime

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

# File to track Teams
TEAMS_FILE = "teams.json"

def load_teams():
    if os.path.exists(TEAMS_FILE):
        with open(TEAMS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_teams(teams):
    with open(TEAMS_FILE, "w") as f:
        json.dump(teams, f, indent=4, default=str)

# Configuration for In-Game Roles
GAME_ROLES_CONFIG = {
    "MLBB": ["Roam", "Jungler", "Gold", "Mage", "Exp", "Flex"],
    "Valorant": ["Duelist", "Controller", "Sentinel", "Initiator", "Flex"]
}

claimed_ids = load_claimed_ids()

# Global flag to control team creation
team_creation_enabled = True

# Bot setup
intents = discord.Intents.default()
intents.members = True  # Needed to manage roles
intents.message_content = True # Needed to read commands like !verify
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

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
        await channel.send(f"Welcome {member.mention}! Please verify yourself by typing `!verify 20XX-X-XXXXX`.", delete_after=60)

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
    
    # Add 'Solo' role (Free Agent status)
    solo_role = discord.utils.get(ctx.guild.roles, name="Solo")
    if solo_role:
        roles_added.append(solo_role)

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

# --- TEAM SYSTEM HELPERS ---

async def update_solo_role(guild, member, has_team):
    """
    Manages the 'Solo' role based on team status.
    - If has_team is True: Remove 'Solo' role.
    - If has_team is False: Add 'Solo' role.
    Does NOT touch the 'Verified' role.
    """
    solo_role = discord.utils.get(guild.roles, name="Solo")
    if not solo_role:
        return

    if has_team:
        if solo_role in member.roles:
            await member.remove_roles(solo_role)
    else:
        if solo_role not in member.roles:
            await member.add_roles(solo_role)

async def perform_verification(guild, member, student_id, moderator_user):
    """Reusable logic to verify a user, assign roles, and log the action."""
    clean_id = student_id.strip()
    
    if clean_id not in student_db:
        return False, f"Student ID {clean_id} not found."

    student_info = student_db[clean_id]
    user_id = str(member.id)

    # 1. Manage Claimed IDs (Prevent Duplicates)
    ids_to_remove = [sid for sid, uid in claimed_ids.items() if uid == user_id]
    for old_sid in ids_to_remove:
        del claimed_ids[old_sid]
    
    claimed_ids[clean_id] = user_id
    save_claimed_ids(claimed_ids)

    # 2. Update Nickname
    new_nickname = student_info['name'].split()[0].replace(',', '')
    try:
        if member.id != guild.owner_id:
            await member.edit(nick=new_nickname)
    except:
        pass # Ignore permission errors

    # 3. Assign Roles
    roles_to_add = []
    verified_role = discord.utils.get(guild.roles, name="Verified")
    if verified_role: roles_to_add.append(verified_role)
    
    for sport in student_info['sports']:
        r = discord.utils.get(guild.roles, name=sport)
        if r: roles_to_add.append(r)
    
    # Solo Role (Only if NOT in a team)
    teams = load_teams()
    in_team = False
    for t in teams.values():
        if user_id in t['members']:
            in_team = True
            break
    
    if not in_team:
        solo_role = discord.utils.get(guild.roles, name="Solo")
        if solo_role: roles_to_add.append(solo_role)
    
    if roles_to_add:
        await member.add_roles(*roles_to_add)

    # 4. Remove Unverified
    unverified_role = discord.utils.get(guild.roles, name="Unverified")
    if unverified_role and unverified_role in member.roles:
        await member.remove_roles(unverified_role)

    # 5. Log Action
    log_channel = discord.utils.get(guild.text_channels, name="mod-logs")
    if log_channel:
        embed = discord.Embed(title="🛡️ Verification Action", color=discord.Color.orange())
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Student ID", value=clean_id, inline=True)
        embed.add_field(name="Nickname", value=new_nickname, inline=True)
        embed.add_field(name="Action By", value=moderator_user.mention, inline=False)
        embed.set_footer(text="User has been linked and roles assigned.")
        await log_channel.send(embed=embed)
    
    return True, f"Verified {member.display_name} as {new_nickname}"

async def update_mod_dashboard(guild):
    """Updates the #mod-team channel with a list of all teams."""
    teams = load_teams()
    
    # Find or Create #mod-team channel
    mod_channel = discord.utils.get(guild.text_channels, name="mod-team")
    if not mod_channel:
        # Create channel exclusive to Moderators
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        mod_role = discord.utils.get(guild.roles, name="Moderator")
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True)
        
        mod_channel = await guild.create_text_channel("mod-team", overwrites=overwrites)

    # Clear previous messages to keep it clean (Dashboard style)
    try:
        await mod_channel.purge(limit=10)
    except:
        pass # Fail silently if history is too old or perms issue

    # Build the Dashboard Embed
    embed = discord.Embed(title="🏆 Tournament Teams Dashboard", color=discord.Color.gold())
    embed.description = f"**Total Teams:** {len(teams)}\nLast Updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    # Group teams by Game
    teams_by_game = {}
    for team_name, data in teams.items():
        game = data['game'].upper()
        if game not in teams_by_game:
            teams_by_game[game] = []
        teams_by_game[game].append(team_name)
    
    if not teams_by_game:
        embed.add_field(name="Status", value="No teams created yet.", inline=False)
    else:
        for game, team_list in teams_by_game.items():
            embed.add_field(name=f"{game} ({len(team_list)})", value="\n".join(team_list), inline=False)

    await mod_channel.send(embed=embed)

# --- TEAM COMMANDS ---

@bot.command()
async def createteam(ctx, game: str = None, *, team_name: str = None):
    """Creates a team, private channels, and role. Usage: !createteam valorant "Team Name" """
    
    if not team_creation_enabled:
        await ctx.send(f"🚫 {ctx.author.mention}, team creation is currently **PAUSED** by the moderators.", delete_after=10)
        return

    # 1. Input Validation
    if not game or not team_name:
        await ctx.send(f"{ctx.author.mention}, usage: `!createteam <game> <team_name>`\nExample: `!createteam valorant Team Eagles`", delete_after=10)
        return
    
    # Clean quotes from team name (e.g., "CCS" -> CCS)
    team_name = team_name.strip('"')

    # Map input to Category Names
    CATEGORY_MAP = {
        "valorant": "valorant-team",
        "mlbb": "mlbb-team",
        "mobile legends": "mlbb-team",
        "codm": "codm-team",
        "call of duty": "codm-team"
    }
    
    category_name = CATEGORY_MAP.get(game.lower())
    if not category_name:
        await ctx.send(f"Invalid game. Supported games: Valorant, MLBB, CODM.", delete_after=5)
        return

    # 2. Check if User is Verified
    verified_role = discord.utils.get(ctx.guild.roles, name="Verified")
    if verified_role not in ctx.author.roles:
        await ctx.send("You must be Verified to create a team.", delete_after=5)
        return

    # 3. Check Database (Is user already in a team? Is name taken?)
    teams = load_teams()
    
    if team_name in teams:
        await ctx.send(f"Team name **{team_name}** is already taken.", delete_after=5)
        return

    user_id = str(ctx.author.id)
    for t_name, t_data in teams.items():
        if user_id in t_data['members']:
            await ctx.send(f"You are already in a team ({t_name}). You cannot create another one.", delete_after=5)
            return

    # 4. Create Discord Infrastructure
    guild = ctx.guild
    
    # Find Category
    category = discord.utils.get(guild.categories, name=category_name)
    if not category:
        await ctx.send(f"Error: Category `{category_name}` not found. Please contact an admin.", delete_after=10)
        return

    # Create Role
    team_role = await guild.create_role(name=team_name, mentionable=True)
    await ctx.author.add_roles(team_role)

    # Create Channels (Private)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False),
        team_role: discord.PermissionOverwrite(read_messages=True, connect=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, connect=True)
    }

    text_channel = await guild.create_text_channel(team_name.replace(" ", "-").lower(), category=category, overwrites=overwrites)
    voice_channel = await guild.create_voice_channel(team_name, category=category, overwrites=overwrites)

    # 5. Save to Database
    teams[team_name] = {
        "game": game.lower(),
        "captain_id": user_id,
        "members": [user_id],
        "text_channel_id": text_channel.id,
        "voice_channel_id": voice_channel.id,
        "role_id": team_role.id,
        "invites": [],
        "created_at": datetime.datetime.now().isoformat()
    }
    save_teams(teams)

    # 6. Post Captain's Guide
    embed = discord.Embed(title=f"👑 Welcome to {team_name}", description="You are the Captain! Here are your commands:", color=discord.Color.green())
    embed.add_field(name="!invite <user> ", value="Invite a player to your team.", inline=False)
    embed.add_field(name="!kick @user", value="Remove a player from your team.", inline=False)
    embed.add_field(name="!disband", value="Delete this team permanently.", inline=False)
    await text_channel.send(content=ctx.author.mention, embed=embed)
    await text_channel.pin_message(await text_channel.fetch_message(text_channel.last_message_id))

    # 7. Update 'Solo' Status (User is now in a team)
    # We keep 'Verified' role, but remove 'Solo' role
    await update_solo_role(guild, ctx.author, has_team=True)

    # 8. Update Dashboard
    await update_mod_dashboard(guild)
    
    await ctx.send(f"Team **{team_name}** created successfully! Check {text_channel.mention}.", delete_after=10)

@bot.command()
async def teamstats(ctx):
    """Shows statistics about teams and players."""
    teams = load_teams()
    
    total_teams = len(teams)
    
    # Count players in teams
    players_in_teams = sum(len(t['members']) for t in teams.values())
    
    # Count Solo players
    solo_role = discord.utils.get(ctx.guild.roles, name="Solo")
    solo_count = len(solo_role.members) if solo_role else 0

    embed = discord.Embed(title="📊 Tournament Statistics", color=discord.Color.blue())
    embed.add_field(name="Total Teams", value=str(total_teams), inline=True)
    embed.add_field(name="Players in Teams", value=str(players_in_teams), inline=True)
    embed.add_field(name="Free Agents (Solo)", value=str(solo_count), inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
async def invite(ctx, member: discord.Member):
    """Captain invites a player: !invite <User> !invite Paxton"""
    # 1. Check if Author is a Captain
    teams = load_teams()
    my_team_name = None
    my_team_data = None

    for t_name, t_data in teams.items():
        if t_data['captain_id'] == str(ctx.author.id):
            my_team_name = t_name
            my_team_data = t_data
            break
    
    if not my_team_name:
        await ctx.send(f"{ctx.author.mention}, you are not the captain of any team.", delete_after=5)
        return

    # 2. Validate the Target Member
    if member.bot:
        await ctx.send("You cannot invite bots.", delete_after=5)
        return
    
    verified_role = discord.utils.get(ctx.guild.roles, name="Verified")
    if verified_role not in member.roles:
        await ctx.send(f"{member.display_name} is not Verified yet.", delete_after=5)
        return

    # Check if they are already in a team
    for t_data in teams.values():
        if str(member.id) in t_data['members']:
            await ctx.send(f"{member.display_name} is already in a team.", delete_after=5)
            return

    # 3. Add to Invites List
    # Initialize list if it doesn't exist (for older teams)
    if "invites" not in my_team_data:
        my_team_data["invites"] = []

    if str(member.id) in my_team_data["invites"]:
        await ctx.send(f"{member.display_name} is already invited.", delete_after=5)
        return

    my_team_data["invites"].append(str(member.id))
    save_teams(teams)

    # 4. Notify the User
    try:
        await member.send(f"🎟️ **You have been invited!**\n\nTeam **{my_team_name}** wants you.\nTo accept, go to the server and type:\n`!join \"{my_team_name}\"`")
        await ctx.send(f"Invite sent to **{member.display_name}**!", delete_after=5)
    except discord.Forbidden:
        await ctx.send(f"I couldn't DM {member.display_name}, but they can still join by typing `!join \"{my_team_name}\"`.", delete_after=10)

@bot.command()
async def join(ctx, *, team_name: str):
    """Accept an invite: !join "Team Name" """
    teams = load_teams()
    
    # Clean quotes from input so !join "CCS" works for team CCS
    team_name = team_name.strip('"')
    
    # 1. Check if Team Exists
    if team_name not in teams:
        await ctx.send(f"Team **{team_name}** does not exist. Check spelling (case-sensitive).", delete_after=5)
        return

    team_data = teams[team_name]
    user_id = str(ctx.author.id)

    # 2. Check if User was Invited
    # (Handle case where 'invites' key might be missing in old data)
    invites = team_data.get("invites", [])
    
    if user_id not in invites:
        await ctx.send(f"{ctx.author.mention}, you have not been invited to **{team_name}**. Ask the captain to `!invite` you.", delete_after=5)
        return

    # 3. Double Check: Is user already in a team?
    for t_name, t_data in teams.items():
        if user_id in t_data['members']:
            await ctx.send(f"You are already in **{t_name}**. You must leave it first.", delete_after=5)
            return

    # 4. Process Joining
    # Update Database
    team_data["members"].append(user_id)
    team_data["invites"].remove(user_id) # Remove from invite list
    save_teams(teams)

    # Update Discord Role
    role_id = team_data.get("role_id")
    if role_id:
        role = ctx.guild.get_role(role_id)
        if role:
            await ctx.author.add_roles(role)

    # Update Channel Permissions (Text & Voice)
    # We need to explicitly let them see the channel
    text_channel = ctx.guild.get_channel(team_data["text_channel_id"])
    voice_channel = ctx.guild.get_channel(team_data["voice_channel_id"])

    overwrite = discord.PermissionOverwrite(read_messages=True, connect=True)
    
    if text_channel:
        await text_channel.set_permissions(ctx.author, overwrite=overwrite)
        await text_channel.send(f"👋 Welcome {ctx.author.mention} to the team!")
    
    if voice_channel:
        await voice_channel.set_permissions(ctx.author, overwrite=overwrite)

    # Update Solo Status
    await update_solo_role(ctx.guild, ctx.author, has_team=True)

    # Update Dashboard
    await update_mod_dashboard(ctx.guild)
    
    await ctx.send(f"Successfully joined **{team_name}**!", delete_after=5)

@bot.command()
async def kick(ctx, member: discord.Member):
    """Captain removes a player: !kick @User"""
    # 1. Check if Author is a Captain
    teams = load_teams()
    my_team_name = None
    my_team_data = None

    for t_name, t_data in teams.items():
        if t_data['captain_id'] == str(ctx.author.id):
            my_team_name = t_name
            my_team_data = t_data
            break
    
    if not my_team_name:
        await ctx.send(f"{ctx.author.mention}, you are not the captain of any team.", delete_after=5)
        return

    # 2. Validate Target
    if member.id == ctx.author.id:
        await ctx.send("You cannot kick yourself. Use `!disband` to delete the team.", delete_after=5)
        return
    
    user_id = str(member.id)
    if user_id not in my_team_data['members']:
        await ctx.send(f"{member.display_name} is not in your team.", delete_after=5)
        return

    # 3. Update Database
    my_team_data['members'].remove(user_id)
    save_teams(teams)

    # 4. Remove Discord Role
    role_id = my_team_data.get("role_id")
    if role_id:
        role = ctx.guild.get_role(role_id)
        if role and role in member.roles:
            await member.remove_roles(role)

    # 5. Remove Channel Permissions (Lock them out)
    text_channel = ctx.guild.get_channel(my_team_data["text_channel_id"])
    voice_channel = ctx.guild.get_channel(my_team_data["voice_channel_id"])

    # overwrite=None removes the specific permission override for this user
    if text_channel:
        await text_channel.set_permissions(member, overwrite=None)
    if voice_channel:
        await voice_channel.set_permissions(member, overwrite=None)

    # 6. Update Solo Status (User is now a Free Agent)
    await update_solo_role(ctx.guild, member, has_team=False)

    # 7. Update Dashboard
    await update_mod_dashboard(ctx.guild)

    await ctx.send(f"🚫 **{member.display_name}** has been kicked from **{my_team_name}**.")

@bot.command()
async def leave(ctx):
    """Player leaves their current team."""
    teams = load_teams()
    user_id = str(ctx.author.id)
    
    my_team_name = None
    my_team_data = None
    
    for t_name, t_data in teams.items():
        if user_id in t_data['members']:
            my_team_name = t_name
            my_team_data = t_data
            break
            
    if not my_team_name:
        await ctx.send("You are not in a team.", delete_after=5)
        return
        
    # Check if Captain
    if my_team_data['captain_id'] == user_id:
        await ctx.send("The Captain cannot leave. Use `!disband` to delete the team.", delete_after=10)
        return
        
    # 1. Update Database
    my_team_data['members'].remove(user_id)
    save_teams(teams)
    
    # 2. Remove Discord Role
    role_id = my_team_data.get("role_id")
    if role_id:
        role = ctx.guild.get_role(role_id)
        if role:
            await ctx.author.remove_roles(role)
            
    # 3. Remove Channel Permissions
    text_channel = ctx.guild.get_channel(my_team_data['text_channel_id'])
    voice_channel = ctx.guild.get_channel(my_team_data['voice_channel_id'])
    
    if text_channel: await text_channel.set_permissions(ctx.author, overwrite=None)
    if voice_channel: await voice_channel.set_permissions(ctx.author, overwrite=None)
    
    # 4. Update Solo Status
    await update_solo_role(ctx.guild, ctx.author, has_team=False)
    
    # 5. Update Dashboard
    await update_mod_dashboard(ctx.guild)
    
    # Notify
    if text_channel:
        await text_channel.send(f"👋 **{ctx.author.display_name}** has left the team.")
    await ctx.send(f"You have left **{my_team_name}**.", delete_after=5)

@bot.command()
async def disband(ctx):
    """Captain deletes the team entirely."""
    teams = load_teams()
    
    # Identify team
    my_team_name = None
    my_team_data = None
    for t_name, t_data in teams.items():
        if t_data['captain_id'] == str(ctx.author.id):
            my_team_name = t_name
            my_team_data = t_data
            break
            
    if not my_team_name:
        await ctx.send("You are not the captain of any team.", delete_after=5)
        return

    guild = ctx.guild
    
    # 1. Cleanup Members (Remove Roles & Give Solo back)
    role_id = my_team_data.get("role_id")
    team_role = guild.get_role(role_id)
    
    for member_id in my_team_data['members']:
        member = guild.get_member(int(member_id))
        if member:
            if team_role and team_role in member.roles:
                await member.remove_roles(team_role)
            await update_solo_role(guild, member, has_team=False)
            
    # 2. Delete Channels & Role
    tc = guild.get_channel(my_team_data['text_channel_id'])
    vc = guild.get_channel(my_team_data['voice_channel_id'])
    
    if tc: await tc.delete()
    if vc: await vc.delete()
    if team_role: await team_role.delete()
    
    # 3. Delete from DB & Update Dashboard
    del teams[my_team_name]
    save_teams(teams)
    await update_mod_dashboard(guild)

@bot.command()
async def syncsolo(ctx):
    """Assigns 'Solo' role to users without a team (Moderators/Bots excluded)."""
    # Check for Moderator role
    if "Moderator" not in [r.name for r in ctx.author.roles]:
        await ctx.send("You need the **Moderator** role to use this command.", delete_after=5)
        return

    status_msg = await ctx.send("🔄 Syncing Solo roles... This might take a moment.")
    
    teams = load_teams()
    # Create a set of all user IDs currently in a team
    team_member_ids = set()
    for t_data in teams.values():
        for member_id in t_data.get('members', []):
            team_member_ids.add(str(member_id))
            
    solo_role = discord.utils.get(ctx.guild.roles, name="Solo")
    mod_role = discord.utils.get(ctx.guild.roles, name="Moderator")
    verified_role = discord.utils.get(ctx.guild.roles, name="Verified")
    
    if not solo_role:
        await ctx.send("Error: 'Solo' role not found.", delete_after=5)
        return

    added_count = 0
    removed_count = 0
    
    for member in ctx.guild.members:
        # Skip Bots
        if member.bot:
            continue
            
        # Skip Moderators
        if mod_role and mod_role in member.roles:
            continue
            
        # Skip Unverified (Safety check: only manage Verified users)
        if verified_role and verified_role not in member.roles:
            continue

        user_id = str(member.id)

        if user_id not in team_member_ids:
            # User has NO team -> Add Solo
            if solo_role not in member.roles:
                await member.add_roles(solo_role)
                added_count += 1
        else:
            # User HAS team -> Remove Solo (Cleanup)
            if solo_role in member.roles:
                await member.remove_roles(solo_role)
                removed_count += 1

    await status_msg.edit(content=f"✅ **Sync Complete!**\nAdded @Solo to: {added_count}\nRemoved @Solo from: {removed_count}")

@bot.command()
async def setteam(ctx, member: discord.Member, *, team_name: str):
    """(Moderator Only) Manually assigns a user to a team."""
    # Check for Moderator role
    if "Moderator" not in [r.name for r in ctx.author.roles]:
        await ctx.send("You need the **Moderator** role to use this command.", delete_after=5)
        return

    teams = load_teams()

    # Clean quotes from team name (e.g., "CCS" -> CCS)
    team_name = team_name.strip('"')

    # 1. Check if Team Exists
    if team_name not in teams:
        await ctx.send(f"Team **{team_name}** does not exist. Check spelling (case-sensitive).", delete_after=5)
        return

    team_data = teams[team_name]
    user_id = str(member.id)

    # 2. Check if User is already in a team
    for t_name, t_data in teams.items():
        if user_id in t_data['members']:
            await ctx.send(f"{member.display_name} is already in **{t_name}**. Remove them first.", delete_after=5)
            return

    # 3. Process Joining
    # Update Database
    team_data["members"].append(user_id)
    save_teams(teams)

    # Update Discord Role
    role_id = team_data.get("role_id")
    if role_id:
        role = ctx.guild.get_role(role_id)
        if role:
            await member.add_roles(role)

    # Update Channel Permissions (Text & Voice)
    # We need to explicitly let them see the channel
    text_channel = ctx.guild.get_channel(team_data["text_channel_id"])
    voice_channel = ctx.guild.get_channel(team_data["voice_channel_id"])

    overwrite = discord.PermissionOverwrite(read_messages=True, connect=True)

    if text_channel:
        await text_channel.set_permissions(member, overwrite=overwrite)
        await text_channel.send(f"👋 Moderator has added {member.mention} to the team!")

    if voice_channel:
        await voice_channel.set_permissions(member, overwrite=overwrite)

    # Update Solo Status
    await update_solo_role(ctx.guild, member, has_team=True)

    # Update Dashboard
    await update_mod_dashboard(ctx.guild)
    await ctx.send(f"✅ Moderator has added **{member.display_name}** to **{team_name}**!", delete_after=5)

@bot.command()
async def togglecreation(ctx):
    """(Moderator Only) Toggles team creation on/off."""
    if "Moderator" not in [r.name for r in ctx.author.roles]:
        await ctx.send("You need the **Moderator** role to use this command.", delete_after=5)
        return

    global team_creation_enabled
    team_creation_enabled = not team_creation_enabled
    
    status = "ENABLED" if team_creation_enabled else "PAUSED"
    color = discord.Color.green() if team_creation_enabled else discord.Color.red()
    
    embed = discord.Embed(title="Team Creation Status", description=f"Team creation is now **{status}**.", color=color)
    await ctx.send(embed=embed)

@bot.command()
async def backup(ctx):
    """(Moderator Only) Uploads the current database files to Discord."""
    # Check for Moderator role
    if "Moderator" not in [r.name for r in ctx.author.roles]:
        await ctx.send("You need the **Moderator** role to use this command.", delete_after=5)
        return

    files_to_send = []
    if os.path.exists(TEAMS_FILE):
        files_to_send.append(discord.File(TEAMS_FILE))
    if os.path.exists(CLAIMED_FILE):
        files_to_send.append(discord.File(CLAIMED_FILE))

    if not files_to_send:
        await ctx.send("No database files found on the server.")
        return

    await ctx.send("📦 **System Backup**\nHere are the latest database files:", files=files_to_send)

@bot.command()
async def restore(ctx):
    """(Moderator Only) Upload a backup file (teams.json or claimed_ids.json) to restore data."""
    if "Moderator" not in [r.name for r in ctx.author.roles]:
        await ctx.send("You need the **Moderator** role to use this command.", delete_after=5)
        return

    if not ctx.message.attachments:
        await ctx.send("Please attach the backup file you want to restore.", delete_after=5)
        return

    attachment = ctx.message.attachments[0]
    
    if attachment.filename == "teams.json":
        await attachment.save(TEAMS_FILE)
        await update_mod_dashboard(ctx.guild)
        await ctx.send(f"✅ **Success!** `teams.json` has been restored. Teams are updated.")
    elif attachment.filename == "claimed_ids.json":
        await attachment.save(CLAIMED_FILE)
        global claimed_ids
        claimed_ids = load_claimed_ids()
        await ctx.send(f"✅ **Success!** `claimed_ids.json` has been restored. Verified users updated.")
    else:
        await ctx.send("❌ **Error:** Unknown file. Please upload `teams.json` or `claimed_ids.json`.", delete_after=5)

@bot.command()
async def scanteams(ctx):
    """(Moderator Only) Reconstructs teams.json by scanning existing channels and roles."""
    if "Moderator" not in [r.name for r in ctx.author.roles]:
        await ctx.send("You need the **Moderator** role to use this command.", delete_after=5)
        return

    status_msg = await ctx.send("🕵️ **Starting Team Scan...** This may take a while.")
    
    guild = ctx.guild
    teams = {} # Start fresh reconstruction
    
    # Categories to scan
    TARGET_CATEGORIES = ["valorant-team", "mlbb-team", "codm-team"]
    
    # Map category name to Game Name
    GAME_MAP = {
        "valorant-team": "valorant",
        "mlbb-team": "mlbb",
        "codm-team": "codm"
    }

    log_channel = discord.utils.get(guild.text_channels, name="mod-logs")
    restored_count = 0

    for cat_name in TARGET_CATEGORIES:
        # Find the category object (case-insensitive)
        category = discord.utils.find(lambda c: c.name.lower() == cat_name, guild.categories)
        if not category:
            continue

        game_name = GAME_MAP.get(cat_name, "unknown")

        # Scan text channels in this category
        for channel in category.text_channels:
            # Skip admin channels
            if channel.name == "mod-team":
                continue

            # 1. Find the Role matching the channel name
            # Logic: Channel "team-alpha" matches Role "Team Alpha"
            found_role = None
            for role in guild.roles:
                if role.name.replace(" ", "-").lower() == channel.name:
                    found_role = role
                    break
            
            if not found_role:
                continue

            # 2. Find Members
            member_ids = []
            for m in found_role.members:
                member_ids.append(str(m.id))
                # Ensure team members do not have the Solo role
                await update_solo_role(guild, m, has_team=True)

            # 3. Find Captain (First message mention)
            captain_id = None
            try:
                # Get the very first message in channel history
                async for msg in channel.history(limit=1, oldest_first=True):
                    if msg.mentions:
                        captain_id = str(msg.mentions[0].id)
                        break
            except:
                pass

            # Fallback: First member if history is empty/cleared
            if not captain_id and member_ids:
                captain_id = member_ids[0]
            
            if not captain_id:
                continue

            # 4. Find Voice Channel (Look for VC with same name as Role)
            voice_channel_id = None
            vc = discord.utils.find(lambda c: c.name == found_role.name and isinstance(c, discord.VoiceChannel), category.voice_channels)
            if vc:
                voice_channel_id = vc.id

            # 5. Build Data
            team_name = found_role.name
            teams[team_name] = {
                "game": game_name,
                "captain_id": captain_id,
                "members": member_ids,
                "text_channel_id": channel.id,
                "voice_channel_id": voice_channel_id,
                "role_id": found_role.id,
                "invites": [],
                "created_at": datetime.datetime.now().isoformat()
            }
            
            restored_count += 1
            
            # Log to mod-logs
            if log_channel:
                captain_user = guild.get_member(int(captain_id))
                cap_name = captain_user.display_name if captain_user else "Unknown"
                await log_channel.send(f"♻️ **System restored.** {captain_user.mention if captain_user else cap_name} is now Captain in team **{team_name}**.")

    save_teams(teams)
    await update_mod_dashboard(guild)
    await status_msg.edit(content=f"✅ **Scan Complete!** Restored {restored_count} teams.")

@bot.command()
async def scanclaims(ctx):
    """(Moderator Only) Reconstructs claimed_ids.json based on nicknames."""
    if "Moderator" not in [r.name for r in ctx.author.roles]:
        await ctx.send("You need the **Moderator** role to use this command.", delete_after=5)
        return

    status_msg = await ctx.send("🕵️ **Starting Claim Scan...** This attempts to link Verified users back to Student IDs based on their nickname.")
    
    # 1. Build a lookup map: Surname -> List of Student IDs
    surname_map = {}
    for sid, info in student_db.items():
        # Logic must match !verify nickname generation exactly
        surname = info['name'].split()[0].replace(',', '')
        if surname not in surname_map:
            surname_map[surname] = []
        surname_map[surname].append(sid)

    restored_count = 0
    ambiguous_count = 0
    not_found_count = 0
    
    verified_role = discord.utils.get(ctx.guild.roles, name="Verified")
    if not verified_role:
        await ctx.send("Error: 'Verified' role not found.")
        return

    for member in ctx.guild.members:
        if verified_role in member.roles:
            # Skip if this user is already linked in our database
            if str(member.id) in claimed_ids.values():
                continue

            nickname = member.display_name
            
            matches = surname_map.get(nickname)
            
            if matches and len(matches) == 1:
                # Unique match found!
                sid = matches[0]
                
                # Integrity check: Is this ID already claimed by someone else?
                if sid in claimed_ids:
                    continue
                    
                claimed_ids[sid] = str(member.id)
                restored_count += 1
            elif matches and len(matches) > 1:
                # Multiple students have this surname (e.g. "Santos")
                ambiguous_count += 1
            else:
                # Nickname doesn't match any student surname
                not_found_count += 1

    save_claimed_ids(claimed_ids)
    
    embed = discord.Embed(title="✅ Claim Scan Complete", color=discord.Color.green())
    embed.add_field(name="Restored", value=str(restored_count), inline=True)
    embed.add_field(name="Ambiguous (Skipped)", value=str(ambiguous_count), inline=True)
    embed.add_field(name="No Match (Skipped)", value=str(not_found_count), inline=True)
    embed.set_footer(text="Ambiguous users share a surname. They must re-verify manually.")
    
    await status_msg.edit(content=None, embed=embed)

@bot.command()
async def forceverify(ctx, member: discord.Member, student_id: str):
    """(Moderator Only) Manually verifies a user. Usage: !forceverify @User <StudentID>"""
    if "Moderator" not in [r.name for r in ctx.author.roles]:
        await ctx.send("You need the **Moderator** role to use this command.", delete_after=5)
        return

    success, msg = await perform_verification(ctx.guild, member, student_id, ctx.author)
    if success:
        await ctx.send(f"✅ {msg}", delete_after=5)
    else:
        await ctx.send(f"❌ {msg}", delete_after=5)

@bot.command()
async def fixunverified(ctx):
    """(Moderator Only) Auto-verifies users who are in a team but missing the Verified role."""
    if "Moderator" not in [r.name for r in ctx.author.roles]:
        await ctx.send("You need the **Moderator** role to use this command.", delete_after=5)
        return

    status_msg = await ctx.send("🕵️ **Scanning for unverified team members...**")

    # Build surname map for lookup (Nickname -> List of IDs)
    surname_map = {}
    for sid, info in student_db.items():
        surname = info['name'].split()[0].replace(',', '')
        if surname not in surname_map: surname_map[surname] = []
        surname_map[surname].append(sid)

    teams = load_teams()
    team_members = set()
    for t in teams.values():
        for m in t['members']:
            team_members.add(m)

    verified_role = discord.utils.get(ctx.guild.roles, name="Verified")
    fixed_count = 0
    failed_count = 0
    log_channel = discord.utils.get(ctx.guild.text_channels, name="mod-logs")

    for user_id in team_members:
        member = ctx.guild.get_member(int(user_id))
        if not member: continue
        
        # If they are in a team but NOT verified
        if verified_role not in member.roles:
            student_id = None
            
            # Strategy 1: Check if they already have a claimed ID (maybe role was just removed)
            for sid, uid in claimed_ids.items():
                if uid == user_id:
                    student_id = sid
                    break
            
            # Strategy 2: Try to match Nickname to Database
            if not student_id:
                nick = member.display_name
                matches = surname_map.get(nick)
                if matches and len(matches) == 1:
                    # Unique match found! Check if ID is free.
                    if matches[0] not in claimed_ids:
                         student_id = matches[0]

            if student_id:
                success, msg = await perform_verification(ctx.guild, member, student_id, ctx.author)
                if success:
                    fixed_count += 1
                else:
                    failed_count += 1
            else:
                # Log ambiguity so Mod can fix manually
                if log_channel:
                    await log_channel.send(f"⚠️ **Auto-Fix Failed:** {member.mention} is in a team but unverified. Could not determine Student ID automatically.")
                failed_count += 1

    await status_msg.edit(content=f"✅ **Fix Complete.**\nFixed: {fixed_count}\nFailed/Ambiguous: {failed_count}")

@bot.command()
async def gameroles(ctx, role1: str = None, role2: str = None):
    """Lists roles or assigns them (Max 2 per game). Usage: !gameroles [role1] [role2]"""
    
    # 1. If no argument, List Roles AND Current Status
    if not role1 and not role2:
        embed = discord.Embed(title="🎮 In-Game Roles Manager", description="Type `!gameroles <name>` to add/remove a role.\nYou can have up to **2 roles** per game.", color=discord.Color.purple())
        for game, roles in GAME_ROLES_CONFIG.items():
            # Get all available roles for this game
            role_list = ", ".join([f"`{r}`" for r in roles])
            
            # Get user's current roles for this game
            user_roles = []
            for r in ctx.author.roles:
                if r.name in roles:
                    user_roles.append(r.name)
            
            # Format user's roles with Primary/Secondary labels
            status_str = "None"
            if user_roles:
                formatted_roles = []
                for i, r_name in enumerate(user_roles):
                    label = "Primary" if i == 0 else "Secondary"
                    formatted_roles.append(f"**{r_name}** ({label})")
                status_str = ", ".join(formatted_roles)

            embed.add_field(name=f"{game} Roles", value=f"**Available:** {role_list}\n**Your Roles:** {status_str}", inline=False)
            
        await ctx.send(embed=embed)
        return

    # Collect inputs to process
    roles_to_process = []
    if role1: roles_to_process.append(role1)
    if role2: roles_to_process.append(role2)

    # Snapshot of roles to handle updates within the loop (avoids race conditions)
    current_member_roles = list(ctx.author.roles)

    for role_name in roles_to_process:
        # 2. Find which game(s) this role belongs to
        target_role_proper = None
        affected_games = []
        
        # First pass: find the proper casing of the role name
        for game, roles in GAME_ROLES_CONFIG.items():
            for r in roles:
                if r.lower() == role_name.lower():
                    target_role_proper = r
                    break
            if target_role_proper:
                break
        
        if not target_role_proper:
            await ctx.send(f"❌ Role **{role_name}** not found. Type `!gameroles` to see the list.", delete_after=5)
            continue

        # Second pass: Find ALL games this role belongs to (e.g. Flex is in MLBB and Valorant)
        for game, roles in GAME_ROLES_CONFIG.items():
            if target_role_proper in roles:
                affected_games.append(game)

        # 3. Ensure the role exists in the server
        guild = ctx.guild
        role_obj = discord.utils.get(guild.roles, name=target_role_proper)
        
        if not role_obj:
            try:
                role_obj = await guild.create_role(name=target_role_proper, mentionable=True)
                await ctx.send(f"⚙️ Created new role: **{target_role_proper}**")
            except discord.Forbidden:
                await ctx.send("Error: I don't have permission to create roles.", delete_after=5)
                continue

        # 4. Toggle Logic
        if role_obj in current_member_roles:
            # User has it -> Remove it
            await ctx.author.remove_roles(role_obj)
            current_member_roles.remove(role_obj) # Update local snapshot
            await ctx.send(f"➖ Removed **{target_role_proper}** from your roles.", delete_after=5)
            continue

        # 5. Check Limits for ALL affected games
        # If I add "Flex", I must not exceed limit in MLBB AND I must not exceed limit in Valorant.
        limit_reached = False
        for game in affected_games:
            game_roles_list = GAME_ROLES_CONFIG[game]
            current_game_roles = []
            for r in current_member_roles: # Check against local snapshot
                if r.name in game_roles_list:
                    current_game_roles.append(r)
            
            if len(current_game_roles) >= 2:
                await ctx.send(f"⚠️ Cannot add **{target_role_proper}**. You already have 2 roles for **{game}** ({', '.join([r.name for r in current_game_roles])}).", delete_after=10)
                limit_reached = True
                break
        
        if limit_reached:
            continue

        # 6. Add Role
        await ctx.author.add_roles(role_obj)
        current_member_roles.append(role_obj) # Update local snapshot
        
        # Calculate position for feedback (based on the first affected game found)
        primary_game = affected_games[0]
        game_roles_list = GAME_ROLES_CONFIG[primary_game]
        current_count = 0
        for r in current_member_roles:
            if r.name in game_roles_list:
                current_count += 1
                
        position = "Primary" if current_count == 1 else "Secondary"
        await ctx.send(f"✅ Added **{target_role_proper}** as your **{position}** role!", delete_after=5)

@bot.command()
async def help(ctx):
    """Shows a detailed guide of all available commands."""
    embed = discord.Embed(
        title="📘 Server Command Guide",
        description="Below is the detailed list of commands available. Please note the limits and requirements.",
        color=discord.Color.blue()
    )
    
    # General Commands
    embed.add_field(name="🔹 General Commands (Everyone)", value=(
        "**`!verify <Student Number>`**\n"
        "Links your Student ID to your Discord account.\n"
        "> **Limit:** Exclusive to `#verify` channel.\n"
        "> **Format:** `!verify 20XX-X-XXXXX`\n\n"
        
        "**`!gameroles [role1] [role2]`**\n"
        "Manage your in-game roles (e.g., Duelist, Roam).\n"
        "> **Limit:** Max **2 roles** per game (Primary & Secondary).\n"
        "> **Usage:** `!gameroles` (View list) or `!gameroles Duelist Sentinel`\n\n"
        
        "**`!teamstats`**\n"
        "View current tournament statistics (Total teams, players, free agents)."
    ), inline=False)

    # Team Management
    embed.add_field(name="🏆 Team Creation & Joining", value=(
        "**`!createteam <game> <name>`**\n"
        "Creates a new team with private text/voice channels.\n"
        "> **Limit:** You can only create/join **1 team** at a time.\n"
        "> **Requirement:** Must be Verified.\n"
        "> **Supported Games:** Valorant, MLBB, CODM.\n"
        "> **Example:** `!createteam valorant \"Team Eagles\"`\n\n"
        
        "**`!join <Team Name>`**\n"
        "Joins a team you have been invited to.\n"
        "> **Requirement:** Must have an active invite from the Captain.\n"
        "> **Example:** `!join \"Team Eagles\"`\n\n"
        
        "**`!leave`**\n"
        "Leaves your current team and returns you to Free Agent status.\n"
        "> **Restriction:** Captains cannot leave (must disband)."
    ), inline=False)

    # Captain Commands
    embed.add_field(name="👑 Captain Commands", value=(
        "**`!invite <User>` `!invite Paxton`**\n"
        "Sends an official invite to a player via DM.\n"
        "> **Limit:** Invitee must be Verified and not in a team.\n\n"
        
        "**`!kick <User>`**\n"
        "Removes a player from the team and revokes channel access.\n\n"
        
        "**`!disband`**\n"
        "**⚠️ Destructive:** Permanently deletes the team, role, and channels."
    ), inline=False)

    # Moderator Commands
    embed.add_field(name="🛡️ Moderator Tools", value=(
        "`!setteam <User> \"Team\"` - Manually assign user to team.\n"
        "`!forceverify <User> <ID>` - Manually verify a student.\n"
        "`!fixunverified` - Auto-fix unverified team members.\n"
        "`!togglecreation` - Pause/Resume team creation.\n"
        "`!syncsolo` - Fix 'Solo' roles for all users.\n"
        "`!backup` - Download database files.\n"
        "`!restore` - Upload database files to restore.\n"
        "`!scanteams` - Rebuild database from server channels.\n"
        "`!scanclaims` - Rebuild claimed IDs from nicknames."
    ), inline=False)

    embed.set_footer(text="Tip: Arguments with spaces must be wrapped in quotes (e.g. \"Team Name\").")

    await ctx.send(embed=embed)

# Run bot using token stored in environment variable
token = os.getenv("DISCORD_TOKEN")
if not token:
    print("Error: DISCORD_TOKEN environment variable not found.")
else:
    bot.run(token)