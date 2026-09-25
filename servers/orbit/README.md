# Orbit server

Orbit is a small multiplayer text game (a MUD) set in a shared simulation:
players enter at a space station orbiting the Earth, its hub, and travel on
to other worlds (the Moon, the red planet Karmina, the ice moon Glasir, the
Drift Bazaar, the fantasy world Evergrove, Lumina City and Pixel Pier). It is
played through Hariku's **Orbit** extension (`extensions/orbit`). This folder is the server: Python 3.10 or
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
| `orbit_casino.py` | the Casino Corner: dice, slots, blackjack, coin flips, the weekly lottery |
| `orbit_trade.py` | trading between players (offer, accept), and the pawn shop |
| `orbit_progress.py` | achievements and the leaderboards |
| `orbit_travel.py` | the worlds: the Gate, the ferry, players' own ships, customs |
| `orbit_local.py` | the other worlds' own work: Evergrove's creatures, Lumina City's courier gigs |
| `orbit_events.py` | events: random, weekly, seasonal, parties, the co-op drone, admins' events |
| `orbit_events.py` | events: random, weekly, seasonal, parties, the co-op drone, admins' events |
| `orbit_admin.py` | moving a character to another computer; the admins' commands |
| `orbit_verbs.py` | the commands the server reads from plain text (both languages) |
| `orbit_world.py`, `world.json` | the map: worlds, rooms, compass exits, objects, goods, missions, gestures |
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
   `orbit_casino.py`, `orbit_trade.py`, `orbit_progress.py`, `orbit_travel.py`, `orbit_local.py`,
   `orbit_events.py`,
   `orbit_events.py`,
   `orbit_admin.py`, `orbit_verbs.py`, `orbit_backup.py`,
   `orbit-backup.service`, `orbit-backup.timer`; changed: the other
   `orbit_*.py`, `world.json`, `texts.json`). `config.json` needs no new
   keys: every new setting has a default (below).
2. `systemctl --user restart orbit`.
3. On its first start, the server sees an older database (Orbit 1.0's is
   schema version 0), saves a copy of it as `orbit.db.before-v4.bak` next to
   it, and migrates it to version 4 in one transaction: new columns (voice,
   XP, the daily streak, what a character mined and harvested, what it won
   or lost at the casino) and new tables (companions, ships, events and who
   took part in them, achievements, lottery tickets, transfer codes, old
   secrets, transfers, the admins' log) are added; nothing is dropped or
   changed, and work done before 1.1 counts as XP (10 a repair, 20 a cargo
   run, 25 a mission). The log says "the database was migrated from version
   0 to 4". If the migration fails,
   nothing is changed and the server stops with the error in the log; the
   copy is there.
4. Every room of 1.0 still exists, so characters wake up where they were.
   Returning players are told once what's new, and get a compass (and the
   keycards their XP already earned, and quietly the achievements their
   past work already reached).

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
| `game.events_enabled` | true | events that start by themselves (false: only what admins start or schedule) |
| `game.events_random`, `game.events_seasonal` | true, true | the random events; the station's birthday, New Year, the Lantern Festival |
| `game.events_min_gap`, `game.events_max_gap` | 1800, 3600 | seconds between random events with one player online... |
| `game.events_crowd_factor`, `game.events_min_factor` | 0.1, 0.5 | ...each extra player online makes the gap 10% shorter, down to half |
| `game.events_party_cooldown` | 7200 | how often one player may throw a party |
| `game.events_weekly` | trading fair Saturday 14:00, jackpot night Friday 13:00, night rush Wednesday 13:00 | `[{"event", "weekday" (0 Monday), "hour", "minute"}]`, in UTC |
| `game.events_enabled` | true | events that start by themselves (false: only what admins start or schedule) |
| `game.events_random`, `game.events_seasonal` | true, true | the random events; the station's birthday, New Year, the Lantern Festival |
| `game.events_min_gap`, `game.events_max_gap` | 1800, 3600 | seconds between random events with one player online... |
| `game.events_crowd_factor`, `game.events_min_factor` | 0.1, 0.5 | ...each extra player online makes the gap 10% shorter, down to half |
| `game.events_party_cooldown` | 7200 | how often one player may throw a party |
| `game.events_weekly` | trading fair Saturday 14:00, jackpot night Friday 13:00, night rush Wednesday 13:00 | `[{"event", "weekday" (0 Monday), "hour", "minute"}]`, in UTC |

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
  in the temple (3), the casino's edge, the lottery's cut, and the market's
  fees (10% on buying and 12% on selling; traders 2% and 4%, less with their
  tools), which also make every sale move the price down 2%.
