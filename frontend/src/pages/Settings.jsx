import React, { useState, useEffect, useRef } from 'react';
import { Youtube, Link, Key, Server, Save, CheckCircle, XCircle, Cpu, Image, Film, Database, RefreshCw, Plus, Trash2, ExternalLink, RefreshCcw, Archive, Upload, ChevronDown, ChevronUp, AlertTriangle, CheckCircle2, Circle, X } from 'lucide-react';
import api from '../api/client';

function SettingsPage() {
  const [settings, setSettings] = useState({});
  const [channels, setChannels] = useState([]);
  const [comfyuiStatus, setComfyuiStatus] = useState({ status: 'unknown' });
  const [modelInfo, setModelInfo] = useState(null);
  const [externalModelsDir, setExternalModelsDir] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [linking, setLinking] = useState(false);
  const [setupInfo, setSetupInfo] = useState({ secrets_file_exists: false });
  const [showSetupGuide, setShowSetupGuide] = useState(false);
  const [linkState, setLinkState] = useState('idle');
  const [linkError, setLinkError] = useState('');
  const [pendingChannel, setPendingChannel] = useState(null);
  const [pendingChannelName, setPendingChannelName] = useState('');
  const pollRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    loadSettings();
    loadChannels();
    checkStatuses();
    loadModelInfo();
    loadSetupInfo();
  }, []);

  const loadSetupInfo = async () => {
    try {
      const res = await api.get('/settings/youtube/setup-info');
      setSetupInfo(res.data);
    } catch (e) {
      console.error('Failed to load setup info:', e);
    }
  };

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const loadSettings = async () => {
    try {
      const res = await api.get('/settings/');
      setSettings(res.data);
    } catch (e) {
      console.error(e);
    }
  };

  const loadChannels = async () => {
    try {
      const res = await api.get('/settings/youtube/channels');
      setChannels(res.data);
    } catch (e) {
      console.error('Failed to load channels:', e);
      setChannels([]);
    }
  };

  const checkStatuses = async () => {
    try {
      const cfRes = await api.get('/settings/comfyui/status').catch(() => ({ data: { status: 'disconnected' } }));
      setComfyuiStatus(cfRes.data);
    } catch (e) {
      console.error(e);
    }
  };

  const loadModelInfo = async () => {
    try {
      const res = await api.get('/settings/comfyui/models');
      setModelInfo(res.data);
      if (res.data.external_models_dir) {
        setExternalModelsDir(res.data.external_models_dir);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const linkModels = async () => {
    if (!externalModelsDir) {
      alert('Please enter the path to your ComfyUI models folder');
      return;
    }
    try {
      const res = await api.post('/settings/comfyui/link-models', { external_models_dir: externalModelsDir });
      if (res.data.status === 'success') {
        setMessage('Models linked successfully!');
        loadModelInfo();
      } else {
        alert(res.data.message || 'Failed to link models');
      }
    } catch (e) {
      alert('Error: ' + e.message);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      await api.put('/settings/', settings);
      setMessage('Settings saved successfully!');
      setTimeout(() => setMessage(''), 3000);
    } catch (e) {
      setMessage('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleSecretsFile = async (file) => {
    if (!file) return;
    if (!file.name.endsWith('.json')) {
      alert('Please upload a .json file (the client_secrets.json from Google Cloud Console).');
      return;
    }
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await api.post('/settings/youtube/upload-secrets', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      if (res.data.status === 'success') {
        setMessage('Credentials file uploaded. You can now link a channel.');
        setTimeout(() => setMessage(''), 3000);
        await loadSetupInfo();
      } else {
        alert('Upload failed: ' + res.data.message);
      }
    } catch (e) {
      alert('Upload failed: ' + (e.response?.data?.message || e.message));
    }
  };

  const linkNewChannel = async () => {
    if (!setupInfo.secrets_file_exists) {
      setShowSetupGuide(true);
      return;
    }
    setLinking(true);
    setLinkState('starting');
    setLinkError('');
    try {
      const startRes = await api.post('/settings/youtube/auth/start-local');
      if (startRes.data.status === 'error') {
        setLinkError(startRes.data.message);
        setLinkState('error');
        setLinking(false);
        return;
      }
      const { auth_url, state } = startRes.data;
      window.open(auth_url, '_blank', 'width=600,height=700');
      setLinkState('waiting');
      pollRef.current = setInterval(async () => {
        try {
          const statusRes = await api.get('/settings/youtube/auth/status', { params: { state } });
          const data = statusRes.data;
          if (data.status === 'pending') return;
          clearInterval(pollRef.current);
          pollRef.current = null;
          if (data.status === 'success') {
            setPendingChannel(data.channel);
            setPendingChannelName(data.channel.channel_title || data.channel.name || '');
            setLinkState('naming');
          } else {
            setLinkError(data.message || 'Authorization failed.');
            setLinkState('error');
          }
        } catch (e) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setLinkError('Lost connection while checking status.');
          setLinkState('error');
        }
      }, 1500);
    } catch (e) {
      setLinkError(e.response?.data?.message || e.message);
      setLinkState('error');
      setLinking(false);
    }
  };

  const cancelLinking = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setLinking(false);
    setLinkState('idle');
    setLinkError('');
    setPendingChannel(null);
    setPendingChannelName('');
  };

  const savePendingChannel = async () => {
    if (!pendingChannel) return;
    const finalName = pendingChannelName.trim() || pendingChannel.channel_title || 'YouTube Channel';
    try {
      const res = await api.post('/settings/youtube/channels', { ...pendingChannel, name: finalName });
      if (res.data.status === 'success') {
        setMessage(`Channel "${finalName}" linked!`);
        setTimeout(() => setMessage(''), 3000);
        loadChannels();
        cancelLinking();
      } else {
        alert(res.data.message);
      }
    } catch (e) {
      alert('Save failed: ' + (e.response?.data?.message || e.message));
    }
  };

  const unlinkChannel = async (channelId, channelName) => {
    if (!confirm(`Unlink "${channelName}"? Projects using this channel will need to be reassigned.`)) return;
    try {
      const res = await api.delete(`/settings/youtube/channels/${channelId}`);
      if (res.data.status === 'success') {
        setMessage(`Channel unlinked (${res.data.detached_projects} project(s) detached)`);
        setTimeout(() => setMessage(''), 3000);
        loadChannels();
      }
    } catch (e) {
      alert('Unlink failed: ' + e.message);
    }
  };

  const refreshChannel = async (channelId) => {
    try {
      const res = await api.post(`/settings/youtube/channels/${channelId}/refresh`);
      if (res.data.status === 'success') {
        loadChannels();
      } else {
        alert(res.data.message);
      }
    } catch (e) {
      alert('Refresh failed: ' + e.message);
    }
  };

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center justify-between mb-8">
        <h2 className="neo-title text-3xl">Settings</h2>
        <button
          onClick={() => { loadSettings(); loadChannels(); checkStatuses(); loadModelInfo(); }}
          className="neo-btn-ghost flex items-center gap-2 px-4 py-2 text-sm"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {message && (
        <div className="mb-6 neo-card px-5 py-3 border-l-4 border-l-[#C6F11D]">
          <div className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-[#C6F11D]" />
            <span className="text-sm text-[#F5F5F5]">{message}</span>
          </div>
        </div>
      )}

      {/* YouTube Channels */}
      <div className="neo-card p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Youtube className="h-6 w-6 text-[#FF5757]" />
            <div>
              <h3 className="text-lg font-semibold text-[#F5F5F5]">YouTube Channels</h3>
              <p className="text-xs text-[#9AA0A6] mt-0.5">Link multiple channels. Each project can use a different one.</p>
            </div>
          </div>
          <button
            onClick={linkNewChannel}
            disabled={linking && linkState !== 'error'}
            className="neo-btn-primary flex items-center gap-2 px-4 py-2 text-sm"
          >
            <Plus className="h-4 w-4" />
            {linking && linkState !== 'error' ? 'Linking...' : 'Link Channel'}
          </button>
        </div>

        {/* Setup Status Banner */}
        <div className={`flex items-start gap-3 p-4 rounded-2xl mb-4 ${
          setupInfo.secrets_file_exists
            ? 'bg-[rgba(107,255,100,0.06)] border border-[rgba(107,255,100,0.25)]'
            : 'bg-[rgba(255,183,77,0.06)] border border-[rgba(255,183,77,0.25)]'
        }`}>
          {setupInfo.secrets_file_exists ? (
            <CheckCircle2 className="h-5 w-5 text-[#6BFF64] flex-shrink-0 mt-0.5" />
          ) : (
            <AlertTriangle className="h-5 w-5 text-[#FFB74D] flex-shrink-0 mt-0.5" />
          )}
          <div className="flex-1 min-w-0">
            {setupInfo.secrets_file_exists ? (
              <p className="text-sm text-[#F5F5F5]">
                <span className="font-semibold text-[#6BFF64]">Setup complete.</span> Google credentials loaded. Click "Link Channel" to connect an account.
              </p>
            ) : (
              <>
                <p className="text-sm text-[#F5F5F5]">
                  <span className="font-semibold text-[#FFB74D]">One-time setup needed.</span> Upload your Google credentials file to enable channel linking.
                </p>
                <p className="text-xs text-[#9AA0A6] mt-1">
                  This is a one-time 5-minute setup. After that, linking channels takes 1 click.
                </p>
              </>
            )}
          </div>
          <button
            onClick={() => setShowSetupGuide(!showSetupGuide)}
            className="neo-btn-ghost flex items-center gap-1 px-3 py-1.5 text-xs"
          >
            {showSetupGuide ? 'Hide' : 'Show'} instructions
            {showSetupGuide ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
        </div>

        {/* Setup Guide */}
        {showSetupGuide && (
          <div className="mb-4 p-5 rounded-2xl bg-[#0E1116] border border-[#252A33]">
            <h4 className="text-sm font-semibold text-[#F5F5F5] mb-3 flex items-center gap-2">
              <Key className="h-4 w-4 text-[#C6F11D]" />
              How to get your Google credentials (one-time, ~5 min)
            </h4>
            <ol className="space-y-3 text-sm text-[#9AA0A6]">
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[#C6F11D] text-[#050608] flex items-center justify-center text-xs font-bold">1</span>
                <div>
                  <p className="text-[#F5F5F5]">Go to <a href="https://console.cloud.google.com" target="_blank" rel="noopener noreferrer" className="text-[#C6F11D] underline">console.cloud.google.com</a> and create a new project (or pick an existing one).</p>
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[#C6F11D] text-[#050608] flex items-center justify-center text-xs font-bold">2</span>
                <div>
                  <p className="text-[#F5F5F5]">Open <span className="text-[#C6F11D]">APIs &amp; Services → Library</span>, search for <span className="text-[#C6F11D]">"YouTube Data API v3"</span>, and click <span className="font-semibold">Enable</span>.</p>
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[#C6F11D] text-[#050608] flex items-center justify-center text-xs font-bold">3</span>
                <div>
                  <p className="text-[#F5F5F5]">Go to <span className="text-[#C6F11D]">APIs &amp; Services → OAuth consent screen</span>.</p>
                  <p className="text-xs mt-1">• User type: <span className="text-[#C6F11D]">External</span></p>
                  <p className="text-xs">• App name: anything (e.g. "AI Shorts Creator")</p>
                  <p className="text-xs">• Scopes: add <code className="text-[#C6F11D]">.../auth/youtube.upload</code> and <code className="text-[#C6F11D]">.../auth/youtube.readonly</code></p>
                  <p className="text-xs">• Test users: add your YouTube channel's Google account email</p>
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[#C6F11D] text-[#050608] flex items-center justify-center text-xs font-bold">4</span>
                <div>
                  <p className="text-[#F5F5F5]">Go to <span className="text-[#C6F11D]">APIs &amp; Services → Credentials → Create Credentials → OAuth client ID</span>.</p>
                  <p className="text-xs mt-1">• Application type: <span className="text-[#C6F11D]">Desktop app</span></p>
                  <p className="text-xs">• Name: anything (e.g. "AI Shorts Desktop")</p>
                  <p className="text-xs">• Click Create, then <span className="text-[#C6F11D]">Download JSON</span></p>
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[#C6F11D] text-[#050608] flex items-center justify-center text-xs font-bold">5</span>
                <div>
                  <p className="text-[#F5F5F5]">Upload the downloaded file below (or drag and drop it).</p>
                </div>
              </li>
            </ol>

            {!setupInfo.secrets_file_exists && (
              <div
                className="mt-4 p-6 rounded-2xl border-2 border-dashed border-[#252A33] hover:border-[#C6F11D] transition-colors cursor-pointer"
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                onDrop={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  const file = e.dataTransfer.files?.[0];
                  if (file) handleSecretsFile(file);
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json,application/json"
                  className="hidden"
                  onChange={(e) => handleSecretsFile(e.target.files?.[0])}
                />
                <div className="flex flex-col items-center gap-2 text-center">
                  <Upload className="h-8 w-8 text-[#9AA0A6]" />
                  <p className="text-sm text-[#F5F5F5]">Click or drag your <code className="text-[#C6F11D]">client_secrets.json</code> here</p>
                  <p className="text-xs text-[#5F6772]">Saved to <code>storage/client_secrets.json</code> on the server</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Linking in progress / naming */}
        {linking && linkState !== 'idle' && (
          <div className="mb-4 p-5 rounded-2xl bg-[#0E1116] border border-[#C6F11D]/30">
            {linkState === 'starting' && (
              <p className="text-sm text-[#9AA0A6]">Starting authorization...</p>
            )}
            {linkState === 'waiting' && (
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <div className="h-4 w-4 border-2 border-[#C6F11D] border-t-transparent rounded-full animate-spin" />
                  <p className="text-sm text-[#F5F5F5]">Waiting for Google authorization...</p>
                </div>
                <p className="text-xs text-[#9AA0A6] ml-7">A new tab opened. Sign in, grant access, then return here. This page updates automatically.</p>
                <button onClick={cancelLinking} className="mt-3 ml-7 neo-btn-ghost px-3 py-1 text-xs text-[#FF5757]">Cancel</button>
              </div>
            )}
            {linkState === 'naming' && pendingChannel && (
              <div>
                <div className="flex items-center gap-3 mb-4">
                  {pendingChannel.thumbnail_url ? (
                    <img src={pendingChannel.thumbnail_url} alt={pendingChannel.channel_title} className="w-12 h-12 rounded-full" />
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-[rgba(255,87,87,0.12)] flex items-center justify-center">
                      <Youtube className="h-6 w-6 text-[#FF5757]" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-[#6BFF64]">Connected to YouTube!</p>
                    <p className="text-xs text-[#9AA0A6] truncate">{pendingChannel.channel_title}</p>
                  </div>
                </div>
                <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">Display name in this app</label>
                <input
                  type="text"
                  value={pendingChannelName}
                  onChange={(e) => setPendingChannelName(e.target.value)}
                  placeholder="e.g., Tech Reviews, Cooking, Main Channel"
                  className="w-full px-4 py-2.5 rounded-xl bg-[#050608] border border-[#252A33] text-[#F5F5F5] placeholder-[#5F6772] outline-none focus:border-[#C6F11D]/50 text-sm"
                  autoFocus
                />
                <p className="text-[11px] text-[#5F6772] mt-1">You can rename it later by unlinking and re-adding.</p>
                <div className="flex gap-2 mt-4">
                  <button onClick={savePendingChannel} className="neo-btn-primary px-4 py-2 text-sm">Save Channel</button>
                  <button onClick={cancelLinking} className="neo-btn-ghost px-4 py-2 text-sm">Cancel</button>
                </div>
              </div>
            )}
            {linkState === 'error' && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <XCircle className="h-4 w-4 text-[#FF5757]" />
                  <p className="text-sm font-semibold text-[#FF5757]">Linking failed</p>
                </div>
                <p className="text-xs text-[#9AA0A6] ml-6">{linkError}</p>
                <div className="flex gap-2 mt-3 ml-6">
                  <button onClick={linkNewChannel} className="neo-btn-secondary px-3 py-1 text-xs">Try again</button>
                  <button onClick={cancelLinking} className="neo-btn-ghost px-3 py-1 text-xs">Dismiss</button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Linked channels list */}
        {channels.length === 0 ? (
          <div className="p-8 text-center border border-dashed border-[#252A33] rounded-2xl">
            <Youtube className="h-10 w-10 text-[#5F6772] mx-auto mb-3" />
            <p className="text-sm text-[#9AA0A6]">No channels linked yet</p>
            <p className="text-xs text-[#5F6772] mt-1">
              {setupInfo.secrets_file_exists
                ? 'Click "Link Channel" above to connect your first YouTube account'
                : 'Upload your Google credentials first, then link a channel'}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {channels.map(channel => (
              <div key={channel.id} className="flex items-center gap-3 p-3 rounded-2xl bg-[#0E1116] border border-[#252A33] hover:border-[rgba(198,241,29,0.2)] transition-all duration-150">
                {channel.thumbnail_url ? (
                  <img src={channel.thumbnail_url} alt={channel.name} className="w-10 h-10 rounded-full" />
                ) : (
                  <div className="w-10 h-10 rounded-full bg-[rgba(255,87,87,0.12)] flex items-center justify-center">
                    <Youtube className="h-5 w-5 text-[#FF5757]" />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-[#F5F5F5] truncate">{channel.name}</p>
                  <p className="text-xs text-[#9AA0A6] truncate">
                    {channel.channel_title}
                    {channel.channel_id && <span className="text-[#5F6772]"> • ID: {channel.channel_id.slice(0, 12)}...</span>}
                  </p>
                </div>
                <button
                  onClick={() => refreshChannel(channel.id)}
                  className="neo-btn-ghost p-1.5"
                  title="Refresh channel info"
                >
                  <RefreshCcw className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => unlinkChannel(channel.id, channel.name)}
                  className="neo-btn-ghost p-1.5 text-[#FF5757] hover:bg-[rgba(255,87,87,0.1)]"
                  title="Unlink channel"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Services */}
      <div className="neo-card p-6 mb-6">
        <h3 className="text-lg font-semibold text-[#F5F5F5] mb-4">External Services</h3>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">Ollama Host</label>
            <input
              type="text"
              value={settings.ollama_host || 'http://localhost:11434'}
              onChange={(e) => setSettings({ ...settings, ollama_host: e.target.value })}
              className="w-full px-4 py-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-[#F5F5F5] placeholder-[#5F6772] outline-none focus:border-[#C6F11D]/50 transition-all"
            />
            <p className="text-[11px] text-[#5F6772] mt-1">Local LLM server for script generation</p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">ComfyUI Host</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={settings.comfyui_host || 'http://127.0.0.1:8188'}
                onChange={(e) => setSettings({ ...settings, comfyui_host: e.target.value })}
                className="flex-1 px-4 py-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-[#F5F5F5] placeholder-[#5F6772] outline-none focus:border-[#C6F11D]/50 transition-all"
              />
              <button
                onClick={checkStatuses}
                className="neo-btn-secondary px-4 py-2 text-sm"
              >
                Test
              </button>
            </div>
            <p className="text-[11px] text-[#5F6772] mt-1">
              Status: {comfyuiStatus.status === 'connected' ? (
                <span className="text-[#6BFF64]">Connected</span>
              ) : (
                <span className="text-[#FF5757]">Disconnected</span>
              )}
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">Pixabay API Key</label>
            <input
              type="password"
              value={settings.pixabay_api_key || ''}
              onChange={(e) => setSettings({ ...settings, pixabay_api_key: e.target.value })}
              placeholder="Optional - get free key from pixabay.com"
              className="w-full px-4 py-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-[#F5F5F5] placeholder-[#5F6772] outline-none focus:border-[#C6F11D]/50 transition-all"
            />
            <p className="text-[11px] text-[#5F6772] mt-1">
              Optional. Improves stock footage results. Free at pixabay.com/api/docs
            </p>
          </div>
        </div>
      </div>

      {/* AI Models */}
      <div className="neo-card p-6 mb-6">
        <div className="flex items-center gap-3 mb-4">
          <Cpu className="h-5 w-5 text-[#C6F11D]" />
          <h3 className="text-lg font-semibold text-[#F5F5F5]">AI Models (LTX 2.3 t2v only)</h3>
        </div>

        {modelInfo ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="neo-card-hover p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Film className="h-4 w-4 text-[#C6F11D]" />
                  <span className="text-xs font-medium text-[#9AA0A6]">LTX Video</span>
                </div>
                <span className={`text-xs ${modelInfo.models?.ltx_video ? 'text-[#6BFF64]' : 'text-[#FF5757]'}`}>
                  {modelInfo.models?.ltx_video ? 'Ready' : 'Missing'}
                </span>
              </div>
              <div className="neo-card-hover p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Database className="h-4 w-4 text-[#C6F11D]" />
                  <span className="text-xs font-medium text-[#9AA0A6]">VAE</span>
                </div>
                <span className={`text-xs ${modelInfo.models?.vae ? 'text-[#6BFF64]' : 'text-[#FF5757]'}`}>
                  {modelInfo.models?.vae ? 'Ready' : 'Missing'}
                </span>
              </div>
              <div className="neo-card-hover p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Image className="h-4 w-4 text-[#C6F11D]" />
                  <span className="text-xs font-medium text-[#9AA0A6]">Text Encoder</span>
                </div>
                <span className={`text-xs ${modelInfo.models?.text_encoder ? 'text-[#6BFF64]' : 'text-[#FF5757]'}`}>
                  {modelInfo.models?.text_encoder ? 'Ready' : 'Missing'}
                </span>
              </div>
              <div className="neo-card-hover p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Server className="h-4 w-4 text-[#C6F11D]" />
                  <span className="text-xs font-medium text-[#9AA0A6]">Upscaler</span>
                </div>
                <span className={`text-xs ${modelInfo.models?.upscaler ? 'text-[#6BFF64]' : 'text-[#FF5757]'}`}>
                  {modelInfo.models?.upscaler ? 'Ready' : 'Missing'}
                </span>
              </div>
            </div>

            <div>
              <p className="text-sm font-medium text-[#9AA0A6] mb-2">Style LoRAs ({modelInfo.styles?.filter(s => s.available).length}/{modelInfo.styles?.length || 0} ready)</p>
              <div className="flex flex-wrap gap-2">
                {modelInfo.styles?.map((style) => (
                  <span
                    key={style.id}
                    className={`px-3 py-1 rounded-full text-xs border transition-all ${
                      style.available
                        ? 'bg-[rgba(198,241,29,0.08)] text-[#C6F11D] border-[rgba(198,241,29,0.25)]'
                        : 'bg-[#0E1116] text-[#5F6772] border-[#252A33]'
                    }`}
                  >
                    {style.name}
                    {style.available && style.matched_lora && ' ✓'}
                  </span>
                ))}
              </div>
              <p className="text-[11px] text-[#5F6772] mt-2">
                {modelInfo.loras?.length || 0} total LoRAs detected
              </p>
            </div>

            <div className="pt-4 border-t border-[#252A33]">
              <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">Link External Models</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={externalModelsDir}
                  onChange={(e) => setExternalModelsDir(e.target.value)}
                  placeholder="e.g., F:\ComfyUI\models"
                  className="flex-1 px-4 py-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-[#F5F5F5] placeholder-[#5F6772] outline-none text-sm transition-all focus:border-[#C6F11D]/50"
                />
                <button
                  onClick={linkModels}
                  className="neo-btn-secondary flex items-center gap-2 px-4 py-2 text-sm"
                >
                  <Link className="h-4 w-4" />
                  Link
                </button>
              </div>
              {modelInfo.models_linked && (
                <p className="text-[11px] text-[#6BFF64] mt-1">
                  Linked: {modelInfo.external_models_dir}
                </p>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-[#5F6772]">Loading...</p>
        )}
      </div>

      {/* Upload Schedule */}
      <div className="neo-card p-6 mb-6">
        <h3 className="text-lg font-semibold text-[#F5F5F5] mb-4">Upload Schedule</h3>
        <p className="text-sm text-[#9AA0A6] mb-4">Global settings for how videos are posted to YouTube.</p>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">Videos per day</label>
            <div className="grid grid-cols-3 gap-3">
              {[1, 2, 4].map((count) => (
                <button
                  key={count}
                  onClick={() => setSettings({ ...settings, videos_per_day: count })}
                  className={`py-3 rounded-xl text-center transition-all duration-150 ${
                    (settings.videos_per_day || 2) === count
                      ? 'neo-card-selected'
                      : 'neo-card-hover'
                  }`}
                >
                  <div className="text-lg font-bold text-[#F5F5F5]">{count}</div>
                  <div className="text-[10px] text-[#5F6772]">video{count > 1 ? 's' : ''}/day</div>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">Upload times</label>
            <div className="space-y-2">
              {(settings.upload_times || ['10:00', '16:00']).map((time, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type="time"
                    value={time}
                    onChange={(e) => {
                      const times = [...(settings.upload_times || ['10:00', '16:00'])];
                      times[i] = e.target.value;
                      setSettings({ ...settings, upload_times: times });
                    }}
                    className="px-4 py-2 rounded-xl bg-[#0E1116] border border-[#252A33] text-[#F5F5F5] text-sm outline-none focus:border-[#C6F11D]/50 transition-all"
                  />
                  {(settings.upload_times || ['10:00', '16:00']).length > 1 && (
                    <button
                      onClick={() => {
                        const times = (settings.upload_times || ['10:00', '16:00']).filter((_, idx) => idx !== i);
                        setSettings({ ...settings, upload_times: times });
                      }}
                      className="px-2 py-2 rounded-lg text-[#FF5757] hover:bg-[rgba(255,87,87,0.1)] transition-all text-sm"
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
              {(settings.upload_times || ['10:00', '16:00']).length < 4 && (
                <button
                  onClick={() => {
                    const times = [...(settings.upload_times || ['10:00', '16:00']), '12:00'];
                    setSettings({ ...settings, upload_times: times });
                  }}
                  className="text-xs text-[#C6F11D] hover:text-[#D9FF3D] transition-all"
                >
                  + Add time slot
                </button>
              )}
            </div>
            <p className="text-[11px] text-[#5F6772] mt-2">Videos are spread across these times each day</p>
          </div>
        </div>
      </div>

      {/* Archive */}
      <div className="neo-card p-6 mb-6">
        <div className="flex items-center gap-3 mb-4">
          <Archive className="h-5 w-5 text-[#C6F11D]" />
          <div>
            <h3 className="text-lg font-semibold text-[#F5F5F5]">Archive</h3>
            <p className="text-xs text-[#9AA0A6] mt-0.5">Videos are auto-archived (moved) after N successful uploads.</p>
          </div>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">Archive path</label>
            <input
              type="text"
              value={settings.archive_path || ''}
              onChange={(e) => setSettings({ ...settings, archive_path: e.target.value })}
              placeholder="e.g., D:\Archives\AI_Shorts"
              className="w-full px-4 py-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-[#F5F5F5] placeholder-[#5F6772] outline-none focus:border-[#C6F11D]/50 transition-all"
            />
            <p className="text-[11px] text-[#5F6772] mt-1">Subfolders will be created as: {archive_path || '{path}'}/category/DDMMYYYY/</p>
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">Auto-archive threshold</label>
            <div className="flex gap-2">
              {[10, 20, 50].map(n => (
                <button
                  key={n}
                  onClick={() => setSettings({ ...settings, archive_threshold: n })}
                  className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all duration-150 ${
                    (settings.archive_threshold || 20) === n
                      ? 'bg-[#C6F11D] text-[#050608]'
                      : 'bg-[#0E1116] text-[#9AA0A6] border border-[#252A33] hover:text-[#F5F5F5]'
                  }`}
                >
                  Every {n}
                </button>
              ))}
              <input
                type="number"
                min="1"
                max="100"
                value={![10, 20, 50].includes(Number(settings.archive_threshold)) ? settings.archive_threshold || '' : ''}
                onChange={(e) => setSettings({ ...settings, archive_threshold: parseInt(e.target.value) || 20 })}
                placeholder="Custom"
                className="w-20 px-3 py-2 rounded-xl bg-[#0E1116] border border-[#252A33] text-[#F5F5F5] text-xs text-center outline-none focus:border-[#C6F11D]/50 transition-all"
              />
            </div>
            <p className="text-[11px] text-[#5F6772] mt-1">Auto-archives when {settings.archive_threshold || 20}+ posted videos are pending archive</p>
          </div>
        </div>
      </div>

      {/* Save */}
      <div className="flex justify-end">
        <button
          onClick={saveSettings}
          disabled={saving}
          className="neo-btn-primary flex items-center gap-2 px-6 py-2.5 text-sm"
        >
          <Save className="h-4 w-4" />
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}

export default SettingsPage;
