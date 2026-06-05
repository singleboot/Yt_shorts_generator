import React, { useState, useRef } from 'react';
import { X, Sparkles, RotateCcw, Volume2, Play, Square } from 'lucide-react';
import { AI_STYLES, VOICES, MUSIC_GENRES } from '../constants/production';

function EditVideoModal({ video, project, onClose, onSave }) {
  const vs = project.visual_settings || {};
  const [selectedStyle, setSelectedStyle] = useState(video.overrides?.ai_style || vs.ai_style || 'none');
  const [selectedVoice, setSelectedVoice] = useState(video.overrides?.voice_id || vs.voice_id || 'en-US-AriaNeural');
  const [selectedMusic, setSelectedMusic] = useState(video.overrides?.music_genre || vs.music_genre || 'none');
  const [musicPrompt, setMusicPrompt] = useState(video.overrides?.music_prompt || '');
  const [voiceCustom, setVoiceCustom] = useState(video.overrides?.voice_custom || '');
  const [loraStrength, setLoraStrength] = useState(video.overrides?.lora_strength || vs.lora_strength || 0.6);
  const [saving, setSaving] = useState(false);
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

  const handleSave = async () => {
    setSaving(true);
    const payload = {
      ai_style: selectedStyle,
      voice_id: selectedVoice,
      voice_custom: selectedVoice === '__custom__' ? voiceCustom.trim() || undefined : undefined,
      music_genre: selectedMusic,
      lora_strength: loraStrength,
    };
    if (musicPrompt.trim()) {
      payload.music_prompt = musicPrompt.trim();
    }
    Object.keys(payload).forEach(k => payload[k] === undefined && delete payload[k]);
    await onSave(payload);
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#050608]/90" onClick={onClose}>
      <div
        className="neo-card w-full max-w-2xl max-h-[85vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-[#252A33]">
          <div>
            <h2 className="text-lg font-bold text-[#F5F5F5]">Edit Video {video.index + 1}</h2>
            <p className="text-xs text-[#9AA0A6] mt-0.5">Changing settings will regenerate this video</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-xl hover:bg-[rgba(255,255,255,0.03)] transition-colors">
            <X className="h-4 w-4 text-[#9AA0A6]" />
          </button>
        </div>

        {/* Style grid */}
        <div className="p-5 space-y-6">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="h-4 w-4 text-[#C6F11D]" />
              <h3 className="text-sm font-semibold text-[#F5F5F5]">Visual Style</h3>
            </div>
            <div className="grid grid-cols-4 gap-2">
              {AI_STYLES.map(style => (
                <button
                  key={style.id}
                  onClick={() => setSelectedStyle(style.id)}
                  className={`flex flex-col items-center gap-1.5 p-2 rounded-xl border transition-all duration-150 ${
                    selectedStyle === style.id
                      ? 'neo-card-selected'
                      : 'neo-card-hover'
                  }`}
                >
                  <span className="text-xl">{style.icon}</span>
                  <span className="text-[10px] font-medium text-[#F5F5F5]">{style.name}</span>
                  <span className="text-[9px] text-[#9AA0A6] text-center leading-tight">{style.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <audio ref={audioRef} onEnded={() => setPreviewPlaying(null)} className="hidden" />

          {/* Voice dropdown */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm">🎤</span>
              <h3 className="text-sm font-semibold text-[#F5F5F5]">Voice</h3>
            </div>
            <div className="flex items-center gap-2">
              <select
                value={selectedVoice}
                onChange={e => setSelectedVoice(e.target.value)}
                className="flex-1 p-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-sm text-[#F5F5F5] outline-none focus:border-[#C6F11D]/50 transition-all"
              >
                {VOICES.map(v => (
                  <option key={v.id} value={v.id} className="bg-[#0E1116] text-[#F5F5F5]">
                    {v.name} ({v.gender}) — {v.locale}
                  </option>
                ))}
                <option value="__custom__">Custom...</option>
              </select>
              {selectedVoice !== '__custom__' && (
                <button
                  onClick={() => togglePreview('voice', selectedVoice)}
                  className={`flex items-center gap-1 px-2.5 py-2.5 rounded-xl text-xs font-medium border transition-all duration-150 ${
                    previewPlaying === `voice:${selectedVoice}`
                      ? 'border-[#FF5757] bg-[rgba(255,87,87,0.1)] text-[#FF5757]'
                      : 'border-[#252A33] bg-transparent text-[#9AA0A6] hover:text-[#C6F11D] hover:border-[#C6F11D]'
                  }`}
                  title="Preview this voice"
                >
                  {previewPlaying === `voice:${selectedVoice}` ? <Square className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
                </button>
              )}
            </div>
            {selectedVoice === '__custom__' && (
              <textarea
                value={voiceCustom}
                onChange={e => setVoiceCustom(e.target.value)}
                placeholder="e.g. young male narrator with British accent"
                rows={2}
                className="w-full mt-2 p-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-xs text-[#F5F5F5] outline-none focus:border-[#C6F11D]/50 transition-all resize-none"
              />
            )}
          </div>

          {/* Music genre */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm">🎵</span>
              <h3 className="text-sm font-semibold text-[#F5F5F5]">Background Music</h3>
            </div>
            <div className="flex flex-wrap gap-2">
              {MUSIC_GENRES.map(m => (
                <div key={m.id} className="flex items-center">
                  <button
                    onClick={() => setSelectedMusic(m.id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-l-xl text-xs font-medium border border-r-0 transition-all duration-150 ${
                      selectedMusic === m.id
                        ? 'border-[#C6F11D] bg-[rgba(198,241,29,0.1)] text-[#C6F11D]'
                        : 'border-[#252A33] bg-transparent text-[#9AA0A6] hover:bg-[rgba(255,255,255,0.03)]'
                    }`}
                  >
                    <span>{m.emoji}</span>
                    {m.name}
                  </button>
                  <button
                    onClick={() => togglePreview('music', m.id)}
                    className={`px-2 py-1.5 rounded-r-xl text-xs border transition-all duration-150 ${
                      previewPlaying === `music:${m.id}`
                        ? 'border-[#FF5757] bg-[rgba(255,87,87,0.1)] text-[#FF5757]'
                        : selectedMusic === m.id
                          ? 'border-[#C6F11D] bg-[rgba(198,241,29,0.1)] text-[#C6F11D]'
                          : 'border-[#252A33] bg-transparent text-[#9AA0A6] hover:text-[#C6F11D] hover:border-[#C6F11D]'
                    }`}
                    title="Preview this genre"
                  >
                    {previewPlaying === `music:${m.id}` ? <Square className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Custom Music Prompt (overrides genre) */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-sm">🎼</span>
                <h3 className="text-sm font-semibold text-[#F5F5F5]">Custom Music Prompt <span className="text-[10px] text-[#5F6772] font-normal">(overrides genre)</span></h3>
              </div>
              {musicPrompt && (
                <button
                  onClick={() => setMusicPrompt('')}
                  className="text-[10px] text-[#9AA0A6] hover:text-[#FF5757] flex items-center gap-1"
                >
                  <RotateCcw className="h-3 w-3" /> Clear
                </button>
              )}
            </div>
            <textarea
              value={musicPrompt}
              onChange={e => setMusicPrompt(e.target.value)}
              placeholder="e.g. lofi, chill, hip hop, relaxed, 85 BPM, A minor"
              rows={2}
              className="w-full p-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-xs text-[#F5F5F5] outline-none focus:border-[#C6F11D]/50 transition-all resize-none"
            />
            <p className="text-[10px] text-[#5F6772] mt-1">ACE 1.5 tag string — comma-separated moods, instruments, BPM, key. Leave empty to use the genre above.</p>
          </div>

          {/* LoRA strength slider */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-sm">🎯</span>
                <h3 className="text-sm font-semibold text-[#F5F5F5]">LoRA Strength</h3>
              </div>
              <span className="text-xs text-[#9AA0A6]">{Math.round(loraStrength * 100)}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={loraStrength}
              onChange={e => setLoraStrength(parseFloat(e.target.value))}
              className="w-full h-1.5 rounded-full appearance-none outline-none"
              style={{
                background: `linear-gradient(to right, #C6F11D ${loraStrength * 100}%, rgba(255,255,255,0.06) ${loraStrength * 100}%)`,
              }}
            />
            <div className="flex justify-between text-[10px] text-[#5F6772] mt-1">
              <span>Subtle</span>
              <span>Strong</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-5 border-t border-[#252A33]">
          <div className="flex items-center gap-2">
            <RotateCcw className="h-3.5 w-3.5 text-[#FFC845]" />
            <span className="text-[11px] text-[#FFC845]/70">Video will be regenerated</span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="neo-btn-ghost px-4 py-2 text-xs"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="neo-btn-primary px-5 py-2 text-xs flex items-center gap-2"
            >
              {saving ? (
                <>
                  <div className="h-3 w-3 border-2 border-[#050608]/30 border-t-[#050608] rounded-full animate-spin" />
                  Regenerating...
                </>
              ) : (
                'Save & Regenerate'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default EditVideoModal;
