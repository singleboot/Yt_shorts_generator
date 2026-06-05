import React, { useState, useEffect } from 'react';
import { Youtube, Link, Key, Server, Save, CheckCircle, XCircle, Cpu, Image, Film, Database, RefreshCw, Plus, Trash2, ExternalLink, RefreshCcw, Archive } from 'lucide-react';
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

  useEffect(() => {
    loadSettings();
    loadChannels();
    checkStatuses();
    loadModelInfo();
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

  const linkNewChannel = async () => {
    setLinking(true);
    try {
      const startRes = await api.post('/settings/youtube/auth/start');
      if (startRes.data.status === 'error') {
        alert(startRes.data.message);
        setLinking(false);
        return;
      }
      const authUrl = startRes.data.auth_url;
      window.open(authUrl, '_blank');
      const code = prompt(
        'After authorizing YouTube, paste the auth code from the redirect URL here.\n\n(The "code" parameter from https://localhost/?code=XXXX&scope=...)'
      );
      if (!code) {
        setLinking(false);
        return;
      }
      const channelName = prompt('Name this channel (e.g., "Tech Reviews", "Cooking"):') || '';

      const completeRes = await api.post('/settings/youtube/auth/complete', { code, channel_name: channelName });
      if (completeRes.data.status !== 'success') {
        alert(completeRes.data.message);
        setLinking(false);
        return;
      }

      const saveRes = await api.post('/settings/youtube/channels', completeRes.data.channel);
      if (saveRes.data.status === 'success') {
        setMessage(`Channel "${saveRes.data.channel.name}" linked successfully!`);
        setTimeout(() => setMessage(''), 3000);
        loadChannels();
      } else {
        alert(saveRes.data.message);
      }
    } catch (e) {
      alert('Link failed: ' + (e.response?.data?.message || e.message));
    } finally {
      setLinking(false);
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
            disabled={linking}
            className="neo-btn-primary flex items-center gap-2 px-4 py-2 text-sm"
          >
            <Plus className="h-4 w-4" />
            {linking ? 'Linking...' : 'Link Channel'}
          </button>
        </div>

        {channels.length === 0 ? (
          <div className="p-8 text-center border border-dashed border-[#252A33] rounded-2xl">
            <Youtube className="h-10 w-10 text-[#5F6772] mx-auto mb-3" />
            <p className="text-sm text-[#9AA0A6]">No channels linked yet</p>
            <p className="text-xs text-[#5F6772] mt-1">Click "Link Channel" to connect your first YouTube account</p>
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
