from pathlib import Path
import os
import yt_dlp

ROOT_DIR = Path(__file__).resolve().parent

def get_ytdl_opts(extra=None):
    opts = {
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 20,
        'retries': 3,
        'fragment_retries': 3,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
    }
    for candidate in [ROOT_DIR / 'cookies.txt', ROOT_DIR / 'data' / 'cookies.txt']:
        if candidate.is_file():
            opts['cookiefile'] = str(candidate)
            break

    if extra:
        if 'extractor_args' in extra:
            merged = dict(opts['extractor_args'])
            for k, v in extra['extractor_args'].items():
                if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                    merged[k] = {**merged[k], **v}
                else:
                    merged[k] = v
            extra_copy = dict(extra)
            extra_copy['extractor_args'] = merged
            opts.update(extra_copy)
        else:
            opts.update(extra)
    return opts

def create_ytdl(extra=None):
    return yt_dlp.YoutubeDL(get_ytdl_opts(extra))
