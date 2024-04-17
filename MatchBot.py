import discord
from discord.ext import tasks, commands
import discord.ui
import aiosqlite
from views import MatchSubmissionView, PaginationView
from MatchManager import MatchManager

description = """
This bot processes match submissions for a Pokémon Draft server called SCDA
"""

MODERATOR_CHANNEL_ID = 123456789 # insert own channel ids
LEADERBOARD_CHANNEL_ID = 123456789


class MatchBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(command_prefix="!", description=description, intents=discord.Intents.all(), *args, **kwargs)

        self.match_manager = MatchManager()

    @staticmethod
    async def setup_database():
        """
        Asynchronously sets up the database for the bot.
        This function creates a table for players if it doesn't exist, with columns for Discord ID and ELO score.
        """
        async with aiosqlite.connect('elo.db') as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS players (discord_id TEXT PRIMARY KEY, elo INTEGER, division 
            TEXT DEFAULT NULL)''')
            await db.commit()
            print("Finished setting up database")

    @staticmethod
    async def get_top_players():
        """
        Retrieves the top 20 players sorted by ELO score in descending order.

        Returns:
            list: A list of tuples containing the player's Discord ID and their ELO score.
        """
        async with aiosqlite.connect("elo.db") as db:
            async with db.execute('SELECT * FROM players ORDER BY elo DESC LIMIT 20') as cursor:
                return await cursor.fetchall()

    @staticmethod
    async def get_all_players():
        async with aiosqlite.connect('elo.db') as db:
            async with db.execute('SELECT discord_id, elo FROM players ORDER BY elo DESC') as cursor:
                return await cursor.fetchall()

    async def fetch_players_in_division(self, division):
        async with aiosqlite.connect('elo.db') as db:
            cursor = await db.execute("SELECT discord_id FROM players WHERE division = ?", (division,))
            players = await cursor.fetchall()

        users = []
        for player in players:
            user = await self.fetch_user(int(player[0]))
            users.append(user)
        return users

    async def process_match_result(self, ctx, match, opp, score, urls, division):
        await self.match_manager.update_match_result(match[1], score, urls)
        await self.update_elo(ctx, opp, score, division)

    async def update_elo(self, ctx, opp, score, division):
        async with aiosqlite.connect("elo.db") as db:
            cursor = await db.execute("SELECT elo FROM players WHERE discord_id IN (?, ?)", (ctx.user.id, opp[1]))
            elos = await cursor.fetchall()
            player1_elo, player2_elo = elos[0][0], elos[1][0]

            # Determine match result (1 win, 0 loss)
            scores = score.split("-")
            result_team1 = 1 if int(scores[0]) > int(scores[1]) else 0
            result_team2 = 1 - result_team1

            # Calculate new ELOs
            new_elo1 = self.calculate_elo_change(player1_elo, player2_elo, result_team1, division)
            new_elo2 = self.calculate_elo_change(player2_elo, player1_elo, result_team2, division)

            # Update ELOs in the database
            await db.execute("UPDATE players SET elo=? WHERE discord_id=?", (new_elo1, ctx.user.id))
            await db.execute("UPDATE players SET elo=? WHERE discord_id=?", (new_elo2, opp[1]))
            await db.commit()

    @staticmethod
    def calculate_elo_change(current_elo, opponent_elo, result, division):
        k = 32 if division == "Poke" else 16 if division == "Ultra" else 24
        expected_score = 1 / (1 + 10 ** ((opponent_elo - current_elo) / 400))
        new_elo = current_elo + k * (result - expected_score)
        return new_elo


bot = MatchBot()


@tasks.loop(hours=24)
async def update_leaderboard():
    """
    A scheduled task that updates the leaderboard every 24 hours.
    Fetches the top players, constructs an embed with their rankings, and posts or updates it in the leaderboard channel
    """
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    top_players = await bot.get_top_players()
    embed = discord.Embed(title="🏆 Top 20 Players 🏆", description="ELO Leaderboard", color=0x1E90FF)
    leaderboard_lines = []

    for index, player in enumerate(top_players):
        user = await bot.fetch_user(int(player[0]))
        rank_emoji = "🌟" if index == 0 else "⭐" if index == 1 else "✨" if index == 2 else "🔹"
        leaderboard_lines.append(f"{rank_emoji} {index + 1}. {user.name} - {player[1]}")

    embed.add_field(name="Rankings", value="\n".join(leaderboard_lines), inline=False)
    embed.set_footer(text="Updated every 24 hours")
    messages = await channel.history(limit=10).flatten()
    if messages:
        await messages[0].edit(embed=embed)
    else:
        await channel.send(embed=embed)


@bot.event
async def on_ready():
    """Indicates the bot has successfully logged in and is ready."""
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")
    await bot.setup_database()
    await bot.match_manager.setup_match_database()
    update_leaderboard.start()


@bot.slash_command(name="player_card", description="Displays your SCDA Player Card.")
@discord.default_permissions()
async def player_card(ctx: discord.ApplicationContext):
    """
    A slash command that allows users to query their current ELO score.
    Responds with an ephemeral message displaying the user's ELO score, ensuring privacy.
    """
    async with aiosqlite.connect('elo.db') as db:
        async with db.execute('SELECT elo, division FROM players WHERE discord_id = ?',
                              (str(ctx.author.id),)) as cursor:
            player = await cursor.fetchone()
            if player:
                embed = discord.Embed(title=f"{ctx.author.display_name}'s Player Card",
                                      description="Here are your current ELO and Division in the league:",
                                      color=discord.Color.gold())  # You can change the color to match your theme
                embed.add_field(name="ELO Score", value=f"**{player[0]}**", inline=True)
                embed.add_field(name="Division", value=f"**{player[1]}**", inline=True)
                embed.set_thumbnail(url=ctx.author.avatar.url)
                embed.set_footer(text="Silph Co. Draft Association")
                await ctx.respond(embed=embed, ephemeral=True)
            else:
                await ctx.respond("You are not registered.", ephemeral=True)


@bot.slash_command(name="all_players", description="Shows all registered players and their ELO.")
@commands.has_permissions(administrator=True)
@discord.default_permissions()
async def all_players(ctx: discord.ApplicationContext):
    players_data = await bot.get_all_players()
    formatted_data = []

    for player_id, elo in players_data:
        user = await bot.fetch_user(int(player_id))
        formatted_data.append((user.name, elo))  # Replace ID with username

    if formatted_data:
        view = PaginationView(formatted_data)
        await ctx.respond(embed=view.generate_embed(), view=view, ephemeral=False)
    else:
        await ctx.respond("No registered players found.", ephemeral=True)


@bot.slash_command(description="Register a player and initialize their ELO score.")
@discord.default_permissions()
async def register(ctx: discord.ApplicationContext):
    """
    Registers the user in the database with an initial ELO score of 1200.
    If the user is already registered, it informs them without making any changes.
    """
    async with aiosqlite.connect('elo.db') as db:
        discord_id = str(ctx.author.id)
        async with db.execute('SELECT * FROM players WHERE discord_id = ?', (discord_id,)) as cursor:
            if await cursor.fetchone():
                await ctx.respond("You are already registered.", ephemeral=True)
            else:
                await db.execute('INSERT INTO players (discord_id, elo) VALUES (?, ?)', (discord_id, 1200))
                await db.commit()
                await ctx.respond("You have been registered with an initial ELO of 1200. Being sorted into a skill "
                                  "dependent division will add or subtract a small amount.", ephemeral=True)


@bot.slash_command(description="Assign player(s) to a division")
@commands.has_permissions(administrator=True)
@discord.default_permissions()
async def assign_division(
    ctx: discord.ApplicationContext,
    player_ids: str,  # Player IDs as a comma-separated string
    division: discord.Option(str, "Select a division", choices=["Ultra", "Poke", "Premier", "Test"])
):
    ids = player_ids.split(',')  # Split the string into individual IDs
    async with aiosqlite.connect('elo.db') as db:
        for player_id in ids:
            # Trim whitespace and update each player's division
            await db.execute('UPDATE players SET division = ? WHERE discord_id = ?', (division, player_id.strip()))
        await db.commit()
    await ctx.respond(f"Assigned players to division {division}.", ephemeral=True)


@bot.slash_command(description="Start the season by adding matches for all divisions to the database and updating the "
                               "sheet.")
@commands.has_permissions(administrator=True)
@discord.default_permissions()
async def start_season(ctx: discord.ApplicationContext):
    divisions = ["Ultra", "Poke", "Premier", "Test"]
    for division in divisions:
        await bot.match_manager.add_matches_for_division(division)

    await bot.match_manager.write_matches_to_sheet()
    await ctx.respond("All matches are now added to the database.", ephemeral=True)


@bot.slash_command(description="Submit your match result")
@discord.default_permissions()
async def submit_match(ctx: discord.ApplicationContext,
                       division: discord.Option(str, "Choose your division",
                                                choices=["Ultra", "Poke", "Premier", "Test"])):
    matches = await bot.match_manager.fetch_unplayed_matches(division)  # Fetch unplayed matches for the division
    matches = bot.match_manager.filter_matches(matches)
    players = await bot.fetch_players_in_division(division)
    if matches:
        # Create and send the match selection view
        mod = bot.get_channel(MODERATOR_CHANNEL_ID)
        await ctx.respond("Select your match:", view=MatchSubmissionView(ctx, matches, players, division, mod, bot),
                          ephemeral=True)
    else:
        await ctx.respond("No unplayed matches found in this division.", ephemeral=True)


@bot.slash_command(name="info", description="Displays help information for available commands.")
@discord.default_permissions()
async def info(ctx: discord.ApplicationContext):
    embed = discord.Embed(title="Bot Commands Help", description="List of available commands:",
                          color=discord.Color.blue())
    embed.add_field(name="/player_card", value="Displays your current ELO rating and division.", inline=False)
    embed.add_field(name="/register", value="Register a new player in the database.", inline=False)
    embed.add_field(name="/submit_match", value="Walks player through match submission steps.", inline=False)
    await ctx.respond(embed=embed, ephemeral=True)


bot.run(BOT_TOKEN)
