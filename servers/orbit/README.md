# Orbit server

Orbit is a small multiplayer text game (a MUD) on a space station orbiting the
Earth, played through Hariku's **Orbit** extension (`extensions/orbit`). This
folder is the server: Python 3.10 or newer, **standard library only**, one
process, one SQLite file.

It listens on `127.0.0.1` behind the web server, which handles TLS and passes
`/orbit/` on to it:

| Path | What |
|---|---|
| `GET /orbit/ws` | the game, over WebSocket |
| `GET /orbit/health` | `{"ok": true, "service": "orbit", "version": "1.0", "protocol": 1, "online": 3}` |

`/ws` and `/health` work too, for a proxy that strips the `/orbit` prefix.

## Files

| File | What |
|---|---|
| `orbit_server.py` | the program: HTTP, WebSocket connections, limits, the tick |
| `orbit_ws.py` | the WebSocket protocol (RFC 6455), shared with the Hariku extension |
| `orbit_game.py` | the game: commands, jobs, missions, market, admin (no I/O) |
| `orbit_world.py`, `world.json` | the station: places, objects, goods, missions, gestures |
| `orbit_earth.py` | what you see from the Observation Deck, from the real time |
| `orbit_lang.py`, `texts.json` | everything the server says, in English and Indonesian |
| `orbit_safety.py`, `words.json` | names, the word filter, rate limits |
| `orbit_store.py` | saving (SQLite) |
| `config.example.json` | a configuration to copy to `config.json` |
| `orbit.service` | a systemd user unit |

## Running it

On the VPS (Ubuntu 22.04, Python 3.10, user `rafli`), in `~/orbit/`:

```sh
mkdir -p ~/orbit
# copy this folder's files there: orbit_*.py, *.json, orbit.service
cd ~/orbit
cp config.example.json config.json        # then put your character's name in "admins"
python3 orbit_server.py --config config.json
# "Orbit 1.0 listening on 127.0.0.1:7340"; Ctrl+C stops it
```

As a systemd **user** service (no sudo; linger is already on):

```sh
mkdir -p ~/.config/systemd/user
cp ~/orbit/orbit.service ~/.config/systemd/user/orbit.service
systemctl --user daemon-reload
systemctl --user enable --now orbit
systemctl --user status orbit
journalctl --user -u orbit -f             # the log
```

`orbit.service`:

```ini
[Unit]
Description=Orbit, the Hariku multiplayer game server
After=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/orbit
ExecStart=/usr/bin/python3 %h/orbit/orbit_server.py --config %h/orbit/config.json
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
NoNewPrivileges=yes

[Install]
WantedBy=default.target
```

To update: copy the new files over and `systemctl --user restart orbit`.
Players hear "the station's computer is restarting" and their Orbit reconnects
by itself. The database is `~/orbit/orbit.db` (with `orbit.db-wal` next to it
while running); to back it up while it runs:

```sh
python3 -c "import sqlite3; s=sqlite3.connect('orbit.db'); d=sqlite3.connect('orbit-backup.db'); s.backup(d)"
```

Checks, on the VPS and from anywhere:

```sh
curl -fsS http://127.0.0.1:7340/orbit/health
curl -fsS https://infiartt.com/orbit/health
```

## The web server

### nginx (aaPanel)

Paste this inside the `server { ... }` block of infiartt.com's site, in
`/www/server/panel/vhost/nginx/infiartt.com.conf` (or the site's
"Config" in aaPanel), above the other `location` blocks; then check and reload
(`nginx -t`, then reload in aaPanel or `/etc/init.d/nginx reload`):

```nginx
    # Orbit (Hariku's multiplayer game): WebSocket to the local server.
    location /orbit/ {
        proxy_pass http://127.0.0.1:7340;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        # Behind Cloudflare, the visitor's address is in CF-Connecting-IP
        # ($remote_addr would be Cloudflare's). Without Cloudflare, use $remote_addr.
        proxy_set_header X-Real-IP $http_cf_connecting_ip;
        proxy_read_timeout 1h;
        proxy_send_timeout 1h;
        proxy_buffering off;
    }
```

