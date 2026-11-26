"""Direct YouTube Shorts and Instagram Reels upload & share integration for RealCut."""
import json
import os
import threading
import time
import uuid
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from reedit import read_record, latest_file

UPLOADS = {}  # upload_id -> {'status': 'running'|'done'|'error', 'stage': str, 'progress': float, 'url': str, 'error': str}

def get_social_config(data_dir: Path):
    cfg_file = data_dir / 'social_config.json'
    if cfg_file.exists():
        try:
            return json.loads(cfg_file.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'youtube': {}, 'instagram': {}}

def save_social_config(data_dir: Path, cfg: dict):
    cfg_file = data_dir / 'social_config.json'
    cfg_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')

def build_social_metadata(record: dict, file_id: str):
    settings = record.get('settings', {})
    title = str(settings.get('title') or 'RealCut Highlight').strip()
    hook = str(settings.get('hook') or '').strip()
    caption = str(settings.get('post_caption') or '').strip()

    yt_title = f"{title} #Shorts"
    if len(yt_title) > 95:
        yt_title = f"{title[:90]}... #Shorts"

    yt_desc_parts = []
    if hook:
        yt_desc_parts.append(f"🔥 {hook}")
    if caption:
        yt_desc_parts.append(caption)
    elif title and title != hook:
        yt_desc_parts.append(title)
    yt_desc_parts.append("\n#Shorts #ShortsFeed #Viral #Trending #RealCut")
    yt_desc = "\n\n".join(yt_desc_parts)

    yt_tags = ["Shorts", "ShortsFeed", "Viral", "Trending", "RealCut", "Clip", "Highlights"]

    ig_caption_parts = []
    if hook:
        ig_caption_parts.append(f"✨ {hook}")
    if caption:
        ig_caption_parts.append(caption)
    elif title and title != hook:
        ig_caption_parts.append(title)
    ig_caption_parts.append(".\n.\n#reels #reelsinstagram #viral #trending #explorepage #fyp #reelsvideo #viralvideos #shorts #realcut")
    ig_caption = "\n\n".join(ig_caption_parts)

    return {
        'file': file_id,
        'title': title,
        'hook': hook,
        'post_caption': caption,
        'youtube': {
            'title': yt_title,
            'description': yt_desc,
            'tags': yt_tags,
            'privacy': 'public',
            'web_url': 'https://studio.youtube.com/channel/uploader'
        },
        'instagram': {
            'caption': ig_caption,
            'web_url': 'https://www.instagram.com/create/details/'
        }
    }

