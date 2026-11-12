#!/usr/bin/env python3
"""Fast Telegram digest straight from the Telethon session — no LLM rounds.

Usage:
    telegram_fetch.py --env ~/.env-file --out /tmp/tg-quick.json [--max-chats 8] [--limit 5]

Walks dialogs once, picks unread hits (users first, then groups), fetches only
the last N messages on those hits, writes one compact JSON. Prints one line:
`<username> unread_chats=<n> msgs=<m> in <s>s`.
Never prints phone, session, or api hash.
"""
from __future__ import annotations
import argparse, asyncio, json, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import dotenv_values
from telethon import TelegramClient
from telethon.sessions import StringSession

MSK = timezone(timedelta(hours=3))
SKIP_NAMES = {"hermes_hzfi_bot"}  # own agent bot mirrors the session, not new work

def clip(text, n=280):
    return " ".join((text or "").split())[:n]

async def fetch_chat(client, d, limit):
    msgs = []
    chat_name = d.name or d.title
    async for m in client.iter_messages(d, limit=limit):
        if m.out:
            sender = "я"
        elif d.is_user:
            sender = chat_name  # 1-1 DM: sender is the contact, skip lookup
        else:
            sender = None
            if m.sender_id:
                try:
                    s = await m.get_sender()
                    sender = getattr(s, "first_name", None) or getattr(s, "title", None) or str(m.sender_id)
                except Exception:
                    sender = str(m.sender_id)
        msgs.append({"t": m.date.astimezone(MSK).strftime("%m-%d %H:%M"),
                     "out": bool(m.out), "sender": sender,
                     "text": clip(m.message),
                     "media": type(m.media).__name__ if m.media else None})
    msgs.reverse()
    return {"title": d.name or d.title,
            "kind": "user" if d.is_user else ("group" if d.is_group else "channel"),
            "id": d.id, "unread": d.unread_count, "msgs": msgs}

async def quick(env_path, max_chats, limit, recent=12, search=None, search_limit=8):
    env = dotenv_values(str(env_path))
    client = TelegramClient(StringSession(env["TELEGRAM_SESSION_STRING"]),
                            int(env["TELEGRAM_API_ID"]), env["TELEGRAM_API_HASH"])
    await client.connect()
    me = await client.get_me()
    hits = []
    seen = set()
    recent_dialogs = []
    async for d in client.iter_dialogs(limit=None):
        recent_dialogs.append(d)
        if search:
            continue
        if not d.unread_count:
            continue
        uname = getattr(d.entity, "username", None) or ""
        if uname in SKIP_NAMES:
            continue
        hits.append(d)
        seen.add(d.id)
    # users first, humans before bots, then by unread desc
    def rank(d):
        try:
            is_bot = bool(getattr(d.entity, "bot", False))
        except Exception:
            is_bot = False
        return (is_bot, not d.is_user, -(d.unread_count or 0))
    hits.sort(key=rank)
    hits = hits[:max_chats]
    chats = []
    for d in hits:
        chats.append(await fetch_chat(client, d, limit))
    # today's human activity even when read: most recent dialogs, last 3 msgs, keep today's incoming
    today = datetime.now(MSK).date()
    fresh = []
    for d in recent_dialogs:
        if len(fresh) >= recent:
            break
        if d.id in seen:
            continue
        uname = getattr(d.entity, "username", None) or ""
        if uname in SKIP_NAMES:
            continue
        row = await fetch_chat(client, d, 3)
        todays = [m for m in row["msgs"]
                   if not m["out"] and m["t"].startswith(today.strftime("%m-%d")) and (m["text"] or m["media"])]
        if todays:
            row["msgs"] = todays
            row["today"] = True
            fresh.append(row)
    for row in fresh:
        chats.append(row)
    if search:
        needle = search.strip().lower()
        found = []
        for d in recent_dialogs:
            nm = (d.name or d.title or "")
            if needle and needle in nm.lower():
                uname = getattr(d.entity, "username", None) or ""
                if uname in SKIP_NAMES:
                    continue
                found.append(d)
                if len(found) >= 3:
                    break
        for d in found:
            row = await fetch_chat(client, d, search_limit)
            row["today"] = True
            chats.append(row)
    await client.disconnect()
    return {"me": me.username, "chats": chats,
            "unread_chats": len(hits),
            "total_msg": sum(len(c["msgs"]) for c in chats)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-chats", type=int, default=10)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--search", default=None, help="dialog name substring, max 3 hits")
    ap.add_argument("--search-limit", type=int, default=8)
    a = ap.parse_args()
    t0 = time.time()
    data = asyncio.run(quick(Path(a.env).expanduser(), a.max_chats, a.limit,
                             search=a.search, search_limit=a.search_limit))
    out = Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{data['me']} unread_chats={data['unread_chats']} msgs={data['total_msg']} in {time.time()-t0:.1f}s -> {out}")

if __name__ == "__main__":
    main()
