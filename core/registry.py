# jarvis/commands/registry.py
import os

import grpc
from dataclasses import dataclass
from typing import List, Union, Callable, Optional
import sys


"""
import smart_home_pb2
import smart_home_pb2_grpc
import spotify_pb2
import spotify_pb2_grpc
import weather_pb2
import weather_pb2_grpc
import binance_pb2
import binance_pb2_grpc
import jarvis_core_pb2
import jarvis_core_pb2_grpc
import news_pb2
import news_pb2_grpc
import camera_pb2
import camera_pb2_grpc
import google_gemini_pb2
import google_gemini_pb2_grpc
"""


from generated import spotify_pb2, spotify_pb2_grpc

spotify = spotify_pb2_grpc.SpotifyServiceStub(grpc.insecure_channel("spotify-service:50052"))


"""smart_home = smart_home_pb2_grpc.SmartHomeStub(grpc.insecure_channel("smart_home:50051"))
spotify = spotify_pb2_grpc.SpotifyStub(grpc.insecure_channel("spotify:50051"))
weather = weather_pb2_grpc.WeatherStub(grpc.insecure_channel("weather:50051"))
binance = binance_pb2_grpc.BinanceStub(grpc.insecure_channel("binance:50051"))
jarvis_core = jarvis_core_pb2_grpc.JarvisCoreStub(grpc.insecure_channel("jarvis_core:50051"))
news = news_pb2_grpc.NewsStub(grpc.insecure_channel("news:50051"))
camera = camera_pb2_grpc.CameraStub(grpc.insecure_channel("camera:50051"))
google_gemini = google_gemini_pb2_grpc.GoogleGeminiStub(grpc.insecure_channel("google_gemini:50051"))
"""

@dataclass
class Command:
    keywords: List[Union[str, List[str]]]
    handler: Callable
    description: str
    extract_args: bool = False


class CommandRegistry:
    def __init__(self):
        self.commands: List[Command] = []

    def register(self, keywords: List[Union[str, List[str]]], description: str, extract_args: bool = False):
        def decorator(handler: Callable):
            self.commands.append(Command(keywords, handler, description, extract_args))
            return handler
        return decorator

    def find_command(self, words: List[str]) -> Optional[tuple[Command, List[str]]]:
        lower_words = [w.lower() for w in words]
        for command in self.commands:
            matches = True
            for keyword in command.keywords:
                if isinstance(keyword, list):
                    if not any(alt in lower_words for alt in keyword):
                        matches = False
                        break
                else:
                    if keyword not in lower_words:
                        matches = False
                        break
            if matches:
                if command.extract_args:
                    used_words = set()
                    for keyword in command.keywords:
                        if isinstance(keyword, list):
                            for alt in keyword:
                                if alt in lower_words:
                                    used_words.add(alt)
                                    break
                        else:
                            used_words.add(keyword)
                    args = [word for word in words if word.lower() not in used_words]
                    return command, args
                return command, []
        return None


# Global registry
registry = CommandRegistry()

def set_mood_handler(args):
    return "Hello!"

registry.register([["hello", "hi"]], "Hello world!")(set_mood_handler)


registry.register(["play", "music"], "Play a song on spotify", extract_args=True)(
    lambda args: spotify.PlaySong(spotify_pb2.SongRequest(name=" ".join(args)))
)

registry.register(["play", "playlist"], "Play a playlist on spotify", extract_args=True)(
    lambda args: spotify.PlayPlaylist(spotify_pb2.PlaylistRequest(name=" ".join(args)))
)

registry.register([["stop", "pause"], ["music", "song"]], "Stop playback on spotify", extract_args=True)(
    lambda args: spotify.Stop(spotify_pb2.Empty())
)

registry.register([["next", "skip"], ["music", "song"]], "Skip playback on spotify", extract_args=True)(
    lambda args: spotify.Next(spotify_pb2.Empty())
)

registry.register([["continue", "unpause", "resume"], ["music", "song"]], "Resume playback on spotify", extract_args=True)(
    lambda args: spotify.Unpause(spotify_pb2.Empty())
)
registry.register([["shuffle", "change"], ["music", "song"]], "Toggle shuffle on spotify", extract_args=True)(
    lambda args: spotify.ToggleShuffle(spotify_pb2.Empty())
)


registry.register([["volume", "sound"], ["high", "max"]], "Set maximum volume on spotify", extract_args=True)(
    lambda args: spotify.SetVolume(spotify_pb2.VolumeRequest(level=90))
)

registry.register([["volume", "sound"], ["medium", "normal"]], "Set normal volume on spotify", extract_args=True)(
    lambda args: spotify.SetVolume(spotify_pb2.VolumeRequest(level=60))
)

