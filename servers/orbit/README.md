# Orbit server

Orbit is a small multiplayer text game (a MUD) set in a shared simulation:
players enter at a space station orbiting the Earth, its hub, and travel on
to other worlds (the Moon, the red planet Karmina, the ice moon Glasir, the
Drift Bazaar, the fantasy world Evergrove, Lumina City and Pixel Pier). It is
played through Hariku's **Orbit** extension (`extensions/orbit`). This folder is the server: Python 3.10 or
newer, **standard library only**, one process, one SQLite file. The server
decides everything (movement, money, things, progress); the client only sends
commands and shows or speaks the results.

**Orbit is played in English** (since 1.4): everything the server says is
English, whatever language a client asks for, and it reads English commands
and English names. Words in another language get its help hint.

Since 1.5, "x here" says what can be done in the room you're in, a command a
line, and "x" and a name what can be done with someone or something; and a
reply of several parts (a room, your things, who is online, a list) goes to
clients from 1.6 as lines, one part each, so the Messages box reads them one
by one (see Protocol: `lines`).

Since 1.6 the rooms and the people in them feel the way the Nova Realm did:
you sit, lie down, sleep and stand on the rooms' furniture (bar stools,
benches, the lawn, your bunk and sofa) and others see it; walking stands you
up first; `exits` (or `ex`) says where each way out leads, a line each, and
`peer north` glimpses the next room; you follow someone, or lead them, after
they say yes; there are more gestures (kiss, wink, high five...), your own
(`emote waves hello`, `:waves hello`), dice for the room (`roll 2d6`), the
time, `afk`; things can be dropped, picked up, put on a table, thrown and
caught; `again` repeats your last command, and a near miss gets "did you
mean". Rooms have more to look at, lines of their own now and then, and new
places (Willow Nook and its fishing pond, the Crew Lounge, the Reading Room,
the Starboard Gallery, the Sky Terrace), the Cantina a jukebox, and the food
counters more to eat. See [The room and its people](#the-room-and-its-people-16).

It listens on `127.0.0.1` behind the web server, which handles TLS and passes
`/orbit/` on to it:

| Path | What |
|---|---|
| `GET /orbit/ws` | the game, over WebSocket |
| `GET /orbit/health` | `{"ok": true, "service": "orbit", "version": "1.6", "protocol": 1, "online": 3}` |

`/ws` and `/health` work too, for a proxy that strips the `/orbit` prefix.

## Files

| File | What |
|---|---|
| `orbit_server.py` | the program: HTTP, WebSocket connections, limits, the tick |
| `orbit_ws.py` | the WebSocket protocol (RFC 6455), shared with the Hariku extension |
| `orbit_game.py` | the game's core: joining, talking, looking, time passing (no I/O) |
| `orbit_nav.py` | walking by compass, the way (compact) and the guide, maps, dark rooms, locks, air, the Wombat, cabins |
| `orbit_items.py` | things: shops, using, wearing, examining, food, the temple |
| `orbit_work.py` | jobs and their mini-games, XP and levels, missions, the daily bonus |
| `orbit_econ.py` | the markets (prices where you stand, the way to the nearest), the farm, mining and salvage, profiles, the economy's totals |
| `orbit_casino.py` | the Casino Corner: dice, slots, blackjack, coin flips, the weekly lottery |
| `orbit_trade.py` | trading between players (offer, accept), and the pawn shop |
| `orbit_progress.py` | achievements and the leaderboards |
| `orbit_travel.py` | the worlds: the Gate, the ferry, players' own ships, customs |
| `orbit_local.py` | the other worlds' own work: Evergrove's creatures, Lumina City's courier gigs |
| `orbit_events.py` | events: random, weekly, seasonal, parties, the co-op drone, admins' events |
| `orbit_arcade.py` | Pixel Pier's arcade: four cabinet games, tokens, prize tickets, high scores |
| `orbit_crews.py` | crews: founding, invitations, crew chat, the captain, points and the board |
| `orbit_duels.py` | duels: quick-draw contests between two players in the contest zones |
| `orbit_npcs.py`, `npcs.json` | the residents who aren't players: their days, talking, topics, memory and affinity |
| `orbit_pets.py` | pets: feeding, playing, resting, growing up, tricks, finds on the worlds |
| `orbit_family.py` | families: partners (both agree), adopting, children growing up, the naming rite |
| `orbit_weddings.py` | weddings: the ring, booking a hall, invitations, the two ceremonies, the memory |
| `orbit_here.py` | "x here": what can be done in this room, and "x" and a name: with someone or something |
| `orbit_social.py` | postures (sit, lie, sleep, stand, wake), following and leading, exits and peering, your own emote, dice, the time, afk, the rooms' own lines |
| `orbit_floor.py` | things dropped, picked up, put on a table, thrown and caught; the cleaning drone |
| `orbit_pastimes.py` | the Cantina's jukebox and the fishing pond in Willow Nook |
| `orbit_hunt.py` | the hunt (the Lost Chord): seasons of riddles, clues, answers kept only as hashes, the rival |
| `orbit_hunt_tool.py`, `hunt.example.json` | a season's server file from its authoring file; a fake demo season |
| `orbit_admin.py` | moving a character to another computer; the admins' commands |
| `orbit_verbs.py` | the commands the server reads from plain text (English) |
| `orbit_world.py`, `world.json` | the map: worlds, rooms, compass exits, objects, goods, missions, gestures |
| `economy.json` | the balance: levels, ranks, the daily bonus, crops, mining, the shops' things |
| `orbit_earth.py` | what you see from the Observation Deck, from the real time |
| `orbit_lang.py`, `texts.json` | everything the server says, in English; a reply's lines, and the same as one line |
| `orbit_safety.py`, `words.json` | names, the word filter, rate limits |
| `orbit_store.py` | saving (SQLite), and migrating older databases |
| `orbit_backup.py`, `orbit-backup.service`, `orbit-backup.timer` | a daily copy of the database |
| `config.example.json` | a configuration to copy to `config.json` |
| `orbit.service` | a systemd user unit |

`world.json`, `economy.json`, `npcs.json` and `texts.json` are only read;
everything that changes while people play is in the database.

## Running it

On the VPS (Ubuntu 22.04, Python 3.10, user `rafli`), in `~/orbit/`:

```sh
mkdir -p ~/orbit
# copy this folder's files there: orbit_*.py, *.json, orbit*.service, orbit-backup.timer
cd ~/orbit
cp config.example.json config.json        # then put your character's name in "admins"
python3 orbit_server.py --config config.json
# "Orbit 1.6 listening on 127.0.0.1:7340"; Ctrl+C stops it
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

### Updating to 1.6 (the room and its people; no migration)

1. Copy these files to `~/orbit/`, never `private/`. New in 1.6: `orbit_social.py`,
   `orbit_floor.py`, `orbit_pastimes.py`. Changed: `orbit_game.py`, `orbit_nav.py`,
   `orbit_verbs.py`, `orbit_here.py`, `orbit_items.py`, `orbit_work.py`, `orbit_events.py`,
   `orbit_trade.py`, `orbit_npcs.py`, `orbit_econ.py`, `orbit_world.py`, `orbit_server.py`,
   `world.json`, `economy.json`, `npcs.json`, `texts.json` (copying the whole folder but
   `private/`, as before, is just as good). `words.json` and the service files are
   unchanged, and `config.json` needs no new keys.
2. `systemctl --user restart orbit` (players hear that the station's computer restarts,
   and their Orbit reconnects by itself).
3. **The database stays at version 8: there is nothing to migrate**, so no copy is made
   and the log has no migration line. What's new is kept like this:
   - things put down in a room are in the `meta` table, key `floor` (JSON, saved in the
     same transaction as the character who put them down or picked them up), so a
     restart keeps them; after half an hour a cleaning drone gives them back to whoever
     put them down, online or not, and nothing is lost or made;
   - postures, following and leading, being away from the keyboard, a line in the pond,
     a thing in the air and the jukebox's song live in memory: a restart stands everyone
     up (the same as logging out) and forgets them;
   - the daily count of fish and each player's biggest catch are in the character's
     `stats` (JSON), like the other counters.
4. Returning players hear once what's new in 1.6 (`whats_new_16`), after the older notes
   they missed.
5. The 1.0 to 1.6 clients keep working: every new command reaches the server from them
   as plain text (`exits`, `sit on the sofa`, `kiss Maya`, `drop coffee`...), and "take",
   "get" and "pick up", which every client reads as `take`, now also pick up what lies
   in the room. "stand" is blackjack's only while you're playing a hand; otherwise it's
   the posture, from every client. Their own "again" still says the last message again
   (client 1.7's sends "again" to the server: the last command). Client 1.7 says hello as
   `"client": "Hariku Orbit 1.7"` and reads your own replies aloud whatever its "Read
   aloud" boxes say.
6. Check: `curl -fsS http://127.0.0.1:7340/orbit/health` says `"version": "1.6"`; in the
   game, `exits` in the Cantina says "Exits from the Cantina: East: the West Promenade;
   West: the Casino Corner." (line by line with Orbit 1.6 or 1.7), `sit` answers "You sit
   down on a bar stool.", and `help social` lists the rest.

### Updating to 1.5 ("x here", replies line by line; no migration)

1. Copy these files to `~/orbit/`, never `private/`. New in 1.5: `orbit_here.py`.
   Changed: `orbit_arcade.py`, `orbit_casino.py`, `orbit_crews.py`, `orbit_econ.py`,
   `orbit_events.py`, `orbit_family.py`, `orbit_game.py`, `orbit_hunt.py`,
   `orbit_items.py`, `orbit_lang.py`, `orbit_local.py`, `orbit_nav.py`, `orbit_npcs.py`,
   `orbit_pets.py`, `orbit_progress.py`, `orbit_server.py`, `orbit_trade.py`,
   `orbit_travel.py`, `orbit_verbs.py`, `orbit_weddings.py`, `orbit_work.py`,
   `orbit_world.py`, `texts.json` (copying the whole folder but `private/`, as before, is
   just as good). `world.json`, `economy.json`, `npcs.json`, `words.json` and the service
   files are unchanged, and `config.json` needs no new keys.
2. `systemctl --user restart orbit` (players hear that the station's computer restarts,
   and their Orbit reconnects by itself).
3. **The database stays at version 8: there is nothing to migrate**, so no copy is made
   and the log has no migration line. Nothing new is stored: "x here" is worked out from
   the room, the players and residents in it and the character, each time it's asked.
4. Returning players hear once what's new in 1.5 (`whats_new_15`), after the older notes
   they missed.
5. The 1.0 to 1.5 clients keep working, and get every reply as one line, as before: the
   parts of a list are joined with "; " and end with "." (`orbit_lang.one_line`), so a
   room, "who", the prices and the rest read the way they always did. A few lists that
   were joined with "and" (your things, your achievements) now read "You carry: a
   compass; 3 sacks of coffee." They send "x here", "what can I do here" and "x Rocco"
   as plain text, which the server reads (`orbit_verbs.py`); clients 1.1 to 1.5 send
   "help here" and "commands here" as the help topic "here", which is "x here" too. Only
   their "examine" still means look. Client 1.6 says hello as `"client": "Hariku Orbit
   1.6"`, gets the `lines` too, and sends `examine`.
6. Check: `curl -fsS http://127.0.0.1:7340/orbit/health` says `"version": "1.5"`; in the
   game, "x here" in the Cantina starts with "Here in the Cantina you can:" and ends with
   "Type help for everything else.", and, with Orbit 1.6, "l" puts the room's name, its
   description and its exits on lines of their own in the Messages box.

### Updating to 1.4 (English only, English names; no migration)

1. Copy these files to `~/orbit/`, never `private/`: `orbit_admin.py`,
   `orbit_arcade.py`, `orbit_casino.py`, `orbit_crews.py`, `orbit_duels.py`,
   `orbit_earth.py`, `orbit_econ.py`, `orbit_events.py`, `orbit_family.py`,
   `orbit_game.py`, `orbit_hunt.py`, `orbit_hunt_tool.py`, `orbit_items.py`,
   `orbit_lang.py`, `orbit_local.py`, `orbit_nav.py`, `orbit_npcs.py`,
   `orbit_pets.py`, `orbit_progress.py`, `orbit_server.py`, `orbit_store.py`,
   `orbit_trade.py`, `orbit_travel.py`, `orbit_verbs.py`, `orbit_weddings.py`,
   `orbit_work.py`, `orbit_world.py`, `world.json`, `npcs.json`,
   `economy.json`, `texts.json`, `hunt.example.json` (copying the whole
   folder but `private/`, as before, is just as good). No new files, and
   `config.json` needs no new keys; `words.json` (the word filter, still
   English and Indonesian: players may type anything) is unchanged.
2. `systemctl --user restart orbit`.
3. **The database stays at version 8: there is nothing to migrate.** Every id
   is the same (rooms, things, goods, events, residents), so characters,
   their things, pets, families, weddings, the residents' memory, crews,
   high scores and the hunt's progress keep their meaning; only names, words
   and descriptions changed. The ids still work as names too, so "buy
   martabak" or "talk to jali" still find the stuffed pancake and Rocco. A
   pet keeps the name it has; new pets are called Marmalade, Tinker and Dusk
   instead of Oyen, Timah and Senja.
4. Returning players hear once what's new in 1.4 (`whats_new_14`: English
   only, and the new names of the markets, the shuttles, the foods and the
   residents), after the older notes they missed.
