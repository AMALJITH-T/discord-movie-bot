import discord
from discord.ext import commands
from discord import app_commands
import requests
from config import DISCORD_TOKEN, TMDB_API_KEY

GENRE_MAP = {
    "Action": 28,
    "Comedy": 35,
    "Drama": 18,
    "Fantasy": 14,
    "Horror": 27,
    "Romance": 10749,
    "Sci-Fi": 878,
    "Thriller": 53,
    "Animation": 16,
    "Crime": 80
}

LANGUAGE_CODES = {
    "English": "en",
    "Hindi": "hi",
    "Japanese": "ja",
    "French": "fr",
    "Korean": "ko"
}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

user_saved_movies = {}  # user_id: [movie_title, ...]

class GenreDropdown(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=g, value=g) for g in GENRE_MAP.keys()]
        super().__init__(placeholder="Pick a genre", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_genre = self.values[0]
        await interaction.response.send_modal(MovieForm(genre=selected_genre))

class GenreDropdownView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(GenreDropdown())

class MovieForm(discord.ui.Modal, title="🎬 Movie Preferences"):
    def __init__(self, genre):
        super().__init__()
        self.genre_val = genre

    year_range = discord.ui.TextInput(label="Year Range", placeholder="e.g. 2010-2022", required=True)
    rating = discord.ui.TextInput(label="Min Rating", placeholder="e.g. 7.0", required=True)
    language = discord.ui.TextInput(label="Language", placeholder="e.g. English", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            filters = {
                "genre": self.genre_val,
                "year_from": self.year_range.value.strip().split("-")[0],
                "year_to": self.year_range.value.strip().split("-")[1],
                "rating": float(self.rating.value.strip()),
                "language": LANGUAGE_CODES.get(self.language.value.strip(), "en")
            }
            await send_movie_recommendations(interaction, filters)
        except Exception as e:
            await interaction.followup.send(f"❌ Something went wrong: {e}", ephemeral=True)

def fetch_movies(filters):
    genre_id = GENRE_MAP.get(filters["genre"])
    exclude_genres = "16,10751,14" if filters["genre"] == "Horror" else ""

    url = "https://api.themoviedb.org/3/discover/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "with_genres": genre_id,
        "without_genres": exclude_genres,
        "sort_by": "vote_average.desc",
        "vote_count.gte": 50,
        "vote_average.gte": filters["rating"],
        "primary_release_date.gte": f"{filters['year_from']}-01-01",
        "primary_release_date.lte": f"{filters['year_to']}-12-31",
        "language": filters["language"],
        "page": 1
    }

    res = requests.get(url, params=params)
    if res.status_code != 200:
        return []

    return res.json().get("results", [])[:5]

def get_streaming_info(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
    res = requests.get(url, params={"api_key": TMDB_API_KEY})
    if res.status_code != 200:
        return "❌ No info"
    providers = res.json().get("results", {}).get("US", {}).get("flatrate", [])
    return ", ".join([p["provider_name"] for p in providers]) if providers else "Not available"

class SaveButton(discord.ui.Button):
    def __init__(self, movie_title):
        super().__init__(label="💾 Save for Later", style=discord.ButtonStyle.success)
        self.movie_title = movie_title

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id not in user_saved_movies:
            user_saved_movies[user_id] = []
        user_saved_movies[user_id].append(self.movie_title)
        await interaction.response.send_message(f"✅ Saved **{self.movie_title}** to your list!", ephemeral=True)

async def send_movie_recommendations(interaction, filters):
    movies = fetch_movies(filters)
    if not movies:
        await interaction.followup.send("😢 No movies found with your filters.", ephemeral=True)
        return

    for movie in movies:
        title = movie.get("title")
        rating = movie.get("vote_average")
        overview = movie.get("overview", "")[:300]
        poster_path = movie.get("poster_path")
        movie_id = movie.get("id")
        platforms = get_streaming_info(movie_id)

        embed = discord.Embed(
            title=f"🎬 {title}",
            description=f"⭐ {rating}/10\n\n{overview}...",
            color=discord.Color.purple()
        )
        embed.add_field(name="Platforms", value=platforms, inline=True)
        embed.add_field(name="Language", value=filters["language"].title(), inline=True)
        if poster_path:
            embed.set_image(url=f"https://image.tmdb.org/t/p/w500{poster_path}")

        view = discord.ui.View()
        view.add_item(SaveButton(title))

        await interaction.followup.send(embed=embed, view=view, ephemeral=False)

@tree.command(name="recommend", description="🎯 Get movie recommendations!")
async def recommend(interaction: discord.Interaction):
    await interaction.response.send_message("🎬 Pick your preferred genre:", view=GenreDropdownView(), ephemeral=True)

@tree.command(name="saved", description="📂 View your saved movies")
async def saved(interaction: discord.Interaction):
    user_id = interaction.user.id
    saved = user_saved_movies.get(user_id, [])
    if not saved:
        await interaction.response.send_message("❌ You haven’t saved any movies yet.", ephemeral=True)
        return

    saved_list = "\n".join([f"• {title}" for title in saved])
    await interaction.response.send_message(f"📂 **Your Saved Movies:**\n\n{saved_list}", ephemeral=True)

@tree.command(name="clear_saved", description="🗑️ Clear your saved movie list")
async def clear_saved(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id in user_saved_movies and user_saved_movies[user_id]:
        user_saved_movies[user_id] = []
        await interaction.response.send_message("🧹 Your saved list has been cleared!", ephemeral=True)
    else:
        await interaction.response.send_message("📂 You don't have any saved movies yet.", ephemeral=True)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"{bot.user} is online!")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
