# Apple Music MCP

A [Model Context Protocol](https://modelcontextprotocol.io/) server that lets Claude control your Apple Music library — search songs, create playlists, import from Spotify or setlist.fm, and more.

## What it does

- **Search** for songs in the Apple Music catalog
- **Create, rename, and delete** playlists
- **Add songs** to playlists
- **Get your playlists and folders**, move playlists into folders
- **Import from Spotify** — paste a Spotify playlist URL and it recreates it in Apple Music
- **Import from setlist.fm** — paste a setlist URL and it builds the playlist from the concert setlist

## How it works

The server uses [Playwright](https://playwright.dev/python/) to drive a headless Chromium browser authenticated as you on `music.apple.com`. It calls MusicKit JS APIs directly from within the page, just like the web player does — no Apple Developer account or API keys needed.

For Spotify imports, it intercepts the Spotify GraphQL API responses to extract track listings, then searches Apple Music for each song.

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A valid Apple Music subscription

### Install

```bash
git clone https://github.com/davenadkarni/apple-music-mcp.git
cd apple-music-mcp
uv sync
uv run playwright install chromium
```

### Authorize

Run this once to sign into Apple Music and save your browser session:

```bash
uv run python auth.py
```

A browser window will open. Sign into Apple Music, then press Enter in the terminal. Your session is saved to `~/.config/apple-music-mcp/browser_state.json` and never committed to git.

### Configure Claude Code

Add to your `claude_desktop_config.json` (or Claude Code MCP settings):

```json
{
  "mcpServers": {
    "apple-music": {
      "command": "uv",
      "args": ["run", "python", "server.py"],
      "cwd": "/path/to/apple-music-mcp"
    }
  }
}
```

Then restart Claude Code.

## Available tools

| Tool | Description |
|------|-------------|
| `search_songs` | Search the Apple Music catalog |
| `get_my_playlists` | List all your library playlists |
| `get_folders` | List your playlist folders |
| `create_playlist` | Create a new playlist |
| `rename_playlist` | Rename a playlist |
| `delete_playlist` | Delete a playlist |
| `get_playlist_tracks` | Get the tracks in a playlist |
| `add_songs_to_playlist` | Add songs to a playlist by search query |
| `move_playlists_to_folder` | Move playlists into a folder |
| `import_from_spotify` | Import a Spotify playlist by URL |
| `import_from_setlistfm` | Import a concert setlist from setlist.fm by URL |
| `set_playlist_artwork` | Attempt to set playlist artwork *(experimental — Apple's web API does not officially support this)* |

## Notes

- **Rate limiting**: Apple Music search has a per-session rate limit. Large imports (500+ songs) may hit it; the server will report how many songs were successfully matched.
- **Session expiry**: If tools stop working, re-run `auth.py` to refresh your browser session.
- **Spotify matching**: Track matching uses fuzzy search — remaster/edition suffixes are stripped automatically. Expect ~90–95% match rates on typical playlists.
- **`move_playlists_to_folder` — UI refresh**: The tool works correctly, but occasionally the Apple Music web player sidebar won't update immediately. If a playlist doesn't appear in the folder right away, try dragging any one playlist manually in the Music desktop app to trigger a sync.

## Security

`browser_state.json` contains your Apple Music session cookies. It is excluded from git via `.gitignore` and stored only at `~/.config/apple-music-mcp/browser_state.json` on your machine.
