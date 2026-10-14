"""Save a Gemini key through a hidden local terminal prompt; never make an API call."""

import argparse
import getpass
import re
import sys
from pathlib import Path

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--status', action='store_true', help='Show configuration presence without showing secrets.'
    )
    parser.add_argument('--model', default='gemini-3.8-flash')
    args = parser.parse_args()
    path = ROOT / '.env.local'
    if args.status:
        settings = dotenv_values(path)
        print('Gemini key: ' + ('configured' if settings.get('GEMINI_API_KEY') else 'missing'))
        print('Gemini model: ' + ('configured' if settings.get('GEMINI_MODEL') else 'missing'))
        return 0
    if not re.fullmatch(r'[A-Za-z0-9._:-]{1,100}', args.model):
        print('Invalid model ID.')
        return 2
    if not sys.stdin.isatty():
        print(
            'Open a local terminal and run scripts/configure-gemini.ps1. The key is never accepted as a command argument.'
        )
        return 2
    key = getpass.getpass('Gemini API key (hidden; saved to private .env.local): ').strip()
    if not key or len(key) > 512 or any(character.isspace() for character in key):
        print('No valid key entered. Configuration unchanged.')
        return 2
    set_key(path, 'GEMINI_API_KEY', key)
    set_key(path, 'GEMINI_MODEL', args.model)
    set_key(path, 'LLM_PROVIDER', 'gemini')
    print('Gemini configuration saved. Restart the app to use it. No provider request was made.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.')
        raise SystemExit(2)
    except OSError:
        print('Could not save local configuration.')
        raise SystemExit(2)
