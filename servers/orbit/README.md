# Orbit server

Orbit is a small multiplayer text game (a MUD) on a space station orbiting the
Earth, the entry hub of a shared simulation, played through Hariku's **Orbit**
extension (`extensions/orbit`). This folder is the server: Python 3.10 or
newer, **standard library only**, one process, one SQLite file. The server
decides everything (movement, money, things, progress); the client only sends
commands and shows or speaks the results.

It listens on `127.0.0.1` behind the web server, which handles TLS and passes
`/orbit/` on to it:

| Path | What |
|---|---|
| `GET /orbit/ws` | the game, over WebSocket |
| `GET /orbit/health` | `{"ok": true, "service": "orbit", "version": "1.1", "protocol": 1, "online": 3}` |

`/ws` and `/health` work too, for a proxy that strips the `/orbit` prefix.

## Files

| File | What |
|---|---|
| `orbit_server.py` | the program: HTTP, WebSocket connections, limits, the tick |
| `orbit_ws.py` | the WebSocket protocol (RFC 6455), shared with the Hariku extension |
| `orbit_game.py` | the game's core: joining, talking, looking, time passing (no I/O) |
| `orbit_nav.py` | walking by compass, the way, maps, dark rooms, locks, air, the Kancil, cabins |
| `orbit_items.py` | things: shops, using, wearing, examining, food, pets, the temple |
| `orbit_work.py` | jobs and their mini-games, XP and levels, missions, the daily bonus |
| `orbit_econ.py` | the markets, the farm, mining and salvage, profiles, the economy's totals |
| `orbit_admin.py` | moving a character to another computer; the admins' commands |
| `orbit_verbs.py` | the commands the server reads from plain text (both languages) |
| `orbit_world.py`, `world.json` | the map: rooms, compass exits, objects, goods, missions, gestures |
| `economy.json` | the balance: levels, ranks, the daily bonus, crops, mining, the shops' things |
| `orbit_earth.py` | what you see from the Observation Deck, from the real time |
| `orbit_lang.py`, `texts.json` | everything the server says, in English and Indonesian |
| `orbit_safety.py`, `words.json` | names, the word filter, rate limits |
| `orbit_store.py` | saving (SQLite), and migrating older databases |
| `orbit_backup.py`, `orbit-backup.service`, `orbit-backup.timer` | a daily copy of the database |
| `config.example.json` | a configuration to copy to `config.json` |
| `orbit.service` | a systemd user unit |

`world.json`, `economy.json` and `texts.json` are only read; everything that
changes while people play is in the database.

## Running it

On the VPS (Ubuntu 22.04, Python 3.10, user `rafli`), in `~/orbit/`:

