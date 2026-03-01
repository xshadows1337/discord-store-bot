import os
import json
from pathlib import Path


def _load_dotenv():
    """Load .env file from the src directory (or current working dir) if present."""
    try:
        from dotenv import load_dotenv
        # Try src/.env, then ./.env, then ../.env
        for candidate in [
            Path(__file__).parent.parent / '.env',
            Path.cwd() / '.env',
            Path.cwd().parent / '.env',
        ]:
            if candidate.exists():
                load_dotenv(candidate, override=False)
                break
    except ImportError:
        pass  # dotenv not installed — fall back to env vars or settings.json


class Config(dict):
    """
    Configuration wrapper. Load priority:
      1. .env file (VPS / WinterNode deployment)
      2. Environment variables (Railway / Docker / shell exports)
      3. settings.json (local development fallback)
    """

    def __init__(self):
        super().__init__()
        _load_dotenv()

        if os.environ.get('BOT_TOKEN'):
            # Load from environment variables
            self['bot_token'] = os.environ['BOT_TOKEN']
            self['discord_guild_id'] = int(os.environ['DISCORD_GUILD_ID'])
            self['admin_ids'] = json.loads(os.environ.get('ADMIN_IDS', '[]'))
            self['log_channel_id'] = int(os.environ['LOG_CHANNEL_ID'])
            self['store_channel_id'] = int(os.environ['STORE_CHANNEL_ID'])
            self['bot_api_secret'] = os.environ.get('BOT_API_SECRET', '')
            self['bot_api_url'] = os.environ.get('BOT_API_URL', '')
        else:
            # Fallback to settings.json for local development
            from readsettings import ReadSettings
            file_config = ReadSettings('settings.json')
            for key in file_config.data:
                self[key] = file_config.data[key]

        self.data = dict(self)

    def save(self):
        """No-op for env-var based config."""
        pass


def get_env(key, default=None):
    """Helper to get an environment variable with optional default."""
    return os.environ.get(key, default)