def attach(app, data_dir: Path):
    data_dir = Path(data_dir)

    @app.get('/social/config')
    def get_config():
        cfg = get_social_config(data_dir)
        yt_token = data_dir / 'youtube_token.json'
        yt_secret = data_dir / 'youtube_client_secret.json'
        ig_session = data_dir / 'instagram_session.json'
        yt_cfg = cfg.get('youtube', {})
        return {
            'youtube': {
                'connected': yt_token.exists(),
                'has_secret': yt_secret.exists(),
                'client_id': yt_cfg.get('client_id', ''),
                'channel': yt_cfg.get('channel_title', '')
            },
            'instagram': {
                'connected': ig_session.exists() or bool(cfg.get('instagram', {}).get('username')),
                'username': cfg.get('instagram', {}).get('username', '')
            }
        }

    @app.get('/social/clip-info/{file_id}')
    def get_clip_info(file_id: str):
        actual_file = latest_file(data_dir, file_id)
        mp4_path = data_dir / f"{actual_file}.mp4"
        if not mp4_path.exists():
            raise HTTPException(404, f"Clip video not found for {file_id}")
        record = read_record(data_dir, actual_file)
        meta = build_social_metadata(record, actual_file)
        meta['video_url'] = f"/media/{actual_file}"
        return meta

    @app.post('/social/youtube/save-secret')
    def save_youtube_secret(body: dict):
        client_id = body.get('client_id', '').strip()
        client_secret = body.get('client_secret', '').strip()
        secret_content = body.get('client_secret_json', '').strip()

        parsed = None
        if client_id and client_secret:
            parsed = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "redirect_uris": [
                        "http://127.0.0.1:8770/social/youtube/oauth2callback",
                        "http://localhost:8770/social/youtube/oauth2callback",
                        "http://localhost",
                        "http://127.0.0.1"
                    ]
                }
            }
        elif secret_content:
            try:
                parsed = json.loads(secret_content)
                root_obj = parsed.get('installed') or parsed.get('web') or parsed
                client_id = root_obj.get('client_id', client_id)
            except Exception as e:
                lines = secret_content.splitlines()
                extracted_id, extracted_secret = '', ''
                for line in lines:
                    if ':' in line:
                        k, v = line.split(':', 1)
                        k, v = k.strip().lower(), v.strip().strip('",\'')
                        if 'client_id' in k or k == 'id': extracted_id = v
                        if 'client_secret' in k or k == 'secret': extracted_secret = v
                if extracted_id and extracted_secret:
                    client_id, client_secret = extracted_id, extracted_secret
                    parsed = {
                        "installed": {
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                            "redirect_uris": ["http://127.0.0.1:8770/social/youtube/oauth2callback", "http://localhost:8770/social/youtube/oauth2callback"]
                        }
                    }
                else:
                    raise HTTPException(400, f"Could not parse credentials: {str(e)}. Enter Client ID and Client Secret in the boxes.")

        if not parsed:
            raise HTTPException(400, "Please enter Google Client ID and Client Secret.")

        for key in ('installed', 'web'):
            if key in parsed:
                uris = parsed[key].setdefault('redirect_uris', [])
                for uri in ("http://127.0.0.1:8770/social/youtube/oauth2callback", "http://localhost:8770/social/youtube/oauth2callback"):
                    if uri not in uris:
                        uris.append(uri)
                if not client_id:
                    client_id = parsed[key].get('client_id', '')

        secret_file = data_dir / 'youtube_client_secret.json'
        secret_file.write_text(json.dumps(parsed, indent=2), encoding='utf-8')

        cfg = get_social_config(data_dir)
        cfg.setdefault('youtube', {})['client_id'] = client_id
        cfg['youtube']['has_secret'] = True
        save_social_config(data_dir, cfg)

        return {'status': 'saved', 'client_id': client_id, 'message': 'Google Client ID & Secret saved! Now click "Connect Google Account".'}

    @app.get('/social/youtube/auth-url')
    def get_youtube_auth_url(request: Request, redirect_uri: str = None):
        secret_file = data_dir / 'youtube_client_secret.json'
        if not secret_file.exists():
            raise HTTPException(400, 'Google Client ID & Secret are not saved yet. Please enter and save them first.')
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            scopes = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']
            host = request.headers.get('host', '127.0.0.1:8770')
            chosen_uri = redirect_uri or f"http://{host}/social/youtube/oauth2callback"

            try:
                secret_data = json.loads(secret_file.read_text(encoding='utf-8'))
                for k in ('installed', 'web'):
                    if k in secret_data:
                        uris = secret_data[k].setdefault('redirect_uris', [])
                        if chosen_uri not in uris:
                            uris.append(chosen_uri)
                secret_file.write_text(json.dumps(secret_data, indent=2), encoding='utf-8')
            except Exception:
                pass

            flow = InstalledAppFlow.from_client_secrets_file(
                str(secret_file),
                scopes=scopes,
                redirect_uri=chosen_uri
            )
            auth_url, state = flow.authorization_url(prompt='consent', access_type='offline')

            # Preserve PKCE code_verifier and redirect_uri so token exchange succeeds
            try:
                p_file = data_dir / 'youtube_oauth_pending.json'
                current_sessions = {}
                if p_file.exists():
                    try: current_sessions = json.loads(p_file.read_text(encoding='utf-8'))
                    except Exception: pass
                # Keep up to last 10 pending auth states
                current_sessions[state] = {
                    'code_verifier': getattr(flow, 'code_verifier', None),
                    'redirect_uri': chosen_uri,
                    'time': time.time()
                }
                if len(current_sessions) > 10:
                    current_sessions = dict(list(current_sessions.items())[-10:])
                p_file.write_text(json.dumps(current_sessions, indent=2), encoding='utf-8')
            except Exception:
                pass

            return {'auth_url': auth_url, 'redirect_uri': chosen_uri, 'state': state}
        except Exception as e:
            raise HTTPException(500, f"Failed to generate auth URL: {str(e)}")

    @app.get('/social/youtube/oauth2callback')
    def oauth2callback(request: Request, code: str = None, state: str = None, error: str = None):
        if error:
            return HTMLResponse(f"<html><body style='background:#100c17;color:#ff4b72;font-family:sans-serif;text-align:center;padding:50px'><h3>Google Authorization Error: {error}</h3><button onclick='window.close()'>Close</button></body></html>")
        if not code:
            return HTMLResponse("<html><body style='background:#100c17;color:#ff4b72;font-family:sans-serif;text-align:center;padding:50px'><h3>No authorization code received.</h3></body></html>")

        secret_file = data_dir / 'youtube_client_secret.json'
        if not secret_file.exists():
            return HTMLResponse("<html><body style='background:#100c17;color:#ff4b72;font-family:sans-serif;text-align:center;padding:50px'><h3>youtube_client_secret.json missing on server.</h3></body></html>")

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            scopes = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']
            
            # Lookup pending session info by state to restore code_verifier and redirect_uri
            pending = None
            try:
                p_file = data_dir / 'youtube_oauth_pending.json'
                if p_file.exists():
                    current_sessions = json.loads(p_file.read_text(encoding='utf-8'))
                    pending = current_sessions.get(state)
            except Exception:
                pass

            req_uri = str(request.url).split('?')[0]
            redirect_uri = (pending and pending.get('redirect_uri')) or req_uri or 'http://127.0.0.1:8770/social/youtube/oauth2callback'
            code_verifier = pending.get('code_verifier') if pending else None

            flow = InstalledAppFlow.from_client_secrets_file(
                str(secret_file),
                scopes=scopes,
                redirect_uri=redirect_uri
            )
            if code_verifier:
                flow.code_verifier = code_verifier

            flow.fetch_token(code=code)
            creds = flow.credentials
            token_file = data_dir / 'youtube_token.json'
            token_file.write_text(creds.to_json(), encoding='utf-8')

            # Clean up pending state
            try:
                if state and p_file.exists():
                    current_sessions = json.loads(p_file.read_text(encoding='utf-8'))
                    current_sessions.pop(state, None)
                    p_file.write_text(json.dumps(current_sessions, indent=2), encoding='utf-8')
            except Exception:
                pass

            yt = build('youtube', 'v3', credentials=creds)
            ch = yt.channels().list(mine=True, part='snippet').execute()
            ch_title = ''
            if ch.get('items'):
                ch_title = ch['items'][0]['snippet']['title']
            cfg = get_social_config(data_dir)
            cfg.setdefault('youtube', {})['channel_title'] = ch_title
            save_social_config(data_dir, cfg)

            return HTMLResponse(f"""
            <html><head><title>YouTube Connected</title></head>
            <body style='background:#0b0912;color:#fbf6ff;font-family:sans-serif;text-align:center;padding:60px 20px;line-height:1.6'>
                <div style='max-width:480px;margin:auto;background:#171320;border:1px solid #30263e;border-radius:16px;padding:30px;box-shadow:0 10px 40px rgba(0,0,0,0.5)'>
                    <div style='font-size:40px;margin-bottom:10px'>🎉</div>
                    <h2 style='color:#58e8f7;margin:0 0 10px'>Connected to YouTube!</h2>
                    <p style='color:#d4fb58;font-weight:bold;font-size:16px;margin:0 0 16px'>Channel: {ch_title or 'YouTube Channel'}</p>
                    <p style='color:#a99db7;font-size:13px;margin:0 0 24px'>Your YouTube account is now connected to RealCut. You can close this tab and start uploading clips directly.</p>
                    <button onclick='if(window.opener){{window.opener.postMessage("yt_connected","*");}}window.close();' style='background:#ff4ba5;color:#1c0714;border:0;border-radius:8px;padding:12px 24px;font-weight:bold;cursor:pointer;font-size:14px'>Return to RealCut</button>
                </div>
                <script>
                    if(window.opener){{
                        try {{ window.opener.postMessage("yt_connected","*"); }} catch(e){{}}
                        setTimeout(() => window.close(), 1500);
                    }}
                </script>
            </body></html>
            """)
        except Exception as e:
            return HTMLResponse(f"<html><body style='background:#100c17;color:#ff4b72;font-family:sans-serif;text-align:center;padding:50px'><h3>OAuth Verification Failed: {str(e)}</h3><button onclick='window.close()'>Close</button></body></html>")

    @app.post('/social/youtube/auth-code')
    def verify_youtube_code(body: dict):
        code = body.get('code', '').strip()
        if not code:
            raise HTTPException(400, 'Authorization code is required')
        secret_file = data_dir / 'youtube_client_secret.json'
        if not secret_file.exists():
            raise HTTPException(400, 'client_secret.json missing')
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            scopes = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']
            flow = InstalledAppFlow.from_client_secrets_file(
                str(secret_file),
                scopes=scopes,
                redirect_uri='http://127.0.0.1:8770/social/youtube/oauth2callback'
            )
            flow.fetch_token(code=code)
            creds = flow.credentials
            token_file = data_dir / 'youtube_token.json'
            token_file.write_text(creds.to_json(), encoding='utf-8')

            yt = build('youtube', 'v3', credentials=creds)
            ch = yt.channels().list(mine=True, part='snippet').execute()
            ch_title = ch['items'][0]['snippet']['title'] if ch.get('items') else ''
            cfg = get_social_config(data_dir)
            cfg.setdefault('youtube', {})['channel_title'] = ch_title
            save_social_config(data_dir, cfg)

            return {'status': 'connected', 'channel_title': ch_title}
        except Exception as e:
            raise HTTPException(400, f"OAuth verification failed: {str(e)}")

    @app.post('/social/youtube/upload')
    def upload_to_youtube(body: dict):
        file_id = body.get('file')
        if not file_id:
            raise HTTPException(400, 'Clip file is required')
        actual_file = latest_file(data_dir, file_id)
        mp4_path = data_dir / f"{actual_file}.mp4"
        if not mp4_path.exists():
            raise HTTPException(404, 'Video file not found')

        title = (body.get('title') or 'Highlight #Shorts')[:100]
        description = body.get('description') or ''
        tags = body.get('tags') or ["Shorts", "Viral", "RealCut"]
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',') if t.strip()]
        privacy = body.get('privacy') or 'public'

        upload_id = uuid.uuid4().hex
        UPLOADS[upload_id] = {
            'status': 'running',
            'stage': 'Preparing YouTube upload…',
            'progress': 0.05,
            'platform': 'youtube'
        }

        def worker():
            token_file = data_dir / 'youtube_token.json'
            if not token_file.exists():
                UPLOADS[upload_id] = {
                    'status': 'error',
                    'error': 'YouTube account is not connected. Save credentials and click Connect Google Account, or use Open in YouTube Studio.'
                }
                return
            try:
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                from googleapiclient.discovery import build
                from googleapiclient.http import MediaFileUpload

                creds = Credentials.from_authorized_user_file(str(token_file))
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    token_file.write_text(creds.to_json(), encoding='utf-8')

                youtube = build('youtube', 'v3', credentials=creds)
                video_body = {
                    'snippet': {
                        'title': title,
                        'description': description,
                        'tags': tags,
                        'categoryId': '22'
                    },
                    'status': {
                        'privacyStatus': privacy,
                        'selfDeclaredMadeForKids': False
                    }
                }

                UPLOADS[upload_id]['stage'] = 'Uploading video chunks to YouTube…'
                UPLOADS[upload_id]['progress'] = 0.2

                media = MediaFileUpload(str(mp4_path), mimetype='video/mp4', resumable=True, chunksize=1024*1024*2)
                request = youtube.videos().insert(part='snippet,status', body=video_body, media_body=media)

                response = None
                while response is None:
                    status_chunk, response = request.next_chunk()
                    if status_chunk:
                        prog = 0.2 + (status_chunk.progress() * 0.75)
                        UPLOADS[upload_id]['progress'] = min(0.95, prog)
                        UPLOADS[upload_id]['stage'] = f"Uploading: {int(status_chunk.progress()*100)}%"

                video_id = response['id']
                short_url = f"https://youtube.com/shorts/{video_id}"
                UPLOADS[upload_id] = {
                    'status': 'done',
                    'stage': 'Published to YouTube Shorts!',
                    'progress': 1.0,
                    'url': short_url,
                    'video_id': video_id
                }
            except Exception as e:
                UPLOADS[upload_id] = {
                    'status': 'error',
                    'error': str(e)
                }

        threading.Thread(target=worker, daemon=True).start()
        return {'upload_id': upload_id}

    @app.post('/social/instagram/upload')
    def upload_to_instagram(body: dict):
        file_id = body.get('file')
        if not file_id:
            raise HTTPException(400, 'Clip file is required')
        actual_file = latest_file(data_dir, file_id)
        mp4_path = data_dir / f"{actual_file}.mp4"
        if not mp4_path.exists():
            raise HTTPException(404, 'Video file not found')

        caption = body.get('caption') or ''
        username = body.get('username') or ''
        password = body.get('password') or ''
        save_session = body.get('save_session', True)

        cfg = get_social_config(data_dir)
        saved_ig = cfg.get('instagram', {})
        if not username and saved_ig.get('username'):
            username = saved_ig['username']

        upload_id = uuid.uuid4().hex
        UPLOADS[upload_id] = {
            'status': 'running',
            'stage': 'Logging into Instagram…',
            'progress': 0.1,
            'platform': 'instagram'
        }

        def worker():
            try:
                from instagrapi import Client
                cl = Client()
                session_path = data_dir / 'instagram_session.json'

                logged_in = False
                if session_path.exists():
                    try:
                        cl.load_settings(str(session_path))
                        cl.get_timeline_feed()
                        logged_in = True
                    except Exception:
                        logged_in = False

                if not logged_in:
                    if not username or not password:
                        UPLOADS[upload_id] = {
                            'status': 'error',
                            'error': 'Instagram username & password are required for initial login.'
                        }
                        return
                    UPLOADS[upload_id]['stage'] = f"Logging in as @{username}…"
                    cl.login(username, password)
                    if save_session:
                        cl.dump_settings(str(session_path))
                        cfg['instagram'] = {'username': username}
                        save_social_config(data_dir, cfg)

                UPLOADS[upload_id]['stage'] = 'Uploading Reel to Instagram…'
                UPLOADS[upload_id]['progress'] = 0.45

                media = cl.clip_upload(path=str(mp4_path), caption=caption)
                post_code = getattr(media, 'code', None) or getattr(media, 'pk', '')
                reel_url = f"https://www.instagram.com/reel/{post_code}/" if post_code else 'https://www.instagram.com/'

                UPLOADS[upload_id] = {
                    'status': 'done',
                    'stage': 'Reel published to Instagram!',
                    'progress': 1.0,
                    'url': reel_url
                }
            except Exception as e:
                err_msg = str(e)
                if 'Challenge' in err_msg or 'checkpoint' in err_msg:
                    err_msg = 'Instagram asked for verification. Please verify in your Instagram app or use Open in Instagram Web.'
                UPLOADS[upload_id] = {
                    'status': 'error',
                    'error': err_msg
                }

        threading.Thread(target=worker, daemon=True).start()
        return {'upload_id': upload_id}

    @app.get('/social/upload-status/{upload_id}')
    def get_upload_status(upload_id: str):
        if upload_id not in UPLOADS:
            raise HTTPException(404, 'Upload job not found')
        return UPLOADS[upload_id]