```sh
mkdir -p ~/orbit
# copy this folder's files there: orbit_*.py, *.json, orbit*.service, orbit-backup.timer
cd ~/orbit
cp config.example.json config.json        # then put your character's name in "admins"
python3 orbit_server.py --config config.json
# "Orbit 1.1 listening on 127.0.0.1:7340"; Ctrl+C stops it
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
while running).

### Updating to 1.1 (the database migrates by itself)

1. Copy every file of this folder to `~/orbit/` (new in 1.1: `economy.json`,
   `orbit_nav.py`, `orbit_items.py`, `orbit_work.py`, `orbit_econ.py`,
   `orbit_admin.py`, `orbit_verbs.py`, `orbit_backup.py`,
   `orbit-backup.service`, `orbit-backup.timer`; changed: the other
   `orbit_*.py`, `world.json`, `texts.json`). `config.json` needs no new
   keys: every new setting has a default (below).
2. `systemctl --user restart orbit`.
3. On its first start, the server sees an Orbit 1.0 database (schema version
   0), saves a copy of it as `orbit.db.before-v1.bak` next to it, and
   migrates it in one transaction: new columns (voice, XP, the daily streak,
   what a character mined and harvested) and new tables (companions,
   transfer codes, old secrets, transfers, the admins' log) are added;
   nothing is dropped or changed, and work done before 1.1 counts as XP
   (10 a repair, 20 a cargo run, 25 a mission). The log says "the database
   was migrated from version 0 to 1". If the migration fails, nothing is
   changed and the server stops with the error in the log; the copy is there.
4. Every room of 1.0 still exists, so characters wake up where they were.
   Returning players are told once what's new, and get a compass (and the
   keycards their XP already earned).

### Backups

`orbit_backup.py` copies the database while the server runs (SQLite's online
backup, checked with `PRAGMA quick_check` before older copies are removed)
and keeps the newest 7:

```sh
python3 ~/orbit/orbit_backup.py --db ~/orbit/orbit.db --dir ~/orbit/backups --keep 7
```

Once a day, as a systemd user timer (04:30, or soon after boot if a day was missed):

```sh
cp ~/orbit/orbit-backup.service ~/orbit/orbit-backup.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now orbit-backup.timer
systemctl --user list-timers orbit-backup.timer
```

The same with the `sqlite3` tool, if it's installed:
`sqlite3 ~/orbit/orbit.db ".backup '/home/rafli/orbit/backups/manual.db'"`.
To restore: stop the server, copy a backup over `orbit.db` (and delete
`orbit.db-wal` and `orbit.db-shm`), start it again.

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
    # ^~ keeps aaPanel's regex locations (images, .well-known...) from taking these paths.
    location ^~ /orbit/ {
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
seconds, and reconnects by itself when Cloudflare restarts a connection. The
client is not a browser: if Bot Fight Mode, "I'm Under Attack" or a WAF
challenge is on for the site, add a rule that skips them for the path
`/orbit/`, or the client gets a challenge page instead of the game (it then
says Orbit is offline and keeps retrying).

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
| `world`, `economy`, `texts` | the bundled files | the map, the balance, the lines |
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
| `game.work_cooldown`, `game.work_fail_cooldown` | 120, 30 | the same for scientists and security officers |
| `game.market_seconds` | 180 | how often prices drift |
| `game.missions_per_day` | 3 | missions on the daily board |
| `game.linkdead_seconds` | 60 | how long a dropped player stays before leaving (a player who types "quit" leaves at once) |
| `game.econ_rate`, `game.econ_burst` | 1, 6 | farming, mining, buying, using things: a second apart on average, this many in a quick row |
| `game.max_goods` | 20 | goods a bag holds (bigger bags hold more) |
| `game.transfer_minutes` | 10 | how long a transfer code works |
| `game.transfer_tries`, `game.transfer_window` | 5, 900 | wrong transfer codes one address may send in that many seconds |

### The balance (economy.json)

Everything in `economy.json` can be changed; it's read when the server starts.
What 1.1 ships with:

- **Levels:** reaching level L takes 60 × L × (L-1) / 2 XP (level 2 at 60,
  5 at 600, 10 at 2,700, 20, the top, at 11,400). XP: a repair 10 (+2 for
  each tone over three), a cargo run 20, an analysis or a patrol 12, a
  mission 25. Each level adds 3% to work pay; a job's tools add 10% or 20%
  (a trader's lower the market's fees instead). Ranks: trainee (1), plain
  (3), senior (6), chief (10), master (15), legendary (20). Everyone gets a
  crew keycard at level 2 and an officer keycard at 10; engineers a
  technician keycard at 3.
- **Work pay** (before levels and tools): a repair 10 + 10 per tone (40 to
  70; the Reactor Core a quarter more), a cargo run 70 to 100, an analysis
  45 + 5 per difficulty step, a patrol 40 + 5 per traveller. Breaks: 2
  minutes (5 after a cargo run); a martabak halves the next one.
- **The daily bonus:** 40, then 15 more for each day in a row, up to 130 on
  the seventh; every seventh day also 3 strawberry seeds. Missing a day
  starts again at 40.
- **The farm:** 2 plots to start, up to 8 (150, 250, 400, 600, 900, 1,300
  credits each). Crops (seed price, time, yield, market price): kangkung 5,
  10 min, 3-4, 4; chilli 10, 30 min, 3-5, 8; tomato 15, 1 h, 4-5, 9;
  strawberry 30, 2 h, 4-6, 16; vanilla 60 (level 3), 4 h, 3-5, 36; dragon
  fruit 100 (level 5), 8 h, 4-6, 50; moon melon 180 (level 8), 24 h, 3-5,
  120. Watering once adds one to a plot's crop; a golden chilli (300) turns
  up in 2% of harvests.
- **Mining:** a strike every 25 s (steel drill, 500 credits, level 3: 20 s;
  plasma drill, 2,000, level 8: 16 s). The Belt Platform yields mostly iron
  (4) and nickel (7); the Asteroid Surface (an EVA suit) and the Crystal Cave
  (a suit and a headlamp) more titanium (18), platinum (45), meteorite (90)
  and quantum crystals (150). A rich vein gives two (8%). The old miner on
  the platform buys ore at three quarters of the market's price. Salvage in
  the Debris Field every 20 s: scrap 5, circuit boards 14, satellite chips
  40, gold foil 120.
- **Money sinks:** the shops (devices 100 to 5,000, tools 250 to 2,000,
  furniture 60 to 1,500, clothes 150 to 2,500, titles 200 to 5,000, pets
  600 and 900), seeds, food (3 to 20), plots, the Kancil's fare (5 from the
  Dock; pilots ride free), the tow when your air runs out (20), lanterns
  in the temple (3), and the market's fees (10% on buying and 12% on selling;
  traders 2% and 4%, less with their tools), which also make every sale move
  the price down 2%.
- **The EVA suit** holds 3 minutes of air, an oxygen tank 3 more; warnings at
  60 and 20 seconds.

The admins' **economy** report shows the credits in circulation (all
characters), the richest, and every credit earned by source (work,
missions, daily, market, finds, admin) and spent by sink (shops, market,
fares, rescues, lanterns, admin), so you can see whether money grows too
fast and adjust these numbers.

## Admin commands

Typed in the game by a character in `game.admins` (Indonesian first):

| Command | What |
|---|---|
| `bisukan Budi 10` / `mute Budi 10`, `unmute Budi` | mute for minutes |
| `tendang Budi` / `kick Budi` | send off the station |
| `ban Budi`, `unban Budi` | the character, and its address for 7 days |
| `umumkan ...` / `announce ...` | to everyone |
| `beri kredit Budi 500` / `grant Budi 500` | give credits (from a player, "beri kredit" is a gift) |
| `ambil kredit Budi 100` / `take credits Budi 100` | take credits |
| `beri item Budi senter 1` / `give item Budi headlamp` | give any thing (a pet too) |
| `ekonomi` / `economy` | the economy's report |
| `atur harga kopi 20` / `set price coffee 20` | a market price for the next hour |
| `reset harian Budi` / `reset streak Budi` | a daily streak back to zero |
| `pergi ke Anjungan`, `pergi ke Budi` / `goto the bridge`, `goto Budi` | teleport (players walk) |
| `tak terlihat` / `invisible` | nobody sees you come, go, or in who (again: visible) |
| `pindahan` / `transfers` | recent character transfers |
| `cabut akses Budi` / `revoke Budi` | no computer can play Budi until a transfer code is used (a stolen laptop) |
| `kode pindah untuk Budi` / `transfer code for Budi` | a code for someone who lost their computer |
| `log admin` / `admin log` | the last admin actions |
| `bantuan admin` / `help admin` | this list, in the game (players don't see it) |

Every admin action is written to the log and to the database's `admin_log`
table, with who did it and when.

## Moving a character to another computer

A character lives on the computer that made it: the client keeps a random
secret, the server only a hash of it. In Preferences, Orbit ("Move my
character to another computer"), or with `kode pindah` / `move my character`,
the server makes a one-time code: 16 letters from an alphabet without I and O
(about 70 bits), shown as four groups; only its keyed hash is stored, for 10
minutes, and a new one replaces the old. The other computer sends the code
with a new secret of its own (`{"t": "hello", ..., "secret": new, "transfer":
code}`): the character's secret becomes the new one, the code is used up, and
the old computer's secret is kept only as a hash in `old_secrets`, so that
computer is told "this character has been moved to another computer" (or
"revoked" after an admin's revoke) instead of making a new character. A
connected old computer is closed like a login from elsewhere. An address that
sends 5 wrong codes in 15 minutes has to wait. Transfers are logged (the
`transfers` table: the character, what happened, when, and which admin).

## What is kept, and the log

The database keeps each character's name, job, credits, things (inventory),
place, the short description its player wrote, XP, the daily streak, the
voice number others hear it in, what it mined and harvested, a JSON "stats"
field with the rest of its play state (cooldowns, missions, farm plots and
their timers, worn things, the rooms it knows, its beacon, friends, air left
outside, a shuttle ride in progress), when it was made and last seen, and
whether it is banned or muted; its companions (a pet: kind, name, and its
own stats); transfer codes (a hash, for 10 minutes); secrets that no longer
work (a hash); the transfers log; the admins' log; and, in `meta`, the
market's prices, the economy's totals and today's temple lanterns. Accounts
have no password or email: the client makes a random 256-bit secret the
first time it joins this server and keeps it on the player's computer; the
server keeps only a PBKDF2-SHA256 hash of it (with a salt made once for this
server). Chat (say, whisper, shout) is passed on to whoever hears it and
never written anywhere. A banned connection's address is kept only as a
salted hash, for 7 days.

The log says when the server starts and stops, when characters are created,
join, resume, log out and leave (by name), transfers, and what admins did. It
never contains secrets, codes, chat or addresses.

## Protocol

JSON text messages over WebSocket (text frames only; 4096 bytes at most from
a client). Everything the server sends is already in the player's language.
Protocol version 1 is unchanged since Orbit 1.0: everything 1.1 added is
optional, so the 1.0 client keeps working (it only misses the new sounds).

**Joining.** The client's first message:

```json
{"t": "hello", "v": 1, "lang": "id", "secret": "<64 hex characters>",
 "name": "Rafli", "job": "pilot", "client": "Hariku Orbit 1.1"}
