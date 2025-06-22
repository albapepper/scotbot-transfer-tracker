user_lib <- Sys.getenv("R_LIBS_USER")
if (!dir.exists(user_lib)) dir.create(user_lib, recursive = TRUE)
install.packages("worldfootballR", lib = user_lib, repos = "https://cloud.r-project.org")
library(worldfootballR, lib.loc = user_lib)

league_url <- "https://fbref.com/en/comps/9/Premier-League-Stats"
teams <- fb_teams_urls(league_url)
squads <- lapply(teams, fb_team_player_stats, stat_type = "standard")
combined <- do.call(rbind, squads)

players <- sort(unique(combined$Player))
writeLines(players, "player_names.txt")
cat("✅ Saved", length(players), "players to player_names.txt\n")
