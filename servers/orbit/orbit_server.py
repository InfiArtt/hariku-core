#!/usr/bin/env python3
# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The Orbit server: a small multiplayer text game (a MUD) on a space station,
played through Hariku's Orbit extension. Python 3.10+, standard library only.

    python3 orbit_server.py --config config.json

It listens on 127.0.0.1 (port 7340 by default) behind a web server that
handles TLS and passes /orbit/ on to it:

    GET /orbit/ws       the game, over WebSocket (orbit_ws.py)
    GET /orbit/health   {"ok": true, "online": 3, ...} for checks

(/ws and /health work too, for a proxy that strips the /orbit prefix.)

One thread, one asyncio loop: connections are read and written here, and
orbit_game.Game (plain code, no I/O) decides everything. Each connection has
a rate limit, a size limit on messages, an idle timeout and a limit on how
much may wait to be sent to it. Only a salted hash of a client's address is
kept, for bans; addresses, secrets and chat never reach the log.

Configuration: a JSON file (see config.example.json), and ORBIT_CONFIG,
ORBIT_HOST, ORBIT_PORT, ORBIT_DB in the environment, and the command line.
See README.md for running it with systemd and nginx or Apache.
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import orbit_game  # noqa: E402
import orbit_lang  # noqa: E402
import orbit_safety  # noqa: E402
import orbit_store  # noqa: E402
import orbit_world  # noqa: E402
import orbit_ws as ws  # noqa: E402

VERSION = "1.6"
logger = logging.getLogger("orbit")

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 7340,
    "ws_paths": ["/orbit/ws", "/ws"],
    "health_paths": ["/orbit/health", "/health"],
    "database": "orbit.db",
    "world": "world.json",
    "economy": "economy.json",
    "npcs": "npcs.json",          # the residents who aren't players
    "texts": "texts.json",
    "words": "words.json",
    "hunt": "",                   # the hunt's season file (private: never in the repository)
    "max_connections": 200,
    "max_per_ip": 8,
    "max_message": 4096,
    "max_pending_bytes": 512 * 1024,
    "handshake_timeout": 10,
    "hello_timeout": 20,
    "idle_timeout": 120,
    "linger_seconds": 2.0,        # after the server closes: reading what the client still sends
    "tick_seconds": 1.0,
    "rate": 5.0,                  # messages a second from one connection...
    "burst": 15,                  # ...with this many in a quick row
    "abuse_limit": 40,            # dropped messages before the connection is closed
    "proxy_ip_header": "X-Real-IP",   # read only from a proxy on this computer; "" to ignore
    "allowed_origins": [],        # browsers send an Origin; the Hariku client doesn't
    "hash_iterations": orbit_store.HASH_ITERATIONS,
    "log_level": "INFO",
    "game": {},                   # orbit_game.GAME_DEFAULTS: admins, cooldowns, ...
}


def load_config(path=None, overrides=None):
    """The settings: DEFAULTS, then the JSON file, then ORBIT_* variables,
    then `overrides`. File paths in it are relative to the file's folder."""
    config = json.loads(json.dumps(DEFAULTS))
    base = HERE
    path = path or os.environ.get("ORBIT_CONFIG")
    if path:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("the configuration file must hold a JSON object")
        game = data.pop("game", None)
        config.update(data)
        if isinstance(game, dict):
            config["game"].update(game)
        base = os.path.dirname(os.path.abspath(path))
    env = {"host": os.environ.get("ORBIT_HOST"), "port": os.environ.get("ORBIT_PORT"),
           "database": os.environ.get("ORBIT_DB")}
    for key, value in env.items():
        if value:
            config[key] = int(value) if key == "port" else value
    for key, value in (overrides or {}).items():
        if value is not None:
            if key == "game":
                config["game"].update(value)
            else:
                config[key] = value
    for key in ("database", "world", "economy", "npcs", "texts", "words", "hunt"):
        value = config.get(key)
        if value and value != ":memory:" and not os.path.isabs(value):
            candidate = os.path.join(base, value)
            if key != "database" and not os.path.exists(candidate):
                candidate = os.path.join(HERE, value)       # the bundled file
            config[key] = candidate
    return config


