import base64
import json
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from mcp.server.fastmcp import FastMCP

PROJECT = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(PROJECT, "browser_worker.py")
UV = shutil.which("uv") or "uv"
mcp = FastMCP("Apple Music")


def run_in_browser(js: str, arg=None, url: str = None, no_musickit: bool = False,
                   capture_responses: str = None):
    """Run JS in a browser subprocess.

    url:               navigate here before evaluating (default: music.apple.com).
    no_musickit:       if True, skip the MusicKit auth wait.
    arg:               passed as 2nd argument to page.evaluate.
    capture_responses: URL substring — matching JSON responses are collected and
                       returned as result["captured"] alongside result["js_result"].
    """
    if arg is not None or url or no_musickit or capture_responses:
        payload: dict = {"js": js}
        if arg is not None:
            payload["arg"] = arg
        if url:
            payload["url"] = url
        if no_musickit:
            payload["no_musickit"] = True
        if capture_responses:
            payload["capture_responses"] = capture_responses
        input_data = json.dumps(payload).encode()
    else:
        input_data = js.encode()

    result = subprocess.run(
        [UV, "run", "--project", PROJECT, "python", WORKER],
        input=input_data,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return json.loads(result.stdout.decode("utf-8", errors="replace"))


@mcp.tool()
def search_songs(query: str, limit: int = 10) -> str:
    """Search the Apple Music streaming catalog for songs."""
    result = run_in_browser(f"""
        async () => {{
            const mk = MusicKit.getInstance();
            const sf = mk.storefrontId || 'us';
            const term = encodeURIComponent({json.dumps(query)});
            const res = await mk.api.get('/v1/catalog/' + sf + '/search?term=' + term + '&types=songs&limit={limit}');
            const songs = res.json && res.json.results && res.json.results.songs && res.json.results.songs.data || [];
            return songs.map(s => ({{
                id: s.id,
                name: s.attributes.name,
                artist: s.attributes.artistName,
                album: s.attributes.albumName,
            }}));
        }}
    """)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_playlist(name: str, songs: list[str], description: str = "", folder_id: str = "") -> str:
    """
    Create an Apple Music playlist from the streaming catalog.
    songs: list of song names, e.g. ["Bohemian Rhapsody by Queen", "Hotel California by Eagles"]
    folder_id: optional folder ID to create the playlist inside a folder
    """
    folder_id_js = json.dumps(folder_id)
    result = run_in_browser(f"""
        async () => {{
            const mk = MusicKit.getInstance();
            const sf = mk.storefrontId || 'us';
            const songQueries = {json.dumps(songs)};
            const added = [];
            const notFound = [];
            const trackIds = [];

            for (const query of songQueries) {{
                try {{
                    const term = encodeURIComponent(query);
                    const res = await mk.api.get('/v1/catalog/' + sf + '/search?term=' + term + '&types=songs&limit=1');
                    const matches = res.json && res.json.results && res.json.results.songs && res.json.results.songs.data || [];
                    if (matches.length > 0) {{
                        trackIds.push(matches[0].id);
                        added.push(matches[0].attributes.name + ' — ' + matches[0].attributes.artistName);
                    }} else {{
                        notFound.push(query);
                    }}
                }} catch(e) {{
                    notFound.push(query + ' (error: ' + e.message + ')');
                }}
            }}

            const folderId = {folder_id_js};
            const body = {{
                attributes: {{ name: {json.dumps(name)}, description: {json.dumps(description)} }},
                relationships: {{
                    tracks: {{ data: trackIds.map(id => ({{ id, type: 'songs' }})) }},
                    ...(folderId ? {{ parent: {{ data: [{{ id: folderId, type: 'library-playlist-folders' }}] }} }} : {{}})
                }}
            }};

            const playlist = await mk.api.post('/v1/me/library/playlists', {{
                body: JSON.stringify(body)
            }});

            const pid = playlist.json && playlist.json.data && playlist.json.data[0] && playlist.json.data[0].id;
            return {{
                playlist: {json.dumps(name)},
                id: pid,
                added,
                notFound,
                folder_id: folderId || null,
                message: 'Playlist created with ' + added.length + ' song(s).' + (folderId ? ' (in folder)' : '')
            }};
        }}
    """)
    return json.dumps(result, indent=2)


@mcp.tool()
def add_songs_to_playlist(playlist_id: str, songs: list[str]) -> str:
    """Add songs by name to an existing Apple Music playlist by playlist ID."""
    result = run_in_browser(f"""
        async () => {{
            const mk = MusicKit.getInstance();
            const sf = mk.storefrontId || 'us';
            const songQueries = {json.dumps(songs)};
            const added = [];
            const notFound = [];
            const trackIds = [];

            for (const query of songQueries) {{
                const term = encodeURIComponent(query);
                const res = await mk.api.get('/v1/catalog/' + sf + '/search?term=' + term + '&types=songs&limit=1');
                const matches = res.json && res.json.results && res.json.results.songs && res.json.results.songs.data || [];
                if (matches.length > 0) {{
                    trackIds.push(matches[0].id);
                    added.push(matches[0].attributes.name + ' — ' + matches[0].attributes.artistName);
                }} else {{
                    notFound.push(query);
                }}
            }}

            try {{
                await mk.api.post('/v1/me/library/playlists/{playlist_id}/tracks', {{
                    body: JSON.stringify({{ data: trackIds.map(id => ({{ id, type: 'songs' }})) }})
                }});
            }} catch(e) {{
                if (!e.message.includes('Unexpected end of JSON')) throw e;
            }}

            return {{ added, notFound, message: 'Added ' + added.length + ' song(s).' }};
        }}
    """)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_my_playlists() -> str:
    """List playlists in your Apple Music library."""
    result = run_in_browser("""
        async () => {
            const mk = MusicKit.getInstance();
            const res = await mk.api.get('/v1/me/library/playlists?limit=100');
            const playlists = res.json && res.json.data || [];
            return playlists.map(p => ({
                id: p.id,
                name: p.attributes.name,
            }));
        }
    """)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_playlist_tracks(playlist_id: str) -> str:
    """Get all tracks in an Apple Music library playlist by playlist ID."""
    result = run_in_browser(f"""
        async () => {{
            const mk = MusicKit.getInstance();
            const res = await mk.api.get('/v1/me/library/playlists/{playlist_id}/tracks?limit=100');
            const tracks = res.json && res.json.data || [];
            return tracks.map((t, i) => ({{
                index: i + 1,
                id: t.id,
                name: t.attributes.name,
                artist: t.attributes.artistName,
                album: t.attributes.albumName,
            }}));
        }}
    """)
    return json.dumps(result, indent=2)


@mcp.tool()
def rename_playlist(playlist_id: str, name: str, description: str = "") -> str:
    """Rename an existing Apple Music library playlist, optionally updating its description."""
    attrs = {"name": name}
    if description:
        attrs["description"] = description
    result = run_in_browser(f"""
        async () => {{
            const mk = MusicKit.getInstance();
            try {{
                await mk.api.patch('/v1/me/library/playlists/{playlist_id}', {{
                    body: JSON.stringify({{ attributes: {json.dumps(attrs)} }})
                }});
            }} catch(e) {{
                if (!e.message.includes('Unexpected end of JSON')) throw e;
            }}
            return {{ id: '{playlist_id}', name: {json.dumps(name)}, message: 'Playlist renamed successfully.' }};
        }}
    """)
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_playlist(playlist_id: str) -> str:
    """Permanently delete an Apple Music library playlist by playlist ID."""
    result = run_in_browser(f"""
        async () => {{
            const mk = MusicKit.getInstance();
            try {{
                await mk.api.delete('/v1/me/library/playlists/{playlist_id}');
            }} catch(e) {{
                if (!e.message.includes('Unexpected end of JSON')) throw e;
            }}
            return {{ id: '{playlist_id}', message: 'Playlist deleted successfully.' }};
        }}
    """)
    return json.dumps(result, indent=2)


@mcp.tool()
def set_playlist_artwork(playlist_id: str, image_url: str = "", image_path: str = "") -> str:
    """Attempt to set artwork on an Apple Music library playlist from a URL or local file path.

    NOTE: Apple Music's web API does not officially support artwork updates for library
    playlists — this endpoint is not documented and is blocked by CORS in most environments.
    This tool is experimental and will likely return an error (403/404 or CORS failure).
    """
    if image_path:
        with open(image_path, "rb") as f:
            image_data = f.read()
        ext = os.path.splitext(image_path)[1].lower()
        content_type = "image/png" if ext == ".png" else "image/jpeg"
    elif image_url:
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            image_data = resp.read()
            content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
    else:
        return json.dumps({"error": "Provide either image_url or image_path."})

    image_b64 = base64.b64encode(image_data).decode("utf-8")

    # Use a direct PUT to the /artwork endpoint with the image as binary,
    # authenticated via MusicKit's own developerToken + musicUserToken.
    result = run_in_browser(f"""
        async () => {{
            const mk = MusicKit.getInstance();
            const b64 = {json.dumps(image_b64)};
            const binary = atob(b64);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

            try {{
                const resp = await fetch(
                    'https://api.music.apple.com/v1/me/library/playlists/{playlist_id}/artwork',
                    {{
                        method: 'PUT',
                        headers: {{
                            'Authorization': 'Bearer ' + mk.developerToken,
                            'Music-User-Token': mk.musicUserToken,
                            'Content-Type': {json.dumps(content_type)}
                        }},
                        body: bytes.buffer
                    }}
                );
                const text = await resp.text().catch(() => '');
                return {{
                    playlist_id: {json.dumps(playlist_id)},
                    ok: resp.ok,
                    status: resp.status,
                    body: text.substring(0, 300)
                }};
            }} catch(e) {{
                return {{
                    playlist_id: {json.dumps(playlist_id)},
                    ok: false,
                    error: e.message
                }};
            }}
        }}
    """)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_folders() -> str:
    """List all playlist folders in your Apple Music library."""
    result = run_in_browser("""
        async () => {
            const mk = MusicKit.getInstance();
            const res = await mk.api.get('/v1/me/library/playlist-folders?limit=100');
            const folders = res.json && res.json.data || [];
            return folders.map(f => ({
                id: f.id,
                name: f.attributes && f.attributes.name,
            }));
        }
    """)
    return json.dumps(result, indent=2)


@mcp.tool()
def move_playlists_to_folder(folder_id: str, playlist_ids: list[str]) -> str:
    """Move one or more Apple Music library playlists into a folder by folder ID."""
    result = run_in_browser(f"""
        async () => {{
            const mk = MusicKit.getInstance();
            const ids = {json.dumps(playlist_ids)};
            const moved = [];
            const failed = [];
            for (const pid of ids) {{
                try {{
                    await mk.api.patch('/v1/me/library/playlists/' + pid, {{
                        body: JSON.stringify({{
                            relationships: {{
                                parent: {{
                                    data: [{{ id: '{folder_id}', type: 'library-playlist-folders' }}]
                                }}
                            }}
                        }})
                    }});
                    moved.push(pid);
                }} catch(e) {{
                    if (e.message.includes('Unexpected end of JSON')) {{
                        moved.push(pid);
                    }} else {{
                        failed.push(pid + ': ' + e.message);
                    }}
                }}
            }}
            return {{ folder_id: '{folder_id}', moved, failed, message: 'Moved ' + moved.length + ' playlist(s) into folder.' }};
        }}
    """)
    return json.dumps(result, indent=2)


def _http_get(url: str, headers: dict = None) -> str:
    """Simple HTTP GET returning response body as string."""
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    if headers:
        default_headers.update(headers)
    req = urllib.request.Request(url, headers=default_headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _fix_encoding(s: str) -> str:
    """Fix mojibake where UTF-8 bytes were mis-read as Windows-1252."""
    try:
        return s.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _fetch_spotify_tracks(spotify_url: str):
    """
    Fetch track list from a public Spotify playlist/album URL using Playwright.
    Intercepts Spotify's own internal API calls to get full track+artist data.
    Returns (title, [tracks]) where tracks are "Song by Artist" strings.
    """
    m = re.search(r'spotify\.com/(playlist|album|track)/([A-Za-z0-9]+)', spotify_url)
    if not m:
        raise ValueError(f"Could not parse Spotify URL: {spotify_url}")
    kind, sid = m.group(1), m.group(2)
    # Main web player uses the JSON partner API; embed uses Protobuf (not parseable)
    page_url = f"https://open.spotify.com/{kind}/{sid}"

    # Intercept Spotify's partner/catalog GraphQL API calls — full JSON with
    # track names AND artist names, bypassing any DOM rendering issues.
    result = run_in_browser(
        js="""
        async () => {
            // Wait for the page to make its API calls
            await new Promise(r => setTimeout(r, 5000));
            const title = document.title
                .replace(/\\s*[|\\u2013-]\\s*Spotify\\s*$/i, '')
                .replace(/\\s*on Spotify\\s*$/i, '')
                .trim();
            return { title, url: window.location.href };
        }
        """,
        url=page_url,
        no_musickit=True,
        capture_responses="api-partner.spotify.com",
    )

    # result = { "js_result": {...}, "captured": [ {url, body}, ... ] }
    js_result = result.get("js_result", {}) if isinstance(result, dict) else {}
    captured = result.get("captured", []) if isinstance(result, dict) else []
    title = _fix_encoding((js_result.get("title") or "").strip())

    tracks = []

    def _extract_artist(raw_artists):
        if not raw_artists:
            return ""
        first = raw_artists[0]
        return (first.get("profile") or {}).get("name") or first.get("name", "")

    for cap in captured:
        body = cap.get("body", {})

        # ── Spotify Web API: GET /v1/playlists/{id}/tracks ──────────────────
        if body.get("items") is not None:
            for item in body["items"]:
                track = (item or {}).get("track") or {}
                name = track.get("name", "")
                artist = _extract_artist(track.get("artists") or [])
                if name:
                    tracks.append(f"{name} by {artist}" if artist else name)
            continue  # process all captured pages

        # ── Spotify Partner (GraphQL) API ────────────────────────────────────
        # Real shape: data.playlistV2.content.items[].item.data.{name, artists}
        try:
            data_node = body.get("data", {})

            # Playlist
            gql_items = (data_node.get("playlistV2") or {}).get("content", {}).get("items", [])
            for item in gql_items:
                # item.item.data  OR  item.itemV2.data  (Spotify uses both across versions)
                td = (
                    (item.get("item") or {}).get("data")
                    or (item.get("itemV2") or {}).get("data")
                    or item.get("track")
                    or {}
                )
                name = td.get("name", "")
                artist = _extract_artist(
                    (td.get("artists") or {}).get("items")
                    or td.get("artists")
                    or []
                )
                if name:
                    tracks.append(f"{name} by {artist}" if artist else name)

            # Album
            album_items = (data_node.get("albumUnion") or {}).get("tracks", {}).get("items", [])
            for item in album_items:
                td = item.get("track") or item
                name = td.get("name", "")
                artist = _extract_artist(
                    (td.get("artists") or {}).get("items")
                    or td.get("artists")
                    or []
                )
                if name:
                    tracks.append(f"{name} by {artist}" if artist else name)

        except (AttributeError, TypeError):
            pass

    if not tracks:
        # Last resort: DOM extraction (works for shorter/visible playlists)
        dom_result = run_in_browser(
            js="""
            async () => {
                for (let i = 0; i < 30; i++) {
                    if (document.querySelectorAll('[data-testid="tracklist-row"]').length > 0) break;
                    await new Promise(r => setTimeout(r, 500));
                }
                const tracks = [];
                for (const row of document.querySelectorAll('[data-testid="tracklist-row"]')) {
                    const linkEl = row.querySelector('[data-testid="internal-track-link"], a[href*="/track/"]');
                    if (!linkEl) continue;
                    const titleEl = linkEl.querySelector('div') || linkEl;
                    const title = titleEl.innerText.trim();
                    if (!title) continue;
                    const artistEl = row.querySelector('a[href*="/artist/"]');
                    const artist = artistEl ? artistEl.innerText.trim() : '';
                    tracks.push(artist ? title + ' by ' + artist : title);
                }
                const debug = (document.querySelector('[data-testid="tracklist-row"]') || {}).innerHTML || '';
                return { tracks, debug: debug.substring(0, 500) };
            }
            """,
            url=page_url,
            no_musickit=True,
        )
        raw = dom_result.get("tracks") or [] if isinstance(dom_result, dict) else []
        tracks = [_fix_encoding(t) for t in raw]
        debug_html = dom_result.get("debug", "") if isinstance(dom_result, dict) else ""
        if not tracks:
            cap_urls = " | ".join(c["url"][:100] for c in captured[:5])
            # Show the keys of the first captured body to understand its shape
            first_keys = list((captured[0].get("body") or {}).keys())[:10] if captured else []
            raise ValueError(
                f"Could not extract tracks from Spotify. "
                f"Captured {len(captured)} responses: [{cap_urls}]. "
                f"First body keys: {first_keys}"
            )

    tracks = [_fix_encoding(t) for t in tracks]
    return title, tracks


def _clean_track_for_search(track: str) -> str:
    """
    Strip Spotify remaster/edition qualifiers from "Title by Artist" so
    Apple Music search finds the canonical version.
    e.g. "Heroes - 2017 Remaster by Bowie" → "Heroes by Bowie"
    """
    # Split on " by " (last occurrence) to isolate title vs artist
    parts = track.rsplit(" by ", 1)
    if len(parts) != 2:
        return track
    title, artist = parts

    # Remove remaster / edition / deluxe qualifiers from the title
    title = re.sub(
        r'\s*[-–]\s*(?:\d{4}\s+)?(?:Digital\s+)?(?:Remaster(?:ed)?|Deluxe(?:\s+Edition)?|'
        r'Anniversary\s+Edition|Expanded\s+Edition|Special\s+Edition|'
        r'Mono\s+Version|Stereo\s+Version|Single\s+Version|Radio\s+Edit|'
        r'Live\s+Version|Album\s+Version)\b.*',
        '', title, flags=re.IGNORECASE,
    ).strip()

    # Remove trailing year in parentheses: "Song (2019)"
    title = re.sub(r'\s*\(\d{4}\)\s*$', '', title).strip()

    # Normalize en-dash/em-dash in artist names (e.g. Run–D.M.C.)
    artist = artist.replace('–', '-').replace('—', '-')

    return f"{title} by {artist}"


@mcp.tool()
def import_from_spotify(spotify_url: str, playlist_name: str = "", folder_id: str = "") -> str:
    """
    Import any public Spotify playlist or album into Apple Music.
    spotify_url: full Spotify URL (playlist, album, or track)
    playlist_name: optional override — defaults to the Spotify playlist title
    folder_id: optional Apple Music folder ID to place the playlist in
    """
    try:
        detected_title, tracks = _fetch_spotify_tracks(spotify_url)
    except Exception as e:
        return json.dumps({"error": str(e)})

    name = playlist_name.strip() or detected_title or "Imported from Spotify"

    if not tracks:
        return json.dumps({"error": "No tracks found in Spotify playlist.", "detected_title": detected_title})

    # Clean remaster qualifiers before searching Apple Music
    search_tracks = [_clean_track_for_search(t) for t in tracks]

    result_json = create_playlist(name=name, songs=search_tracks, folder_id=folder_id)
    result = json.loads(result_json)
    result["spotify_url"] = spotify_url
    result["tracks_found_on_spotify"] = len(tracks)
    return json.dumps(result, indent=2)


def _clean_html_entities(s: str) -> str:
    return (
        s.replace("&amp;", "&")
         .replace("&#039;", "'")
         .replace("&apos;", "'")
         .replace("&quot;", '"')
         .replace("&lt;", "<")
         .replace("&gt;", ">")
         .strip()
    )


def _songs_from_setlistfm_html(html: str) -> list[str]:
    """
    Extract song names from a setlist.fm setlist page.

    setlist.fm marks each song link with a title attribute of the form:
        title="statistics for SONG NAME performed by ARTIST"
    That's the most reliable hook — it's present even when CSS class names change.

    Falls back to <a class="songLabel"> text content.
    """
    songs = re.findall(r'title="statistics for (.+?) performed by ', html)
    if not songs:
        songs = re.findall(r'class="songLabel"[^>]*>([^<]+)<', html)
    songs = [_clean_html_entities(s) for s in songs]
    return [s for s in songs if s and len(s) < 200]


def _fetch_setlistfm(artist: str, date: str = "", setlist_url: str = "") -> dict:
    """
    Fetch a setlist from setlist.fm.
    Accepts either a direct setlist URL or artist + date (YYYY-MM-DD or MM/DD/YYYY).
    Returns {"artist", "date", "venue", "city", "songs": [...]}
    """
    # --- Direct URL ---
    if setlist_url:
        if not setlist_url.startswith("http"):
            setlist_url = "https://www.setlist.fm" + setlist_url
        html = _http_get(setlist_url)
    else:
        if not artist:
            raise ValueError("Provide either setlist_url or artist name.")

        # Normalise date digits to YYYYMMDD for setlist.fm search param
        date_param = ""
        if date:
            digits = re.sub(r'[^0-9]', '', date)
            if len(digits) == 8:
                date_param = digits if int(digits[:4]) > 1900 else digits[4:] + digits[:4]

        query = urllib.parse.urlencode({"query": artist})
        search_url = f"https://www.setlist.fm/search?{query}"
        if date_param:
            search_url += f"&date={date_param}"
        html = _http_get(search_url)

        # Search results page — follow the first setlist link
        link_m = (
            re.search(r'href="(/setlist/[^"]+\.html)"', html)
            or re.search(r'href="(https://www\.setlist\.fm/setlist/[^"]+\.html)"', html)
        )
        if link_m:
            target = link_m.group(1)
            if target.startswith("/"):
                target = "https://www.setlist.fm" + target
            html = _http_get(target)

    # --- Extract songs ---
    songs = _songs_from_setlistfm_html(html)

    # --- Extract metadata ---
    # Artist
    artist_m = (
        re.search(r'"name":\s*"([^"]+)"', html)
        or re.search(r'<h1[^>]*>.*?<a[^>]*>([^<]+)</a>', html, re.DOTALL)
    )
    artist_name = _clean_html_entities(artist_m.group(1)) if artist_m else artist

    # Date — JSON-LD eventDate (DD-MM-YYYY) is most reliable
    date_m = re.search(r'"eventDate":\s*"(\d{2}-\d{2}-\d{4})"', html)
    if date_m:
        dd, mm, yyyy = date_m.group(1).split("-")
        show_date = f"{mm}/{dd}/{yyyy}"
    else:
        span_m = re.search(
            r'<span class="month">([^<]+)</span>.*?'
            r'<span class="day">([^<]+)</span>.*?'
            r'<span class="year">([^<]+)</span>',
            html, re.DOTALL,
        )
        show_date = (
            f"{span_m.group(1).strip()} {span_m.group(2).strip()}, {span_m.group(3).strip()}"
            if span_m else date
        )

    # Venue
    venue = ""
    city = ""
    venue_m = re.search(r'"location":\s*\{[^}]*"name":\s*"([^"]+)"', html, re.DOTALL)
    if venue_m:
        venue = _clean_html_entities(venue_m.group(1))
    city_m = re.search(r'"addressLocality":\s*"([^"]+)"', html)
    if city_m:
        city = _clean_html_entities(city_m.group(1))

    return {
        "artist": artist_name,
        "date": show_date,
        "venue": venue,
        "city": city,
        "songs": songs,
    }


@mcp.tool()
def import_from_setlistfm(
    artist: str = "",
    date: str = "",
    setlist_url: str = "",
    playlist_name: str = "",
    folder_id: str = "",
) -> str:
    """
    Create an Apple Music playlist from a setlist.fm concert setlist.

    Provide EITHER:
      - setlist_url: full setlist.fm URL for a specific show
      OR
      - artist + date: e.g. artist="Radiohead", date="2012-08-04"

    playlist_name: optional override (defaults to "Artist @ Venue – Date")
    folder_id: optional Apple Music folder ID
    """
    try:
        info = _fetch_setlistfm(artist=artist, date=date, setlist_url=setlist_url)
    except Exception as e:
        return json.dumps({"error": str(e)})

    if not info["songs"]:
        return json.dumps({"error": "No songs found for this setlist.", "info": info})

    # Build Apple Music search queries — setlist.fm has no artist per song, so search "{song} {artist}"
    artist_name = info["artist"]
    queries = [f"{song} by {artist_name}" for song in info["songs"]]

    # Default playlist name
    if not playlist_name:
        parts = [artist_name]
        if info["venue"]:
            parts.append(f"@ {info['venue']}")
        if info["city"]:
            parts.append(info["city"])
        if info["date"]:
            parts.append(f"– {info['date']}")
        playlist_name = " ".join(parts)

    result_json = create_playlist(name=playlist_name, songs=queries, folder_id=folder_id)
    result = json.loads(result_json)
    result["setlist_info"] = info
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    mcp.run()
