import discord
from discord.ui import Button


class PaginationView(discord.ui.View):
    def __init__(self, data, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data = data
        self.current_page = 0
        self.max_items_per_page = 20  # Adjust based on your embed size limits
        self.total_pages = len(self.data) // self.max_items_per_page + (
            1 if len(self.data) % self.max_items_per_page > 0 else 0)

        # Previous page button
        self.previous_page_button = Button(label="<< Previous", style=discord.ButtonStyle.primary)
        self.previous_page_button.callback = self.previous_page
        self.add_item(self.previous_page_button)

        # Next page button
        self.next_page_button = Button(label="Next >>", style=discord.ButtonStyle.primary)
        self.next_page_button.callback = self.next_page
        self.add_item(self.next_page_button)

        self.update_buttons()

    async def previous_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.generate_embed(), view=self)
            self.update_buttons()

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.generate_embed(), view=self)
            self.update_buttons()

    def generate_embed(self):
        start_index = self.current_page * self.max_items_per_page
        end_index = start_index + self.max_items_per_page
        page_data = self.data[start_index:end_index]

        embed = discord.Embed(title="Registered Players", description="All players and their ELO", color=0x00ff00)
        for player in page_data:
            embed.add_field(name=f"{player[0]} - ELO: {player[1]}", value="\u200b", inline=False)

        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages}")
        return embed

    def update_buttons(self):
        self.previous_page_button.disabled = self.current_page == 0
        self.next_page_button.disabled = self.current_page == self.total_pages - 1
