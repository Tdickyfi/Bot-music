import os
import asyncio
import subprocess
import time
from datetime import datetime, timedelta
from highrise import BaseBot, User, Position, AnchorPosition
from highrise.models import SessionMetadata, ChatEvent
import yt_dlp
from flask import Flask, Response
import threading
# Removed import ffmpeg as it was causing typing_extensions issues

# Configuration
ICECAST_URL = "icecast://source:wom2jIQw@link.zeno.fm:80/b5jjtoz7edcuv"
AUTOPLAY_SOURCE = "https://drive.uber.radio/uber/bollywood2010s/icecast.audio"
HOST_USERNAME = "harmanpreet_19"

# State management
queue = []
current_song = None
mods = set()
user_last_request = {} # username: datetime
ffmpeg_process = None

app = Flask(__name__)

def get_audio_url(query):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',
        'source_address': '0.0.0.0'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(query, download=False)
            if info and 'entries' in info and len(info['entries']) > 0:
                info = info['entries'][0]
            if info:
                return info.get('url'), info.get('title', 'Unknown Title')
        except Exception:
            pass
    return None, None

def start_streaming(url, is_relay=False):
    global ffmpeg_process
    if ffmpeg_process:
        try:
            ffmpeg_process.terminate()
        except:
            pass

    if is_relay:
        # User requested relay logic
        command = [
            'ffmpeg', '-i', url,
            '-f', 'mp3', '-acodec', 'copy',
            '-ice_name', 'My Relay Station',
            '-ice_genre', 'Mixed',
            ICECAST_URL
        ]
    else:
        command = [
            'ffmpeg', '-re', '-i', url,
            '-acodec', 'libmp3lame', '-ab', '128k',
            '-f', 'mp3', ICECAST_URL
        ]

    ffmpeg_process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

