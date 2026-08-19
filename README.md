# yt-synchro

CLI tool that downloads YouTube playlist videos to a local folder, managing storage limits and auto-cleaning old content.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [ffmpeg](https://ffmpeg.org/) (for metadata embedding)
- [QuickJS](https://bellard.org/quickjs/) (JavaScript runtime for yt-dlp)

## Setup

### 1. Install system dependencies

**Debian/Ubuntu:**
```bash
sudo apt install quickjs ffmpeg
```

**Arch Linux:**
```bash
sudo pacman -S quickjs ffmpeg
```

### 2. Install yt-synchro

```bash
git clone <repo-url> && cd yt-synchro

# Create virtual environment and install dependencies
uv venv
uv sync
```

This creates a `.venv/` directory and installs all Python dependencies.

### 3. Configure yt-dlp

yt-dlp requires a JavaScript runtime to solve YouTube's anti-bot challenges. Create the config file:

```bash
mkdir -p ~/.config/yt-dlp
cat << EOF > ~/.config/yt-dlp/config 
--js-runtimes quickjs:/usr/bin/qjs
--remote-components ejs:github
EOF
```

### 4. Verify installation

```bash
uv run yt-synchro --help
```

## Usage

```bash
# One-shot download
uv run yt-synchro run --playlist URL --max-storage 50GB --max-videos 20

# Continuous daemon
uv run yt-synchro daemon --playlist URL

# Show status
uv run yt-synchro status

# List downloaded videos
uv run yt-synchro list
```

## Configuration

Config file: `~/.config/yt-synchro/config.toml`

Auto-created with defaults on first run. CLI flags override config values.

| Setting | Default | Description |
|---------|---------|-------------|
| `playlist_url` | `""` | YouTube playlist URL |
| `output_dir` | `~/Downloads/yt-synchro` | Download directory |
| `max_storage_gb` | `50.0` | Max disk usage in GB |
| `max_videos` | `20` | Max videos on disk |
| `parallel` | `3` | Max concurrent downloads |
| `quality` | `1080p` | Video quality |
| `daemon_interval_minutes` | `60` | Daemon check interval |
| `video_max_age_days` | `14` | Auto-delete videos older than this |

## Clean Build

To rebuild the package from scratch:

```bash
# Remove build artifacts
rm -rf build dist *.egg-info
find . -type d -name __pycache__ -exec rm -rf {} +

# Rebuild
uv build
```

The built wheel and sdist will be in `dist/`.

## Troubleshooting

### 403 Forbidden errors

If downloads fail with HTTP 403:

1. Verify yt-dlp config exists to enable Javascript runtime via QuickJS:
   ```bash
   cat ~/.config/yt-dlp/config
   ```

2. Test yt-dlp directly:
   ```bash
   uv run yt-dlp --verbose "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
   ```

3. Update yt-dlp:
   ```bash
   uv lock --upgrade && uv sync
   ```

# AI Disclosure

This codebase is entirely vibe coded with the sole goal of getting the job done.
Do not expect it to be secure or durable. Use at your own risk.
