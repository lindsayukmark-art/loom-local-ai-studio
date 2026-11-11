'use strict';

const node = id => document.getElementById(id);
const size = bytes => bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

function link(id, file) {
  const element = node(id);
  if (!element) return;
  if (file?.available && typeof file.url === 'string' && file.url.startsWith('/api/downloads/')) {
    element.href = file.url;
    element.download = file.filename;
    element.hidden = false;
  } else {
    element.hidden = true;
    element.removeAttribute('href');
  }
}

async function loadDownloads() {
  const status = node('download-status');
  try {
    const response = await fetch('/api/downloads', {credentials: 'same-origin', signal: AbortSignal.timeout(20000)});
    if (!response.ok) throw new Error('Downloads are temporarily unavailable. Reload this page to try again.');
    const manifest = await response.json();
    const files = new Map(manifest.files.map(file => [file.id, file]));
    node('version-label').textContent = `Version ${manifest.version}`;
    const source = files.get('source');
    link('source-download', source);
    link('installer-download', files.get('windows-installer'));
    link('windows-guide-link', files.get('windows-guide'));
    link('readme-link', files.get('readme'));
    link('checksum-download', files.get('checksum'));
    node('source-details').textContent = source?.available ? `${size(source.size)} ZIP · source code and build files` : 'The source bundle is not included in this installation.';
    node('source-checksum').textContent = source?.sha256 || 'Checksum unavailable';
    node('installer-pending').hidden = manifest.installer_available;
    if (manifest.installer_available) {
      if (node('installer-badge')) node('installer-badge').textContent = 'WINDOWS X64';
      if (node('installer-state')) node('installer-state').textContent = 'Installer archive available';
    }
    status.textContent = source?.available ? 'Source download ready. Model files are not included.' : 'Source download unavailable. See the setup guide for build instructions.';
  } catch (error) {
    status.textContent = error.name === 'TimeoutError' ? 'Download information took too long to load. Reload to try again.' : error.message;
    status.classList.add('download-error');
  }
}

loadDownloads();