# ------------------------------------------------------------
# One WebSocket connection
# ------------------------------------------------------------

class Connection:
    """What the game calls a connection: send(), close(), lang, ip_hash, session."""

    def __init__(self, server, reader, writer, ip):
        self.server = server
        self.reader = reader
        self.writer = writer
        config = server.config
        self.ip_hash = server.store.ip_hash(ip)
        self.lang = orbit_lang.DEFAULT_LANGUAGE
        self.session = None
        self.decoder = ws.FrameDecoder(expect_masked=True, max_message=config["max_message"])
        self.queue = asyncio.Queue()
        self.pending = 0
        self.closing = False
        self.closing_at = None        # when the server started closing (time.monotonic)
        self.close_queued = False     # a close frame is on its way: end politely
        self.read_done = asyncio.Event()      # nothing more will be read (see _half_close)
        self.bucket = orbit_safety.TokenBucket(config["rate"], config["burst"])
        self.dropped_messages = 0
        self.warned_at = 0.0
        self.joined = False

    # --- what the game uses ---------------------------------------------------------

    def send(self, message):
        if self.closing:
            return
        data = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        self._queue(ws.encode_frame(ws.OP_TEXT, data))

    def close(self, code=ws.CLOSE_NORMAL, reason=""):
        """Every close the server starts (a policy, kick, ban, a login from
        elsewhere, bad data, a message too big, restarting) comes here: the
        close frame goes after everything already queued, then _half_close."""
        if self.closing:
            return
        self._start_closing()
        self.close_queued = True
        self.queue.put_nowait(ws.encode_frame(ws.OP_CLOSE, ws.close_payload(code, reason)))
        self.queue.put_nowait(None)

    # --- inside ---------------------------------------------------------------------

    def _start_closing(self):
        self.closing = True
        if self.closing_at is None:
            self.closing_at = time.monotonic()

    def _queue(self, frame):
        self.pending += len(frame)
        if self.pending > self.server.config["max_pending_bytes"]:
            # A client that doesn't read: let it go rather than hold its backlog.
            self._start_closing()
            self.queue.put_nowait(None)
            return
        self.queue.put_nowait(frame)

    async def _write_loop(self):
        polite = False
        try:
            while True:
                frame = await self.queue.get()
                if frame is None:
                    polite = self.close_queued
                    break
                self.pending -= len(frame)
                self.writer.write(frame)
                await asyncio.wait_for(self.writer.drain(), timeout=30)
        except (ConnectionError, OSError, asyncio.TimeoutError):
            pass
        finally:
            self._start_closing()
            if polite:
                await self._half_close()
            try:
                self.writer.close()
            except Exception:
                pass

    async def _half_close(self):
        """After our close frame: end our side only (a FIN), and give run() a
        moment to read what the client still sends before the socket closes.
        A socket closed with unread data in it sends a reset instead of a FIN
        (Windows and Linux alike), and a reset can make the client lose the
        last lines and the close frame still on their way to it, which a
        player on a bad connection would hear as a dropped line."""
        try:
            if self.writer.can_write_eof():
                self.writer.write_eof()         # after what is still buffered
        except (OSError, RuntimeError):
            return
        try:
            await asyncio.wait_for(self.read_done.wait(), timeout=self._linger_seconds())
        except asyncio.TimeoutError:
            pass

    def _linger_seconds(self):
        return max(0.0, float(self.server.config.get("linger_seconds", 2.0)))

    async def _linger(self, pending=b""):
        """Reads and drops what the client sends after the server started
        closing, until its close frame, the end of its data, or
        linger_seconds after closing began: bounded, and never blocking the
        loop."""
        decoder = self.decoder
        deadline = (self.closing_at or time.monotonic()) + self._linger_seconds()
        data = pending
        while True:
            if data and decoder is not None:
                try:
                    if any(opcode == ws.OP_CLOSE for opcode, _payload in decoder.feed(data)):
                        return
                except ws.ProtocolError:
                    decoder = None              # past the rules: just drop the rest
            left = deadline - time.monotonic()
            if left <= 0:
                return
            try:
                data = await asyncio.wait_for(self.reader.read(65536), timeout=left)
            except (asyncio.TimeoutError, ConnectionError, OSError):
                return
            if not data:
                return

    async def run(self, leftover=b""):
        config = self.server.config
        writer_task = asyncio.ensure_future(self._write_loop())
        started = time.monotonic()
        ended = False               # the client's data ended (or its connection broke)
        pending = b""               # read after the server began closing: not handled
        try:
            data = leftover
            while not self.closing:
                if data:
                    for opcode, payload in self.decoder.feed(data):
                        self._handle(opcode, payload)
                        if self.closing:
                            break
                if self.closing:
                    break
                timeout = config["idle_timeout"]
                if not self.joined:
                    timeout = max(0.1, config["hello_timeout"] - (time.monotonic() - started))
                try:
                    data = await asyncio.wait_for(self.reader.read(65536), timeout=timeout)
                except asyncio.TimeoutError:
                    self.close(ws.CLOSE_POLICY if not self.joined else ws.CLOSE_GOING_AWAY,
                               "no hello" if not self.joined else "idle")
                    break
                if not data:
                    ended = True
                    break
                if self.closing:
                    pending = data          # closed meanwhile (a kick, a login elsewhere)
        except ws.ProtocolError as e:
            self.close(e.code, str(e)[:100])
        except (ConnectionError, OSError):
            ended = True
        except Exception:
            logger.exception("a connection failed")
            self.close(ws.CLOSE_INTERNAL, "server error")
        finally:
            if self.session is not None:
                self.server.game.dropped(self)
            if not self.closing:
                self._start_closing()
                self.queue.put_nowait(None)
            if self.close_queued and not ended:
                try:
                    await self._linger(pending)
                except Exception:
                    logger.exception("closing a connection failed")
            self.read_done.set()
            try:
                await asyncio.wait_for(writer_task, timeout=5 + self._linger_seconds())
            except (asyncio.TimeoutError, Exception):
                writer_task.cancel()

    def _handle(self, opcode, payload):
        if opcode == ws.OP_PING:
            self._queue(ws.encode_frame(ws.OP_PONG, payload))
        elif opcode == ws.OP_PONG:
            pass
        elif opcode == ws.OP_CLOSE:
            try:
                code, _reason = ws.parse_close(payload)
            except ws.ProtocolError as e:
                code = e.code
            self.close(ws.CLOSE_NORMAL if code in (ws.CLOSE_NO_STATUS,) else code)
        elif opcode == ws.OP_BINARY:
            self.close(ws.CLOSE_UNSUPPORTED, "text only")
        else:
            self._message(payload)

    def _message(self, text):
        if not self.bucket.take():
            self.dropped_messages += 1
            if self.dropped_messages > self.server.config["abuse_limit"]:
                self.close(ws.CLOSE_POLICY, "too many messages")
                return
            now = time.monotonic()
            if self.session is not None and now - self.warned_at > 2.0:
                self.warned_at = now
                self.send({"t": "ev", "k": "error",
                           "text": self.server.game.render(self.lang, "slow_down")})
            return
        try:
            message = json.loads(text)
        except ValueError:
            return
        if not isinstance(message, dict):
            return
        if not self.joined:
            if message.get("t") != "hello":
                self.close(ws.CLOSE_POLICY, "hello first")
                return
            self.joined = self.server.game.hello(self, message)
            return
        self.server.game.receive(self, message)


