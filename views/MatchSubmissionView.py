import discord

from .MatchReview import MatchReview


class MatchSubmissionView(discord.ui.View):
    def __init__(self, ctx, matches, players, division, mod, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(MatchSelect(ctx, matches, players, division, mod, bot))


class MatchSelect(discord.ui.Select):
    def __init__(self, ctx, matches, players, division, mod, bot):
        self.ctx = ctx
        self.matches = matches
        self.players = players
        self.division = division
        self.mod = mod
        self.bot = bot
        options = [discord.SelectOption(label=match[0]) for match in matches]
        super().__init__(placeholder="Select your match", options=options, custom_id="select_match")

    async def callback(self, interaction: discord.Interaction):
        match_id = ""
        for match in self.matches:
            if match[0] == self.values[0]:
                match_id = match[1]
        await interaction.response.edit_message(content="Select your opponent",
                                                view=OpponentView(self.ctx, self.players, [self.values[0], match_id],
                                                                  self.division, self.mod, self.bot))


class OpponentView(discord.ui.View):
    def __init__(self, ctx, players, match, division, mod, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(OpponentSelect(ctx, players, match, division, mod, bot))


class OpponentSelect(discord.ui.Select):
    def __init__(self, ctx, players, match, division, mod, bot):
        self.ctx = ctx
        self.players = players
        self.match = match
        self.division = division
        self.mod = mod
        self.bot = bot
        options = [discord.SelectOption(label=player.name) for player in players]
        super().__init__(placeholder="Select your opponent", options=options, custom_id="select_opp")

    async def callback(self, interaction: discord.Interaction):
        opp_id = ""
        for player in self.players:
            if player.name == self.values[0]:
                opp_id = player.id

        await interaction.response.edit_message(content="Select the score",
                                                view=ScoreView(self.ctx, self.match, [self.values[0], opp_id],
                                                               self.division, self.mod, self.bot))


class ScoreView(discord.ui.View):
    def __init__(self, ctx, match, opp, division, mod, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_item(ScoreSelect(ctx, match, opp, division, mod, bot))


class ScoreSelect(discord.ui.Select):
    def __init__(self, ctx, match, opp, division, mod, bot):
        self.ctx = ctx
        self.match = match
        self.opp = opp
        self.division = division
        self.mod = mod
        self.bot = bot
        options = [discord.SelectOption(label="2-1"), discord.SelectOption(label="2-0"),
                   discord.SelectOption(label="0-2"), discord.SelectOption(label="1-2")]
        super().__init__(placeholder="Select the score", options=options, custom_id="select_score")

    async def callback(self, interaction: discord.Interaction):
        modal = ReplayModal(self.ctx, self.match, self.opp, self.values[0], self.division, self.mod, self.bot,
                            interaction)
        await interaction.response.send_modal(modal)
        await interaction.edit_original_response(content="Please submit replay URLs", view=None)


class ReplayModal(discord.ui.Modal):
    def __init__(self, ctx, match, opp, score, division, mod, bot, interaction, *args, **kwargs):
        super().__init__(title="Submit Replay URLs", *args, **kwargs)
        self.ctx = ctx
        self.match = match
        self.opp = opp
        self.score = score
        self.division = division
        self.mod = mod
        self.bot = bot
        self.original_interaction = interaction

        self.add_item(discord.ui.InputText(label="Replay URL 1", required=False))
        self.add_item(discord.ui.InputText(label="Replay URL 2", required=False))
        self.add_item(discord.ui.InputText(label="Replay URL 3", required=False))

    async def callback(self, interaction: discord.Interaction):
        urls = [self.children[0].value, self.children[1].value, self.children[2].value]
        urls = [url for url in urls if url]
        msg = (f"You have selected:\n"
               f"Match: {self.match[0]}\n"
               f"Opponent: {self.opp[0]}\n"
               f"Score: {self.score}\n"
               f"Replays: {'\n'.join(urls)}\n"
               f"Confirm match submission?")
        await interaction.response.edit_message(content=msg,
                                                view=ConfirmationView(self.ctx, self.match, self.opp, self.score, urls,
                                                                      self.division, self.mod, self.bot))


class ConfirmationView(discord.ui.View):
    def __init__(self, ctx, match, opp, score, urls, division, mod, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ctx = ctx
        self.match = match
        self.opp = opp
        self.score = score
        self.urls = urls
        self.division = division
        self.moderator_channel = mod
        self.bot = bot

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_button(self, _: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.edit_message(content=f"Match submission sent!", view=None)
        view = MatchReview(self.ctx, self.match, self.opp, self.score, self.urls, self.division, self.bot)
        msg = (f"New match submission for {self.division} Ball division by <@{self.ctx.user.id}>\n"
               f"Opponent: {self.opp[0]}\n"
               f"Match: {self.match[0]}\n"
               f"Score: {self.score}\n"
               f"Replays: {'\n'.join(self.urls)}\n")
        await self.moderator_channel.send(msg, view=view)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject_button(self, _: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.edit_message(content=f"Match submission rejected!", view=None)