```

A known secret resumes its character (the name and job are then ignored); an
unknown one creates a character with that name and job (pilot, engineer,
trader, scientist, security). With `"transfer": "<code>"` (and no name or job),
the code's character moves to this secret. The answer is either

```json
{"t": "welcome", "v": 1, "name": "Rafli", "job": "pilot", "new": true,
 "resumed": false, "credits": 100, "voice": 0, "room": "dock", "amb": "vent",
 "floor": "metal", "acoustics": "hangar"}
```

or `{"t": "err", "code": "...", "text": "...", "fatal": true}` and a close.
Codes: `version`, `banned`, `bad_secret`, `name_length`, `name_characters`,
`name_filtered`, `name_reserved`, `name_taken`, `bad_job`, `moved`, `revoked`,
`transfer_bad`, `transfer_wait`. `resumed` is true when the character was
still on the station (a reconnect within a minute: nobody is told anything).

**Commands** (`{"t": "cmd", "c": ..., ...}`); the client reads what was typed
and sends the command word, the server finds places, people and things by
their names in either language. Anything the client doesn't know goes as
`text`, and the server reads the rest itself (`orbit_verbs.py`), so new
commands need no new client:

| `c` | Fields | |
|---|---|---|
| `look` | `a`: nothing, a person, a thing, a thing you own, a direction | |
| `move` | `d`: n, ne, e, se, s, sw, w, nw, u, d | walk one room |
| `go` | `a`: a direction or a place | next door: a walk; further: the way (admins teleport) |
| `way`, `map`, `where`, `compass`, `scan`, `locate` | `a` / `to` | finding your way and people |
| `board` | | the Kancil, at the Dock or the Belt Platform |
| `say`, `shout` | `a`: the words | shout: station-wide, once every 10 s |
| `whisper` | `to`, `a` | to anyone on the station |
| `emote` | `e`: smile, wave, laugh, nod, shrug, clap, cheer, sigh, bow, dance, hug; `to` (optional) | |
| `who`, `inventory`, `prices` (`a`: a kind), `missions`, `complete`, `abandon`, `work`, `help` (`a`: a topic) | | |
| `give` | `to`, `n`, `item` (`credits` or a thing) | in the same room |
| `describe` | `a`: a short description (nothing: show it) | |
| `answer` | `a`: the reactor's numbers, a reading, a traveller | |
| `accept` | `n`: a mission's number | |
| `take` | `item`, `n` | a mission's things |
| `buy`, `sell` | `item`, `n` (`"all"` to sell everything, or all of a kind) | market goods, and the shop you're in |
| `list`, `use`, `unequip`, `open` | `a` / `item` (`equip`: true to wear) | shops and things |
| `plant` (`item`, `n`), `water`, `harvest`, `farm`, `mine`, `collect` | | the farm, mining, salvage |
| `daily`, `profile` (`to`), `rank`, `voice` (`a`: 1-10 or auto), `transfer` | | |
| `friends` (`op`, `to`), `invite` (`op`, `to`), `visit` (`to`), `pet` (`op`, `a`), `ring`, `lantern` | | |
| `bye` | | leaving on purpose: gone at once |
| `away` | `on` | the client's window is hidden and its player idle |
| `status` | | connected as, where, how many online |
| `text` | `a`: plain words | the server reads them (see above) |
| `admin` | `op`: mute, unmute, kick, ban, unban, announce, grant, take_credits, give_item, economy, set_price, reset_streak, goto, invisible, transfers, revoke, transfer_for, admin_log; `to`, `n`, `a`, `item` | admins only |

**Events** (`{"t": "ev", "k": kind, "text": "...", ...}`). `k` tells the
client which sound fits and whose voice reads it: `room`, `moved`, `arrive`,
`leave`, `say`/`said`, `whisper`/`whispered`, `shout`/`shouted`, `emote`,
`who`, `info`, `error`, `tones`, `task`, `paid`, `failed`, `received`,
`gave`, `mission`, `trade`, `flight`, `offer`, `announce`, `system`. Optional
fields: `actor` (who did it), `brief` (a short line to say for your own
action), `room`, `amb` (`vent`, `cantina`, `engine`, `garden`, `deck`,
`space`, `belt`, `venue`), `floor` and `acoustics` (where you are now),
`dir` (the way you walked, or the side someone came from or left by), `via`
(`lift`, `ladder`, `slide`, `airlock`, `door`), `codes` (the reactor's
tones, 1 to 4), `sound` (a cue more specific than the kind's), `emote`
(which gesture), `voice` (the voice number a speaker chose), `preview` (read
this line in `voice`), `ask` (an invitation), `transfer_code` and `expires`.

**Closing codes**: 1001 the server is restarting (reconnect), 1008 a broken
rule (too many messages, no hello), 4000 kicked, 4001 connected from
somewhere else, moved to another computer or revoked, 4003 banned (don't
reconnect after these three); 1000 after `bye`.

Pings: the client pings every 25 seconds; the server answers pings and
closes a connection that says nothing for `idle_timeout` seconds.

## Sounds (the client's cues)

The extension plays a **cue** for each event, by name. A cue is a WAV file,
or numbered variants of one (`step_metal_1.wav`, `step_metal_2.wav`...; one
is picked at random each time). Orbit looks in these folders, in order, and
the first with any file for the cue wins:

1. `%APPDATA%\Hariku2\orbit_sounds\` (your own recordings)
2. `orbit\` inside the Sound Themes theme in use (`%APPDATA%\Hariku2\sound_themes\<theme>\orbit\`)
3. the extension's `sounds\` folder (generated by `extensions/orbit/orbit_sounds.py`)

So a pack of recordings (CC0 or your own) is just files named like the cues.
A name with parts falls back to a shorter one when no folder has it
(`emote_clap` plays `emote`). Positional cues (steps, arrive, leave,
gestures, door, bump, ladder) are best mono: Orbit pans them to the side
they happen on and adds the room's echo (small, room, hall, hangar, cave,
open, the muffled hush outside) as it plays them, keeping those copies in
`%APPDATA%\Hariku2\orbit_sound_cache\`.

| Cue | When |
|---|---|
| `step_metal`, `step_carpet`, `step_grass`, `step_stone`, `step_rock`, `step_suit`, `step_wet` | your steps, by the floor you walk on |
| `door`, `airlock`, `lift_up`, `lift_down`, `ladder`, `slide`, `bump`, `locked` | doors, airlocks, lifts, ladders, the slide, walls, a locked door |
| `arrive`, `leave` | someone comes in or goes, from their side |
| `say`, `whisper`, `shout`, `sent`, `announce`, `offer` | talking; your own words going out; the Bridge; an invitation |
| `emote`, `emote_smile`, `emote_wave`, `emote_laugh`, `emote_nod`, `emote_shrug`, `emote_clap`, `emote_cheer`, `emote_sigh`, `emote_bow`, `emote_dance`, `emote_hug` | gestures |
| `success`, `fail`, `error`, `mission`, `task`, `tone1` to `tone4` | work, a mission, a task starting, the reactor's tones |
| `coins`, `register` | money changing hands; a shop's till |
| `mine`, `rare`, `plant`, `water`, `harvest`, `ripe` | mining, a rare find, the farm |
| `levelup`, `daily` | a new level; the daily bonus |
| `equip`, `gadget`, `scan`, `air`, `rescue`, `gulp`, `crunch`, `pet_robot`, `pet_cat` | things: wearing, devices, the scanner, the air warning, the tow, food, pets |
| `bell`, `lantern` | the temple's star bell; lighting a lantern |
| `launch`, `landing` | shuttles |
| `amb_vent`, `amb_cantina`, `amb_engine`, `amb_garden`, `amb_deck`, `amb_space`, `amb_belt`, `amb_venue` | the ambience loops (4 seconds, seamless) |

The generated set: 104 files, about 6.3 MB (4.7 MB zipped).

## Tests

From Hariku's source folder (they run on Windows or Linux, and use only this
computer):

```sh
python -m pytest tests/test_orbit_server.py tests/test_orbit_map.py tests/test_orbit_economy.py tests/test_orbit_compat.py tests/test_orbit_e2e.py -q
```

`tests/orbit_parse_1_0.py` is a frozen copy of the 1.0 client's command
reader: `test_orbit_compat.py` checks that every command added later still
reaches the server from it.

## Later (not in 1.1)

- **Companions:** a pet is already a general `companions` record (its kind,
  name, JSON stats and state, when it came, and its owners in
  `companion_owners`), so later versions can add feeding and attention,
  growing up and learning tricks, several kinds, and companions shared by two
  players, without another big migration.
- **Families:** two players partnering up with consent, and a baby companion
  that needs care, grows into a child, and follows and helps its family.
- **Ceremonies at the venues** (the Star Dome Hall and the Jasmine Pavilion
  are marked `venue` in world.json): a wedding with two lanterns joined into
  one light, a moment of silence, vows the two write themselves and three
  chimes of the star bell (and a neutral ceremony without the temple); a
  naming ceremony for a baby companion; and the yearly Lantern Festival of
  the Way of Starlight as a station-wide event.
