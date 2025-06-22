FROM rocker/r-ver:4.3.2

# Install dependencies
RUN apt-get update && apt-get install -y \
    libxml2-dev libcurl4-openssl-dev libssl-dev libgit2-dev && \
    apt-get clean

# Install remotes & worldfootballR from GitHub
RUN Rscript -e "install.packages('remotes', repos = 'https://cloud.r-project.org')" \
    && Rscript -e "remotes::install_github('JaseZiv/worldfootballR')"

# Copy your script into the container
COPY generate_player_names.R /usr/local/src/generate_player_names.R
WORKDIR /usr/local/src

# Default command to run your script
CMD ["Rscript", "generate_player_names.R"]
