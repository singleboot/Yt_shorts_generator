import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Clock, Loader2, Youtube as YoutubeIcon, Check, Music, Mic, Palette, Volume2, Play, Square } from 'lucide-react';
import { AI_STYLES, VOICES, MUSIC_GENRES } from '../constants/production';
import api from '../api/client';

function ProjectWizard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [channels, setChannels] = useState([]);
  const audioRef = useRef(null);
  const [previewPlaying, setPreviewPlaying] = useState(null);

  const togglePreview = (type, id) => {
    const key = `${type}:${id}`;
    if (previewPlaying === key) {
      if (audioRef.current) { audioRef.current.pause(); audioRef.current.currentTime = 0; }
      setPreviewPlaying(null);
      return;
    }
    const BASE = 'http://127.0.0.1:8002';
    const url = type === 'voice'
      ? `${BASE}/settings/preview-voice?voice_id=${id}`
      : `${BASE}/settings/preview-music/${id}`;
    if (audioRef.current) {
      audioRef.current.src = url;
      audioRef.current.play().catch(() => {});
    }
    setPreviewPlaying(key);
  };

  useEffect(() => {
    api.get('/settings/youtube/channels').then(res => setChannels(res.data || [])).catch(() => setChannels([]));
  }, []);

  const [form, setForm] = useState({
    name: '',
    ai_style: 'none',
    lora_strength: 0.8,
    voice_id: 'en-US-AriaNeural',
    music_genre: 'ambient',
    youtube_channel_id: null,
  });

  const update = (key, value) => setForm(prev => ({ ...prev, [key]: value }));

  const createProject = async () => {
    setLoading(true);
    try {
      const res = await api.post('/projects/', {
        name: form.name || 'New Project',
        source_type: 'topic',
        source_value: '',
        category: 'general',
        visual_type: 'ai_generated',
        visual_settings: {
          ai_style: form.ai_style,
          lora_strength: form.lora_strength,
          visual_type: 'ai_generated',
          total_duration: 60,
        },
        audio_settings: {
          voice_id: form.voice_id,
          language: form.voice_id.split('-')[0],
          music_genre: form.music_genre,
          music_volume: 0.15,
          voice_volume: 1.0,
        },
        caption_settings: {
          style: 'bold_yellow', font: 'Impact', font_size: 52, color: '#FFD700',
          stroke_color: '#000000', stroke_width: 3, animation: 'word_by_word',
        },
        schedule_settings: {},
        seo_settings: { auto_generate: true, hashtag_count: 12, auto_hashtags: true },
        youtube_channel_id: form.youtube_channel_id,
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
      <audio ref={audioRef} onEnded={() => setPreviewPlaying(null)} className="hidden" />
      <div className="max-w-3xl mx-auto">
        <div className="neo-card p-8">
          <h1 className="neo-title text-2xl mb-1">Create Project</h1>
          <p className="text-[#9AA0A6] text-sm mb-8">Set your production rules. You'll pick a topic & generate videos on the project page.</p>

          {/* Project Name */}
          <div className="mb-6">
            <label className="block text-sm font-semibold text-[#F5F5F5] mb-2">Project Name</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => update('name', e.target.value)}
              placeholder="e.g., History Shorts"
              className="w-full px-4 py-2.5 rounded-xl"
            />
          </div>

          {/* Visual Style */}
          <div className="mb-6">
            <label className="block text-sm font-semibold text-[#F5F5F5] mb-2">
              <Palette className="inline h-4 w-4 mr-1 text-[#C6F11D]" />
              Visual Style
            </label>
            <div className="grid grid-cols-4 gap-2">
              {AI_STYLES.map((style) => (
                <button
                  key={style.id}
                  onClick={() => update('ai_style', style.id)}
                  className={`neo-card-hover p-3 text-xs font-medium text-center ${
                    form.ai_style === style.id ? 'neo-card-selected' : ''
                  }`}
                >
                  {form.ai_style === style.id && (
                    <Check className="h-3 w-3 text-[#C6F11D] absolute top-1.5 right-1.5" />
                  )}
                  {style.name}
                </button>
              ))}
            </div>
            {form.ai_style !== 'none' && (
              <div className="mt-3">
                <label className="text-xs text-[#9AA0A6] block mb-1">Strength: {form.lora_strength.toFixed(1)}</label>
                <input
                  type="range" min="0" max="1.5" step="0.1"
                  value={form.lora_strength}
                  onChange={(e) => update('lora_strength', parseFloat(e.target.value))}
                  className="w-full accent-[#C6F11D]"
                />
              </div>
            )}
          </div>

          {/* Voice + Music row */}
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div>
              <label className="block text-sm font-semibold text-[#F5F5F5] mb-2">
                <Mic className="inline h-4 w-4 mr-1 text-[#C6F11D]" />
                Voice
              </label>
              <div className="flex items-center gap-2">
                <select
                  value={form.voice_id}
                  onChange={(e) => update('voice_id', e.target.value)}
                  className="flex-1 px-4 py-2.5 rounded-xl"
                >
                  {VOICES.map(v => (
                    <option key={v.id} value={v.id}>{v.name} ({v.gender}) — {v.locale}</option>
                  ))}
                </select>
                <button
                  onClick={() => togglePreview('voice', form.voice_id)}
                  className={`flex items-center gap-1 px-2.5 py-2.5 rounded-xl text-xs font-medium border transition-all duration-150 ${
                    previewPlaying === `voice:${form.voice_id}`
                      ? 'border-[#FF5757] bg-[rgba(255,87,87,0.1)] text-[#FF5757]'
                      : 'border-[#252A33] bg-transparent text-[#9AA0A6] hover:text-[#C6F11D] hover:border-[#C6F11D]'
                  }`}
                  title="Preview this voice"
                >
                  {previewPlaying === `voice:${form.voice_id}` ? <Square className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
            <div>
              <label className="block text-sm font-semibold text-[#F5F5F5] mb-2">
                <Music className="inline h-4 w-4 mr-1 text-[#C6F11D]" />
                Music
              </label>
              <div className="grid grid-cols-4 gap-1.5">
                {MUSIC_GENRES.map((m) => (
                  <div key={m.id} className="flex flex-col items-center gap-0.5">
                    <button
                      onClick={() => update('music_genre', m.id)}
                      className={`flex flex-col items-center gap-1 p-2 rounded-lg text-xs transition-all ${
                        form.music_genre === m.id
                          ? 'bg-[rgba(198,241,29,0.12)] text-[#C6F11D] border border-[rgba(198,241,29,0.3)]'
                          : 'bg-[#050608] text-[#9AA0A6] border border-[#252A33] hover:border-[#C6F11D]'
                      }`}
                    >
                      <span className="text-base">{m.emoji}</span>
                      <span>{m.name}</span>
                    </button>
                    <button
                      onClick={() => togglePreview('music', m.id)}
                      className={`p-1 rounded text-[10px] transition-all ${
                        previewPlaying === `music:${m.id}`
                          ? 'text-[#FF5757]'
                          : 'text-[#5F6772] hover:text-[#C6F11D]'
                      }`}
                      title="Preview this genre"
                    >
                      {previewPlaying === `music:${m.id}` ? <Square className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                    </button>
                  </div>
                ))}
              </div>
            </div>
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
                  onClick={() => update('youtube_channel_id', null)}
                  className={`neo-card-hover flex items-center gap-3 p-2.5 ${
                    !form.youtube_channel_id ? 'neo-card-selected' : ''
                  }`}
                >
                  <div className="w-8 h-8 rounded-full bg-[#050608] flex items-center justify-center border border-[#252A33]">
                    <span className="text-[#5F6772] text-xs">—</span>
                  </div>
                  <div className="flex-1">
                    <p className="text-sm text-[#F5F5F5]">No channel (skip uploads)</p>
                  </div>
                  {!form.youtube_channel_id && <Check className="h-3.5 w-3.5 text-[#C6F11D]" />}
                </button>
                {channels.map(channel => (
                  <button
                    key={channel.id}
                    onClick={() => update('youtube_channel_id', channel.id)}
                    className={`neo-card-hover flex items-center gap-3 p-2.5 ${
                      form.youtube_channel_id === channel.id ? 'neo-card-selected' : ''
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
                    {form.youtube_channel_id === channel.id && <Check className="h-3.5 w-3.5 text-[#C6F11D]" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Create button */}
          <button
            onClick={createProject}
            disabled={loading}
            className="neo-btn-primary w-full flex items-center justify-center gap-2 py-3 text-sm"
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
  );
}

export default ProjectWizard;
