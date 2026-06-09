import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Loader2, Youtube as YoutubeIcon, Check, ArrowLeft } from 'lucide-react';
import api from '../api/client';

function ProjectWizard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [channels, setChannels] = useState([]);
  const [name, setName] = useState('');
  const [channelId, setChannelId] = useState(null);

  useEffect(() => {
    api.get('/settings/youtube/channels').then(res => setChannels(res.data || [])).catch(() => setChannels([]));
  }, []);

  const createProject = async () => {
    setLoading(true);
    try {
      const res = await api.post('/projects/', {
        name: name || 'New Project',
        youtube_channel_id: channelId,
      });
      navigate(`/project/${res.data.id}`);
    } catch (e) {
      console.error('Failed to create project', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen p-8" style={{background:'#050608'}}>
      <div className="max-w-xl mx-auto">
        <div className="neo-card p-8">
          <h1 className="neo-title text-2xl mb-1">Create Project</h1>
          <p className="text-[#9AA0A6] text-sm mb-8">Give your project a name and pick a channel — everything else can be tuned later on the project page.</p>

          {/* Project Name */}
          <div className="mb-6">
            <label className="block text-sm font-semibold text-[#F5F5F5] mb-2">Project Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., History Shorts"
              className="w-full px-4 py-2.5 rounded-xl"
              autoFocus
            />
          </div>

          {/* YouTube Channel */}
          <div className="mb-8">
            <label className="block text-sm font-semibold text-[#F5F5F5] mb-2">
              <YoutubeIcon className="inline h-4 w-4 mr-1 text-[#C6F11D]" />
              YouTube Channel
            </label>
            {channels.length === 0 ? (
              <div className="p-3 rounded-xl bg-[rgba(255,200,69,0.08)] border border-[rgba(255,200,69,0.2)] text-[#FFC845] text-xs">
                No channels linked yet. <button onClick={() => navigate('/settings')} className="underline hover:text-white inline">Link one in Settings</button> to enable uploads.
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-2">
                <button
                  onClick={() => setChannelId(null)}
                  className={`neo-card-hover flex items-center gap-3 p-2.5 ${
                    !channelId ? 'neo-card-selected' : ''
                  }`}
                >
                  <div className="w-8 h-8 rounded-full bg-[#050608] flex items-center justify-center border border-[#252A33]">
                    <span className="text-[#5F6772] text-xs">—</span>
                  </div>
                  <div className="flex-1">
                    <p className="text-sm text-[#F5F5F5]">No channel (skip uploads)</p>
                  </div>
                  {!channelId && <Check className="h-3.5 w-3.5 text-[#C6F11D]" />}
                </button>
                {channels.map(channel => (
                  <button
                    key={channel.id}
                    onClick={() => setChannelId(channel.id)}
                    className={`neo-card-hover flex items-center gap-3 p-2.5 ${
                      channelId === channel.id ? 'neo-card-selected' : ''
                    }`}
                  >
                    {channel.thumbnail_url ? (
                      <img src={channel.thumbnail_url} alt={channel.name} className="w-8 h-8 rounded-full" />
                    ) : (
                      <div className="w-8 h-8 rounded-full bg-[rgba(198,241,29,0.1)] flex items-center justify-center">
                        <YoutubeIcon className="h-4 w-4 text-[#C6F11D]" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0 text-left">
                      <p className="text-sm text-[#F5F5F5] truncate">{channel.name}</p>
                      <p className="text-xs text-[#9AA0A6] truncate">{channel.channel_title}</p>
                    </div>
                    {channelId === channel.id && <Check className="h-3.5 w-3.5 text-[#C6F11D]" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex gap-3">
            <button
              onClick={() => navigate('/')}
              className="neo-card-hover flex items-center justify-center gap-2 px-6 py-3 text-sm text-[#9AA0A6] flex-1"
            >
              <ArrowLeft className="h-4 w-4" />
              Cancel
            </button>
            <button
              onClick={createProject}
              disabled={loading}
              className="neo-btn-primary flex items-center justify-center gap-2 py-3 text-sm flex-[2]"
            >
              {loading ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Creating...</>
              ) : (
                <><Sparkles className="h-4 w-4" /> Create Project</>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ProjectWizard;
