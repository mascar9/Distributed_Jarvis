import os
import grpc
import logging
from concurrent import futures
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from fuzzywuzzy import fuzz
from pathlib import Path
import json

import generated.spotify_pb2 as spotify_pb2
import generated.spotify_pb2_grpc as spotify_pb2_grpc
from dotenv import load_dotenv

load_dotenv()


import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("spotify-service")

class SpotifyService(spotify_pb2_grpc.SpotifyServiceServicer):
    def __init__(self):
        self.sp = None
        self.sp_oauth = None
        self._init_spotify()

    def _init_spotify(self):
        """Initialize Spotify client with token management"""
        try:
            self.sp_oauth = SpotifyOAuth(
                client_id=os.getenv('SPOTIPY_CLIENT_ID'),
                client_secret=os.getenv('SPOTIPY_CLIENT_SECRET'),
                redirect_uri=os.getenv('SPOTIPY_REDIRECT_URI', 'http://localhost:8888/callback'),
                scope="user-read-playback-state,user-modify-playback-state,user-read-currently-playing"
            )

            # Try to load existing tokens
            token_file = Path('/app/data/spotify_tokens.json')

            if token_file.exists():
                with open(token_file, 'r') as f:
                    token_info = json.load(f)

                # Check if token needs refresh
                if self.sp_oauth.is_token_expired(token_info):
                    logger.info("Refreshing Spotify access token...")
                    token_info = self.sp_oauth.refresh_access_token(token_info['refresh_token'])

                    # Save refreshed token
                    with open(token_file, 'w') as f:
                        json.dump(token_info, f, indent=2)

                self.sp = spotipy.Spotify(auth=token_info['access_token'])
                logger.info("✅ Spotify client initialized successfully")

                # Test connection
                try:
                    user = self.sp.current_user()
                    logger.info(f"👤 Authenticated as: {user.get('display_name', 'Unknown')}")
                except Exception as e:
                    logger.error(f"Could not fetch user info: {e}")

            else:
                logger.error("❌ No Spotify tokens found. Please run authentication first.")
                logger.error("💡 Run: python scripts/spotify_auth.py")

        except Exception as e:
            print(f"Failed to initialize Spotify: {e}")

    def _ensure_authenticated(self):
        """Ensure Spotify client is authenticated and refresh if needed"""
        if not self.sp:
            return False

        try:
            # Test with a simple API call
            self.sp.current_user()
            return True
        except spotipy.SpotifyException as e:
            if e.http_status == 401:  # Unauthorized
                self._init_spotify()
                return self.sp is not None
        except Exception:
            pass

        return False

    def _get_active_device(self):
        """
        Returns the active device dict, or the first device if none are active.
        Returns None if no devices are found.
        """
        try:
            devices_response = self.sp.devices()
            devices = devices_response.get('devices', [])

            if not devices:
                logger.warning("No active Spotify devices found")
                return None

            for device in devices:
                if device.get('is_active'):
                    return device

            # No active device, fallback to first one
            return devices[0]

        except Exception as e:
            logger.error("Failed to fetch Spotify devices", exc_info=True)
            return None


    def PlaySong(self, request, context):
        if not self._ensure_authenticated():
            return spotify_pb2.SpotifyResponse(
                response="❌ Spotify not authenticated. Please check logs.",
                success=False
            )

        try:
            logger.info(f"🔍 Searching for: {request.name}")

            # Search for the track
            search_results = self.sp.search(q=request.name, type='track', limit=1)

            if not search_results['tracks']['items']:
                return spotify_pb2.SpotifyResponse(
                    response=f"🚫 Song '{request.name}' not found",
                    success=False
                )

            track = search_results['tracks']['items'][0]
            track_uri = track['uri']
            track_name = track['name']
            artist_name = track['artists'][0]['name']

            # Get available devices
            active_device = self._get_active_device()
            if not active_device:
                return spotify_pb2.SpotifyResponse(
                    response="No active Spotify devices found. Please open Spotify on a device first.",
                    success=False
                )

            device_id = active_device['id']
            device_name = active_device['name']

            # Start playback
            self.sp.start_playback(uris=[track_uri], device_id=device_id)

            response_msg = f"Playing '{track_name}' by {artist_name} on {device_name}"
            logger.info(response_msg)

            return spotify_pb2.SpotifyResponse(
                response=response_msg,
                success=True
            )

        except spotipy.SpotifyException as e:
            error_msg = f"Spotify API error: {e.reason if hasattr(e, 'reason') else str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )
        except Exception as e:
            error_msg = f"Error playing song: {str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )

    def PlayPlaylist(self, request, context):
        if not self._ensure_authenticated():
            return spotify_pb2.SpotifyResponse(
                response="❌ Spotify not authenticated. Please check logs.",
                success=False
            )

        try:

            playlist_name = request.name

            logger.info(f"🔍 Searching for playlist: {playlist_name}")

            # Fetch user playlists
            playlists = self.sp.current_user_playlists()

            max_similarity = 0
            best_playlist = None

            for playlist in playlists.get('items', []):
                similarity = fuzz.ratio(playlist_name.lower(), playlist['name'].lower())
                if similarity > max_similarity:
                    max_similarity = similarity
                    best_playlist = playlist

            if best_playlist:
                playlist_uri = best_playlist['uri']

                devices_response = self.sp.devices()
                devices = devices_response.get('devices', [])

                if not devices:
                    return spotify_pb2.SpotifyResponse(
                        response="No active Spotify devices found. Please open Spotify on a device first.",
                        success=False
                    )

                active_device = self._get_active_device()
                if not active_device:
                    return spotify_pb2.SpotifyResponse(
                        response="No active Spotify devices found. Please open Spotify on a device first.",
                        success=False
                    )

                device_id = active_device['id']
                device_name = active_device['name']


                # Start playing from the last song in the playlist
                playlist_id = best_playlist['id']
                playlist_tracks = self.sp.playlist_tracks(playlist_id)
                total_tracks = playlist_tracks['total']
                last_song_offset = total_tracks - 5
                offset = {"position": last_song_offset}


                logger.info(f"Now playing {playlist_name}, starting on offset {offset['position']}")
                self.sp.start_playback(device_id=device_id, context_uri=playlist_uri, offset=offset, position_ms=0)

                playlist_correct_name = best_playlist.get('name', playlist_name)
                response_msg = f"🎵 Playing playlist '{playlist_correct_name}' on {device_name}"

                return spotify_pb2.SpotifyResponse(
                    response=response_msg,
                    success=True
                )

            else:
                logger.error(f"No matching playlists found for: {playlist_name}")
                return spotify_pb2.SpotifyResponse(
                    response=f"No matching playlists found for: {playlist_name}",
                    success=False
                )

        except spotipy.SpotifyException as e:
            error_msg = f"Spotify API error: {e.reason if hasattr(e, 'reason') else str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )
        except Exception as e:
            error_msg = f"Error playing song: {str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )

    def Stop(self, request, context):
        if not self._ensure_authenticated():
            return spotify_pb2.SpotifyResponse(
                response="❌ Spotify not authenticated. Please check logs.",
                success=False
            )

        try:
            logger.info(f"Starting to pause...")
            active_device = self._get_active_device()
            if not active_device:
                return spotify_pb2.SpotifyResponse(
                    response="No active Spotify devices found. Please open Spotify on a device first.",
                    success=False
                )

            device_id = active_device['id']
            device_name = active_device['name']

            self.sp.pause_playback(device_id=device_id)

            success_msg = f"Successfully paused spotify on device on {device_name}"
            logger.info(success_msg)

            return spotify_pb2.SpotifyResponse(
                    response=success_msg,
                    success=True
            )

        except spotipy.SpotifyException as e:
            error_msg = f"Spotify API error: {e.reason if hasattr(e, 'reason') else str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )
        except Exception as e:
            error_msg = f"Error stopping spotify: {str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )

    def Unpause(self, request, context):
        if not self._ensure_authenticated():
            return spotify_pb2.SpotifyResponse(
                response="❌ Spotify not authenticated. Please check logs.",
                success=False
            )

        try:
            logger.info(f"Resuming playback...")
            active_device = self._get_active_device()
            if not active_device:
                return spotify_pb2.SpotifyResponse(
                    response="No active Spotify devices found. Please open Spotify on a device first.",
                    success=False
                )

            device_id = active_device['id']
            device_name = active_device['name']

            self.sp.start_playback(device_id=device_id)

            success_msg = f"Successfully resuming playback spotify on device on {device_name}"
            logger.info(success_msg)

            return spotify_pb2.SpotifyResponse(
                    response=success_msg,
                    success=True
            )

        except spotipy.SpotifyException as e:
            error_msg = f"Spotify API error: {e.reason if hasattr(e, 'reason') else str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )
        except Exception as e:
            error_msg = f"Error resuming playback spotify: {str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )

    def Next(self, request, context):
        if not self._ensure_authenticated():
            return spotify_pb2.SpotifyResponse(
                response="❌ Spotify not authenticated. Please check logs.",
                success=False
            )

        try:
            logger.info(f"Skipping song...")
            active_device = self._get_active_device()
            if not active_device:
                return spotify_pb2.SpotifyResponse(
                    response="No active Spotify devices found. Please open Spotify on a device first.",
                    success=False
                )

            device_id = active_device['id']
            device_name = active_device['name']

            self.sp.next_track(device_id=device_id)

            success_msg = f"Successfully skipped spotify on device on {device_name}"
            logger.info(success_msg)

            return spotify_pb2.SpotifyResponse(
                    response=success_msg,
                    success=True
            )

        except spotipy.SpotifyException as e:
            error_msg = f"Spotify API error: {e.reason if hasattr(e, 'reason') else str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )
        except Exception as e:
            error_msg = f"Error skipping song on spotify: {str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )

    def ToggleShuffle(self, request, context):
        if not self._ensure_authenticated():
            return spotify_pb2.SpotifyResponse(
                response="❌ Spotify not authenticated. Please check logs.",
                success=False
            )

        try:
            logger.info(f"Skipping song...")
            active_device = self._get_active_device()
            if not active_device:
                return spotify_pb2.SpotifyResponse(
                    response="No active Spotify devices found. Please open Spotify on a device first.",
                    success=False
                )

            device_id = active_device['id']
            device_name = active_device['name']

            self.sp.shuffle(True, device_id=device_id)

            success_msg = f"Successfully toggled shuffle spotify on device on {device_name}"
            logger.info(success_msg)

            return spotify_pb2.SpotifyResponse(
                    response=success_msg,
                    success=True
            )

        except spotipy.SpotifyException as e:
            error_msg = f"Spotify API error: {e.reason if hasattr(e, 'reason') else str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )
        except Exception as e:
            error_msg = f"Error modifying shuffle on spotify: {str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )

    def SetVolume(self, request, context):
        if not self._ensure_authenticated():
            return spotify_pb2.SpotifyResponse(
                response="❌ Spotify not authenticated. Please check logs.",
                success=False
            )

        try:
            logger.info(f"Setting volume song...")

            volume = request.level

            active_device = self._get_active_device()
            if not active_device:
                return spotify_pb2.SpotifyResponse(
                    response="No active Spotify devices found. Please open Spotify on a device first.",
                    success=False
                )

            device_id = active_device['id']
            device_name = active_device['name']

            self.sp.volume(volume, device_id=device_id)

            success_msg = f"Successfully set volume to {volume} on device on {device_name}"
            logger.info(success_msg)

            return spotify_pb2.SpotifyResponse(
                    response=success_msg,
                    success=True
            )

        except spotipy.SpotifyException as e:
            error_msg = f"Spotify API error: {e.reason if hasattr(e, 'reason') else str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )
        except Exception as e:
            error_msg = f"Error setting volume on spotify: {str(e)}"
            logger.error(error_msg)
            return spotify_pb2.SpotifyResponse(
                response=f"❌ {error_msg}",
                success=False
            )

    def HealthCheck(self, request, context):
        try:
            return spotify_pb2.HealthResponse(
                status="healthy",
                message="Spotify service is running normally"
            )
        except Exception as e:
            return spotify_pb2.HealthResponse(
                status="unhealthy",
                message=f"Error: {str(e)}"
            )


def serve():

    port = os.getenv('GRPC_PORT', '50051')

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))

    spotify_service = SpotifyService()
    spotify_pb2_grpc.add_SpotifyServiceServicer_to_server(spotify_service, server)

    listen_addr = f'[::]:{port}'
    server.add_insecure_port(listen_addr)
    server.start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == '__main__':
    serve()