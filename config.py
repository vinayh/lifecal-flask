from pathlib import Path
from sys import exit

import os

SECRETS_TO_PATHS = {
    'FLASK_SECRET_KEY': Path('.secrets/flask_secret_key'),
    'GITHUB_CLIENT_ID': Path('.secrets/github_client_id'),
    'GITHUB_CLIENT_SECRET': Path('.secrets/github_client_secret'),
    'GOOGLE_CLIENT_ID': Path('.secrets/google_client_id'),
    'GOOGLE_CLIENT_SECRET': Path('.secrets/google_client_secret'),
    'DATABASE_URL': Path('.secrets/database_url')
}


def get_secret_file(path) -> str:
    try:
        with path.open("r") as f:
            return f.read()
    except:
        exit(f'Error getting secret {path}')


def get_secret(name: str):
    if os.getenv('LIFECAL_ENV') == 'RENDER':
        return get_secret_file(SECRETS_TO_PATHS[name].relative_to('.secrets'))
    elif os.getenv('LIFECAL_ENV') == 'FLY':
        if name in os.environ:
            return os.getenv(name)
        else:
            raise Exception
    else:
        return get_secret_file(SECRETS_TO_PATHS[name])


def get_oauth2_providers():
    return {
        'github': {
            'client_id': get_secret('GITHUB_CLIENT_ID'),
            'client_secret': get_secret('GITHUB_CLIENT_SECRET'),
            'authorize_url': 'https://github.com/login/oauth/authorize',
            'token_url': 'https://github.com/login/oauth/access_token',
            'userinfo': {
                'url': 'https://api.github.com/user',
                'oauth_id': lambda r: 'gh_' + str(r.json()['id']),
            },
            'scopes': ['read:user'],
        },
        'google': {
            'client_id': get_secret('GOOGLE_CLIENT_ID'),
            'client_secret': get_secret('GOOGLE_CLIENT_SECRET'),
            'authorize_url': 'https://accounts.google.com/o/oauth2/auth',
            'token_url': 'https://accounts.google.com/o/oauth2/token',
            'userinfo': {
                'url': 'https://www.googleapis.com/oauth2/v3/userinfo',
                'oauth_id': lambda r: 'go_' + str(r.json()['sub']),
            },
            'scopes': ['https://www.googleapis.com/auth/userinfo.profile'],
        },
    }