5. The 1.0 to 1.4 clients keep working: every structured command they send
   is the same, and the server answers in English even when their hello says
   `"lang": "id"`. What they send as plain text is read in English only
   ("way to the cantina", "guide me to the cantina", "u" for up); Indonesian
   words ("arah ke kantin", "harian", "utara") get the help hint,
   `I don't understand "...". Type help for the commands.` Client 1.5 is
   English only too (its window and settings, and it no longer reads
   Indonesian itself).
6. The hunt: nothing to rebuild. A season's server file may keep its other
   languages beside `"en"` (the private seasons are bilingual); the server
   shows only the English riddles, texts, hints and the rival's name, and
   any answer the season accepted (in any language) is still right, since
   answers are compared by their hashes.
7. Check: `curl -fsS http://127.0.0.1:7340/orbit/health` says `"version":
   "1.4"`; in the game, "help" answers in English, "u" goes up, and "talk to
   Rocco" in the Cantina works.

The renames players meet most (ids unchanged):

| Before 1.4 | Now |
|---|---|
| the Kancil (the mining shuttle to the Belt) | the Wombat ("ride the Wombat") |
| the Merpati (the cargo shuttle to the Moon) | the Dove |
| sweet martabak | stuffed pancake |
| kangkung, kangkung seeds | water spinach, water spinach seeds |
| kerupuk (as a name) | prawn crackers |
| batik rug, batik shirt | woven rug, rocket-print shirt |
| Bang Jali (the Cantina) | Rocco |
| Pak Harsa (Engineering) | Oskar |
| Ibu Sekar (the Star Dome Hall) | Amara |
| Kelana (the Observation Deck at night) | Soren |
| Mas Tegar (Gearworks) | Felix |
| Kak Nilam (Whiskers & Widgets) | Priya |
| Bu Safira (Starglint Jewellers) | Celeste |
| Kapten Bayu (the Dock) | Captain Mateo |
| Laras | Poppy |
| Bayang (the Drift Bazaar's back alley) | Shade |
| Ciko (the Tournament Stage) | Dario |
| Pak Gino | Gino |
| Mbak Tari | Hana |
| Nenek Rimba (Evergrove) | Granny Fern |

The places, the markets (the Spice Market, the Ice Depot, the Mineral
Exchange, the Workshop's parts counter and the other worlds' markets), the
shops, the worlds, the ships, the events and the titles already had English
names and keep them.

### Updating to 1.3 (markets where you stand, the guide; no migration)

1. Copy these files to `~/orbit/`, never `private/`: `orbit_econ.py`,
   `orbit_game.py`, `orbit_items.py`, `orbit_nav.py`, `orbit_npcs.py`,
   `orbit_server.py`, `orbit_trade.py`, `orbit_travel.py`, `orbit_verbs.py`,
   `orbit_work.py`, `orbit_world.py`, `world.json`, `npcs.json`, `texts.json`
   (copying the whole folder, as before, is just as good). No new files, and
   `config.json` needs no new keys.
2. `systemctl --user restart orbit`.
3. **The database stays at version 8: there is nothing to migrate**, so no
   copy is made and the log has no migration line. What is stored keeps its
   meaning: the station's prices (meta `market`, by good, with an admin's
   price for the hour), each world's own (`market_worlds`, by world) and an
   event's boom or crash (by world and kind). A good is traded at one market
   on each world (the server refuses a `world.json` that breaks this), so the
   station's stored price for coffee is simply the Spice Market's now, and the
   Mineral Exchange's for iron. Characters stay where they were (the
   Promenade is still there, with a signpost to the markets); the new rooms
   are on everyone's map; a character's rooms known and missions are
   untouched.
4. Returning players hear once what's new in 1.3 (and in 1.2 and 1.1, if they
   missed those).
5. The 1.0 to 1.3 clients keep working: `prices`, `buy` and `sell` are the
   same commands, and "guide me to the cantina" and "stop guide" reach the
   server as plain text. The guide's lines are
   ordinary `info` events; the arrival's `sound` (`gadget_arrived`) falls back
   to `gadget` in clients from 1.1 (1.0 plays nothing). Client 1.4 only makes
   "orbit connect" connect and "orbit disconnect" disconnect (it was one
   toggle).
6. Check: `curl -fsS http://127.0.0.1:7340/orbit/health` says `"version":
   "1.3"`; in the game, "prices" on the Promenade names the markets and the
   way to each.

### Updating to 1.2 (the database migrates by itself)

1. Copy every file of this folder to `~/orbit/`, but never `private/`. New
   in 1.2: `orbit_npcs.py`, `npcs.json`, `orbit_pets.py`,
   `orbit_family.py`, `orbit_weddings.py`; changed: the other `orbit_*.py`,
   `world.json`, `economy.json`, `texts.json`. `config.json` needs no new
   keys (`npcs` names another residents' file, if you ever want one; by
   default the one next to the program is read).
