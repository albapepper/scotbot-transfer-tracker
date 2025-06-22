# Install remotes if needed and then worldfootballR from GitHub
if (!require("remotes")) install.packages("remotes", repos = "https://cloud.r-project.org")
remotes::install_github("JaseZiv/worldfootballR")

library(worldfootballR)

# Get all league URLs for the 2023-24 season
leagues <- fb_league_urls(season_end_year = 2024)

# Filter out cups and international tournaments
leagues <- leagues[!grepl("Champions-League|Europa|World-Cup|UEFA-Nations|Friendlies|CONCACAF|Copa", leagues)]

all_squads <- list()

# Loop through each league and scrape player stats
for (url in leagues) {
  cat("🔍 Scraping:", url, "\n")
  try({
    team_urls <- fb_teams_urls(url)
    league_squads <- lapply(team_urls, fb_team_player_stats, stat_type = "standard")
    all_squads <- c(all_squads, league_squads)
  }, silent = TRUE)
}

# Merge and extract player names
combined <- do.call(rbind, all_squads)
player_names <- sort(unique(combined$Player))

# Save to file
writeLines(player_names, "player_names.txt")
cat("✅ Saved", length(player_names), "unique player names to player_names.txt\n")
