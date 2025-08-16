import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import os
from pathlib import Path
from dotenv import load_dotenv


def authenticate_spotify():
    """One-time authentication to get refresh token"""
    load_dotenv()

    # Ensure data directory exists
    data_dir = Path("./data")
    data_dir.mkdir(exist_ok=True)

    sp_oauth = SpotifyOAuth(
        client_id=os.getenv('SPOTIPY_CLIENT_ID'),
        client_secret=os.getenv('SPOTIPY_CLIENT_SECRET'),
        redirect_uri="http://localhost:8888/callback",
        scope="user-read-playback-state,user-modify-playback-state,user-read-currently-playing",
        cache_path="./data/.spotify_cache"
    )

    # Get authorization URL
    auth_url = sp_oauth.get_authorize_url()
    print(f"\n🎵 Spotify Authentication Required")
    print(f"1. Open this URL in your browser:")
    print(f"   {auth_url}")
    print(f"2. Login and authorize the app")
    print(f"3. Copy the full redirect URL from your browser")

    # Get the redirect response
    redirect_response = input("\nPaste the full redirect URL here: ").strip()

    try:
        # Extract code and get token
        code = sp_oauth.parse_response_code(redirect_response)
        token_info = sp_oauth.get_access_token(code)

        # Save token info
        token_file = data_dir / "spotify_tokens.json"
        with open(token_file, 'w') as f:
            json.dump(token_info, f, indent=2)

        print(f"✅ Authentication successful!")
        print(f"🔑 Tokens saved to {token_file}")

        # Test the connection
        sp = spotipy.Spotify(auth=token_info['access_token'])
        user = sp.current_user()
        print(f"👤 Authenticated as: {user['display_name']}")

        return True

    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return False


if __name__ == "__main__":
    authenticate_spotify()