`proxy_pass` has no path after the port, so the server sees `/orbit/ws`. The
server trusts `X-Real-IP` only from a proxy on the same machine; it uses the
address for the per-address connection limit and for bans (only a salted hash
of it is kept). If people could reach the origin without Cloudflare they could
put anything in `CF-Connecting-IP`; that only affects those two things.

### Cloudflare

WebSockets must be on (Network, WebSockets; on by default). Cloudflare closes a
WebSocket after 100 seconds without traffic: the Hariku client pings every 25
seconds, and reconnects by itself when Cloudflare restarts a connection.

### Apache

Apache 2.4.47 or newer (modules `proxy`, `proxy_http`, `headers`):

```apache
<Location "/orbit/">
    ProxyPass "http://127.0.0.1:7340/orbit/" upgrade=websocket timeout=3600
    ProxyPassReverse "http://127.0.0.1:7340/orbit/"
    RequestHeader set X-Real-IP "%{REMOTE_ADDR}s"
</Location>
```

Older Apache (also `proxy_wstunnel` and `rewrite`):

```apache
RewriteEngine On
RewriteCond %{HTTP:Upgrade} =websocket [NC]
RewriteRule ^/orbit/(.*) ws://127.0.0.1:7340/orbit/$1 [P,L]
ProxyPass /orbit/ http://127.0.0.1:7340/orbit/ timeout=3600
ProxyPassReverse /orbit/ http://127.0.0.1:7340/orbit/
RequestHeader set X-Real-IP "%{REMOTE_ADDR}s"
```

## Configuration

`config.json` (every key is optional; relative paths are from the file's
folder). The environment can set `ORBIT_CONFIG`, `ORBIT_HOST`, `ORBIT_PORT` and
`ORBIT_DB`, and the command line `--config`, `--host`, `--port`, `--db`.

| Key | Default | What |
|---|---|---|
| `host`, `port` | `127.0.0.1`, `7340` | where to listen |
| `database` | `orbit.db` | the SQLite file |
| `words` | `words.json` | the word filter's list (Indonesian and English; edit freely) |
| `max_connections`, `max_per_ip` | 200, 8 | connections at once, in all and from one address |
| `max_message` | 4096 | the largest message a client may send, in bytes |
| `rate`, `burst`, `abuse_limit` | 5, 15, 40 | messages a second from one connection, a quick burst, and how many dropped messages before it is closed |
| `idle_timeout`, `hello_timeout` | 120, 20 | seconds of silence before a connection is closed; seconds to say hello |
| `proxy_ip_header` | `X-Real-IP` | where a local proxy puts the visitor's address (`""`: ignore it) |
| `allowed_origins` | `[]` | browsers send an Origin header; they are refused unless listed |
| `log_level` | `INFO` | |
| `game.admins` | `[]` | character names that may use the admin commands |
| `game.start_credits` | 100 | a new character's credits |
| `game.flight_seconds`, `game.pilot_cooldown` | 60, 300 | the cargo run's length and the pause after it |
| `game.engineer_cooldown` | 120 | the pause after a reactor repair (30 after a failed one) |
| `game.market_seconds` | 180 | how often prices drift |
| `game.missions_per_day` | 3 | missions on the daily board |
| `game.linkdead_seconds` | 60 | how long a dropped player stays before "leaves the station" |

Admin commands, typed in the game by a character in `game.admins`:
`mute NAME [minutes]`, `unmute NAME`, `kick NAME`, `ban NAME` (the character,
and its address for 7 days), `unban NAME`, `announce TEXT` (Indonesian:
`bisukan`, `tendang`, `umumkan`).

## What is kept, and the log

