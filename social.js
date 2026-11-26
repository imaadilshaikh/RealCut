// RealCut Social Share & Upload (YouTube Shorts, Instagram Reels, System Share)
(function () {
  let currentFile = null;
  let clipData = null;
  let activeTab = 'yt';
  let pollTimer = null;

  function $(id) { return document.getElementById(id); }

  async function req(url, body) {
    const res = await fetch(url, {
      method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined
    });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) throw Error(j.detail || j.error || 'Request failed');
    return j;
  }

  function setStatus(text, isError = false, url = null) {
    const box = $('sm-status');
    const msg = $('sm-status-msg');
    box.hidden = false;
    msg.textContent = text;
    msg.style.color = isError ? '#ff4b72' : '#58e8f7';
    if (url) {
      const link = document.createElement('a');
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = ' ↗ Open Published Link';
      link.style.display = 'block';
      link.style.color = '#d4fb58';
      link.style.marginTop = '6px';
      link.style.fontWeight = 'bold';
      msg.append(link);
    }
  }

  function setProgress(pct) {
    const bar = $('sm-progress-bar');
    if (bar) bar.style.width = Math.max(5, Math.min(100, Math.round(pct * 100))) + '%';
  }

  function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll('.social-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    $('tab-yt').hidden = tab !== 'yt';
    $('tab-ig').hidden = tab !== 'ig';
    $('tab-share').hidden = tab !== 'share';
    $('sm-status').hidden = true;
  }

  async function openSocialModal(fileId, fallbackTitle = '', initialTab = 'yt') {
    currentFile = fileId;
    const dialog = $('social-dialog');
    if (!dialog) return;

    if (initialTab) switchTab(initialTab);
    $('sm-clip-title').textContent = 'Loading clip info…';
    $('sm-status').hidden = true;
    setProgress(0);
    dialog.showModal();

    try {
      const info = await req('/social/clip-info/' + fileId);
      clipData = info;
      $('sm-clip-title').textContent = info.title || fallbackTitle || fileId;

      // Fill YouTube
      $('yt-title').value = info.youtube.title || '';
      $('yt-desc').value = info.youtube.description || '';
      $('yt-tags').value = (info.youtube.tags || []).join(', ');
      $('yt-privacy').value = info.youtube.privacy || 'public';

      // Fill Instagram
      $('ig-caption').value = info.instagram.caption || '';

      // Check configs
      const cfg = await req('/social/config').catch(() => ({}));
      if (cfg.youtube?.connected) {
        $('yt-conn-badge').textContent = '● Connected: ' + (cfg.youtube.channel || 'Ready');
        $('yt-conn-badge').className = 'pill sm-connected';
      } else if (cfg.youtube?.has_secret) {
        $('yt-conn-badge').textContent = '○ Credentials saved (Connect Google Account needed)';
        $('yt-conn-badge').className = 'pill';
      } else {
        $('yt-conn-badge').textContent = '○ Not authenticated (OAuth needed for Direct API)';
        $('yt-conn-badge').className = 'pill';
      }
      if (cfg.youtube?.client_id && $('yt-client-id')) {
        $('yt-client-id').value = cfg.youtube.client_id;
      }

      if (cfg.instagram?.connected) {
        $('ig-conn-badge').textContent = '● Active session: @' + (cfg.instagram.username || 'Saved');
        $('ig-conn-badge').className = 'pill sm-connected';
        if (cfg.instagram.username) $('ig-user').value = cfg.instagram.username;
      } else {
        $('ig-conn-badge').textContent = '○ No saved session';
        $('ig-conn-badge').className = 'pill';
      }
    } catch (e) {
      $('sm-clip-title').textContent = 'Clip: ' + (fallbackTitle || fileId);
      setStatus('Could not load clip metadata: ' + e.message, true);
    }
  }
  window.openSocialModal = openSocialModal;

  async function copyText(text, btn, successLabel = '✓ Copied!') {
    try {
      await navigator.clipboard.writeText(text);
      const prev = btn.textContent;
      btn.textContent = successLabel;
      btn.style.borderColor = '#d4fb58';
      setTimeout(() => { btn.textContent = prev; btn.style.borderColor = ''; }, 2000);
      return true;
    } catch (e) {
      alert('Could not copy automatically. Please copy manually.');
      return false;
    }
  }

  function trackUpload(uploadId) {
    if (pollTimer) clearInterval(pollTimer);
    setProgress(0.15);
    pollTimer = setInterval(async () => {
      try {
        const s = await req('/social/upload-status/' + uploadId);
        setProgress(s.progress || 0.2);
        if (s.status === 'running') {
          setStatus(s.stage || 'Uploading in progress…');
        } else if (s.status === 'done') {
          clearInterval(pollTimer);
          setProgress(1.0);
          setStatus(s.stage || 'Upload complete!', false, s.url);
        } else if (s.status === 'error') {
          clearInterval(pollTimer);
          setStatus('Upload failed: ' + (s.error || 'Unknown error'), true);
        }
      } catch (e) {
        clearInterval(pollTimer);
        setStatus('Status error: ' + e.message, true);
      }
    }, 1500);
  }

  function getActiveClipId() {
    const dl = $('download');
    if (dl && dl.href && !dl.hidden && dl.href.includes('/media/')) {
      return dl.href.split('/media/')[1];
    }
    if (window.editingClip) return window.editingClip;
    const firstVid = document.querySelector('.clip-card video, .mk video');
    if (firstVid && firstVid.src && firstVid.src.includes('/media/')) {
      return firstVid.src.split('/media/')[1];
    }
    return null;
  }

  async function refreshSocialView() {
    const grid = $('social-grid');
    if (!grid) return;
    try {
      const clips = await req('/library');
      grid.replaceChildren();
      if (!clips.length) {
        const empty = document.createElement('div');
        empty.className = 'empty-library';
        empty.textContent = 'No exported clips yet. Make or export clips first to publish to YouTube or Instagram.';
        grid.append(empty);
        return;
      }
      for (const clip of clips) {
        const card = document.createElement('article');
        card.className = 'clip-card';
        const v = document.createElement('video');
        v.src = '/media/' + clip.id;
        v.controls = true;
        v.preload = 'metadata';
        const title = document.createElement('h3');
        title.textContent = clip.title;
        const meta = document.createElement('p');
        meta.textContent = (clip.meta?.duration || 0).toFixed(1) + 's · ' + (clip.settings?.layout || 'vertical');

        const socialRow = document.createElement('div');
        socialRow.className = 'card-social-row';
        const ytBtn = document.createElement('button');
        ytBtn.className = 'yt-card-btn';
        ytBtn.textContent = '▶ YouTube';
        ytBtn.onclick = () => openSocialModal(clip.id, clip.title, 'yt');
        const igBtn = document.createElement('button');
        igBtn.className = 'ig-card-btn';
        igBtn.textContent = '📸 Instagram';
        igBtn.onclick = () => openSocialModal(clip.id, clip.title, 'ig');
        socialRow.append(ytBtn, igBtn);

        const toolsRow = document.createElement('div');
        toolsRow.className = 'card-tools-row';
        const dl = document.createElement('a');
        dl.className = 'dl-btn';
        dl.style.flex = '1';
        dl.style.textAlign = 'center';
        dl.href = '/media/' + clip.id;
        dl.download = 'realcut-' + clip.id + '.mp4';
        dl.textContent = '↓ Download MP4';
        toolsRow.append(dl);

        const delBtn = document.createElement('button');
        delBtn.className = 'del-btn';
        delBtn.title = 'Delete this clip';
        delBtn.innerHTML = '🗑';
        delBtn.onclick = async () => {
          if (!confirm('Are you sure you want to delete "' + clip.title + '"?')) return;
          try {
            await req('/clips/' + clip.id + '/delete', {});
            await refreshSocialView();
            if (window.refreshLibrary) window.refreshLibrary();
          } catch (e) {
            alert('Delete failed: ' + e.message);
          }
        };
        toolsRow.append(delBtn);

        const editBtn = document.createElement('button');
        editBtn.className = 'edit-card-btn';
        editBtn.innerHTML = '✏ &nbsp;Edit clip';
        editBtn.onclick = () => window.openSavedClip?.(clip.id).catch(e => alert(e.message));

        card.append(v, title, meta, editBtn, socialRow, toolsRow);
        grid.append(card);
      }
    } catch (e) {
      console.error(e);
    }
  }
  window.refreshSocialView = refreshSocialView;

  function init() {
    if (!$('social-dialog')) return;

    $('sm-close').onclick = () => $('social-dialog').close();
    document.querySelectorAll('.social-tab').forEach(b => {
      b.onclick = () => switchTab(b.dataset.tab);
    });

    // YouTube: Copy & Open Studio
    $('yt-open-studio').onclick = async (e) => {
      const title = $('yt-title').value.trim();
      const desc = $('yt-desc').value.trim();
      const copyPayload = `Title: ${title}\n\nDescription:\n${desc}\n\nTags: ${$('yt-tags').value}`;
      await copyText(copyPayload, e.target, '✓ Copied Title & Description!');
      window.open('https://studio.youtube.com/channel/uploader', '_blank');
      setStatus('YouTube Studio opened in new tab. Title & description are copied to your clipboard — simply paste!');
    };

    // YouTube: Direct Upload
    $('yt-direct-upload').onclick = async () => {
      if (!currentFile) return;
      $('yt-direct-upload').disabled = true;
      setStatus('Starting YouTube upload…');
      try {
        const res = await req('/social/youtube/upload', {
          file: currentFile,
          title: $('yt-title').value.trim(),
          description: $('yt-desc').value.trim(),
          tags: $('yt-tags').value.split(',').map(s => s.trim()).filter(Boolean),
          privacy: $('yt-privacy').value
        });
        trackUpload(res.upload_id);
      } catch (e) {
        setStatus('YouTube Upload Error: ' + e.message, true);
      } finally {
        $('yt-direct-upload').disabled = false;
      }
    };

    // YouTube: File Secret Upload
    const fileSecret = $('yt-file-secret');
    if (fileSecret) {
      fileSecret.onchange = (e) => {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (evt) => {
          try {
            const data = JSON.parse(evt.target.result);
            const clientObj = data.installed || data.web || data;
            if (clientObj.client_id && $('yt-client-id')) $('yt-client-id').value = clientObj.client_id;
            if (clientObj.client_secret && $('yt-client-secret')) $('yt-client-secret').value = clientObj.client_secret;
            alert('File parsed successfully! Click "Save Credentials".');
          } catch (err) {
            alert('Could not parse JSON file: ' + err.message);
          }
        };
        reader.readAsText(file);
      };
    }

    // YouTube: Save Credentials
    $('yt-save-secret-btn').onclick = async () => {
      const clientId = ($('yt-client-id')?.value || '').trim();
      const clientSecret = ($('yt-client-secret')?.value || '').trim();
      if (!clientId || !clientSecret) {
        return alert('Please enter both Google Client ID and Google Client Secret (or upload client_secret.json).');
      }
      try {
        const res = await req('/social/youtube/save-secret', {
          client_id: clientId,
          client_secret: clientSecret
        });
        alert(res.message || 'Credentials saved successfully! Now click "Connect Google Account".');
        $('yt-conn-badge').textContent = '○ Credentials saved (Click Connect Google Account)';
        $('yt-conn-badge').className = 'pill';
      } catch (e) {
        alert('Save Error: ' + e.message);
      }
    };

    // Copy redirect URIs
    if ($('copy-uri-1')) {
      $('copy-uri-1').onclick = (e) => copyText($('yt-uri-1').textContent.trim(), e.target, '✓ Copied!');
    }
    if ($('copy-uri-2')) {
      $('copy-uri-2').onclick = (e) => copyText($('yt-uri-2').textContent.trim(), e.target, '✓ Copied!');
    }

    // YouTube: Auth Connect
    $('yt-auth-btn').onclick = async () => {
      try {
        const redirectUri = window.location.origin + '/social/youtube/oauth2callback';
        const { auth_url } = await req('/social/youtube/auth-url?redirect_uri=' + encodeURIComponent(redirectUri));
        const authWin = window.open(auth_url, 'GoogleOAuthPopup', 'width=620,height=720,status=0,toolbar=0');
        if (!authWin) {
          window.open(auth_url, '_blank');
        }
      } catch (e) {
        alert('YouTube Auth Error: ' + e.message);
      }
    };

    // Listen for OAuth completion from callback window
    window.addEventListener('message', async (e) => {
      if (e.data === 'yt_connected') {
        try {
          const cfg = await req('/social/config');
          if (cfg.youtube?.connected) {
            $('yt-conn-badge').textContent = '● Connected: ' + (cfg.youtube.channel || 'Ready');
            $('yt-conn-badge').className = 'pill sm-connected';
            alert('🎉 YouTube channel successfully connected: ' + (cfg.youtube.channel || 'Ready'));
            if ($('yt-config-details')) $('yt-config-details').open = false;
          }
        } catch (err) {
          console.error(err);
        }
      }
    });

    // Instagram: Copy & Open Web
    $('ig-open-web').onclick = async (e) => {
      const caption = $('ig-caption').value.trim();
      await copyText(caption, e.target, '✓ Copied Caption & Hashtags!');
      window.open('https://www.instagram.com/create/details/', '_blank');
      setStatus('Instagram Web Create opened in new tab. Caption & hashtags are copied to your clipboard!');
    };

    // Instagram: Direct Upload
    $('ig-direct-upload').onclick = async () => {
      if (!currentFile) return;
      const username = $('ig-user').value.trim();
      const password = $('ig-pass').value.trim();
      $('ig-direct-upload').disabled = true;
      setStatus('Logging in & uploading Reel to Instagram…');
      try {
        const res = await req('/social/instagram/upload', {
          file: currentFile,
          caption: $('ig-caption').value.trim(),
          username: username,
          password: password,
          save_session: true
        });
        trackUpload(res.upload_id);
      } catch (e) {
        setStatus('Instagram Upload Error: ' + e.message, true);
      } finally {
        $('ig-direct-upload').disabled = false;
      }
    };

    // Native System Share
    $('share-native-btn').onclick = async () => {
      if (!currentFile) return;
      try {
        setStatus('Fetching video file for native sharing…');
        const response = await fetch('/media/' + currentFile);
        const blob = await response.blob();
        const file = new File([blob], `realcut-${currentFile}.mp4`, { type: 'video/mp4' });
        const shareData = {
          title: clipData?.title || 'RealCut Highlight',
          text: clipData?.hook || 'Check out this clip!',
          files: [file]
        };
        if (navigator.canShare && navigator.canShare({ files: [file] })) {
          await navigator.share(shareData);
          setStatus('Shared successfully!');
        } else {
          throw Error('Web Share API for files is not supported in this browser. Use Direct Upload or Copy & Open above.');
        }
      } catch (e) {
        if (e.name !== 'AbortError') {
          setStatus('Share Error: ' + e.message, true);
        }
      }
    };

    $('share-download-btn').onclick = () => {
      if (!currentFile) return;
      const a = document.createElement('a');
      a.href = '/media/' + currentFile;
      a.download = 'realcut-' + currentFile + '.mp4';
      a.click();
    };

    // Wire buttons in Step 06 Panel & Export bar
    function triggerAction(tab) {
      const clipId = getActiveClipId();
      if (clipId) {
        openSocialModal(clipId, $('clip-title')?.value || 'Highlight', tab);
      } else {
        alert('Pehle koi video import/export karein, ya sidebar me "My clips" par jakar kisi clip ka YouTube/Insta button dabayein.');
      }
    }

    if ($('panel-yt-btn')) $('panel-yt-btn').onclick = () => triggerAction('yt');
    if ($('panel-ig-btn')) $('panel-ig-btn').onclick = () => triggerAction('ig');
    if ($('panel-share-btn')) $('panel-share-btn').onclick = () => triggerAction('share');
    if ($('export-yt-btn')) $('export-yt-btn').onclick = () => triggerAction('yt');
    if ($('export-ig-btn')) $('export-ig-btn').onclick = () => triggerAction('ig');
    if ($('refresh-social-view')) $('refresh-social-view').onclick = () => refreshSocialView();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