2. `systemctl --user restart orbit`.
3. On its first start, the server sees a version 7 database (Orbit 1.1's),
   saves a copy of it as `orbit.db.before-v8.bak` next to it, and migrates
   it to version 8 in one transaction: one new column, `duels_won` (filled
   from the duels each character already won, for the new leaderboard), and
   four new tables, `npc_memory`, `partnerships`, `weddings` and
   `wedding_guests`. Nothing is dropped or changed; a 1.0 database goes all
   the way from 0 to 8 at once. The log says "the database was migrated
   from version 7 to 8". If the migration fails, nothing is changed and the
   server stops with the error in the log; the copy is there.
4. Pets bought before 1.2 start on the first day of 1.2 as if new (fed and
   content, 80 of 100, and little).
   Returning players hear once what's new (from 1.0: both notes).
5. The 1.0 and 1.1 clients keep working: everything new goes as plain text
   and comes back as ordinary lines. The 1.2 client adds the new sounds and
   the celebration's ambience at a wedding.
6. Check: `curl -fsS http://127.0.0.1:7340/orbit/health` says `"version":
   "1.2"`, and `journalctl --user -u orbit -n 20` shows the migration line.

### Updating to 1.1 (the database migrates by itself)

1. Copy every file of this folder to `~/orbit/`, but never `private/` (the
   hunt's seasons: see below) (new in 1.1: `economy.json`,
   `orbit_nav.py`, `orbit_items.py`, `orbit_work.py`, `orbit_econ.py`,
   `orbit_casino.py`, `orbit_trade.py`, `orbit_progress.py`, `orbit_travel.py`, `orbit_local.py`,
   `orbit_events.py`, `orbit_arcade.py`, `orbit_crews.py`, `orbit_duels.py`,
   `orbit_hunt.py`, `orbit_hunt_tool.py`, `hunt.example.json`,
   `orbit_admin.py`, `orbit_verbs.py`, `orbit_backup.py`,
   `orbit-backup.service`, `orbit-backup.timer`; changed: the other
   `orbit_*.py`, `world.json`, `texts.json`). `config.json` needs no new
   keys: every new setting has a default (below).
2. `systemctl --user restart orbit`.
3. On its first start, the server sees an older database (Orbit 1.0's is
   schema version 0), saves a copy of it as `orbit.db.before-v7.bak` next to
   it, and migrates it to version 7 in one transaction: new columns (voice,
   XP, the daily streak, what a character mined and harvested, what it won
   or lost at the casino) and new tables (companions, ships, events and who
   took part in them, hunt progress, arcade high scores,
   crews and their members, achievements, lottery tickets, transfer codes, old
   secrets, transfers, the admins' log) are added; nothing is dropped or
   changed, and work done before 1.1 counts as XP (10 a repair, 20 a cargo
   run, 25 a mission). The log says "the database was migrated from version
   0 to 7". If the migration fails,
   nothing is changed and the server stops with the error in the log; the
   copy is there.
4. Every room of 1.0 still exists, so characters wake up where they were.
   Returning players are told once what's new, and get a compass (and the
   keycards their XP already earned, and quietly the achievements their
   past work already reached).
5. The hunt starts only when `config.json` names a season file (`"hunt"`;
   see [The hunt](#the-hunt-the-lost-chord)).

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
| `world`, `economy`, `npcs`, `texts` | the bundled files | the map, the balance, the residents, the lines |
| `words` | `words.json` | the word filter's list (Indonesian and English; edit freely) |
| `hunt` | `""` (none) | the hunt's season file, e.g. `private/season1.hunt.json` (never in the repository) |
| `max_connections`, `max_per_ip` | 200, 8 | connections at once, in all and from one address |
| `max_message` | 4096 | the largest message a client may send, in bytes |
| `rate`, `burst`, `abuse_limit` | 5, 15, 40 | messages a second from one connection, a quick burst, and how many dropped messages before it is closed |
| `idle_timeout`, `hello_timeout` | 120, 20 | seconds of silence before a connection is closed; seconds to say hello |
| `linger_seconds` | 2 | after the server closes a connection, how long it reads on what the client still sends (see Closing codes) |
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
| `game.events_enabled` | true | events that start by themselves (false: only what admins start or schedule) |
| `game.events_random`, `game.events_seasonal` | true, true | the random events; the station's birthday, New Year, the Lantern Festival |
| `game.events_min_gap`, `game.events_max_gap` | 1800, 3600 | seconds between random events with one player online... |
| `game.events_crowd_factor`, `game.events_min_factor` | 0.1, 0.5 | ...each extra player online makes the gap 10% shorter, down to half |
| `game.events_party_cooldown` | 7200 | how often one player may throw a party |
| `game.events_weekly` | trading fair Saturday 14:00, jackpot night Friday 13:00, night rush Wednesday 13:00, the duel tournament Sunday 15:00 | `[{"event", "weekday" (0 Monday), "hour", "minute"}]`, in UTC |
| `game.hunt_admins_compete` | false | admins on the hunt's board and in its prizes (they can know the answers) |
| `game.hunt_wrong_base`, `game.hunt_wrong_max` | 60, 86400 | seconds to wait after a wrong answer, doubling each time up to this |

### The balance (economy.json)

Everything in `economy.json` can be changed; it's read when the server starts.
What 1.3 ships with:

- **The markets** (world.json, a room's `market`): the station's goods are
  traded at four rooms, each dealing in its own, both buying and selling:

  | Market | Where | Goods |
  |---|---|---|
  | the Spice Market (`spice_market`, new) | west of Hydroponics, Main Deck | coffee, spices, every crop |
  | the Ice Depot (`ice_depot`, new) | north of the Cargo Bay, Lower Deck | comet ice, helium-3, frost pearls |
  | the Mineral Exchange (`mineral_exchange`, new) | north of the Dock, Lower Deck (east to the Ice Depot) | iron, nickel, titanium, platinum, quantum crystals, meteorites, rust salt, ember crystals |
  | the Workshop's parts counter (`workshop`) | east of Engineering, Lower Deck | scrap, circuit boards, satellite chips, gold foil, memory chips |

  The Promenade trades nothing now; its signpost (`look at the signpost`)
  lists the markets, what each deals in and the way. A market's `buys` and
  `sells` name kinds of goods (`crop`) or goods (`coffee`), with a `factor`
  for all its prices, `prices` for single goods and `about` (what it deals
  in, in words); `"market": true` still means every legal good. A good is
  traded at one market on each world, checked when the server starts, so a
  world's prices are its market's and nothing can be bought at one counter
  and sold dear at the next. The station's markets and the other worlds'
  main markets are landmarks (anyone may ask the way); the Drift Bazaar's
  back alley isn't. `prices` and `list` in a market say what it
  buys and sells at its prices (by kind; `prices crops`, `prices coffee`);
  in a shop or the pawn shop, their own list. Anywhere else, `prices`,
  `buy` and `sell` name the nearest market for what was asked, with the
  compact way there ("Nearest market for coffee: the Spice Market, north,
  then 2 west."; the deck instead, where the player may not ask the way);
  `way to the market` is the nearest one. The trader's report (work) says
  where each good is traded, and so does Rocco's market gossip; a
  Hornbill's scanner bay still reads another world's markets, as a report.
- **The way** is said in runs ("2 east, south, up, north, then 2 west";
  "up 3 levels"), with the number of steps when it is 8
  or more in three runs or more, and it **guides**: after each step one
  short `info` line says the next run ("Then 2 west."), a step off the
  route finds the way again ("Off the route. From here: south."), and
  arriving says so ("You've arrived at the Cantina.", `sound`
  `gadget_arrived`). `guide` alone repeats what's left; `stop guide` ends it,
  and so do logging out, the Gate, the ferry and boarding a ship. The guide
  keeps to the doors the player can open, takes one-way exits only their
  way, rides the Wombat when that's the way, knows the next step in the dark
  and says when the next one needs a worn EVA suit. It lives in the session,
  in memory: a reconnect within the link-dead minute keeps it, a restart
  forgets it (the player asks the way again).

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
  minutes (5 after a cargo run); a stuffed pancake halves the next one.
- **The daily bonus:** 40, then 15 more for each day in a row, up to 130 on
  the seventh; every seventh day also 3 strawberry seeds. Missing a day
  starts again at 40.
- **The farm:** 2 plots to start, up to 8 (150, 250, 400, 600, 900, 1,300
  credits each). Crops (seed price, time, yield, market price): water spinach 5,
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
  600 to 1,600, pet food 6 and treats 15, rings 500 to 4,000), seeds, food
  (3 to 20), adopting (300), weddings (1,000 to 10,000, less what a
  cancellation gives back), plots, the Wombat's fare (5 from the
  Dock; pilots ride free), the tow when your air runs out (20), lanterns
  in the temple (3), the casino's edge, the lottery's cut, and the market's
  fees (10% on buying and 12% on selling; traders 2% and 4%, less with their
  tools), which also make every sale move the price down 2%.
- **The shops** are Star Supply on the East Promenade (the basics) and the
  Mall Ring, up the lift from the Upper Lift Lobby: Gearworks (devices,
  keycards, the suit, drills, job tools), Orbit Outfitters (clothes, titles),
  Cosy Corner (furniture), Whiskers & Widgets (pets), Starglint Jewellers
  (rings, and the wedding desk), the Food Court, and Second Orbit, the pawn
  shop. Prices move up to 10% either way each day
  (`prices.wobble`), the same for everyone that day, and one thing in each
  shop is today's special, 20% cheaper still (`prices.special`); the bar,
  the seed rack and the lottery booth keep fixed prices, and so do plots.
  Second Orbit pays 40% of a thing's list price (`pawn.rate`) for anything
  but goods, pets, services and what can't be sold (the compass, keycards,
  earned titles).
- **Trading:** `offer Sam 3 iron for 200 credits`; the other player (online,
  anywhere) has 2 minutes (`trading.seconds`) to accept. Goods, mission
  cargo, seeds, food, furniture and clothes (without a level) can be traded
  and given; devices, keycards and titles can't. Both sides move in one
  database transaction or not at all.
- **The casino** (`casino` in economy.json), in the Casino Corner west of
  the Cantina: bets of 5 to 500 credits, at most 5,000 an hour, 3 seconds
  apart; a win of 1,000 or more is news for the whole station. Every game
  keeps an edge for the house, checked by the tests from these numbers:
  dice high (8-12) or low (2-6) pay 2.3 times the bet (a 4.2% edge), seven
  5.5 times (8.3%); the slots' three reels (weights star 8, moon 6, comet
  4, planet 3, rocket 2, Orbit 1; three of a kind pay 3, 7, 14, 25, 50 and
  200 times, two Orbits 6, two rockets 2, any other pair the bet back) return
  about 92%; blackjack (the dealer peeks and stands on 17, a win pays 2 to 1
  back, a natural 2.5) returns 97.6% even played perfectly; a coin flip
  between two players costs each 5% (`coinflip.fee`); the weekly lottery
  (10 credits a ticket, up to 50 a week, drawn on Sunday at 12:00 UTC) pays
  80% of the tickets sold to one ticket drawn at random, and a week without
  tickets carries the pot over. What each player won or lost is kept
  (`casino_net`) for the casino leaderboard. Credits have no real-money
  value; the menu and the help say so.
- **Achievements** (`achievements`): 35, each for reaching a number (rooms
  walked, shifts worked, missions, level, crops, ore, a golden chilli, a
  quantum crystal, the daily streak, furniture, credits held, the time
  capsule, a natural, a jackpot, the lottery, a trade, the worlds, a ship,
  events, arcade games, a high score, a crew, duels won), paying 0 to 2,000
  credits and sometimes a title; the big ones (`station`) are news for
  everyone, and the first to earn one is named as the first on the station.
- **Leaderboards:** richest, level, miners, farmers, daily streak, casino and
  duels, the top 5 and your own place; admins are left out.
- **The arcade** (`arcade` in economy.json; see `orbit_arcade.py`): a token
  costs 5 credits (the token machine on Cabinet Row sells up to 100 at a
  time) and plays one game. Prize tickets: Quick Draw points × 0.02 (five
  rounds of up to 100: 100 at 0.2 seconds, none at 2), Star Beat points ×
  0.0067 (three rhythms of 5, 6 and 7 beats, up to 100 a gap, none when a
  gap is 40% off), Echo 2 for each tone past 3, Meteor Dodge one for every
  two dodged (3 seconds to step away at first, 0.1 less each time, down to
  1.5); at most 10, 10, 20 and 20 a game; a new best on a game's table 25
  more. Prizes, for tickets only: a plush comet 40, glow stars 100, a mini
  arcade cabinet 300, the title Arcade Ace 500, the enormous robot 2,500.
  Tokens are spent credits; tickets and prizes can't be sold, traded or
  pawned, so the arcade only takes money out.
- **Worlds and travel** (`worlds` in world.json, `travel` in economy.json).
  Each world sits at a position on one long orbit (the station 0, the Belt 1,
  the Moon 2, Lumina City 3, Pixel Pier 4, Evergrove 5, Karmina 6, the Drift
  Bazaar 7, Glasir 8); the distance between two is the difference (at least
  1). The Gate: at once, 25 credits and 10 a unit of distance (the Moon 45,
  Glasir 105). The ferry: 5 credits and 3 a unit (the Moon 11, Glasir 29),
  leaving every 2 minutes and taking 40 seconds a unit (at least a minute).
  Your own ship: 25 seconds a unit divided by its speed (a pilot flies a
  quarter faster), burning fuel at each world's price (2 to 6 credits a
  unit). The Belt is still the Wombat's.
- **Ships** (the Orbit Shipyard on the Mall Ring; one each, a new one trades
  the old in for half its list price): the Swiftlet shuttle (2,500, level 2:
  hold 40, tank 24, speed 1), the Heron courier (9,000, level 5: 60, 40,
  1.7), the Buffalo hauler (16,000, level 7: 200, 60, 0.8, thirsty), the
  Hornbill explorer (40,000, level 12: 120, 100, 1.5, and a scanner bay that
  reads other worlds' prices and halves the chance of a customs search).
- **Markets on other worlds** start from the station's prices times the
  world's own factor for each good (ice 0.45 on Glasir and 2.0 on Karmina,
  helium-3 0.55 on the Moon and 1.8 in Lumina, spices 0.55 at the Bazaar and
  1.6 on Glasir and in Evergrove...); each world's prices wander by 3% every
  few minutes and move 1% with every unit traded there, coming back 15% of
  the way each time (economy.json `travel.market`). New goods: helium-3,
  red quinoa, rust salt, frost pearls, moonpetals, ember crystals, and two
  kinds of contraband (star orchids, ghost chips) sold only in the Bazaar's
  back alley and bought only at Lumina's Night Market.