class MusicBot(BaseBot):
    async def on_start(self, session_metadata: SessionMetadata) -> None:
        print("Bot started")
        asyncio.create_task(self.playback_loop())

    async def on_user_join(self, user: User, position: Position | AnchorPosition) -> None:
        await self.highrise.chat(f"Welcome to the room, @{user.username}! <color=#FFD700>Enjoy the music!</color>")

    async def on_chat(self, user: User, message: str) -> None:
        parts = message.split()
        if not parts: return
        cmd = parts[0].lower()
        args = " ".join(parts[1:])

        if cmd == "-play":
            await self.handle_play(user, args)
        elif cmd == "-skip":
            await self.handle_skip(user)
        elif cmd == "-np":
            await self.handle_np()
        elif cmd == "-queue":
            await self.handle_queue()
        elif cmd == "-icecast" and user.username == HOST_USERNAME:
            await self.handle_update_icecast(args)
        elif cmd == "-autoplay" and user.username == HOST_USERNAME:
            await self.handle_update_autoplay(args)
        elif cmd == "-mod":
            await self.handle_mod(user, args)
        elif cmd == "-unmod":
            await self.handle_unmod(user, args)

    async def handle_play(self, user: User, query: str):
        if not query:
            await self.highrise.chat("Usage: -play (song name or url)")
            return

        is_mod = user.username == HOST_USERNAME or user.username in mods
        now = datetime.now()

        if not is_mod:
            last_time = user_last_request.get(user.username)
            if last_time and now - last_time < timedelta(minutes=8):
                wait_sec = 480 - (now - last_time).seconds
                wait_min = wait_sec // 60
                await self.highrise.chat(f"@{user.username}, please wait {wait_min}m {wait_sec % 60}s to request again.")
                return

        try:
            url, title = get_audio_url(query)
            if url:
                queue.append({'url': url, 'title': title, 'user': user.username})
                user_last_request[user.username] = now
                await self.highrise.chat(f"<color=#00FF00>Added to queue:</color> {title}")
            else:
                await self.highrise.chat("Could not find the song.")
        except Exception as e:
            await self.highrise.chat(f"Error: {str(e)}")

    async def handle_skip(self, user: User):
        if user.username == HOST_USERNAME or user.username in mods:
            global ffmpeg_process
            if ffmpeg_process:
                ffmpeg_process.terminate()
                ffmpeg_process = None
                await self.highrise.chat("<color=#FF4500>Song skipped by mod.</color>")
        else:
            await self.highrise.chat("Only mods can skip.")

    async def handle_np(self):
        if current_song:
            await self.highrise.chat(f"<color=#1E90FF>Now Playing:</color> {current_song['title']}")
        else:
            await self.highrise.chat("Autoplaying radio...")

    async def handle_queue(self):
        if not queue:
            await self.highrise.chat("Queue is empty.")
            return

        text = "<color=#9370DB>Queue:</color>\n"
        for i, song in enumerate(queue):
            text += f"{i+1}. {song['title']}\n"

        # Split into 250 char chunks
        for i in range(0, len(text), 250):
            chunk = text[i:i+250]
            await self.highrise.chat(chunk)

    async def handle_mod(self, user: User, target: str):
        if user.username != HOST_USERNAME: return
        target = target.replace("@", "").strip()
        mods.add(target)
        await self.highrise.chat(f"@{target} is now a mod.")

    async def handle_unmod(self, user: User, target: str):
        if user.username != HOST_USERNAME: return
        target = target.replace("@", "").strip()
        mods.discard(target)
        await self.highrise.chat(f"@{target} is no longer a mod.")

    async def handle_update_icecast(self, url: str):
        global ICECAST_URL
        if not url:
            await self.highrise.chat(f"Current Icecast: {ICECAST_URL}")
            return
        ICECAST_URL = url.strip()
        await self.highrise.chat(f"Icecast URL updated to: {ICECAST_URL}")
        # Restart streaming if autoplaying
        global ffmpeg_process
        if not queue and ffmpeg_process:
            ffmpeg_process.terminate()

    async def handle_update_autoplay(self, url: str):
        global AUTOPLAY_SOURCE
        if not url:
            await self.highrise.chat(f"Current Autoplay: {AUTOPLAY_SOURCE}")
            return
        AUTOPLAY_SOURCE = url.strip()
        await self.highrise.chat(f"Autoplay source updated to: {AUTOPLAY_SOURCE}")
        # Restart streaming if autoplaying
        global ffmpeg_process
        if not queue and ffmpeg_process:
            ffmpeg_process.terminate()

    async def playback_loop(self):
        global current_song, ffmpeg_process
        while True:
            if queue:
                current_song = queue.pop(0)
                await self.highrise.chat(f"<color=#FF69B4>Starting:</color> {current_song['title']}")
                start_streaming(current_song['url'])
                while ffmpeg_process and ffmpeg_process.poll() is None:
                    await asyncio.sleep(2)
                current_song = None
            else:
                if not ffmpeg_process or ffmpeg_process.poll() is not None:
                    print("Queue empty, starting autoplay relay...")
                    start_streaming(AUTOPLAY_SOURCE, is_relay=True)
                await asyncio.sleep(5)

@app.route("/stream")
def stream():
    def generate_ffmpeg_stream():
        command = [
            'ffmpeg', '-i', AUTOPLAY_SOURCE, '-f', 'mp3', '-ab', '128k', '-acodec', 'libmp3lame', 'pipe:1'
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            while True:
                chunk = process.stdout.read(4096)
                if not chunk: break
                yield chunk
        finally:
            process.terminate()
    return Response(generate_ffmpeg_stream(), mimetype="audio/mpeg")

@app.route("/")
def index():
    return "<h1>Radio Server is Live</h1><audio controls src='/stream'></audio>"

def run_flask():
    app.run(host="0.0.0.0", port=5000, threaded=True)

if __name__ == "__main__":

    room_id = "699437b233d230a20ef07a72"

    bot_token = "09e6b17fc8510e5a146fbb5de4d45eefc42227bae692ac80070319c8f22719ad"

    # Run Flask in a separate thread
    threading.Thread(target=run_flask, daemon=True).start()

    from highrise.__main__ import BotDefinition, main
    
    # Create the bot definition as required by the SDK's main function
    # Definitions: List[BotDefinition]
    # In some versions of the SDK, MusicBot might not need to be instantiated here
    # if main() handles it, but typically BotDefinition takes the instance.
    definitions = [BotDefinition(MusicBot(), room_id, bot_token)]
    
    try:
        # Check if main is a coroutine
        if asyncio.iscoroutinefunction(main):
            asyncio.run(main(definitions))
        else:
            main(definitions)
    except Exception as e:
        print(f"Error starting bot: {e}")
        pass
