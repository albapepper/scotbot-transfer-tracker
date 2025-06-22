# Set a custom library path
lib_path <- Sys.getenv("R_LIBS_USER")
if (!dir.exists(lib_path)) dir.create(lib_path, recursive = TRUE)

# Install remotes and use it to install worldfootballR
install.packages("remotes", repos = "http://cran.us.r-project.org", lib = lib_path)
remotes::install_github("JaseZiv/worldfootballR", lib = lib_path)

# Install other dependencies
install.packages(c("dplyr", "readr", "purrr"), repos = "http://cran.us.r-project.org", lib = lib_path)

# Load libraries from the custom path
library(worldfootballR, lib.loc = lib_path)
library(dplyr, lib.loc = lib_path)
library(readr, lib.loc = lib_path)

# Generate player list
leagues <- c("ENG-Premier League", "ESP-La Liga", "GER-Bundesliga", "ITA-Serie A", "FRA-Ligue 1")
season <- 2024

players <- purrr::map_df(leagues, ~ fb_teams(.x, season_end_year = season) %>%
  pull(Squad_url) %>%
  purrr::map_df(~ fb_player_squad_stats(.x, stat_type = "standard")))

player_names <- unique(players$Player)
write_lines(player_names, "player_names.txt")