- **Customs:** arriving with contraband on a world that checks (the station,
  the Moon and Karmina fully, Glasir and Lumina 0.8, Pixel Pier 0.5; the
  Bazaar, Evergrove and the Belt never), the chance of a search is 60% by
  the Gate, 35% by the ferry, 25% by ship (half with a scanner bay), times
  the world's own; a search takes all contraband and fines half its usual
  value.
- **Events** (world.json `events`; see `orbit_events.py`): 22 in all. Random,
  every 30 to 60 minutes while someone is online (sooner when more are),
  never two big ones at once, each with its own cooldown: a meteor shower
  (collect meteorites, 5 each, at the Observation Deck, on the hull walk or
  the Moon's Sea of Dust), a solar storm (engineers' repairs pay half
  again), a cargo spill (8 to 20 credits a crate, 6 each), a runaway robot
  pet and a stowaway (hidden in one of 39 station rooms; listen or search
  says which way; 120 and 100 credits to whoever finds them, security
  double), a market boom or crash (one world, one kind of goods, a third up
  or down), a double XP hour, happy hour (the bar and the Food Court half
  price), a comet flyby (watch for 20 credits), a power outage (seven rooms
  dark), a dust storm on Karmina (join in the shelter for 30), and the
  runaway drone at the Dock (at least two online; strength 10 + 8 for each
  player online; each successful tug does 1 or 2; everyone who helped gets
  40 + 15 a point, at most 300, or 10 if it gets away). Weekly: the trading
  fair (the Mall Ring a fifth off for two hours), jackpot night (three of a
  kind pays double), the night rush (courier gigs pay double), the duel
  tournament (see [Duels](#duels)). Seasonal:
  the station's birthday on 25 September (100 credits and an iced coffee
  each), New Year (watch the fireworks for 50), the Lantern Festival on the
  hundredth day of the year (free lanterns, a 25-credit thank-you, and a
  gift for everyone when 30 are lit: see [The Way of
  Starlight](#the-way-of-starlight)).
  Parties: a player's cabin is open to everyone for half an hour, once in
  two hours. Admins can start, stop and schedule events.
- **The worlds' work:** helium-3 in the Moon's tunnels (mining, like the
  Belt); collecting in Karmina's farming domes, on its Rust Flats, in
  Glasir's ice quarry and its blue crevasse; Evergrove's creatures (a d20
  plus half your level against 6 to 14; a win gives a moonpetal or an ember
  crystal and 5 to 14 XP, a loss only a 20-second wait); Lumina's courier
  gigs (20 credits and 12 a step, raised by your level, within 25 seconds
  and 14 a step, 8 XP).
- **The EVA suit** holds 3 minutes of air, an oxygen tank 3 more; warnings at
  60 and 20 seconds.

The admins' **economy** report shows the credits in circulation (all
characters), the richest, and every credit earned by source (work,
missions, daily, market, finds, pawn, casino wins, lottery prizes,
achievements, events, favours, weddings (what cancellations gave back),
admin) and spent by sink (shops, market, fares, rescues, lanterns, casino
bets, lottery, adoption, weddings, admin), so you can see whether money grows
too fast and adjust these numbers.

## The room and its people (1.6)

What the Nova Realm did, in Orbit's words (`orbit_social.py`, `orbit_floor.py`,
`orbit_pastimes.py`). Every command is attached to where it works, and says so
briefly where it doesn't ("The jukebox is in the Cantina."); `x here` lists what's
attached to the room you're in.

- **The ways out:** `exits` (or `ex`) says each exit on a line of its own with where
  it leads, in the Nova Realm's order (north, northeast, east... up, down), and
  what's special: "Southwest: the Maintenance Junction (locked, dark)", "South: the
  Hull Walkway (vacuum: an EVA suit)", "Down: the Service Corridor (one way)",
  "North: the Crew Hangar (crew only)", "Ride the Wombat: to the Belt Platform". A
  secret room you haven't found is "a way you haven't explored yet"; in the dark
  you only feel the way you came in. `peer north` glimpses the next room: its name,
  the first sentence of its description, who's there (and sitting or asleep),
  residents and what lies about; the room sees you peer.
- **Postures:** `sit`, `sit on the sofa`, `lie down`, `lie on the lawn`, `sleep`,
  `stand` (or `stand up`, `get up`) and `wake`. A room's furniture is an object's
  `seat` in world.json: `{"n": how many at once, "at": {"en": "on a bar stool"},
  "lie": true, "lie_at": {...}, "sit": false, "full": {"en": "Every bar stool is
  taken."}}`; in a cabin, its owner's sofa and hammock count too (their `seat` in
  economy.json). Without one you sit on the floor, or the grass, sand, snow, dust or
  ground by the room's floor (a room's `sit_at` and `lie_at` for the ferry, the
  shuttles and ships). The room sees the change ("Maya sits down on a bar stool."),
  and a look shows it ("Maya is sitting on a bar stool."). Walking stands you up
  ("You stand up and walk north to the Promenade."; the room you leave hears "Maya
  gets up."). Asleep, a command that does something wakes you first ("You wake
  up."), looking and asking don't; `wake` gets you up; `wake Maya` wakes someone
  gently. "stand" is blackjack's only while you're playing a hand.
- **Following:** `follow Maya` asks Maya, `lead Maya` offers; they answer `accept`
  or `decline` (a minute, like an offer). The follower walks a step behind the
  leader: "You follow Sam north to the Promenade.", the room left hears "Maya follows
  Sam north.", the room reached "Maya arrives, following Sam.", and the leader "Maya
  follows you.". Nobody follows a follower (no chains). It ends with `stop
  following`, `stop leading`, `disband`, walking off on your own, a door the follower
  can't pass or a private room, falling asleep, or the leader leaving the game.
- **Gestures:** world.json's `emotes` has 26 now: the old eleven, and kiss (on the
  cheek), wink, giggle, cry, yawn, blush, poke, high five, thank, salute, facepalm,
  stretch, ponder, comfort and handshake, each with and without someone, and their
  `words` ("high five", "thank you", "shake hands with"). Each new one reuses one of
  the old gestures' sounds (`sound`). Residents answer each (`npc_react_*` in
  texts.json). `emote waves hello` (or `:waves hello`) says your own after your name.
- **Dice, time, being away:** `roll` (two dice), `roll a die`, `roll 2d6`, `roll d20`
  (up to 10 dice of up to 100 sides): the server's own generator, the room sees the
  result, and the log says who rolled what. "roll 20 low" in the casino is still the
  casino's dice. `time` says the station's time (UTC) and, on another world, its local
  time (world.json: a world's `day`, its length in hours and where its clock
  stands). `afk` (or `brb`), with a note if you like: others see it when they look and
  in `who`, a whisper tells the whisperer, and any command brings you back.
- **Things:** `drop 2 coffee`, `put down coffee`, `put coffee on the table` (an
  object's `holds`: how many piles, and `holds_at`), `get coffee`, `take`, `pick up`,
  `get coffee from the table`, `throw crackers to Maya` and `catch` (anyone in the
  room, within 5 seconds; nobody does, it lands on the floor). Only what may be given
  away can be put down, never what you wear, and never in vacuum or aboard. No
  litter: 12 piles a room, 6 of one player's about the station, and after half an
  hour a cleaning drone gives a pile back to whoever put it down. Goods on the floor
  still count in your bag until someone else picks them up, so dropping is never a
  way round the bag. `undress` takes off your clothes and title.
- **Again:** `again` (client 1.7 also `!`) runs your last command again. A mistyped
  first word gets "Did you mean exits?".
- **The rooms' own lines:** a room's `ambient` lines (29 rooms) come now and then,
  paced like the residents' idle lines and sharing their gap (at most one a room
  every 5 minutes, 7 to 15 minutes apart), never while players there have talked in
  the last 90 seconds, never the same twice running. They're `info` events with
  `"ambient": true`.
- **The jukebox** (the Cantina; `jukebox` in economy.json): `jukebox` lists the 8
  songs, `jukebox 3` or `pick song moonlight` plays one for the room for 2 credits,
  one a minute; the Cantina's own lines mention it.
- **The pond** (Willow Nook, north of the Sky Park; `fishing` in economy.json): `fish`
  casts, a tug comes 10 to 30 seconds later, `reel` within 5 seconds lands a speckled
  perch (3 credits at the Spice Market, which buys and sells fish now), a pond carp
  (6) or a rainbow trout (11); a golden koi (2%) is let go, for 15 XP. 30 fish a day
  at most. That's less an hour than mining the Belt with no drill
  (tests/test_orbit_social.py checks it), so it's a pastime.
- **Food:** the Cantina's bar also sells hot chocolate, ginger fizz, instant noodles
  and the Orbit Special; the Food Court space ramen, a moon cheese toastie, a fruit
  skewer and a sesame bun; and three new counters sell food on other worlds: the
  Tumbling Cup at the Drift Bazaar (ginger tea, cardamom coffee, date cake), the
  noodle stalls on Lumina's Neon Boulevard, and the Thermal Lodge's kitchen on Glasir.
  They're for the taste (a thing's `taste` and `other` lines), a small money sink,
  and children eat them too.

## Crews

`crew create` and a name founds a crew (500 credits, from level 3; a name of
3 to 24 letters, digits and spaces, through the word filter, and unlike any
other crew's however its spaces and capitals fall); its founder is the
captain. `crew invite Sam` (also `invite Sam to crew`) asks someone in:
they `accept` or `decline` within two minutes, like an offer (a crew holds
12). `crew say` and the words (`say to crew ...`, `cs ...`, or a whisper to
`crew`) reach every member online, anywhere; it is
filtered, rate-limited and muted like the rest of the chat and never
stored, and players can ignore a member there as anywhere. `crew` shows the
crew, `crew leave`, `crew kick Sam`, `crew captain Sam` (hand it over),
`crew motto` and a line; when the captain leaves, the longest-serving member
takes over, and the last one out ends the crew. Every XP a member earns
while in it is a point for the crew; `crews` (`crew board`) shows the board.
Others see a player's crew when they look at them or at their profile.
Admins can disband a crew (`disband crew Nova`).
The Crew Hangar, north of the Hangar, is a room each crew has to itself:
only members get in, each crew meets only its own, and its board says the
crew's points and place. The numbers are `crews` in economy.json.

## Duels

Two players settle it with a quick draw, only in the contest zones (rooms
marked `arena` in world.json: the Zero-G Gym on the station and the
Tournament Stage on Pixel Pier). `duel Sam` (also `duel with Sam`), or
`duel Sam 20` for a stake of up to 100 credits each: Sam answers `accept`
or `decline` within a minute, like an offer; both pay the stake when it
starts, and the room hears it begin. Best of three rounds: "ready", then
"draw!" 2 to 5 seconds later, and the first number typed wins the round (a
number before it loses the round; a round nobody answers in 3 seconds is
played again, at most five in all). The winner takes both stakes less 5%; a
draw gives them back; walking out, leaving the game or losing the
connection forfeits. Both then rest a minute; a player who was declined
waits five minutes before challenging the same person again; `duels off`
refuses every challenge (`duels` shows the record); muted players can't
challenge; admins can stop a duel (`stop duel Sam`, the stakes go back). The numbers are `duels` in economy.json.

Every duel won counts on the duels' leaderboard (`leaderboard duels`; the
`duels_won` column). The weekly **duel tournament**
(Sunday 15:00 UTC, two hours; `game.events_weekly`) counts the duels won on
the Tournament Stage while it's on: the most wins take 500, 200 and 100
credits and the champion the title Tournament Champion (`prizes` and `prize_thing` of
`tournament` in world.json's events; a tie goes to who got there first).
Dario, the stage's host, knows who leads. Admins can start one at any time
(`start event tournament`).

## Residents (npcs.json)

The simulation has 14 residents who aren't players, each with a voice
number of their own (the 1.2 client reads their words in it) and every
line in English (their ids are still the old ones: `jali` is Rocco, and so
on; see Updating to 1.4). Eleven keep a post: Rocco, the Cantina's
bartender; Oskar, the old engineer in Engineering; Amara, the keeper of the
Way of Starlight in the Star Dome Hall; Felix at Gearworks; Priya at
Whiskers & Widgets; Celeste, the jeweller and wedding planner, at Starglint
Jewellers; Captain Mateo, the ferry's pilot, at the Dock; Shade in the
Drift Bazaar's back alley; Dario, the host of Pixel Pier's Tournament
Stage; Soren, a traveller at the Observation Deck from 19:00 to 05:00 only;
and Poppy, a curious girl who spends her day in the Archive, the park, the
Food Court and at the Observation Deck. Three walk the map on a daily
schedule (station time, UTC), room by room by the compass, and the rooms
they pass hear them come and go: Gino (the Dock, the Food Court, Cargo, the
Cantina), Hana (Hydroponics, the park, the Jasmine Pavilion, the Cantina)
and Granny Fern in Evergrove.

- **Honesty:** residents are never in `who`, the online count or any list
  of players; `look` names them on a line of their own ("Residents here:
  ..."), looking at one says it's a resident, not a player, and so does
  whispering to one. Players can't take their names (nor their ids).
  `residents` lists them all and where they are now.
- **Talking:** `talk to Rocco` (a greeting and the topics), `ask Rocco about
  gossip`, `greet Rocco` (also `hi Rocco`, and any gesture at them), and giving
  them things. Some answers are live: the gossip (a wedding, the richest,
  the top miner, the leading crew), who's online, the market, the events,
  the station time, your own progress, today's specials, the ferry, your
  pet, the arcade, the duels' board, the tournament, the weddings to come,
  the Lantern Festival, the hunt (never its answers). A topic they don't
  know gets a kind "I don't know that one", in character.
- **Memory and affinity** (0 to 100, in the `npc_memory` table): talking,
  greeting or a gesture 1 (once a day), a topic asked for the first time 1,
  a gift 2 (4 for something they like; one gift a day counts), a favour
  done 6. A stranger, then an acquaintance at 5, a friend at 15, close at
  30: some topics and errands open only to friends, and a shopkeeper gives
  friends 5% off in their own shop, close friends 10% (`discount`). A
  resident who knows you well may greet you when you walk in (half of the
  times, at most once in half an hour).
- **Favours:** `ask Oskar about work` names what they need (3 pieces of
  scrap, later circuit boards, satellite chips...); give it to them for
  credits, XP or a thing, each favour once a day.
- **Idle lines** are rare (7 to 15 minutes apart, at most one in a room
  every 5 minutes, never the same line twice in a row), fit the room they're
  in, and never come while players have talked there in the last 90
  seconds.

`npcs.json` is checked when the server starts (every line in English,
schedules, rooms that exist, routes that avoid
airless, dark and private rooms, voices 1 to 10, names unique); a mistake
stops the server with the reason in the log. Its `rules` are the numbers
above: `walk_seconds` (8 to 14 seconds a room), `idle_gap`, `room_gap`,
`quiet_seconds`, `notice_seconds`, `notice_chance`, `affinity`, `levels`
and `discount`.

## Pets

Whiskers & Widgets on the Mall Ring sells a little robot (600), an orange
space cat (900), a mini drone (1,000), a robot cat (1,100), a space fox
(1,300) and a glow jellyfish (1,600), pet food (6) and treats (15). The fox,
the jellyfish and the drone may also choose a player out on the worlds, if
that player has none of the kind: a fox 2% of the times someone faces Grove
Wood's creatures, a jellyfish 1% of collecting in Glasir's crevasse, a drone
0.5% of salvage in the Debris Field. The numbers are `pets` in economy.json,
and each kind's `pet` (its sound, what it eats, its tricks).

- **Needs** (0 to 100): food falls 3 an hour, fun 4, rest 2 (`decay`). Pet
  food gives 35 food, a treat 20 food and 20 fun; playing 30 fun and costs
  8 rest (a tired pet gets a gentle cuddle instead), 5 minutes apart;
  resting 45, 20 minutes apart; a pat a little fun. A pet whose mood (the
  average) falls under 30 is sad and quiet (no tricks, no reactions); it
  never dies, runs away or falls ill, and a little care always cheers it
  up. A reminder, at most hourly, says when a need is under 25.
- **Growing up:** caring for a need that was under 75 counts. Young after 8
  such cares and 2 days, grown after 25 and 7 days (`stages`).
- **Tricks:** young pets learn two, grown ones a third; 3 lessons each
  (`lessons`), 5 minutes apart, when the pet is content and not tired.
- `pet status`, `feed Kiki`, `play with Kiki`, `rest Kiki`, `pat`, `teach
  trick sit`, `trick sit`, `name pet Kiki`, `rename Kiki to Momo`. A new pet
  has its kind's name (`name` in its `pet`: Marmalade the orange cat, Tinker
  the robot cat, Dusk the fox, Bip the little robot...) until it's given one. Pets follow their
  owner, join in their gestures and react to others'.

## Families

- **Partners:** `partner with Sam`; Sam answers
  `accept` or `decline` within 2 minutes (`ask_seconds`); after a no, the
  same player can't be asked again for 10 minutes (`snub_seconds`). Ending
  it takes two commands: `end partnership`, then `confirm end` within a
  minute; the other partner is
  told kindly (at once, or when they next come). A new partnership waits a
  day after one ended (`partner_cooldown`). Admins can end one for players
  who can't (`end partnership Sam`). It stays
  wholesome: partners are partners, and the texts never turn romantic.
- **Adopting,** at the Medbay's family desk: 300 credits, from level 3, at
  most 2 children each, 3 days apart. Partners decide together (the other
  is asked and must say yes; both are then the child's parents, and stay so
  if the partnership ends). **A player on their own may adopt too:** many
  play alone, and a family here is about looking after someone, not about
  having a partner.
- **A child's needs** fall more gently than a pet's (food 1.5 an hour, fun
  2, rest 1): baby porridge from the Food Court (8 credits, 40 food; a
  stuffed pancake 30, prawn crackers 15), play (30 fun, 5 minutes apart), a story (15 fun
  and 15 rest, 10 minutes apart), rest (45, 20 minutes apart). A child left
  alone grows quiet and asks for you; it's never harmed. With care it grows
  over real days: a toddler after 6 cares and 2 days, a child after 18 and
  5 (`stages`), saying more as it grows, in a voice of its own.
- **Helping:** a happy child (the third stage) at your side adds 5% to the
  XP from work (`xp_bonus`); once a day `ask Lily for help` fetches
  something small (prawn crackers, water spinach seeds, a pet treat or an
  iced coffee, by the weights in `fetch`). `bring Lily`: the child follows
  you.
- **The naming rite:** `naming rite Lily` in the Star Dome Hall, with Amara
  there: a lantern lit, the name spoken under the
  dome, the star bell once.

The numbers are `family` in economy.json (with the children's lines, by
stage).

## Weddings

- **The ring:** Starglint Jewellers, north-east of the Mall Ring's east
  side, sells silver (500), gold (1,500) and star (4,000) rings. `propose
  to Sam` in the same room; Sam answers `accept` (engaged)
  or `decline` (the ring stays yours) within 2 minutes; after a no, 10
  minutes before asking again.
- **Booking,** at the jeweller's wedding desk, for an engaged couple: a hall
  (the rooms marked `venue`: the Star Dome Hall, the Jasmine Pavilion,
  Evergrove's Great Hall), a tier, a ceremony and a time in station time
  (`book wedding pavilion grand neutral 14:00`, also `tomorrow 14:00` or
  `2026-10-03 14:00`), at least 10 minutes and at most 14 days ahead.
  Tiers: simple 1,000 credits (10 guests), grand 4,000 (30 guests, music
  and the celebration's ambience), luxurious 10,000 (60 guests, and
  fireworks for the whole station). A hall takes one wedding an hour
  (`slot_minutes`); a wedding lasts 45 minutes. Cancelling gives all the
  money back a day or more ahead, half of it an hour or more ahead, and
  nothing later. A character marries again only after 7 days
  (`cooldown_days`). Admins can cancel any wedding, all the money back
  (`cancel wedding Sam`).
- **Guests:** `invite Sam to the wedding`; guests answer `rsvp yes` or
  `rsvp no` (`i'll come`, `can't come`), hear of invitations waiting when they
  join and are reminded 10 minutes before. At the ceremony they `throw
  flowers`, cheer and clap, each with its sound.
- **The ceremony** waits 20 minutes for both partners at the hall
  (`wait_minutes`); if they don't come, it's missed and half the price
  comes back. Two kinds, chosen when booking. The **Starlight rite**, led by
  Amara: each partner lights a lantern, the two lights are joined into
  one, a moment of silence, the vows the two write themselves, the star bell
  three times. A **neutral ceremony**, led by Celeste as the station's
  registrar: the vows, each partner's yes, their signatures. Neither
  borrows from any real faith's rites. Each step waits a few minutes
  (`lantern_seconds`, `join_seconds`, `vow_seconds`, `consent_seconds`,
  `sign_seconds`); the keeper's hands light a lantern or join the lights
  for a couple who don't, a vow can be left unspoken, a yes or signatures
  not given stop the ceremony (half back), and a "no" ends it kindly, with
  all the money back. A partner who steps out pauses it; 20 minutes away
  stops it.
- **Afterwards:** the station hears the news, the couple get a title
  (Starlit or Wedded) and a keepsake, and the day is kept as a memory (who
  came, the vows, the flowers and cheers) that the couple and their guests
  can read (`read memory`).

The numbers are `weddings` in economy.json.

## The Way of Starlight

The station's own quiet tradition, made up for Orbit (no real faith's
rites, words or symbols): lanterns lit in the Star Dome Hall for someone,
the star bell, the naming rite and the Starlight wedding, kept by Amara.
On the Lantern Festival (the hundredth day of the year) lanterns
are free and each one lit is thanked with a small gift; the lanterns lit
that day also count towards the festival's goal, 30 in all and at most 5
from each player (`temple.festival_goal`, `festival_cap`). Reaching it
gives everyone on the station 60 credits and a lantern charm
(`festival_reward`, `festival_thing`), and players who come later that day
too.

## The arcade (Pixel Pier)

Cabinet Row, west of Pixel Pier's Grand Arcade Hall, has four cabinets and a
token machine (`buy 10 tokens`); `arcade` (anywhere) lists them. `play` and
a game's name there spends a token; every game is played by ear, with
numbers and Enter (both clients send a number alone as `answer`), and
`stop game` ends one early (it counts as it is). Walking away, leaving or
losing the connection ends it too.

- **Quick Draw** (reaction): five rounds; "ready", then a beep 2 to 5
  seconds later; type any number at once. Too soon or too slow: no points.
- **Star Beat** (rhythm): a rhythm of short (0.5 s) and long (1 s) gaps is
  played (the 1.1 client plays the beats; the words say the gaps too); the
  player taps it back, a number and Enter for each beat. Only the gaps
  between their taps are compared, so the network's delay doesn't count.
- **Echo** (memory): tones 1 to 4 (the reactor's), typed back as numbers;
  one more every time, from 3 up to 16.
- **Meteor Dodge** (stereo): a meteor comes from the left, the right or
  ahead; 4 steps left, 6 right (or the words left and right). Its
  sound is placed on its side; clients older than 1.1 are told the side.

Each game's table (`arcade scores`, `arcade scores meteor`, or looking at
the High Score Wall) keeps each player's best; beating the top
of a table is announced to everyone and pays more tickets. The Prize
Counter, east of the Hall, takes the tickets (`list`, `buy plush comet`).
Everything is timed on the server when commands arrive; a client of one's
own could cheat at it, as at any game played through a client, but the
prizes are only for fun.

## The hunt (the Lost Chord)

A season-long chain of hard riddles for the whole server: the simulation's
founder broke her last chord apart and hid each note behind a riddle, and
whoever finds them all first wins.
Players type `hunt` (their riddle, and any hints released), `investigate`
(also `look for clues`) where they think a clue is, `solve ...` (also `my
answer is ...`) and `hunt board`. Everything the hunt says is English; a
season's file may hold other languages too, and only its `"en"` is shown.

- **Clues** are in rooms. Some show only to someone carrying a thing (a
  scanner), wearing one (a headlamp), or at certain station hours (UTC;
  `[22, 5]` runs past midnight); some are tones to listen to, played like
  the reactor's (1 to 4, low to high and left to right); a dark room hides
  them without a light. When a clue of your riddle is in the room, looking
  says "Something here seems to invite a closer look"; investigating where
  one is hidden from you says you can't quite make it out.
- **A wrong answer** makes you wait: a minute, then 2, 4, 8... up to a day
  (`game.hunt_wrong_base`, `game.hunt_wrong_max`), and every try is
  rate-limited, so guessing doesn't pay. Answers are compared in lower case
  without accents, spaces or punctuation.
- **A right one** gives the next riddle, and the station hears "Ani has found
  note 2 of 5". The first to finish wins the season's `prize.first` credits
  and its title (Keeper of the Lost Chord, a thing of their own); the next
  ones `prize.others` in order, then `prize.rest` each. Everyone hears who
  finished and in which place.
- **The rival**, the Meridian Grey company, "finds" a note every
  `rival.hours` and says so, to keep the pressure on, but never the last one.
- **Admins** know the answers, so they're left off the board and out of the
  prizes (unless `game.hunt_admins_compete`); `hunt test`
  plays the season from the start without counting, to try it out.

**A season is never in this repository**, which is public: the riddles,
where the clues are and what unlocks them are the game. Seasons are written
in `servers/orbit/private/` (ignored by git) and live in `~/orbit/private/`
on the server. There are two files. The **authoring** file has the answers in
plain text (`"accept"`: every answer a riddle takes, in any language and
other spellings); it stays on the computer it was written on. The server's
file, built from it, has only keyed hashes of them (HMAC-SHA256 with a new
random salt of 32 bytes, over "season:stage:answer"), so the answers can't
be read from it; keep it private all the same (short answers, like numbers,
could be guessed offline from it). `orbit_hunt_tool.py` builds and checks
them (its docstring describes the format):

```sh
cd servers/orbit
python orbit_hunt_tool.py template > private/season2.authoring.json    # a start
python orbit_hunt_tool.py build private/season1.authoring.json private/season1.hunt.json
python orbit_hunt_tool.py check private/season1.hunt.json
python orbit_hunt_tool.py try private/season1.hunt.json 2 "an answer"    # right or wrong
```

To run a season on the server:

```sh
mkdir -p ~/orbit/private && chmod 700 ~/orbit/private
# copy private/season1.hunt.json there: only the built file, never the authoring one
chmod 600 ~/orbit/private/season1.hunt.json
# in config.json: "hunt": "private/season1.hunt.json"
systemctl --user restart orbit
```

The log says "the hunt's season 1 begins" the first time (a restart goes on
with the same season). For the next season: build its file and copy it over
the one `"hunt"` names, then an admin types `new season`,
with no restart (a new name in config.json needs a restart instead):
everyone starts it at the first riddle and hears so; the old season's
progress stays in the database. A file that can't be read or isn't right is
refused (the log says why) and the season running goes on. When a riddle
proves too hard, `release hint 2` (or `announce hint 2`) gives everyone the
next of riddle 2's hints (the season file has them), and `hunt` repeats it
from then on. `hunt status` shows where everyone is,
their tries and waits.

`hunt.example.json` is a fake two-riddle demo season (its answers are
"orbit" and "1234"), for trying the hunt out and for the tests.

## Admin commands

Typed in the game by a character in `game.admins` (in English, like every
command since 1.4):

| Command | What |
|---|---|
| `mute Sam 10`, `unmute Sam` | mute for minutes |
| `kick Sam` | send off the station |
| `ban Sam`, `unban Sam` | the character, and its address for 7 days |
| `announce ...` | to everyone |
| `grant Sam 500` | give credits (from a player, "give Sam 500 credits" is a gift) |
| `take credits Sam 100` | take credits |
| `give item Sam headlamp` | give any thing (a pet too) |
| `economy` | the economy's report |
| `set price coffee 20` | a market price for the next hour |
| `reset streak Sam` | a daily streak back to zero |
| `goto the bridge`, `goto Sam` | teleport (players walk) |
| `invisible` | nobody sees you come, go, or in who (again: visible) |
| `transfers` | recent character transfers |
| `revoke Sam` | no computer can play Sam until a transfer code is used (a stolen laptop) |
| `transfer code for Sam` | a code for someone who lost their computer |
| `admin log` | the last admin actions |
| `start event meteor shower` | start any event now (`start event tournament`: the duel tournament) |
| `stop event` (and a name) | stop the event (or cancel a scheduled one) |
| `schedule event 2026-09-27 14:00 ...`, `schedule event 30 ...` | an announcement of your own at a UTC time, or in so many minutes |
| `hunt status` | the hunt: everyone's riddle, tries and waits |
| `new season` | read the hunt's season file again (a new season begins when its number changed) |
| `release hint 2` | the next hint of the hunt's riddle 2, to everyone |
| `stop duel Sam` | stop a duel (the stakes go back) |
| `disband crew Nova` | end a crew (its members are told) |
| `end partnership Sam` | end Sam's partnership, for players who can't (both are told kindly) |
| `cancel wedding Sam` | cancel Sam's coming wedding, all the money back (the couple and guests are told) |
| `hunt test` | play the hunt from the start without counting (again: back) |
| `help admin` | this list, in the game (players don't see it) |

Every admin action is written to the log and to the database's `admin_log`
table, with who did it and when.

## Moving a character to another computer

A character lives on the computer that made it: the client keeps a random
secret, the server only a hash of it. In Preferences, Orbit ("Move my
character to another computer"), or with `transfer code` / `move my character`,
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
outside, a shuttle ride or ferry trip in progress, a courier gig, its casino
bets of the last hour a minute at a time, how many trades, jackpots,
naturals, gigs and creatures), what it won or lost at the casino, when it
was made and last seen, and whether it is banned or muted; its companions (a
pet: kind, name, and its own stats); its ship (model, name, where it's
docked or flying to, fuel and cargo); the events it took part in (and how
much, for the drone's rewards); its achievements (which, and when); its
lottery tickets (how many, for which week's draw); its best score and games
played at each arcade cabinet; its crew and its role there (a crew keeps its
name, motto, points and when it was founded); how far it got in each season
of the hunt (its riddle, tries, wrong answers in a row and the wait, when it
finished and in which place; the answers it typed are only compared, never
kept); transfer codes (a hash, for 10 minutes); secrets that no longer work
(a hash); the transfers log; the admins' log; and, in `meta`, the market's
prices, each world's own prices, the economy's totals, today's temple
lanterns, the lottery's next draw and carried-over pot, and the events'
pacing (when the next random one may come, when each last came, which weekly
and seasonal ones have run) and the hunt's season (the rival's progress, the
hints released, how many have finished). Every event that runs or is
scheduled is a row in `events`, with its state and how it ended (the
tournament's wins and the Lantern Festival's lanterns are its points).

Since 1.6 also: things put down in a room (`meta` key `floor`: what, how many, who put it
down and when, on the floor or on which table), and in a character's `stats` the fish
caught today and the biggest of each kind. Postures, following, being away and the
jukebox's song live only in memory.

Since 1.2 also: what each resident remembers of each character
(`npc_memory`: affinity, how many talks, gifts and favours, when they first
and last met, the topics asked, the favours done today); a pet's needs,
stage, care and tricks (in its companion's stats); partnerships
(`partnerships`: the two characters, partners, engaged or married, since
when, and when and by whom one ended); children (companions owned by their
parents: name, voice, stage, needs); weddings (`weddings`: the couple's
partnership, hall, tier, ceremony, time, what was paid and given back, and
the memory of the day: who came, the vows the couple wrote, the flowers and
cheers) and their guests (`wedding_guests`: who was invited, their answer,
whether they came). Vows are written by the couple to be kept (they're told
so when asked for them) and are read back only by the couple and those who
came; everything else said at a wedding is chat, never stored. Trade
offers, coin-flip challenges, crew invitations, duel challenges, partnership,
adoption and ring proposals, a duel, a naming rite, the guide's way and a
blackjack hand in progress live only in memory (a hand is played out,
standing, if its player leaves or the server stops). Accounts have no
password or email: the client makes a random 256-bit secret the first time
it joins this server and keeps it on the player's computer; the server keeps
only a PBKDF2-SHA256 hash of it (with a salt made once for this server).
Chat (say, whisper, shout) is passed on to whoever hears it and never
written anywhere. A banned connection's address is kept only as a salted
hash, for 7 days.

The log says when the server starts and stops, when characters are created,
join, resume, log out and leave (by name), transfers, and what admins did. It
never contains secrets, codes, chat or addresses.

## Protocol

JSON text messages over WebSocket (text frames only; 4096 bytes at most from
a client). Everything the server sends is English, ready to show and
speak, whatever `lang` the hello asked for.
Protocol version 1 is unchanged since Orbit 1.0: everything 1.1, 1.2, 1.3,
1.4 and 1.5 added is optional, so the older clients keep working (they only miss
the new sounds and the lines; every newer command reaches the server from them as
plain text).

**Joining.** The client's first message:

```json
{"t": "hello", "v": 1, "lang": "en", "secret": "<64 hex characters>",
 "name": "Rafli", "job": "pilot", "client": "Hariku Orbit 1.6"}
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
their English names (and their ids). Anything the client doesn't know goes as
`text`, and the server reads the rest itself (`orbit_verbs.py`), so new
commands need no new client:

| `c` | Fields | |
|---|---|---|
| `look` | `a`: nothing, a person, a thing, a thing you own, a direction | |
| `examine` | `a`: `here` (or `room`, `around`), a player, a resident, a pet or child, a thing here, one you own or one for sale here, a good at this market, a place, `me`; nothing: how it's used | 1.5: what can be done (from text: x here, x Rocco, what can I do here, commands here; `help` with `a`: `here` too) |
| `move` | `d`: n, ne, e, se, s, sw, w, nw, u, d | walk one room |
| `go` | `a`: a direction or a place | next door: a walk; further: the way (admins teleport) |
| `way`, `map`, `where`, `compass`, `scan`, `locate` | `a` / `to` | finding your way and people (`way` also starts the guide) |
| `guide` | `a`: a place (the way, guided); nothing: what's left; `op`: `stop` | the guide (1.3; from text: guide me to, stop guide) |
| `board` | | the Wombat, at the Dock or the Belt Platform |
| `say`, `shout` | `a`: the words | shout: station-wide, once every 10 s |
| `whisper` | `to`, `a` | to anyone on the station |
| `emote` | `e`: smile, wave, laugh, nod, shrug, clap, cheer, sigh, bow, dance, hug; `to` (optional) | |
| `who`, `inventory`, `prices` (`a`: a kind, a good, or a world for a Hornbill's scanner), `missions`, `complete`, `abandon`, `work`, `help` (`a`: a topic) | | `prices`: at a market, its list; elsewhere, the nearest market |
| `give` | `to`, `n`, `item` (`credits` or a thing) | in the same room |
| `describe` | `a`: a short description (nothing: show it) | |
| `answer` | `a`: the reactor's numbers, a reading, a traveller | |
| `accept` | `n`: a mission's number (none: the newest trade offer or coin flip waiting for you) | |
| `take` | `item`, `n` | a mission's things |
| `buy`, `sell` | `item`, `n` (`"all"` to sell everything, or all of a kind) | the goods of the market you're in, and the shop you're in |
| `list`, `use`, `unequip`, `open` | `a` / `item` (`equip`: true to wear) | shops and things |
| `plant` (`item`, `n`), `water`, `harvest`, `farm`, `mine`, `collect` | | the farm, mining, salvage |
| `daily`, `profile` (`to`), `rank`, `voice` (`a`: 1-10 or auto), `transfer` | | |
| `friends` (`op`, `to`), `invite` (`op`, `to`), `visit` (`to`), `pet` (`op`, `a`), `ring`, `lantern` | | |
| `casino`, `dice` (`a`: high, low or seven; `n`: the bet), `slots` (`n`), `blackjack` (`n`), `hit`, `stand`, `challenge` (`to`, `n`), `lottery` | | the casino (tickets: `buy` there) |
| `offer` (`to`, `a`: "3 iron for 200 credits"), `decline`, `cancel_offer` | | trading |
| `achievements` (`to`), `leaderboard` (`a`: richest, level, miners, farmers, streak, casino) | | |
| `worlds`, `gate` (`a`: a world), `ferry` (`a`), `embark` (`to`: a friend's ship), `disembark`, `fly` (`a`), `refuel` (`n`), `load`, `unload` (`item`, `n` or `"all"`), `cargo`, `name_ship` (`a`) | | travel and ships |
| `face` (`a`: a creature), `gig` | | Evergrove's creatures, Lumina's courier gigs |
| `events`, `join`, `listen`, `catch`, `search`, `watch`, `party` | | events (the drone: `work` at the Dock) |
| `hunt`, `investigate`, `solve` (`a`: the answer), `hunt_board` | | the hunt |
| `crew`, `crew_create` (`a`: the name), `crew_invite` (`to`), `crew_say` (`a`), `crew_leave`, `crew_kick` (`to`), `crew_captain` (`to`), `crew_motto` (`a`), `crews` | | crews (an invitation is answered with `accept` or `decline`) |
| `duel` (`to`, `n`: the stake), `duels` (`op`: on, off) | | duels (answered with `accept` or `decline`) |
| `talk` (`to`), `ask` (`to`, `a`: the topic), `greet` (`to`), `residents` | | the residents |
| `pet` (`op`: status, feed, play, rest, pat, teach, trick, name; `a`) | | pets |
| `partner` (`op`: status, ask, end, end_confirm; `to`), `adopt`, `family`, `child` (`op`: feed, play, rest, story, fetch, take, talk; `a`: the child), `naming` (`a`: the name) | | families (a proposal or an adoption is answered with `accept` or `decline`) |
| `wedding` (`op`: status, propose, book, cancel, schedule, invite, invitations, rsvp_yes, rsvp_no, flowers, vow, join, yes, no, sign, memory; `to`, `a`) | | weddings (a proposal is answered with `accept` or `decline`) |
| `arcade`, `play` (`a`: a game), `stop_game`, `high_scores` (`a`: a game) | | the arcade; a game's input is `answer` (numbers alone: both clients send them so) |
| `exits`, `peer` (`a`: a direction) | | the ways out, a line each; a glimpse next door (1.6) |
| `sit`, `lie`, `sleep` (`a`: a seat), `stand`, `stand_up`, `wake` (`a`: a sleeper) | | postures ("stand": blackjack's only in a hand) (1.6) |
| `follow`, `lead` (`to`; `op`: stop, disband) | | following, after a yes (1.6) |
| `pose` (`a`: the words), `roll` (`a`: 2d6...), `time`, `afk` (`a`: a note) | | your own gesture, dice, the time, away (1.6) |
| `drop` (`item`), `put` (`a`: "coffee on the table"), `throw` (`a`: "crackers to Maya"), `undress` | | things put down (`take` picks up; `catch` catches) (1.6) |
| `jukebox` (`a`: a song), `fish`, `reel` | | the jukebox, the pond (1.6) |
| `bye` | | leaving on purpose: gone at once |
| `away` | `on` | the client's window is hidden and its player idle |
| `status` | | connected as, where, how many online |
| `text` | `a`: plain words | the server reads them (see above) |
| `admin` | `op`: mute, unmute, kick, ban, unban, announce, grant, take_credits, give_item, economy, set_price, reset_streak, goto, invisible, transfers, revoke, transfer_for, admin_log, event_start, event_stop, event_schedule, hunt_status, new_season, release_hint, hunt_test, crew_disband, duel_stop; `to`, `n`, `a`, `item` | admins only |

**Events** (`{"t": "ev", "k": kind, "text": "...", ...}`). `k` tells the
client which sound fits and whose voice reads it: `room`, `moved`, `arrive`,
`leave`, `say`/`said`, `whisper`/`whispered`, `shout`/`shouted`, `emote`,
`who`, `info`, `error`, `tones`, `task`, `paid`, `failed`, `received`, `crew`/`crew_sent` (crew chat,
heard and said; Orbit 1.0 reads them as plain lines),
`gave`, `mission`, `trade`, `flight`, `offer`, `announce`, `system`. Optional
fields: `actor` (who did it), `brief` (a short line to say for your own
action), `room`, `amb` (`vent`, `cantina`, `engine`, `garden`, `deck`,
`space`, `belt`, `venue`, `mall`, `casino`, `gate`, `moon`, `colony`, `ice`, `bazaar`, `forest`,
`neon`, `arcade`, and `wedding` during a grand or luxurious wedding, for
a 1.2 client), `floor` and `acoustics` (where you are now),
`dir` (the way you walked, or the side someone came from or left by), `via`
(`lift`, `ladder`, `slide`, `airlock`, `door`), `codes` (the reactor's
or a hunt clue's tones, 1 to 4), `sound` (a cue more specific than the kind's), `emote`
(which gesture), `voice` (the voice number a speaker chose; on your own
lines, yours), `words` (on a line said, whispered or shouted, yours or
another player's: the words alone, so a client can read the name in one
voice and the words in the speaker's), `to` (who you whispered to),
`preview` (read this line in `voice`), `ask` (an invitation, an offer, a challenge, a
proposal: answer with accept or decline; `partner`, `adopt` and `ring` are
1.2's), `lines` (1.5, only to a client from 1.6, the hello's `client`, and only
for a reply of several parts: its parts, a line each, to show one by one; `text`
is always the whole reply as one line, for every client, to read aloud), a resident's lines are `say` and `emote` events with its name as
`actor`, its `voice` and its `words`, like a player's, `transfer_code` and `expires`, `reels` (a slot
machine's three symbols, left to right) and `outcome` (`win`, `lose`,
`push`, `jackpot`: the client plays it after the dice land, the cards turn
or the reels stop), `event` (on an announcement: the event it belongs to,
so a client can leave events unread) and `schedule` (with the `events`
list: `[{"event", "name", "at"}]`, the coming ones as UTC timestamps, for
the client to show in local time and set reminders), `ambient` (1.6: a room's own
line, now and then), `beats` (Star Beat's
rhythm at the arcade: the seconds after the event at which each beat
sounds; the words wait for them). A `sound` with a `dir` is heard on that
side (a meteor at the arcade, the runaway robot); Orbit 1.0 plays it in
the middle, so the arcade tells a client older than 1.1 (the hello's
`client`) the side in words.

**Closing codes**: 1001 the server is restarting (reconnect), 1008 a broken
rule (too many messages, no hello), 4000 kicked, 4001 connected from
somewhere else, moved to another computer or revoked, 4003 banned (don't
reconnect after these three); 1000 after `bye`. When the server closes, it
sends everything queued and the close frame, ends its side of the
connection (a TCP FIN), and reads and drops whatever the client still sends
until the client's close frame, the end of its data, or `linger_seconds`,
and only then closes the socket: a socket closed with unread data would
send a reset, which can make the client lose the last lines and the reason.

Pings: the client pings every 25 seconds; the server answers pings and
closes a connection that says nothing for `idle_timeout` seconds.

## Sounds (the client's cues)

The extension plays a **cue** for each event, by name. A cue is a WAV file,
or numbered variants of one (`step_metal_1.wav`, `step_metal_2.wav`...; one
is picked at random each time). Orbit looks in these folders, in order, and
the first with any file for the cue wins:

1. `%APPDATA%\Hariku2\orbit_sounds\` (your own recordings)
2. `orbit\` inside the Sound Themes theme in use (`%APPDATA%\Hariku2\sound_themes\<theme>\orbit\`)
3. the extension's `sounds\` folder (made by `extensions/orbit/orbit_sounds.py`)

So a pack of recordings (CC0 or your own) is just files named like the cues.
A name with parts falls back to a shorter one when no folder has it
(`emote_clap` plays `emote`). Positional cues (steps, arrive, leave,
gestures, door, bump, ladder) are best mono: Orbit pans them to the side
they happen on and adds the room's echo (small, room, hall, hangar, cave,
open, the muffled hush outside) as it plays them, keeping those copies in
`%APPDATA%\Hariku2\orbit_sound_cache\`.

| Cue | When |
|---|---|
| `step_metal`, `step_carpet`, `step_grass`, `step_stone`, `step_wood`, `step_rock`, `step_suit`, `step_wet`, `step_snow`, `step_sand`, `step_dust` | your steps, by the floor you walk on |
| `door`, `airlock`, `lift_up`, `lift_down`, `ladder`, `slide`, `bump`, `locked` | doors, airlocks, lifts, ladders, the slide, walls, a locked door |
| `arrive`, `leave` | someone comes in or goes, from their side |
| `say`, `whisper`, `shout`, `sent`, `announce`, `offer` | talking; your own words going out; the Bridge; an invitation |
| `emote`, `emote_smile`, `emote_wave`, `emote_laugh`, `emote_nod`, `emote_shrug`, `emote_clap`, `emote_cheer`, `emote_sigh`, `emote_bow`, `emote_dance`, `emote_hug` | gestures (1.6's new ones reuse these: a kiss is a hug's, a giggle a laugh's...) |
| `success`, `fail`, `error`, `mission`, `task`, `tone1` to `tone4` | work, a mission, a task starting, the reactor's tones |
| `coins`, `register`, `trade` | money changing hands; a shop's till; a trade done |
| `mine`, `rare`, `plant`, `water`, `harvest`, `ripe` | mining, a rare find, the farm |
| `levelup`, `daily`, `achievement` | a new level; the daily bonus; an achievement |
| `equip`, `gadget`, `scan`, `air`, `rescue`, `gulp`, `crunch` | things: wearing, devices, the scanner, the air warning, the tow, food (`gadget_arrived`, arriving where the guide led you, plays `gadget` unless a pack has its own) |
| `pet_robot`, `pet_cat`, `pet_robocat`, `pet_minidrone`, `pet_fox`, `pet_jelly`, `pet_trick` | each kind of pet's own sound; a trick shown off |
| `npc_warm`, `baby` | a resident grows fonder of you (and warm moments: partners, a rite's end); a child |
| `ring`, `wedding_music`, `lanterns_join`, `flowers` | a proposal, a wedding beginning, the Starlight rite's two lights joined, flowers thrown |
| `bell`, `lantern` | the temple's star bell; lighting a lantern |
| `launch`, `landing`, `gate`, `ferry`, `refuel`, `cargo`, `customs` | ships and shuttles, the Gate, the ferry, fuel, the hold, a customs check |
| `creature` | one of Evergrove's creatures |
| `event_start`, `event_end`, `event_party`, `event_storm`, `event_boss`, `event_meteor`, `fireworks`, `robot_beep` | events beginning and ending, each kind with a sting of its own; the runaway robot's beeps, from its side |
| `duel_start` | a duel: challenged, and beginning |
| `crew_chat`, `crew_join` | a line on your crew's chat; someone joins (or you found) a crew |
| `arcade_start`, `arcade_ready`, `arcade_go`, `arcade_hit`, `arcade_beat`, `arcade_meteor`, `arcade_whoosh`, `arcade_crash`, `arcade_ticket`, `arcade_over` | the arcade: a coin in, ready and go, a point, a beat, a meteor (placed on its side), dodged, hit, tickets out, game over |
| `hunt_clue`, `hunt_found`, `hunt_rival` | the hunt: a clue (and others' progress, a hint), a note found, the rival ahead |
| `dice`, `reel_spin`, `reel_stop`, `cards`, `deal`, `coinflip`, `lottery`, `lottery_draw` | the casino's games (the reels stop left, middle, right) |
| `win`, `lose`, `push`, `jackpot` | how a game came out |
| `amb_vent`, `amb_cantina`, `amb_engine`, `amb_garden`, `amb_deck`, `amb_space`, `amb_belt`, `amb_venue`, `amb_mall`, `amb_casino`, `amb_gate`, `amb_moon`, `amb_colony`, `amb_ice`, `amb_bazaar`, `amb_forest`, `amb_neon`, `amb_arcade`, `amb_wedding` | the ambience loops (4 seconds, seamless; the other worlds' at 11 kHz) |

The set: 203 files, about 10.7 MB: 106 recorded (3.0 MB) and 97
synthesized; the ambience loops are at 11 kHz. 1.2 added 12 (0.7 MB): the
ring (a box opening and two glass chimes) and the flowers (cloth and
synthesized petals) are mixed from Kenney's recordings, the rest
synthesized.

### Credits: recorded sounds

Many cues are made from recordings by **Kenney** (www.kenney.nl): the packs
Casino Audio, Impact Sounds, RPG Audio, Sci-fi Sounds and Interface Sounds,
released under **CC0 1.0** (public domain,
http://creativecommons.org/publicdomain/zero/1.0/). Attribution isn't
required; we credit Kenney anyway, with thanks. They were trimmed,
level-matched and mixed down to mono 22.05 kHz with
`tools/orbit_convert_kenney.py` (a one-off developer tool; it needs `pip
install soundfile`, which Hariku itself doesn't use), and `orbit_sounds.py
--kenney <folder>` mixes each recorded cue from them (the recipes, which
file each cue uses, are `RECORDED` there). The footsteps, doors, cloth,
coins, mining, cutting crops, the shuttle's engines, the interface's small
sounds and the casino are recorded; laughs, claps, cheers, the reactor's
tones, the temple bell, the ambience loops and the stings are synthesized.
`extensions/orbit/sounds/LICENSE-kenney.txt` says the same next to the files.

## Tests

From Hariku's source folder (they run on Windows or Linux, and use only this
computer):

```sh
python -m pytest tests/test_orbit_server.py tests/test_orbit_map.py tests/test_orbit_economy.py tests/test_orbit_casino.py tests/test_orbit_worlds.py tests/test_orbit_events.py tests/test_orbit_hunt.py tests/test_orbit_arcade.py tests/test_orbit_crews.py tests/test_orbit_duels.py tests/test_orbit_npcs.py tests/test_orbit_pets.py tests/test_orbit_family.py tests/test_orbit_weddings.py tests/test_orbit_starlight.py tests/test_orbit_tournament.py tests/test_orbit_markets.py tests/test_orbit_guide.py tests/test_orbit_compat.py tests/test_orbit_here.py tests/test_orbit_lines.py tests/test_orbit_social.py tests/test_orbit_own_replies.py tests/test_orbit_e2e.py -q
```

`test_orbit_here.py` goes to every room of every world and types each command
"x here" lists there, the way client 1.6 reads it, and fails if the answer is
one that means "not here" (not a market, no farm here, the casino is
elsewhere...): the list comes from the same checks the commands make, and this
keeps it so. It also tries "x" on residents, players and things, the dark, a
mission, the events held in a room, a ship and the ferry, and the words that
ask for it from the 1.0 and 1.4 clients. `test_orbit_lines.py` checks that a
client from 1.6 gets a reply's `lines`, that every client gets the same reply as
one line in `text`, and that the older clients get no `lines` at all.

`test_orbit_social.py` checks 1.6: exits (doors, vacuum, one way, the dark, a secret way),
postures and what the room sees, walking up from a seat, "stand" and blackjack, following
and leading, peering, the new gestures (and the residents' answers), your own emote, dice,
the time, afk, dropping, picking up, putting on a table, throwing and catching with the
litter limits and the cleaning drone (across a restart), again and the near misses, the
rooms' own lines, the jukebox, the pond (and that it earns less than mining), the new food,
every room having things to look at, and every client (1.0, 1.4, 1.6 and now) reaching the
new commands. `test_orbit_own_replies.py` sends every reply a real server gives to a
player's own commands through client 1.7 with every "Read aloud" box off, read by NVDA
alone and mixed: each is spoken.

`test_orbit_casino.py` computes each game's return exactly from
economy.json (blackjack with perfect hit-or-stand play), so a change that
would give players the edge fails there. `test_orbit_worlds.py` checks every
world's map (each room reached from its port and back, 6 to 15 rooms, air
rescue in the same world) and the travel links between the worlds.

`tests/orbit_parse_1_0.py` and `tests/orbit_parse_1_4.py` are frozen copies
of the 1.0 and 1.4 clients' command readers: `test_orbit_compat.py` checks
that every command added later still reaches the server from them and from
client 1.6's, that what they send in Indonesian gets the English help hint,
and that a hello asking for `"lang": "id"` is answered in English. The
residents', pets', families' and weddings' tests run on a fixed clock with
seeded randomness; `test_orbit_npcs.py` also
migrates a version 7 database to 8. `test_orbit_markets.py` checks that each
station market lists and trades only its own goods, the way to the nearest
one, and that a version 8 database keeps its prices at the new markets;
`test_orbit_guide.py` the compact way and the guide (the next step, a
detour, arriving, stopping, logging out and travel), past keycard doors,
through the dark, down the one-way slide and out into vacuum.

## Later (not in 1.6)

- **Pets shared by two players:** a companion already has any number of
  owners (`companion_owners`), as children do; a pet could be given to a
  partner too.
- **More residents,** and residents on the other worlds' posts: `npcs.json`
  takes new ones without code, as long as their live topics are among
  `World.NPC_LIVE` in `orbit_world.py`.