# ------------------------------------------------------------
# The server
# ------------------------------------------------------------

class OrbitServer:
    def __init__(self, config, game=None):
        self.config = config
        self.store = orbit_store.Store(config["database"], iterations=config["hash_iterations"])
        if game is None:
            world = orbit_world.World.load(config["world"], config.get("economy"), config.get("npcs"))
            texts = orbit_lang.Texts(config["texts"])
            words = []
            if config.get("words") and os.path.exists(config["words"]):
                words = orbit_safety.load_words(config["words"])
            game_config = dict(config.get("game") or {})
            if config.get("hunt"):
                game_config.setdefault("hunt_path", config["hunt"])
            game = orbit_game.Game(world, self.store, texts, game_config,
                                   orbit_safety.WordFilter(words))
        self.game = game
        self.connections = set()
        self.per_ip = {}
        self.server = None
        self.port = None
        self._tick_task = None
        self._stopping = None

    async def start(self):
        self._stopping = asyncio.Event()
        self.server = await asyncio.start_server(self._accept, self.config["host"],
                                                 int(self.config["port"]))
        self.port = self.server.sockets[0].getsockname()[1]
        self._tick_task = asyncio.ensure_future(self._ticks())
        logger.info("Orbit %s listening on %s:%s", VERSION, self.config["host"], self.port)
        return self.port

    async def _ticks(self):
        while True:
            await asyncio.sleep(float(self.config["tick_seconds"]))
            try:
                self.game.tick()
            except Exception:
                logger.exception("a tick failed")

    async def stop(self):
        """Tell everyone, save, close every connection, stop listening."""
        if self.server is None:
            return
        logger.info("stopping")
        self.server.close()
        try:
            self.game.shutdown()
        except Exception:
            logger.exception("saving on shutdown failed")
        for conn in list(self.connections):
            conn.close(ws.CLOSE_GOING_AWAY, "server restarting")
        deadline = time.monotonic() + 3
        while self.connections and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        if self._tick_task is not None:
            self._tick_task.cancel()
        await self.server.wait_closed()
        self.store.close()
        self.server = None

    async def serve_forever(self):
        await self.start()
        loop = asyncio.get_running_loop()
        for sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
            if sig is None:
                continue
            try:
                loop.add_signal_handler(sig, self._stopping.set)
            except (NotImplementedError, RuntimeError):
                pass        # Windows: Ctrl+C raises KeyboardInterrupt instead
        try:
            await self._stopping.wait()
        finally:
            await self.stop()

    # --- a new TCP connection: HTTP first -----------------------------------------------

    def _client_ip(self, writer, headers):
        peer = writer.get_extra_info("peername") or ("", 0)
        ip = peer[0] if isinstance(peer, (tuple, list)) else str(peer)
        header = str(self.config.get("proxy_ip_header") or "").lower()
        if header and ws.is_local(ip) and headers.get(header):
            ip = headers[header].split(",")[0].strip() or ip
        return ip

    async def _read_head(self, reader):
        buffer = b""
        while True:
            found = ws.split_head(buffer)
            if found is not None:
                return found
            chunk = await reader.read(4096)
            if not chunk:
                raise ws.HandshakeError("closed before the request ended")
            buffer += chunk

    async def _answer(self, writer, status, body="", content_type="text/plain; charset=utf-8"):
        try:
            writer.write(ws.http_response(status, body, content_type))
            await asyncio.wait_for(writer.drain(), timeout=5)
        except (ConnectionError, OSError, asyncio.TimeoutError):
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def _accept(self, reader, writer):
        if len(self.connections) >= self.config["max_connections"]:
            await self._answer(writer, 503, "full\n")
            return
        try:
            head, rest = await asyncio.wait_for(self._read_head(reader),
                                                timeout=self.config["handshake_timeout"])
            start, headers = ws.parse_head(head)
        except ws.HandshakeError as e:
            await self._answer(writer, e.status, "bad request\n")
            return
        except (asyncio.TimeoutError, ConnectionError, OSError):
            try:
                writer.close()
            except Exception:
                pass
            return
        parts = start.split(" ")
        target = parts[1] if len(parts) >= 2 else "/"
        path = target.split("?", 1)[0]
        if path in self.config["health_paths"]:
            body = json.dumps({"ok": True, "service": "orbit", "version": VERSION,
                               "protocol": orbit_game.PROTOCOL_VERSION,
                               "online": self.game.online_count()})
            await self._answer(writer, 200, body + "\n", "application/json")
            return
        if path not in self.config["ws_paths"]:
            await self._answer(writer, 404, "not found\n")
            return
        origin = headers.get("origin")
        if origin and origin not in self.config["allowed_origins"]:
            await self._answer(writer, 403, "origin not allowed\n")
            return
        try:
            _target, key = ws.check_request(start, headers)
        except ws.HandshakeError as e:
            await self._answer(writer, e.status, f"{e}\n")
            return
        ip = self._client_ip(writer, headers)
        if self.per_ip.get(ip, 0) >= self.config["max_per_ip"]:
            await self._answer(writer, 503, "too many connections\n")
            return
        try:
            writer.write(ws.server_response(key))
            await writer.drain()
        except (ConnectionError, OSError):
            return
        conn = Connection(self, reader, writer, ip)
        self.connections.add(conn)
        self.per_ip[ip] = self.per_ip.get(ip, 0) + 1
        try:
            await conn.run(rest)
        finally:
            self.connections.discard(conn)
            left = self.per_ip.get(ip, 1) - 1
            if left > 0:
                self.per_ip[ip] = left
            else:
                self.per_ip.pop(ip, None)


