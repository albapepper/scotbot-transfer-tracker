# Install worldfootballR if not already installed
if (!require("worldfootballR")) install.packages("worldfootballR", repos = "http://cran.us.r-project.org")

library(worldfootballR)

# Example: Get all players from the English Premier League 2023/24 season
league_url <- "https://fbref.com/en/comps/9/Premier-League-Stats"
squad_data <- fb_teams_urls(league_url) |>
  lapply(fb_team_player_stats, stat_type = "standard") |>
  do.call(rbind, _)

# Extract unique player names
player_names <- sort(unique(squad_data$Player))

# Save to file
writeLines(player_names, "player_names.txt")
cat("✅ Saved", length(player_names), "unique player names to player_names.txt\n")