registry.register([["volume", "sound"], "low"], "Set low volume on spotify", extract_args=True)(
    lambda args: spotify.SetVolume(spotify_pb2.VolumeRequest(level=30))
)
"""
# === Binance ===
registry.register([["portfolio", "crypto", "bitcoin", "balance"]], "Binance Portfolio")(
    lambda args: binance.GetPortfolioValue(binance_pb2.Empty())
)

# === Smart Home (Lights) ===
registry.register([["light", "lights"], "on"], "Turn light on.")(
    lambda args: smart_home.TurnOn(smart_home_pb2.Empty())
)

registry.register([["light", "lights"], ["off", "stop", "pause"]], "Turn light off.")(
    lambda args: smart_home.TurnOff(smart_home_pb2.Empty())
)

registry.register([["light", "lights"], ["blue", "blues"]], "Blue lights")(
    lambda args: smart_home.SetColor(smart_home_pb2.SetColorRequest(color="blue"))
)

registry.register([["light", "lights"], "red"], "Red lights")(
    lambda args: smart_home.SetColor(smart_home_pb2.SetColorRequest(color="red"))
)

# === Mood (multi-call example) ===
def set_mood_handler(args):
    spotify.PlayPlaylist(spotify_pb2.PlaylistRequest(name="chill vibes"))
    smart_home.SetColor(smart_home_pb2.SetColorRequest(color="blue"))
    return "Mood set: lights blue, chill playlist playing."

registry.register(["set", "mood"], "Set the mood.")(set_mood_handler)

# === Spotify ===
registry.register([["playlist", "playlists"]], "Play a playlist", extract_args=True)(
    lambda args: spotify.PlayPlaylist(spotify_pb2.PlaylistRequest(name=" ".join(args)))
)

registry.register(["play"], "Play a song", extract_args=True)(
    lambda args: spotify.PlaySong(spotify_pb2.SongRequest(name=" ".join(args)))
)

registry.register(["shuffle"], "Toggle shuffle")(
    lambda args: spotify.ToggleShuffle(spotify_pb2.Empty())
)

registry.register(["volume"], "Adjust volume", extract_args=True)(
    lambda args: spotify.SetVolume(
        spotify_pb2.VolumeRequest(
            level=33 if "low" in args else 66 if "medium" in args else 100 if "max" in args else 0
        )
    )
)

registry.register([["stop", "pause"], "music"], "Stop/pause music")(
    lambda args: spotify.StopMusic(spotify_pb2.Empty())
)

registry.register(["continue", "unpause"], "Continue/unpause music")(
    lambda args: spotify.UnpauseMusic(spotify_pb2.Empty())
)

registry.register(["next"], "Play next song")(
    lambda args: spotify.NextSong(spotify_pb2.Empty())
)

# === Weather ===
registry.register(["weather"], "Weather")(
    lambda args: weather.GetWeather(weather_pb2.Empty())
)

# === Date ===
registry.register([["date", "dates"]], "Today's date")(
    lambda args: f"Today is {datetime.now().strftime('%Y-%m-%d')}"
)

# === Jarvis Core ===
registry.register(["shut", "up"], "Jarvis's comeback")(
    lambda args: "Sir you can fuck off you stupid bitch!"
)

registry.register([["explode", "destruct"]], "Self destruct protocol")(
    lambda args: jarvis_core.Explode(jarvis_core_pb2.Empty())
)

registry.register([["nights", "night"], "good", "goodnight"], "Sleep routine")(
    lambda args: jarvis_core.Goodbye(jarvis_core_pb2.Empty())
)

registry.register([["morning", "mornings"], "good"], "Morning routine")(
    lambda args: jarvis_core.GoodMorning(jarvis_core_pb2.Empty())
)

registry.register(["conversation"], "Chatting with Jarvis", extract_args=True)(
    lambda args: jarvis_core.Chat(jarvis_core_pb2.ChatRequest(message=" ".join(args)))
)

registry.register([["list", "lists", "tell"], ["commands", "command"]], "List commands")(
    lambda args: "\n".join([f"- {' '.join(map(str, cmd.keywords))}: {cmd.description}" for cmd in registry.commands])
)

# === News ===
registry.register(["news"], "Popular news")(
    lambda args: news.SendNews(news_pb2.Empty())
)

# === Camera ===
registry.register(["photo"], "Takes a photograph and sends via telegram")(
    lambda args: camera.TakePhoto(camera_pb2.Empty())
)

# === Google Gemini ===
registry.register(["google"], "Sends message to Google Gemini API", extract_args=True)(
    lambda args: google_gemini.SendMessage(
        google_gemini_pb2.MessageRequest(text=" ".join(args))
    )
)
"""