- **The shops** are Star Supply on the East Promenade (the basics) and the
  Mall Ring, up the lift from the Upper Lift Lobby: Gearworks (devices,
  keycards, the suit, drills, job tools), Orbit Outfitters (clothes, titles),
  Cosy Corner (furniture), Whiskers & Widgets (pets), the Food Court, and
  Second Orbit, the pawn shop. Prices move up to 10% either way each day
  (`prices.wobble`), the same for everyone that day, and one thing in each
  shop is today's special, 20% cheaper still (`prices.special`); the bar,
  the seed rack and the lottery booth keep fixed prices, and so do plots.
  Second Orbit pays 40% of a thing's list price (`pawn.rate`) for anything
  but goods, pets, services and what can't be sold (the compass, keycards,
  earned titles).
- **Trading:** `offer Budi 3 iron for 200 credits`; the other player (online,
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
- **Achievements** (`achievements`): 24, each for reaching a number (rooms
  walked, shifts worked, missions, level, crops, ore, a golden chilli, a
  quantum crystal, the daily streak, furniture, credits held, the time
  capsule, a natural, a jackpot, the lottery, a trade), paying 0 to 2,000
  credits and sometimes a title; the big ones (`station`) are news for
  everyone, and the first to earn one is named as the first on the station.
- **Leaderboards:** richest, level, miners, farmers, daily streak and casino,
  the top 5 and your own place; admins are left out.
- **Worlds and travel** (`worlds` in world.json, `travel` in economy.json).
  Each world sits at a position on one long orbit (the station 0, the Belt 1,
  the Moon 2, Lumina City 3, Pixel Pier 4, Evergrove 5, Karmina 6, the Drift
  Bazaar 7, Glasir 8); the distance between two is the difference (at least
  1). The Gate: at once, 25 credits and 10 a unit of distance (the Moon 45,
  Glasir 105). The ferry: 5 credits and 3 a unit (the Moon 11, Glasir 29),
  leaving every 2 minutes and taking 40 seconds a unit (at least a minute).
  Your own ship: 25 seconds a unit divided by its speed (a pilot flies a
  quarter faster), burning fuel at each world's price (2 to 6 credits a
  unit). The Belt is still the Kancil's.
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
- **Events** (world.json `events`; see `orbit_events.py`): 21 in all. Random,
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
  kind pays double), the night rush (courier gigs pay double). Seasonal:
  the station's birthday on 25 September (100 credits and an iced coffee
  each), New Year (watch the fireworks for 50), the Lantern Festival on the
  hundredth day of the year (free lanterns and a 25-credit thank-you).
  Parties: a player's cabin is open to everyone for half an hour, once in
  two hours. Admins can start, stop and schedule events.