The database keeps each character's name, job, credits, items, place, the
short description its player wrote, cooldowns and missions, when it was made
and last seen, and whether it is banned or muted; and the market's prices.
Accounts have no password or email: the client makes a random 256-bit secret
the first time it joins this server and keeps it on the player's computer;
the server keeps only a PBKDF2-SHA256 hash of it (with a salt made once for
this server). Chat (say, whisper, shout) is passed on to whoever hears it and
never written anywhere. A banned connection's address is kept only as a salted
hash, for 7 days.

The log says when the server starts and stops, when characters are created,
join, resume and leave (by name), and what admins did. It never contains
secrets, chat or addresses.

## Protocol

JSON text messages over WebSocket (text frames only; 4096 bytes at most from
a client). Everything the server sends is already in the player's language.

**Joining.** The client's first message:

```json
{"t": "hello", "v": 1, "lang": "id", "secret": "<64 hex characters>",
 "name": "Rafli", "job": "pilot", "client": "Hariku Orbit 1.0"}
```

A known secret resumes its character (the name and job are then ignored); an
unknown one creates a character with that name and job (pilot, engineer,
trader, scientist, security). The answer is either

```json
{"t": "welcome", "v": 1, "name": "Rafli", "job": "pilot", "new": true,
 "resumed": false, "credits": 100, "room": "dock", "amb": "vent"}
```

or `{"t": "err", "code": "...", "text": "...", "fatal": true}` and a close.
Codes: `version`, `banned`, `bad_secret`, `name_length`, `name_characters`,
`name_filtered`, `name_reserved`, `name_taken`, `bad_job`. `resumed` is true
when the character was still on the station (a reconnect within a minute:
nobody is told anything).

**Commands** (`{"t": "cmd", "c": ..., ...}`); the client reads what was typed
and sends the command word, the server finds places, people and things by
their names in either language:

| `c` | Fields | |
|---|---|---|
| `look` | `a`: nothing, a person, a thing | |
| `go` | `a`: a place | walks the shortest way |
| `say`, `shout` | `a`: the words | shout: station-wide, once every 10 s |
| `whisper` | `to`, `a` | to anyone on the station |
| `emote` | `e`: smile, wave, laugh, nod, shrug, clap, cheer, sigh, bow, dance, hug; `to` (optional) | |
| `who`, `inventory`, `prices`, `missions`, `complete`, `abandon`, `work`, `help` | | |
| `give` | `to`, `n`, `item` (`credits` or a thing) | in the same room |
| `describe` | `a`: a short description (nothing: show it) | |
| `answer` | `a`: the reactor's numbers | |
| `accept` | `n`: a mission's number | |
| `take` | `item`, `n` | a mission's things |
| `buy`, `sell` | `item`, `n` (`"all"` to sell everything) | on the Promenade |
| `text` | `a`: a plain word | the server guesses: a place, a person, a thing |
| `admin` | `op`: mute, unmute, kick, ban, unban, announce; `to`, `n`, `a` | admins only |

**Events** (`{"t": "ev", "k": kind, "text": "...", ...}`). `k` tells the
client which sound fits and whose voice reads it: `room`, `moved`, `arrive`,
`leave`, `say`/`said`, `whisper`/`whispered`, `shout`/`shouted`, `emote`,
`who`, `info`, `error`, `tones`, `paid`, `failed`, `received`, `gave`,
`mission`, `trade`, `flight`, `announce`, `system`. Some also carry `actor`
(who did it), `brief` (a short line to say for your own action, "Terkirim."),
`room` and `amb` (where you are now and its ambience: `vent`, `cantina`,
`engine`, `garden`, `deck`), `codes` (the reactor's tones, 1 to 4) and
`sound` (`launch`, `landing`).

**Closing codes**: 1001 the server is restarting (reconnect), 1008 a broken
rule (too many messages, no hello), 4000 kicked, 4001 connected from
somewhere else, 4003 banned (don't reconnect after these three).

Pings: the client pings every 25 seconds; the server answers pings and
closes a connection that says nothing for `idle_timeout` seconds.

## Tests

From Hariku's source folder (they run on Windows or Linux, and use only this
computer):

```sh
python -m pytest tests/test_orbit_server.py tests/test_orbit_e2e.py -q
```
