# generate_player_list.R
library(worldfootballR)
library(dplyr)
library(readr)

# Example: Get all players from the Big 5 leagues for the current season
leagues <- c("ENG-Premier League", "ESP-La Liga", "GER-Bundesliga", "ITA-Serie A", "FRA-Ligue 1")
season <- 2024

players <- purrr::map_df(leagues, ~ fb_teams(.x, season_end_year = season) %>%
  pull(Squad_url) %>%
  purrr::map_df(~ fb_player_squad_stats(.x, stat_type = "standard")))

# Extract and save unique player names
player_names <- unique(players$Player)
write_lines(player_names, "player_names.txt")