class ServerThread:
    """The server on a thread of its own, for tests and trying things out:

        with ServerThread(config) as server:
            url = f"ws://127.0.0.1:{server.port}/orbit/ws"
    """

    def __init__(self, config, game=None):
        self.config = config
        self.game = game
        self.port = None
        self.server = None
        self.loop = None
        self._ready = threading.Event()
        self._error = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="orbit-server")

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.server = OrbitServer(self.config, self.game)
            self.port = self.loop.run_until_complete(self.server.start())
        except Exception as e:           # reported by start()
            self._error = e
            self._ready.set()
            return
        self._ready.set()
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    def start(self, timeout=10):
        self._thread.start()
        self._ready.wait(timeout)
        if self._error is not None:
            raise self._error
        if self.port is None:
            raise RuntimeError("the server did not start")
        return self

    def call(self, fn, *args, timeout=5):
        """Run fn(*args) on the server's thread and return what it returns."""
        done = threading.Event()
        box = {}

        def run():
            try:
                box["value"] = fn(*args)
            except Exception as e:
                box["error"] = e
            done.set()

        self.loop.call_soon_threadsafe(run)
        if not done.wait(timeout):
            raise TimeoutError("the server thread did not answer")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def stop(self, timeout=10):
        if self.loop is None or self.server is None:
            return
        future = asyncio.run_coroutine_threadsafe(self.server.stop(), self.loop)
        try:
            future.result(timeout)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._thread.join(timeout)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description="The Orbit game server.")
    parser.add_argument("--config", help="a JSON configuration file (see config.example.json)")
    parser.add_argument("--host", help="the address to listen on (default 127.0.0.1)")
    parser.add_argument("--port", type=int, help="the port to listen on (default 7340)")
    parser.add_argument("--db", dest="database", help="the SQLite database file")
    args = parser.parse_args(argv)
    config = load_config(args.config, {"host": args.host, "port": args.port,
                                       "database": args.database})
    logging.basicConfig(level=getattr(logging, str(config["log_level"]).upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    server = OrbitServer(config)
    try:
        asyncio.run(server.serve_forever())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
