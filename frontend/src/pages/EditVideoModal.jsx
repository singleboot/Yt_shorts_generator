import React, { useState, useRef, useEffect } from 'react';
import { X, Sparkles, RotateCcw, Volume2, Play, Square, Film, Layers, RefreshCw, AlertCircle, CheckCircle, RotateCw as Spinner, Pencil, Eye, EyeOff, Wand2 } from 'lucide-react';
import { AI_STYLES, VOICES, MUSIC_GENRES } from '../constants/production';
import api from '../api/client';

function EditVideoModal({ video, project, onClose, onSave, onSceneRegen, onReassemble }) {
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

  // Tab state
  const [tab, setTab] = useState('settings'); // 'settings' | 'scenes'

  // Scene state
  const [scenes, setScenes] = useState([]);
  const [scenesLoading, setScenesLoading] = useState(false);
  const [sceneRegenStatus, setSceneRegenStatus] = useState({}); // {scene_index: 'regenerating' | 'failed' | 'completed'}
  const [reassembleStatus, setReassembleStatus] = useState(null); // null | 'running' | 'completed' | 'failed'
  const [reassembleMsg, setReassembleMsg] = useState('');
  // Per-scene prompt editor state
  // promptEdits[sceneIndex] = { text, expanded, useCustom, dirty }
  const [promptEdits, setPromptEdits] = useState({});
  const [tweakingAll, setTweakingAll] = useState(false); // global "edit all prompts" mode

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

  // Load scenes when Scenes tab is opened
  useEffect(() => {
    if (tab === 'scenes' && scenes.length === 0) {
      loadScenes();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  // Poll for scene regen / reassemble completion
  useEffect(() => {
    const hasInflight = Object.values(sceneRegenStatus).some(s => s === 'regenerating') || reassembleStatus === 'running';
    if (!hasInflight) return;
    const id = setInterval(async () => {
      try {
        const res = await api.get(`/projects/${project.id}/videos/${video.index}/scenes`);
        const fresh = res.data || [];
        setScenes(fresh);
        // Re-check status by looking for any scene without a clip
        const next = {};
        fresh.forEach(s => { next[s.scene_index] = s.has_clip ? 'completed' : 'regenerating'; });
        setSceneRegenStatus(next);
        if (reassembleStatus === 'running') {
          // Reassemble is synchronous on backend, so if we get here, it's done
          setReassembleStatus('completed');
          setReassembleMsg('Final video rebuilt');
        }
      } catch (e) {
        // Ignore transient errors
      }
    }, 3000);
    return () => clearInterval(id);
  }, [sceneRegenStatus, reassembleStatus, project.id, video.index]);

  const loadScenes = async () => {
    setScenesLoading(true);
    try {
      const res = await api.get(`/projects/${project.id}/videos/${video.index}/scenes`);
      setScenes(res.data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setScenesLoading(false);
    }
  };

  const handleRegenScene = async (sceneIndex, customPrompt = null) => {
    setSceneRegenStatus(prev => ({ ...prev, [sceneIndex]: 'regenerating' }));
    try {
      const params = { seed_offset: 1 };
      if (customPrompt && customPrompt.trim()) {
        params.custom_prompt = customPrompt.trim();
      }
      const res = await api.post(
        `/projects/${project.id}/videos/${video.index}/scenes/${sceneIndex}/regenerate`,
        null,
        { params }
      );
      if (res.data?.status === 'success') {
        setSceneRegenStatus(prev => ({ ...prev, [sceneIndex]: 'completed' }));
        // Mark this scene's edit as no-longer-dirty
        setPromptEdits(prev => {
          const next = { ...prev };
          if (next[sceneIndex]) {
            next[sceneIndex] = { ...next[sceneIndex], dirty: false };
          }
          return next;
        });
        // Reload scene list
        await loadScenes();
        // Notify parent so it can refresh project state
        if (onSceneRegen) onSceneRegen(video.index, sceneIndex);
      } else {
        setSceneRegenStatus(prev => ({ ...prev, [sceneIndex]: 'failed' }));
      }
    } catch (e) {
      setSceneRegenStatus(prev => ({ ...prev, [sceneIndex]: 'failed' }));
      alert('Scene regeneration failed: ' + (e?.response?.data?.detail || e.message));
    }
  };

  const setPromptEdit = (sceneIndex, partial) => {
    setPromptEdits(prev => ({
      ...prev,
      [sceneIndex]: {
        text: partial.text !== undefined ? partial.text : (prev[sceneIndex]?.text ?? ''),
        expanded: partial.expanded !== undefined ? partial.expanded : (prev[sceneIndex]?.expanded ?? false),
        useCustom: partial.useCustom !== undefined ? partial.useCustom : (prev[sceneIndex]?.useCustom ?? false),
        dirty: partial.dirty !== undefined ? partial.dirty : (prev[sceneIndex]?.dirty ?? false),
      },
    }));
  };

  const resetPromptEdit = (sceneIndex, original) => {
    setPromptEdits(prev => ({
      ...prev,
      [sceneIndex]: {
        text: original,
        expanded: prev[sceneIndex]?.expanded ?? false,
        useCustom: false,
        dirty: false,
      },
    }));
  };

  const handleReassemble = async () => {
    setReassembleStatus('running');
    setReassembleMsg('Re-assembling final video...');
    try {
      const res = await api.post(`/projects/${project.id}/videos/${video.index}/reassemble`);
      if (res.data?.status === 'success') {
        setReassembleStatus('completed');
        setReassembleMsg('Final video rebuilt');
        if (onReassemble) onReassemble(video.index);
      } else {
        setReassembleStatus('failed');
        setReassembleMsg(res.data?.message || 'Reassembly failed');
      }
    } catch (e) {
      setReassembleStatus('failed');
      setReassembleMsg(e?.response?.data?.detail || e.message || 'Reassembly failed');
    }
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
            <p className="text-xs text-[#9AA0A6] mt-0.5">{tab === 'settings' ? 'Changing settings will regenerate this video' : 'Regenerate individual scenes without redoing the whole video'}</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-xl hover:bg-[rgba(255,255,255,0.03)] transition-colors">
            <X className="h-4 w-4 text-[#9AA0A6]" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[#252A33] px-5">
          <button
            onClick={() => setTab('settings')}
            className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-semibold border-b-2 transition-colors ${
              tab === 'settings'
                ? 'border-[#C6F11D] text-[#C6F11D]'
                : 'border-transparent text-[#9AA0A6] hover:text-[#F5F5F5]'
            }`}
          >
            <Sparkles className="h-3.5 w-3.5" />
            Settings
          </button>
          <button
            onClick={() => setTab('scenes')}
            className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-semibold border-b-2 transition-colors ${
              tab === 'scenes'
                ? 'border-[#C6F11D] text-[#C6F11D]'
                : 'border-transparent text-[#9AA0A6] hover:text-[#F5F5F5]'
            }`}
          >
            <Film className="h-3.5 w-3.5" />
            Scenes
            {scenes.length > 0 && <span className="text-[10px] text-[#5F6772]">({scenes.length})</span>}
          </button>
        </div>

        {/* SETTINGS TAB */}
        {tab === 'settings' && (
          <>
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
          </>
        )}

        {/* SCENES TAB */}
        {tab === 'scenes' && (
          <div className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-[11px] text-[#9AA0A6]">
                {scenesLoading ? 'Loading scenes…' : `${scenes.length} scenes • Tweak any prompt before regenerating`}
              </p>
              <div className="flex gap-1.5">
                <button
                  onClick={() => {
                    const next = !tweakingAll;
                    setTweakingAll(next);
                    // Expand all editors with their current visual_description as default
                    const updated = { ...promptEdits };
                    scenes.forEach(s => {
                      if (!updated[s.scene_index]) {
                        updated[s.scene_index] = {
                          text: s.visual_description || '',
                          expanded: next,
                          useCustom: false,
                          dirty: false,
                        };
                      } else {
                        updated[s.scene_index] = {
                          ...updated[s.scene_index],
                          expanded: next,
                        };
                      }
                    });
                    setPromptEdits(updated);
                  }}
                  className={`neo-btn-ghost flex items-center gap-1.5 px-2.5 py-1 text-[10px] ${tweakingAll ? 'border-[#C6F11D] text-[#C6F11D]' : ''}`}
                  title={tweakingAll ? 'Hide all prompt editors' : 'Show prompt editor for all scenes'}
                >
                  {tweakingAll ? <EyeOff className="h-3 w-3" /> : <Pencil className="h-3 w-3" />}
                  {tweakingAll ? 'Hide All' : 'Tweak All'}
                </button>
                <button
                  onClick={loadScenes}
                  className="neo-btn-ghost flex items-center gap-1.5 px-2.5 py-1 text-[10px]"
                >
                  <RefreshCw className="h-3 w-3" />
                  Refresh
                </button>
              </div>
            </div>

            {/* Reassemble action bar */}
            {reassembleStatus && (
              <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-[11px] ${
                reassembleStatus === 'running'
                  ? 'bg-[rgba(198,241,29,0.06)] border-[rgba(198,241,29,0.3)] text-[#C6F11D]'
                  : reassembleStatus === 'completed'
                    ? 'bg-[rgba(107,255,100,0.06)] border-[rgba(107,255,100,0.3)] text-[#6BFF64]'
                    : 'bg-[rgba(255,87,87,0.06)] border-[rgba(255,87,87,0.3)] text-[#FF5757]'
              }`}>
                {reassembleStatus === 'running' && <Spinner className="h-3 w-3 animate-spin" />}
                {reassembleStatus === 'completed' && <CheckCircle className="h-3 w-3" />}
                {reassembleStatus === 'failed' && <AlertCircle className="h-3 w-3" />}
                {reassembleMsg}
              </div>
            )}

            <div className="space-y-2 max-h-[50vh] overflow-y-auto pr-1">
              {scenesLoading && (
                <div className="text-center text-[#5F6772] text-xs py-8">
                  <Spinner className="h-6 w-6 mx-auto mb-2 animate-spin text-[#C6F11D]" />
                  Loading scenes…
                </div>
              )}
              {!scenesLoading && scenes.length === 0 && (
                <div className="text-center text-[#5F6772] text-xs py-8">
                  No scenes found. Generate this video first.
                </div>
              )}
              {scenes.map(s => {
                const status = sceneRegenStatus[s.scene_index];
                const isRegenerating = status === 'regenerating';
                const isFailed = status === 'failed';
                const edit = promptEdits[s.scene_index];
                const isTweaking = edit?.expanded || false;
                const effectiveText = edit?.text ?? s.visual_description ?? '';
                const isDirty = edit?.dirty || false;
                return (
                  <div key={s.scene_index} className={`neo-card p-3 ${isRegenerating ? 'border-l-4 border-[#C6F11D]' : isFailed ? 'border-l-4 border-[#FF5757]' : isDirty ? 'border-l-4 border-[#FFC845]' : ''}`}>
                    <div className="flex items-start gap-3">
                      <div className="flex flex-col items-center justify-center w-10 h-10 rounded-lg bg-[#050608] border border-[#252A33] shrink-0">
                        <span className="text-[10px] text-[#5F6772]">SCENE</span>
                        <span className="text-sm font-bold text-[#C6F11D]">{s.scene_number}</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-[11px] text-[#F5F5F5] line-clamp-2 leading-relaxed">
                          "{s.narration}"
                        </p>
                        <div className="flex items-center gap-3 mt-1.5 text-[10px] text-[#5F6772]">
                          <span>{s.duration_seconds?.toFixed(1)}s</span>
                          {s.has_clip ? (
                            <span className="text-[#6BFF64]">● clip ready</span>
                          ) : (
                            <span className="text-[#FFC845]">● no clip</span>
                          )}
                          {s.trigger_words && (
                            <span className="text-[#9AA0A6]">LoRA: {s.lora_name?.split(/[\\/]/).pop() || '—'}</span>
                          )}
                        </div>
                        {isRegenerating && (
                          <div className="mt-2 text-[10px] text-[#C6F11D] flex items-center gap-1.5">
                            <Spinner className="h-3 w-3 animate-spin" />
                            Regenerating scene... (~7 min)
                          </div>
                        )}
                        {isFailed && (
                          <div className="mt-2 text-[10px] text-[#FF5757] flex items-center gap-1.5">
                            <AlertCircle className="h-3 w-3" />
                            Failed
                          </div>
                        )}

                        {/* PROMPT EDITOR (collapsible) */}
                        {isTweaking && (
                          <div className="mt-3 space-y-2 rounded-xl border border-[#252A33] bg-[#0A0C10] p-3">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-1.5 text-[10px] font-semibold text-[#C6F11D]">
                                <Wand2 className="h-3 w-3" />
                                Tweak visual prompt
                              </div>
                              <div className="flex items-center gap-2">
                                {isDirty && (
                                  <span className="text-[9px] text-[#FFC845]">unsaved</span>
                                )}
                                <button
                                  onClick={() => resetPromptEdit(s.scene_index, s.visual_description || '')}
                                  className="text-[10px] text-[#9AA0A6] hover:text-[#F5F5F5] flex items-center gap-1"
                                  title="Reset to original"
                                >
                                  <RotateCcw className="h-3 w-3" /> Reset
                                </button>
                              </div>
                            </div>
                            <textarea
                              value={effectiveText}
                              onChange={e => setPromptEdit(s.scene_index, { text: e.target.value, dirty: e.target.value !== (s.visual_description || '') })}
                              rows={4}
                              className="w-full p-2 rounded-lg bg-[#050608] border border-[#252A33] text-[11px] text-[#F5F5F5] font-mono leading-relaxed outline-none focus:border-[#C6F11D]/50 transition-all resize-none"
                              placeholder="Camera move of subject in setting, doing action, lighting, mood, style triggers..."
                            />
                            {s.trigger_words && (
                              <div className="text-[9px] text-[#5F6772] leading-relaxed">
                                <span className="text-[#C6F11D]">Auto-prepended triggers:</span> {s.trigger_words}
                                <br />
                                <span className="text-[#C6F11D]">Auto-appended suffix:</span> {s.suffix || '25fps, high quality, vertical 9:16...'}
                                <br />
                                <span className="text-[#5F6772]">Your text goes between the triggers and suffix.</span>
                              </div>
                            )}
                            {s.final_prompt && (
                              <details className="text-[9px] text-[#5F6772]">
                                <summary className="cursor-pointer hover:text-[#9AA0A6]">Last sent to ComfyUI ({(s.final_prompt || '').length} chars)</summary>
                                <div className="mt-1 p-2 bg-[#050608] rounded-lg font-mono leading-relaxed break-words whitespace-pre-wrap">
                                  {s.final_prompt}
                                </div>
                              </details>
                            )}
                          </div>
                        )}
                      </div>
                      <div className="flex flex-col gap-1.5 shrink-0">
                        <button
                          onClick={() => setPromptEdit(s.scene_index, { expanded: !isTweaking })}
                          className={`neo-btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 text-[10px] ${isTweaking ? 'border-[#C6F11D] text-[#C6F11D]' : ''}`}
                          title="Tweak visual prompt"
                        >
                          {isTweaking ? <EyeOff className="h-3 w-3" /> : <Pencil className="h-3 w-3" />}
                          {isTweaking ? 'Hide' : 'Tweak'}
                        </button>
                        <button
                          onClick={() => handleRegenScene(s.scene_index, isTweaking && isDirty ? effectiveText : null)}
                          disabled={isRegenerating}
                          className="neo-btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 text-[10px] disabled:opacity-50"
                          title={isDirty ? 'Regenerate with tweaked prompt' : 'Regenerate with new seed'}
                        >
                          {isRegenerating ? (
                            <Spinner className="h-3 w-3 animate-spin" />
                          ) : (
                            <RefreshCw className="h-3 w-3" />
                          )}
                          {isDirty ? 'Tweak & Regen' : 'Regenerate'}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Footer for scenes tab */}
            <div className="flex items-center justify-between p-3 -mx-5 -mb-5 border-t border-[#252A33] bg-[#0A0C10]">
              <div className="flex items-center gap-2 text-[11px] text-[#9AA0A6]">
                <Layers className="h-3.5 w-3.5" />
                <span>After regenerating scenes, click below to rebuild the final video</span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={onClose}
                  className="neo-btn-ghost px-3 py-1.5 text-xs"
                >
                  Close
                </button>
                <button
                  onClick={handleReassemble}
                  disabled={reassembleStatus === 'running'}
                  className="neo-btn-primary px-4 py-1.5 text-xs flex items-center gap-2"
                >
                  {reassembleStatus === 'running' ? (
                    <>
                      <Spinner className="h-3 w-3 animate-spin" />
                      Re-assembling...
                    </>
                  ) : (
                    <>
                      <Layers className="h-3 w-3" />
                      Re-assemble Final
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default EditVideoModal;
