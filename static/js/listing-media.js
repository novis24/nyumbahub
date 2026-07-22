(function () {
  function csrfToken() {
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  function formatSize(bytes) {
    if (!bytes) return '0 MB';
    if (bytes < 1024 * 1024) return Math.ceil(bytes / 1024) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  }

  function completeUrl(root, id) {
    return root.dataset.completeUrlTemplate.replace('00000000-0000-0000-0000-000000000000', id);
  }

  function normalizedVideo(file, policy) {
    let type = file.type || '';
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    if (!type && ext === 'mp4') type = 'video/mp4';
    if (!type && ext === 'webm') type = 'video/webm';
    if (type === 'video/quicktime' && policy.allowed_mime_types.indexOf('video/mp4') !== -1) {
      type = 'video/mp4';
    }
    return {ext: ext === 'mov' ? 'mp4' : ext, type: type};
  }

  document.querySelectorAll('[data-listing-media]').forEach(function (root) {
    const policy = JSON.parse(document.getElementById(root.dataset.policyId).textContent);
    const text = root.querySelector('[data-video-policy-text]');
    const list = root.querySelector('[data-video-list]');
    const inputs = root.querySelectorAll('[data-video-input]');
    const tiles = root.querySelectorAll('[data-video-tile], [data-record-tile]');
    const allowedLabel = policy.allowed_extensions.map(function (ext) { return ext.toUpperCase(); }).join(', ');
    text.textContent = policy.allowed
      ? 'Videos: ' + allowedLabel + ' up to ' + policy.max_video_size_mb + ' MB. ' + policy.max_videos_per_listing + ' per listing.'
      : policy.reason;
    if (!policy.allowed) {
      inputs.forEach(function (input) { input.disabled = true; });
      tiles.forEach(function (tile) { tile.dataset.disabled = 'true'; });
      return;
    }
    if (!policy.direct_recording_allowed) {
      root.querySelectorAll('[data-record-input]').forEach(function (input) { input.removeAttribute('capture'); });
    }

    inputs.forEach(function (input) {
      input.addEventListener('change', function () {
        Array.from(input.files || []).forEach(function (file) {
          uploadVideo(root, list, policy, file);
        });
        input.value = '';
      });
    });
  });

  function uploadVideo(root, list, policy, file) {
    const normalized = normalizedVideo(file, policy);
    const row = document.createElement('div');
    row.className = 'rounded-xl border border-n-200 bg-white p-3';
    row.innerHTML = '<div class="flex gap-3"><video class="h-16 w-24 rounded-lg bg-n-100 object-cover" muted preload="metadata"></video><div class="min-w-0 flex-1"><p class="truncate text-sm font-semibold text-n-800"></p><p class="text-xs text-n-500"></p><div class="mt-2 h-1.5 overflow-hidden rounded-full bg-n-100"><div class="h-full w-0 bg-p-600" data-progress></div></div></div><button type="button" class="h-8 w-8 rounded-full bg-n-100 text-n-600">×</button></div>';
    row.querySelector('p').textContent = file.name;
    const state = row.querySelectorAll('p')[1];
    const video = row.querySelector('video');
    const progress = row.querySelector('[data-progress]');
    video.src = URL.createObjectURL(file);
    list.appendChild(row);
    row.querySelector('button').addEventListener('click', function () { row.remove(); });

    if (file.size > policy.max_video_size_bytes || policy.allowed_extensions.indexOf(normalized.ext) === -1 || policy.allowed_mime_types.indexOf(normalized.type) === -1) {
      state.textContent = 'Not allowed · ' + formatSize(file.size) + ' · ' + (normalized.type || 'unknown type');
      row.classList.add('border-red-200');
      return;
    }

    state.textContent = 'Preparing upload · ' + formatSize(file.size);
    fetch(root.dataset.uploadUrl, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
      body: JSON.stringify({listing_id: root.dataset.listingId || null, filename: file.name, content_type: normalized.type, file_size: file.size, optimize: true})
    }).then(function (r) {
      return r.json().then(function (data) { if (!r.ok) throw new Error(data.error || 'Upload rejected.'); return data; });
    }).then(function (data) {
      return postToR2(data.upload, file, progress).then(function () { return data.video_id; });
    }).then(function (videoId) {
      state.textContent = 'Verifying upload';
      return fetch(completeUrl(root, videoId), {method: 'POST', headers: {'X-CSRFToken': csrfToken()}})
        .then(function (r) { return r.json().then(function (data) { if (!r.ok) throw new Error(data.error || 'Verification failed.'); return data; }); })
        .then(function () {
          state.textContent = 'Ready · ' + formatSize(file.size);
          progress.style.width = '100%';
          const input = document.createElement('input');
          input.type = 'hidden';
          input.name = 'pending_video_ids';
          input.value = videoId;
          root.closest('form').appendChild(input);
        });
    }).catch(function (error) {
      state.textContent = error.message;
      row.classList.add('border-red-200');
    });
  }

  function postToR2(upload, file, progress) {
    return new Promise(function (resolve, reject) {
      const form = new FormData();
      Object.keys(upload.fields).forEach(function (key) { form.append(key, upload.fields[key]); });
      form.append('file', file);
      const xhr = new XMLHttpRequest();
      xhr.open('POST', upload.url);
      xhr.upload.onprogress = function (event) {
        if (event.lengthComputable) progress.style.width = Math.round((event.loaded / event.total) * 95) + '%';
      };
      xhr.onload = function () { xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error('R2 upload failed with status ' + xhr.status + '.')); };
      xhr.onerror = function () { reject(new Error('Network error during video upload.')); };
      xhr.send(form);
    });
  }
})();