- **Events** (world.json `events`; see `orbit_events.py`): 21 in all. Random,
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
  kind pays double), the night rush (courier gigs pay double). Seasonal:
  the station's birthday on 25 September (100 credits and an iced coffee
  each), New Year (watch the fireworks for 50), the Lantern Festival on the
  hundredth day of the year (free lanterns and a 25-credit thank-you).
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
achievements, admin) and spent by sink (shops, market, fares, rescues,
lanterns, casino bets, lottery, admin), so you can see whether money grows
too fast and adjust these numbers.

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
| `mulai acara hujan meteor` / `start event meteor shower` | start any event now |
| `hentikan acara` / `stop event` (and a name) | stop the event (or cancel a scheduled one) |
| `jadwalkan acara 2026-09-27 14:00 ...` / `schedule event 30 ...` | an announcement of your own at a UTC time, or in so many minutes |
| `mulai acara hujan meteor` / `start event meteor shower` | start any event now |
| `hentikan acara` / `stop event` (and a name) | stop the event (or cancel a scheduled one) |
| `jadwalkan acara 2026-09-27 14:00 ...` / `schedule event 30 ...` | an announcement of your own at a UTC time, or in so many minutes |
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
outside, a shuttle ride or ferry trip in progress, a courier gig, its casino
bets of the last hour a minute at a time, how many trades, jackpots,
naturals, gigs and creatures), what it won or lost at the casino, when it was made and last seen, and whether it is
banned or muted; its companions (a pet: kind, name, and its own stats); its
ship (model, name, where it's docked or flying to, fuel and cargo); the
events it took part in (and how much, for the drone's rewards); its
achievements (which, and when); its lottery tickets (how many, for which
week's draw); transfer codes (a hash, for 10 minutes); secrets that no
longer work (a hash); the transfers log; the admins' log; and, in `meta`,
the market's prices, each world's own prices, the economy's totals, today's
temple lanterns, the lottery's next draw and carried-over pot, and the
events' pacing (when the next random one may come, when each last came,
which weekly and seasonal ones have run). Every event that runs or is
scheduled is a row in `events`, with its state and how it ended. Trade offers, coin-flip
challenges and a blackjack hand in progress live only in memory (a hand is
played out, standing, if its player leaves or the server stops). Accounts
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
| `accept` | `n`: a mission's number (none: the newest trade offer or coin flip waiting for you) | |
| `take` | `item`, `n` | a mission's things |
| `buy`, `sell` | `item`, `n` (`"all"` to sell everything, or all of a kind) | market goods, and the shop you're in |
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
| `events`, `join`, `listen`, `catch`, `search`, `watch`, `party` | | events (the drone: `work` at the Dock) |
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
`space`, `belt`, `venue`, `mall`, `casino`, `gate`, `moon`, `colony`, `ice`, `bazaar`, `forest`,
`neon`, `arcade`), `floor` and `acoustics` (where you are now),
`dir` (the way you walked, or the side someone came from or left by), `via`
(`lift`, `ladder`, `slide`, `airlock`, `door`), `codes` (the reactor's
tones, 1 to 4), `sound` (a cue more specific than the kind's), `emote`
(which gesture), `voice` (the voice number a speaker chose; on your own
lines, yours), `words` (on a line said, whispered or shouted, yours or
another player's: the words alone, so a client can read the name in one
voice and the words in the speaker's), `to` (who you whispered to),
`preview` (read this line in `voice`), `ask` (an invitation, an offer, a challenge: answer
with accept or decline), `transfer_code` and `expires`, `reels` (a slot
machine's three symbols, left to right) and `outcome` (`win`, `lose`,
`push`, `jackpot`: the client plays it after the dice land, the cards turn
or the reels stop), `event` (on an announcement: the event it belongs to,
so a client can leave events unread) and `schedule` (with the `events`
list: `[{"event", "name", "at"}]`, the coming ones as UTC timestamps, for
the client to show in local time and set reminders).

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
| `emote`, `emote_smile`, `emote_wave`, `emote_laugh`, `emote_nod`, `emote_shrug`, `emote_clap`, `emote_cheer`, `emote_sigh`, `emote_bow`, `emote_dance`, `emote_hug` | gestures |
| `success`, `fail`, `error`, `mission`, `task`, `tone1` to `tone4` | work, a mission, a task starting, the reactor's tones |
| `coins`, `register`, `trade` | money changing hands; a shop's till; a trade done |
| `mine`, `rare`, `plant`, `water`, `harvest`, `ripe` | mining, a rare find, the farm |
| `levelup`, `daily`, `achievement` | a new level; the daily bonus; an achievement |
| `equip`, `gadget`, `scan`, `air`, `rescue`, `gulp`, `crunch`, `pet_robot`, `pet_cat` | things: wearing, devices, the scanner, the air warning, the tow, food, pets |
| `bell`, `lantern` | the temple's star bell; lighting a lantern |
| `launch`, `landing`, `gate`, `ferry`, `refuel`, `cargo`, `customs` | ships and shuttles, the Gate, the ferry, fuel, the hold, a customs check |
| `creature` | one of Evergrove's creatures |
| `event_start`, `event_end`, `event_party`, `event_storm`, `event_boss`, `event_meteor`, `fireworks`, `robot_beep` | events beginning and ending, each kind with a sting of its own; the runaway robot's beeps, from its side |
| `event_start`, `event_end`, `event_party`, `event_storm`, `event_boss`, `event_meteor`, `fireworks`, `robot_beep` | events beginning and ending, each kind with a sting of its own; the runaway robot's beeps, from its side |
| `dice`, `reel_spin`, `reel_stop`, `cards`, `deal`, `coinflip`, `lottery`, `lottery_draw` | the casino's games (the reels stop left, middle, right) |
| `win`, `lose`, `push`, `jackpot` | how a game came out |
| `amb_vent`, `amb_cantina`, `amb_engine`, `amb_garden`, `amb_deck`, `amb_space`, `amb_belt`, `amb_venue`, `amb_mall`, `amb_casino`, `amb_gate`, `amb_moon`, `amb_colony`, `amb_ice`, `amb_bazaar`, `amb_forest`, `amb_neon`, `amb_arcade` | the ambience loops (4 seconds, seamless; the other worlds' at 11 kHz) |

The set: 175 files, about 9.4 MB: 104 recorded (2.9 MB) and 71 synthesized;
the ambience loops are at 11 kHz.

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
python -m pytest tests/test_orbit_server.py tests/test_orbit_map.py tests/test_orbit_economy.py tests/test_orbit_casino.py tests/test_orbit_worlds.py tests/test_orbit_events.py tests/test_orbit_compat.py tests/test_orbit_e2e.py -q
```

`test_orbit_casino.py` computes each game's return exactly from
economy.json (blackjack with perfect hit-or-stand play), so a change that
would give players the edge fails there. `test_orbit_worlds.py` checks every
world's map (each room reached from its port and back, 6 to 15 rooms, air
rescue in the same world) and the travel links between the worlds.

`tests/orbit_parse_1_0.py` is a frozen copy of the 1.0 client's command
reader: `test_orbit_compat.py` checks that every command added later still
reaches the server from it.

## Later (not in 1.1)

- **Characters who aren't players (1.2):** people to talk to about topics,
  and residents who walk the compass map on daily schedules and remember
  players; always marked as such, never listed as online players. The room
  code already sends looking, who's here, arrivals, departures, their
  positional sounds and chat through the same few paths (`_in_room`,
  `_to_room`, the `actor` and `dir` fields), so an entity that isn't a
  connection can later be placed in a room and speak through them.

- **Companions:** a pet is already a general `companions` record (its kind,
  name, JSON stats and state, when it came, and its owners in
  `companion_owners`), so later versions can add feeding and attention,
  growing up and learning tricks, several kinds, and companions shared by two
  players, without another big migration.
- **Families:** two players partnering up with consent, and a baby companion
  that needs care, grows into a child, and follows and helps its family.
- **Ceremonies at the venues** (the Star Dome Hall, the Jasmine Pavilion and
  Evergrove's Great Hall are marked `venue` in world.json): a wedding with two lanterns joined into
  one light, a moment of silence, vows the two write themselves and three
  chimes of the star bell (and a neutral ceremony without the temple); a
  naming ceremony for a baby companion; and the yearly Lantern Festival of
  the Way of Starlight as a station-wide event.
