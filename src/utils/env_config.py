import os
import json


class Config(dict):
    """
    Configuration wrapper that loads from environment variables.
    Falls back to settings.json for local development.
    Behaves like a dict and exposes .data for compatibility with ReadSettings.
    """

    def __init__(self):
        super().__init__()

        if os.environ.get('BOT_TOKEN'):
            # Load from environment variables (Railway / production)
            self['bot_token'] = os.environ['BOT_TOKEN']
            self['discord_guild_id'] = int(os.environ['DISCORD_GUILD_ID'])
            self['admin_ids'] = json.loads(os.environ.get('ADMIN_IDS', '[]'))
            self['log_channel_id'] = int(os.environ['LOG_CHANNEL_ID'])
            self['store_channel_id'] = int(os.environ['STORE_CHANNEL_ID'])
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
