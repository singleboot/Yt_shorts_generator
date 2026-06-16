import React, { useState, useRef, useEffect } from 'react';
import { X, Sparkles, RotateCcw, Volume2, Play, Square, Film, Layers, RefreshCw, AlertCircle, CheckCircle, RotateCw as Spinner, Pencil, Eye, EyeOff, Wand2, Youtube, Calendar, Globe } from 'lucide-react';
import { AI_STYLES, VOICES, MUSIC_GENRES, CAPTION_PRESETS } from '../constants/production';

import api from '../api/client';

function EditVideoModal({ video, project, onClose, onSave, onSceneRegen, onReassemble }) {
  const vs = project.visual_settings || {};
  const [selectedStyle, setSelectedStyle] = useState(video.overrides?.ai_style || vs.ai_style || 'none');
  const [selectedVoice, setSelectedVoice] = useState(video.overrides?.voice_id || vs.voice_id || 'kokoro-am_adam');
  const [selectedMusic, setSelectedMusic] = useState(video.overrides?.music_genre || vs.music_genre || 'none');
  const [musicPrompt, setMusicPrompt] = useState(video.overrides?.music_prompt || '');
  const [voiceCustom, setVoiceCustom] = useState(video.overrides?.voice_custom || '');
  const [loraStrength, setLoraStrength] = useState(video.overrides?.lora_strength || vs.lora_strength || 0.6);
  const [saving, setSaving] = useState(false);
  const audioRef = useRef(null);
  const [previewPlaying, setPreviewPlaying] = useState(null);

  // Tab state
  const [tab, setTab] = useState('settings'); // 'settings' | 'scenes' | 'seo' | 'captions'

  // Caption Styling states
  const cs = project.caption_settings || {};
  const [captionStyle, setCaptionStyle] = useState(cs.style || 'standard');
  const [captionFont, setCaptionFont] = useState(cs.font || 'Impact');
  const [captionFontSize, setCaptionFontSize] = useState(cs.font_size || 96);
  const [captionColor, setCaptionColor] = useState(cs.color || '#FFE600');
  const [captionStrokeColor, setCaptionStrokeColor] = useState(cs.stroke_color || '#000000');
  const [captionStrokeWidth, setCaptionStrokeWidth] = useState(cs.stroke_width || 4);
  const [captionAnimation, setCaptionAnimation] = useState(cs.animation || 'pop');
  const [captionPosition, setCaptionPosition] = useState(cs.position || 'middle');
  const [captionAllCaps, setCaptionAllCaps] = useState(cs.all_caps || false);
  const [captionBoxed, setCaptionBoxed] = useState(cs.boxed || false);
  const [captionBoxColor, setCaptionBoxColor] = useState(cs.box_color || '#000000');
  const [captionBoxOpacity, setCaptionBoxOpacity] = useState(cs.box_opacity ?? 0.8);
  const [captionBoxShape, setCaptionBoxShape] = useState(cs.box_shape || 'rectangle');
  const [savingCaptions, setSavingCaptions] = useState(false);

  const [customPresets, setCustomPresets] = useState(() => {
    try {
      const saved = localStorage.getItem('custom_caption_presets');
      return saved ? JSON.parse(saved) : [];
    } catch (e) {
      console.error(e);
      return [];
    }
  });

  const handleSaveCustomPreset = () => {
    const name = window.prompt("Enter a name for your custom caption preset:", "My Preset");
    if (!name || !name.trim()) return;

    const newPreset = {
      id: 'custom_' + Date.now(),
      name: name.trim(),
      font: captionFont,
      style: captionStyle,
      color: captionColor,
      strokeColor: captionStrokeColor,
      strokeWidth: captionStrokeWidth,
      size: captionFontSize,
      animation: captionAnimation,
      allCaps: captionAllCaps,
      boxed: captionBoxed,
      boxColor: captionBoxColor,
      boxOpacity: captionBoxOpacity,
      boxShape: captionBoxShape,
      isCustom: true
    };

    const updated = [...customPresets, newPreset];
    setCustomPresets(updated);
    localStorage.setItem('custom_caption_presets', JSON.stringify(updated));
  };

  const handleDeleteCustomPreset = (id, e) => {
    e.stopPropagation();
    if (!window.confirm("Delete this custom preset?")) return;
    const updated = customPresets.filter(p => p.id !== id);
    setCustomPresets(updated);
    localStorage.setItem('custom_caption_presets', JSON.stringify(updated));
  };

  // SEO & Upload state
  const [uploadRecord, setUploadRecord] = useState(video.upload || null);
  const [seoTitle, setSeoTitle] = useState('');
  const [seoDescription, setSeoDescription] = useState('');
  const [seoTags, setSeoTags] = useState('');
  const [scheduledFor, setScheduledFor] = useState('');
  const [seoLoading, setSeoLoading] = useState(false);
  const [seoSaving, setSeoSaving] = useState(false);
  const [uploadingNow, setUploadingNow] = useState(false);
  const [regeneratingSeo, setRegeneratingSeo] = useState(false);
  const [seoMsg, setSeoMsg] = useState({ type: '', text: '' });

  useEffect(() => {
    if (tab === 'seo') {
      loadUploadDetails();
    }
  }, [tab, video.upload?.id]);

  const loadUploadDetails = async () => {
    const uploadId = uploadRecord?.id || video.upload?.id;
    if (!uploadId) return;
    setSeoLoading(true);
    try {
      const res = await api.get(`/uploads/${uploadId}`);
      if (res.data) {
        setUploadRecord(res.data);
        setSeoTitle(res.data.title || '');
        setSeoDescription(res.data.description || '');
        setSeoTags(res.data.tags || '');
        
        if (res.data.scheduled_for) {
          const date = new Date(res.data.scheduled_for);
          const tzOffset = date.getTimezoneOffset() * 60000;
          const localISOTime = new Date(date.getTime() - tzOffset).toISOString().slice(0, 16);
          setScheduledFor(localISOTime);
        } else {
          setScheduledFor('');
        }
      }
    } catch (e) {
      console.error("Failed to load upload record:", e);
      setSeoMsg({ type: 'error', text: 'Failed to load SEO metadata' });
    } finally {
      setSeoLoading(false);
    }
  };

  const handleCreateUploadDraft = async () => {
    setSeoLoading(true);
    setSeoMsg({ type: 'info', text: 'Generating draft SEO metadata...' });
    try {
      const res = await api.post(`/projects/${project.id}/videos/${video.index}/upload`, null, {
        params: { auto_queue: false }
      });
      if (res.data?.upload_id) {
        setSeoMsg({ type: 'success', text: 'SEO Draft Created successfully!' });
        setUploadRecord({ id: res.data.upload_id });
        setTimeout(() => {
          loadUploadDetails();
        }, 100);
      } else {
        setSeoMsg({ type: 'error', text: res.data?.message || 'Failed to create SEO draft' });
      }
    } catch (e) {
      setSeoMsg({ type: 'error', text: e?.response?.data?.detail || e.message || 'Draft creation failed' });
    } finally {
      setSeoLoading(false);
    }
  };

  const handleSaveSeo = async () => {
    const uploadId = uploadRecord?.id || video.upload?.id;
    if (!uploadId) return;
    setSeoSaving(true);
    setSeoMsg({ type: '', text: '' });
    try {
      const payload = {
        title: seoTitle.trim(),
        description: seoDescription.trim(),
        tags: seoTags.trim(),
        scheduled_for: scheduledFor ? new Date(scheduledFor).toISOString() : null
      };
      const res = await api.put(`/uploads/${uploadId}/schedule`, payload);
      if (res.data?.status === 'updated') {
        setSeoMsg({ type: 'success', text: 'SEO settings saved!' });
        loadUploadDetails();
      } else {
        setSeoMsg({ type: 'error', text: 'Failed to update schedule/metadata' });
      }
    } catch (e) {
      setSeoMsg({ type: 'error', text: e?.response?.data?.detail || e.message || 'Failed to save SEO' });
    } finally {
      setSeoSaving(false);
    }
  };

  const handleRegenSeo = async () => {
    const scriptId = video.script?.id;
    if (!scriptId) {
      alert("No script ID found for this video. Generate script first.");
      return;
    }
    setRegeneratingSeo(true);
    setSeoMsg({ type: 'info', text: 'Regenerating SEO using AI...' });
    try {
      const res = await api.post(`/scripts/${scriptId}/seo`);
      if (res.data?.status === 'success' && res.data.seo) {
        const newSeo = res.data.seo;
        setSeoTitle(newSeo.title || '');
        setSeoDescription(newSeo.description || '');
        setSeoTags(newSeo.hashtags ? newSeo.hashtags.join(', ') : '');
        setSeoMsg({ type: 'success', text: 'Regenerated fresh SEO! Review and click Save.' });
      } else {
        setSeoMsg({ type: 'error', text: 'Failed to generate SEO metadata' });
      }
    } catch (e) {
      setSeoMsg({ type: 'error', text: e?.response?.data?.detail || e.message || 'AI generation failed' });
    } finally {
      setRegeneratingSeo(false);
    }
  };

  const handleUploadNow = async () => {
    const uploadId = uploadRecord?.id || video.upload?.id;
    if (!uploadId) return;
    if (!window.confirm("Are you sure you want to upload this video to YouTube immediately?")) return;
    setUploadingNow(true);
    setSeoMsg({ type: 'info', text: 'Uploading to YouTube... please wait, this may take a moment.' });
    try {
      const res = await api.post(`/uploads/${uploadId}/now`);
      if (res.data?.status === 'success') {
        setSeoMsg({ type: 'success', text: `Successfully uploaded! YouTube ID: ${res.data.video_id}` });
        loadUploadDetails();
      } else {
        setSeoMsg({ type: 'error', text: res.data?.message || 'Upload failed' });
      }
    } catch (e) {
      setSeoMsg({ type: 'error', text: e?.response?.data?.detail || e.message || 'Upload failed' });
    } finally {
      setUploadingNow(false);
    }
  };

  // Scene state
  const [scenes, setScenes] = useState([]);
  const [scenesLoading, setScenesLoading] = useState(false);
  const [sceneRegenStatus, setSceneRegenStatus] = useState({}); // {scene_index: 'regenerating' | 'failed' | 'completed'}
  const [reassembleStatus, setReassembleStatus] = useState(null); // null | 'running' | 'completed' | 'failed'
  const [reassembleMsg, setReassembleMsg] = useState('');
  const [promptEdits, setPromptEdits] = useState({});
  const [tweakingAll, setTweakingAll] = useState(false);
  const [regenTimestamp, setRegenTimestamp] = useState(Date.now());

  const togglePreview = (type, id) => {
    const key = `${type}:${id}`;
    if (previewPlaying === key) {
      if (audioRef.current) { audioRef.current.pause(); audioRef.current.currentTime = 0; }
      setPreviewPlaying(null);
      return;
    }
    const BASE = '';
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
        
        setSceneRegenStatus(prev => {
          const next = { ...prev };
          fresh.forEach(s => {
            // Only update active in-flight or status matches
            if (next[s.scene_index] === 'regenerating') {
              if (s.has_clip) {
                next[s.scene_index] = 'completed';
              }
            } else if (!next[s.scene_index]) {
              next[s.scene_index] = s.has_clip ? 'completed' : 'idle';
            }
          });
          return next;
        });

        if (reassembleStatus === 'running') {
          // If we had a running reassemble, we'll check logic elsewhere or complete it
        }
      } catch (e) {
        // Ignore
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
  const [regenQueue, setRegenQueue] = useState([]);
  const [activeRegen, setActiveRegen] = useState(null);

  // Process the queue serially
  useEffect(() => {
    if (regenQueue.length > 0 && activeRegen === null) {
      const nextJob = regenQueue[0];
      setActiveRegen(nextJob);
      setRegenQueue(prev => prev.slice(1));
      processRegen(nextJob);
    }
  }, [regenQueue, activeRegen]);

  const processRegen = async ({ sceneIndex, customPrompt }) => {
    setSceneRegenStatus(prev => ({ ...prev, [sceneIndex]: 'regenerating' }));
    
    // Auto-save edits if dirty
    const edit = promptEdits[sceneIndex];
    if (edit && edit.dirty) {
      console.log('[Regen] Unsaved edits detected. Automatically saving scene edits first...');
      try {
        const payload = {
          visual_description: edit.text,
          narration: edit.narration
        };
        const saveRes = await api.put(`/projects/${project.id}/videos/${video.index}/scenes/${sceneIndex}`, payload);
        if (saveRes.data?.status === 'success') {
          setScenes(prev => prev.map(s => s.scene_index === sceneIndex ? {
            ...s,
            visual_description: edit.text,
            narration: edit.narration,
            has_clip: s.has_clip
          } : s));
          setPromptEdit(sceneIndex, { dirty: false });
        }
      } catch (e) {
        console.error("Failed to save edits before regen", e);
      }
    }

    try {
      const params = { seed_offset: 1 };
      if (customPrompt && customPrompt.trim()) {
        params.custom_prompt = customPrompt.trim();
      }
      
      // We use a very long timeout (e.g. 15 mins) for the Axios request to prevent dropping the connection
      const res = await api.post(
        `/projects/${project.id}/videos/${video.index}/scenes/${sceneIndex}/regenerate`,
        null,
        { params, timeout: 900000 }
      );
      
      if (res.data?.status === 'success') {
        setSceneRegenStatus(prev => ({ ...prev, [sceneIndex]: 'completed' }));
        setRegenTimestamp(Date.now());
        setPromptEdits(prev => {
          const next = { ...prev };
          if (next[sceneIndex]) {
            next[sceneIndex] = { ...next[sceneIndex], dirty: false };
          }
          return next;
        });
        await loadScenes();
        if (onSceneRegen) onSceneRegen(video.index, sceneIndex);
      } else {
        setSceneRegenStatus(prev => ({ ...prev, [sceneIndex]: 'failed' }));
      }
    } catch (e) {
      console.error(e);
      // Fallback: the connection might have timed out, but ComfyUI might still be working.
      setSceneRegenStatus(prev => ({ ...prev, [sceneIndex]: 'failed' }));
      alert('Scene regeneration encountered an error or timed out: ' + (e?.response?.data?.detail || e.message) + '\n\nIf it timed out, ComfyUI may still be generating it in the background.');
    } finally {
      setActiveRegen(null);
    }
  };

  const handleRegenScene = (sceneIndex, customPrompt = null) => {
    // Add to queue instead of processing immediately
    setRegenQueue(prev => [...prev, { sceneIndex, customPrompt }]);
    setSceneRegenStatus(prev => ({ ...prev, [sceneIndex]: 'queued' }));
  };

  const setPromptEdit = (sceneIndex, partial) => {
    setPromptEdits(prev => {
      const current = prev[sceneIndex] || {};
      const newText = partial.text !== undefined ? partial.text : (current.text ?? '');
      const newNarration = partial.narration !== undefined ? partial.narration : (current.narration ?? '');
      const isDirty = partial.dirty !== undefined ? partial.dirty : (partial.text !== undefined || partial.narration !== undefined);
      return {
        ...prev,
        [sceneIndex]: {
          text: newText,
          narration: newNarration,
          expanded: partial.expanded !== undefined ? partial.expanded : (current.expanded ?? false),
          useCustom: partial.useCustom !== undefined ? partial.useCustom : (current.useCustom ?? false),
          dirty: isDirty,
        }
      };
    });
  };

  const resetPromptEdit = (sceneIndex, original, originalNarration) => {
    setPromptEdits(prev => ({
      ...prev,
      [sceneIndex]: {
        text: original,
        narration: originalNarration,
        expanded: prev[sceneIndex]?.expanded ?? false,
        useCustom: false,
        dirty: false,
      },
    }));
  };

  const handleSaveSceneEdits = async (sceneIndex) => {
    const edit = promptEdits[sceneIndex];
    if (!edit) return;
    try {
      const payload = {
        visual_description: edit.text,
        narration: edit.narration
      };
      const res = await api.put(`/projects/${project.id}/videos/${video.index}/scenes/${sceneIndex}`, payload);
      if (res.data?.status === 'success') {
        setScenes(prev => prev.map(s => s.scene_index === sceneIndex ? {
          ...s,
          visual_description: edit.text,
          narration: edit.narration,
          has_clip: s.has_clip
        } : s));
        setPromptEdit(sceneIndex, { dirty: false });
        alert('Scene updates saved! Stale voiceovers have been cleared. Click "Re-assemble Final" below to rebuild the video.');
      }
    } catch (e) {
      alert('Failed to save scene changes: ' + (e?.response?.data?.detail || e.message));
    }
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

  const handleSaveCaptionsAndReassemble = async () => {
    setSavingCaptions(true);
    setReassembleStatus('running');
    setReassembleMsg('Saving caption style and re-assembling video...');
    try {
      const payload = {
        caption_settings: {
          style: captionStyle,
          font: captionFont,
          font_size: captionFontSize,
          color: captionColor,
          stroke_color: captionStrokeColor,
          stroke_width: captionStrokeWidth,
          animation: captionAnimation,
          position: captionPosition,
          all_caps: captionAllCaps,
          boxed: captionBoxed,
          box_color: captionBoxColor,
          box_opacity: captionBoxOpacity,
          box_shape: captionBoxShape,
        }
      };
      await api.put(`/projects/${project.id}`, payload);
      const res = await api.post(`/projects/${project.id}/videos/${video.index}/reassemble`);
      if (res.data?.status === 'success') {
        setReassembleStatus('completed');
        setReassembleMsg('Video successfully re-assembled with new captions!');
        if (onReassemble) onReassemble(video.index);
      } else {
        setReassembleStatus('failed');
        setReassembleMsg(res.data?.message || 'Reassembly failed');
      }
    } catch (e) {
      setReassembleStatus('failed');
      setReassembleMsg(e?.response?.data?.detail || e.message || 'Reassembly failed');
    } finally {
      setSavingCaptions(false);
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
        className="neo-card w-full max-w-5xl max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-[#252A33]">
          <div>
            <h2 className="text-xl font-bold text-[#F5F5F5]">Edit Video {video.index + 1}</h2>
            <p className="text-sm text-[#9AA0A6] mt-1">{tab === 'settings' ? 'Changing settings will regenerate this video' : tab === 'scenes' ? 'Regenerate individual scenes without redoing the whole video' : 'Configure YouTube titles, descriptions, and schedule settings'}</p>
          </div>
          <button onClick={onClose} className="p-2.5 rounded-xl hover:bg-[rgba(255,255,255,0.03)] transition-colors">
            <X className="h-5 w-5 text-[#9AA0A6]" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[#252A33] px-6">
          <button
            onClick={() => setTab('settings')}
            className={`flex items-center gap-2 px-4 py-3.5 text-[14.5px] font-semibold border-b-2 transition-colors ${
              tab === 'settings'
                ? 'border-[#C6F11D] text-[#C6F11D]'
                : 'border-transparent text-[#9AA0A6] hover:text-[#F5F5F5]'
            }`}
          >
            <Sparkles className="h-4.5 w-4.5" />
            Settings
          </button>
          <button
            onClick={() => setTab('scenes')}
            className={`flex items-center gap-2 px-4 py-3.5 text-[14.5px] font-semibold border-b-2 transition-colors ${
              tab === 'scenes'
                ? 'border-[#C6F11D] text-[#C6F11D]'
                : 'border-transparent text-[#9AA0A6] hover:text-[#F5F5F5]'
            }`}
          >
            <Film className="h-4.5 w-4.5" />
            Scenes
            {scenes.length > 0 && <span className="text-[12px] text-[#5F6772]">({scenes.length})</span>}
          </button>
          <button
            onClick={() => setTab('seo')}
            className={`flex items-center gap-2 px-4 py-3.5 text-[14.5px] font-semibold border-b-2 transition-colors ${
              tab === 'seo'
                ? 'border-[#C6F11D] text-[#C6F11D]'
                : 'border-transparent text-[#9AA0A6] hover:text-[#F5F5F5]'
            }`}
          >
            <Youtube className="h-4.5 w-4.5" />
            SEO & Upload
          </button>
          <button
            onClick={() => setTab('captions')}
            className={`flex items-center gap-2 px-4 py-3.5 text-[14.5px] font-semibold border-b-2 transition-colors ${
              tab === 'captions'
                ? 'border-[#C6F11D] text-[#C6F11D]'
                : 'border-transparent text-[#9AA0A6] hover:text-[#F5F5F5]'
            }`}
          >
            <Layers className="h-4.5 w-4.5" />
            Captions
          </button>
        </div>

        {/* CAPTIONS TAB */}
        {tab === 'captions' && (
          <div className="p-6 space-y-4 text-[16px]">
            {/* Presets Row */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-[16px] font-semibold text-[#F5F5F5]">Presets</h3>
                <button
                  type="button"
                  onClick={handleSaveCustomPreset}
                  className="flex items-center gap-1.5 px-2.5 py-1 text-[12px] font-semibold bg-[#252A33] hover:bg-[#343b47] text-[#F5F5F5] rounded border border-[#343b47] transition-all"
                >
                  <Sparkles className="h-3.5 w-3.5 text-[#C6F11D]" />
                  Save as Preset
                </button>
              </div>
              <div className="grid grid-cols-9 gap-1.5">
                {[
                  ...CAPTION_PRESETS,
                  ...customPresets.map(cp => {
                    const isBoxed = cp.style === 'boxed' || cp.boxed;
                    let bgStyleColor = 'rgba(0,0,0,0.8)';
                    if (cp.boxColor) {
                      const hex = cp.boxColor.replace('#', '');
                      const r = parseInt(hex.substring(0, 2), 16) || 0;
                      const g = parseInt(hex.substring(2, 4), 16) || 0;
                      const b = parseInt(hex.substring(4, 6), 16) || 0;
                      bgStyleColor = `rgba(${r}, ${g}, ${b}, ${cp.boxOpacity ?? 0.8})`;
                    }

                    return {
                      ...cp,
                      bgPreview: isBoxed ? '' : 'bg-[#0E1116]',
                      bgStyle: isBoxed ? { backgroundColor: bgStyleColor } : {},
                      textStyle: {
                        fontFamily: cp.font.replace(/-/g, ' '),
                        color: cp.color,
                        fontSize: '10.5px',
                        fontWeight: 'bold',
                        textShadow: cp.strokeWidth > 0 
                          ? `-1px -1px 0 ${cp.strokeColor}, 1px -1px 0 ${cp.strokeColor}, -1px 1px 0 ${cp.strokeColor}, 1px 1px 0 ${cp.strokeColor}` 
                          : 'none',
                        borderRadius: cp.boxShape === 'underline' ? '0px' : '3px',
                        borderBottom: cp.boxShape === 'underline' ? `2px solid ${cp.color}` : 'none',
                        padding: isBoxed && cp.boxShape !== 'underline' ? '1px 3px' : '0px'
                      },
                      textLabel: cp.name.substring(0, 7)
                    };
                  })
                ].map(preset => {
                  const isSelected = captionStyle === preset.style &&
                                     captionFont === preset.font &&
                                     captionColor === preset.color &&
                                     captionStrokeColor === preset.strokeColor &&
                                     captionStrokeWidth === preset.strokeWidth &&
                                     captionFontSize === preset.size &&
                                     captionAnimation === preset.animation &&
                                     captionAllCaps === (preset.allCaps ?? false) &&
                                     captionBoxed === (preset.boxed ?? (preset.style === 'boxed'));

                  return (
                    <button
                      type="button"
                      key={preset.id}
                      onClick={() => {
                        setCaptionStyle(preset.style);
                        setCaptionFont(preset.font);
                        setCaptionColor(preset.color);
                        setCaptionStrokeColor(preset.strokeColor);
                        setCaptionStrokeWidth(preset.strokeWidth);
                        setCaptionFontSize(preset.size);
                        setCaptionAnimation(preset.animation);
                        setCaptionAllCaps(preset.allCaps ?? false);
                        setCaptionBoxed(preset.boxed ?? (preset.style === 'boxed'));
                        setCaptionBoxColor(preset.boxColor || '#000000');
                        setCaptionBoxOpacity(preset.boxOpacity ?? 0.8);
                        setCaptionBoxShape(preset.boxShape || 'rectangle');
                      }}
                      className={`group relative flex flex-col items-center p-1 rounded border transition-all duration-200 text-center w-full ${
                        isSelected 
                          ? 'border-[#C6F11D] bg-[#C6F11D]/5' 
                          : 'border-[#252A33] hover:border-[#9AA0A6]/30 bg-transparent'
                      }`}
                    >
                      {preset.isCustom && (
                        <button
                          type="button"
                          onClick={(e) => handleDeleteCustomPreset(preset.id, e)}
                          className="absolute -top-1 -right-1 bg-red-600 hover:bg-red-700 text-white rounded-full p-0.5 z-10 hidden group-hover:block transition-all"
                        >
                          <X className="h-2.5 w-2.5" />
                        </button>
                      )}
                      
                      <div 
                        style={preset.bgStyle || {}} 
                        className={`w-full h-8 rounded flex items-center justify-center mb-0.5 border border-[#252A33]/55 ${preset.bgPreview}`}
                      >
                        <span style={preset.textStyle}>
                          {preset.textLabel}
                        </span>
                      </div>
                      <span className="text-[11.5px] font-semibold truncate w-full text-[#F5F5F5]">
                        {preset.name}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Customize Section */}
            <div className="p-4 rounded-xl bg-[#0E1116] border border-[#252A33] space-y-4">
              {/* Dropdowns Row (Style, Animation, Font) */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-[13px] text-[#9AA0A6] block mb-1.5 font-bold uppercase tracking-wider">STYLE</label>
                  <select
                    value={captionStyle}
                    onChange={(e) => {
                      setCaptionStyle(e.target.value);
                      if (e.target.value === 'boxed') setCaptionBoxed(true);
                    }}
                    className="w-full px-3 py-2 rounded bg-[#050608] border border-[#252A33] text-[15px] text-[#F5F5F5] outline-none"
                  >
                    <option value="standard">Standard</option>
                    <option value="bold">Bold</option>
                    <option value="minimal">Minimal</option>
                    <option value="boxed">Boxed</option>
                    <option value="karaoke">Karaoke</option>
                    <option value="none">None (No Subtitles)</option>
                  </select>
                </div>

                <div>
                  <label className="text-[13px] text-[#9AA0A6] block mb-1.5 font-bold uppercase tracking-wider">ANIMATION</label>
                  <select
                    value={captionAnimation}
                    onChange={(e) => setCaptionAnimation(e.target.value)}
                    className="w-full px-3 py-2 rounded bg-[#050608] border border-[#252A33] text-[15px] text-[#F5F5F5] outline-none"
                  >
                    <option value="none">None</option>
                    <option value="word_by_word">Word</option>
                    <option value="fade">Fade</option>
                    <option value="pop">Pop</option>
                    <option value="typewriter">Typewriter</option>
                  </select>
                </div>

                <div>
                  <label className="text-[13px] text-[#9AA0A6] block mb-1.5 font-bold uppercase tracking-wider">FONT FAMILY</label>
                  <select
                    value={captionFont}
                    onChange={e => setCaptionFont(e.target.value)}
                    className="w-full px-3 py-2 rounded bg-[#050608] border border-[#252A33] text-[15px] text-[#F5F5F5] outline-none"
                  >
                    {['Arial-Bold','Arial','Impact','Helvetica-Bold','Verdana-Bold','Trebuchet-MS','Comic-Sans-MS','Courier-New-Bold','Times-New-Roman-Bold','Georgia-Bold'].map(f => (
                      <option key={f} value={f} className="bg-[#0E1116] text-[#F5F5F5]">{f}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Slider & Width / Stroke Controls */}
              <div className="grid grid-cols-3 gap-3 items-center text-[15.5px]">
                <div>
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-[#9AA0A6] text-[13px] font-bold uppercase tracking-wider">SIZE</span>
                    <input
                      type="number"
                      min="10"
                      max="300"
                      value={captionFontSize}
                      onChange={(e) => {
                        const val = parseInt(e.target.value);
                        setCaptionFontSize(isNaN(val) ? 0 : val);
                      }}
                      onBlur={(e) => {
                        const val = Math.max(10, Math.min(300, parseInt(e.target.value) || 96));
                        setCaptionFontSize(val);
                      }}
                      className="w-14 px-2 py-1 bg-[#050608] border border-[#252A33] rounded text-[13px] text-[#F5F5F5] outline-none"
                    />
                  </div>
                  <input
                    type="range" min="10" max="300" step="1"
                    value={captionFontSize}
                    onChange={(e) => setCaptionFontSize(parseInt(e.target.value))}
                    className="w-full accent-[#C6F11D] h-1.5"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-[#9AA0A6] text-[13px] font-bold uppercase tracking-wider">STROKE ({captionStrokeWidth}px)</span>
                  </div>
                  <input
                    type="range" min="0" max="8" step="1"
                    value={captionStrokeWidth}
                    onChange={(e) => setCaptionStrokeWidth(parseInt(e.target.value))}
                    className="w-full accent-[#C6F11D] h-1.5"
                  />
                </div>

                <div>
                  <span className="text-[#9AA0A6] text-[13px] block mb-0.5 font-bold uppercase tracking-wider">ALIGN</span>
                  <select
                    value={captionPosition}
                    onChange={e => setCaptionPosition(e.target.value)}
                    className="w-full px-3 py-2 rounded bg-[#050608] border border-[#252A33] text-[15px] text-[#F5F5F5] outline-none"
                  >
                    <option value="top">Top</option>
                    <option value="middle">Middle</option>
                    <option value="bottom">Bottom</option>
                  </select>
                </div>
              </div>

              {/* Combined Color Pickers Row - ALL IN ONE LINE, CAPS labels, 20% larger pickers & text */}
              <div className="flex items-center gap-6 py-2.5 border-t border-[#252A33]/50 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className="text-[15px] text-[#9AA0A6] font-bold tracking-wider">TEXT:</span>
                  <input
                    type="color"
                    value={captionColor}
                    onChange={(e) => setCaptionColor(e.target.value)}
                    className="w-[32px] h-[32px] rounded cursor-pointer border border-[#252A33] p-0 bg-transparent overflow-hidden"
                  />
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[15px] text-[#9AA0A6] font-bold tracking-wider">STROKE:</span>
                  <input
                    type="color"
                    value={captionStrokeColor}
                    onChange={(e) => setCaptionStrokeColor(e.target.value)}
                    className="w-[32px] h-[32px] rounded cursor-pointer border border-[#252A33] p-0 bg-transparent overflow-hidden"
                  />
                </div>

                {captionBoxed && (
                  <div className="flex items-center gap-2 animate-fadeIn">
                    <span className="text-[15px] text-[#9AA0A6] font-bold tracking-wider">BOX:</span>
                    <input
                      type="color"
                      value={captionBoxColor}
                      onChange={(e) => setCaptionBoxColor(e.target.value)}
                      className="w-[32px] h-[32px] rounded cursor-pointer border border-[#252A33] p-0 bg-transparent overflow-hidden"
                    />
                  </div>
                )}

                {captionBoxed && (
                  <div className="flex flex-1 items-center gap-2 min-w-0 max-w-[175px]">
                    <span className="text-[15px] text-[#9AA0A6] font-bold tracking-wider shrink-0">OPACITY:</span>
                    <input
                      type="range" min="0.1" max="1.0" step="0.05"
                      value={captionBoxOpacity}
                      onChange={(e) => setCaptionBoxOpacity(parseFloat(e.target.value))}
                      className="w-full accent-[#C6F11D] h-1.5"
                    />
                  </div>
                )}
              </div>

              {/* Toggles, Alignment, Box Shape (Inline Row) - 20% larger checkboxes & text */}
              <div className="flex items-center justify-between gap-6 pt-2.5 border-t border-[#252A33]/50 flex-wrap">
                <div className="flex items-center gap-6">
                  {/* All Caps Checkbox */}
                  <label className="flex items-center gap-2.5 cursor-pointer text-[15.5px] font-bold text-[#9AA0A6] hover:text-[#F5F5F5] select-none">
                    <input
                      type="checkbox"
                      checked={captionAllCaps}
                      onChange={(e) => setCaptionAllCaps(e.target.checked)}
                      className="w-6 h-6 rounded border-[#252A33] bg-[#050608] text-[#C6F11D] accent-[#C6F11D] cursor-pointer"
                    />
                    ALL CAPS
                  </label>

                  {/* Boxed Checkbox */}
                  <label className="flex items-center gap-2.5 cursor-pointer text-[15.5px] font-bold text-[#9AA0A6] hover:text-[#F5F5F5] select-none">
                    <input
                      type="checkbox"
                      checked={captionBoxed}
                      onChange={(e) => {
                        setCaptionBoxed(e.target.checked);
                        if (e.target.checked) {
                          setCaptionStyle('boxed');
                        } else if (captionStyle === 'boxed') {
                          setCaptionStyle('standard');
                        }
                      }}
                      className="w-6 h-6 rounded border-[#252A33] bg-[#050608] text-[#C6F11D] accent-[#C6F11D] cursor-pointer"
                    />
                    BOXED
                  </label>
                </div>

                <div className="flex items-center gap-3">
                  {/* Box Shape */}
                  {captionBoxed && (
                    <div className="flex items-center gap-1.5">
                      <span className="text-[13px] text-[#9AA0A6] font-bold uppercase tracking-wider">SHAPE:</span>
                      <select
                        value={captionBoxShape}
                        onChange={e => setCaptionBoxShape(e.target.value)}
                        className="px-2.5 py-1.5 rounded bg-[#050608] border border-[#252A33] text-[14px] text-[#F5F5F5] outline-none"
                      >
                        <option value="rectangle">Rectangle</option>
                        <option value="underline">Underline</option>
                      </select>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Reassemble Status Feedback */}
            {reassembleStatus && (
              <div className={`p-2 rounded border text-[14px] flex items-center gap-2.5 ${
                reassembleStatus === 'completed'
                  ? 'bg-[rgba(107,255,100,0.06)] border-[rgba(107,255,100,0.3)] text-[#6BFF64]'
                  : reassembleStatus === 'failed'
                    ? 'bg-[rgba(255,87,87,0.06)] border-[rgba(255,87,87,0.3)] text-[#FF5757]'
                    : 'bg-[rgba(198,241,29,0.06)] border-[rgba(198,241,29,0.3)] text-[#C6F11D]'
              }`}>
                {reassembleStatus === 'completed' && <CheckCircle className="h-4 w-4" />}
                {reassembleStatus === 'failed' && <AlertCircle className="h-4 w-4" />}
                {reassembleStatus === 'running' && <Spinner className="h-4 w-4 animate-spin" />}
                <span>{reassembleMsg}</span>
              </div>
            )}

            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={handleSaveCaptionsAndReassemble}
                disabled={savingCaptions}
                className="neo-btn-primary px-6 py-2.5 text-[16px] flex items-center gap-2.5"
              >
                {savingCaptions ? <Spinner className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                Save Caption & Re-assemble Video
              </button>
            </div>
          </div>
        )}

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
                // A scene is regenerating if local status is regenerating/queued OR backend PromptLog is running
                const isRegenerating = status === 'regenerating' || s.status === 'running';
                const isQueued = status === 'queued';
                // A scene is failed if the local status is failed OR the backend PromptLog status is failed
                const isFailed = status === 'failed' || s.status === 'failed';
                const edit = promptEdits[s.scene_index];
                const isTweaking = edit?.expanded || false;
                const effectiveText = edit?.text ?? s.visual_description ?? '';
                const isDirty = edit?.dirty || false;
                return (
                  <div key={s.scene_index} className={`neo-card p-3 ${isRegenerating ? 'border-l-4 border-[#C6F11D]' : isQueued ? 'border-l-4 border-[#6BFF64]' : isFailed ? 'border-l-4 border-[#FF5757]' : isDirty ? 'border-l-4 border-[#FFC845]' : ''}`}>
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
                        {isQueued && (
                          <div className="mt-2 text-[10px] text-[#6BFF64] flex items-center gap-1.5">
                            <RefreshCw className="h-3 w-3 animate-pulse" />
                            Queued for regeneration...
                          </div>
                        )}
                        {isFailed && (
                          <div className="mt-2 text-[10px] text-[#FF5757] flex items-center gap-1.5">
                            <AlertCircle className="h-3 w-3" />
                            Failed to Generate (Backend)
                          </div>
                        )}

                        {/* PROMPT & CAPTION EDITOR */}
                        {isTweaking && (
                          <div className="mt-3 space-y-3 rounded-xl border border-[#252A33] bg-[#0A0C10] p-3">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-1.5 text-[10px] font-semibold text-[#C6F11D]">
                                <Wand2 className="h-3 w-3" />
                                Edit Scene Caption & Visuals
                              </div>
                              <div className="flex items-center gap-2">
                                {isDirty && (
                                  <span className="text-[9px] text-[#FFC845]">unsaved edits</span>
                                )}
                                <button
                                  onClick={() => resetPromptEdit(s.scene_index, s.visual_description || '', s.narration || '')}
                                  className="text-[10px] text-[#9AA0A6] hover:text-[#F5F5F5] flex items-center gap-1"
                                  title="Reset to original"
                                >
                                  <RotateCcw className="h-3 w-3" /> Reset
                                </button>
                              </div>
                            </div>

                            {s.has_clip && s.clip_url && (
                              <div className={`relative rounded-xl overflow-hidden border border-[#252A33] bg-[#050608] mx-auto ${
                                vs.aspect === 'horizontal' || vs.aspect === 'horizontal_hd'
                                  ? 'w-full aspect-video max-w-[280px]'
                                  : 'w-[140px] aspect-[9/16]'
                              } mb-3 shadow-inner group`}>
                                <video
                                  src={`${s.clip_url}?t=${regenTimestamp}`}
                                  controls
                                  loop
                                  muted
                                  playsInline
                                  className="w-full h-full object-cover"
                                />
                              </div>
                            )}

                            <div className="space-y-1">
                              <label className="text-[9px] text-[#9AA0A6] uppercase tracking-wider block font-semibold">Spoken Caption / Narration</label>
                              <textarea
                                value={edit?.narration ?? s.narration ?? ''}
                                onChange={e => setPromptEdit(s.scene_index, { narration: e.target.value, dirty: true })}
                                rows={2}
                                className="w-full p-2 rounded-lg bg-[#050608] border border-[#252A33] text-[11px] text-[#F5F5F5] font-sans leading-relaxed outline-none focus:border-[#C6F11D]/50 transition-all resize-none"
                                placeholder="What the voiceover says..."
                              />
                            </div>

                            <div className="space-y-1">
                              <label className="text-[9px] text-[#9AA0A6] uppercase tracking-wider block font-semibold">Visual Prompt / Description</label>
                              <textarea
                                value={effectiveText}
                                onChange={e => setPromptEdit(s.scene_index, { text: e.target.value, dirty: true })}
                                rows={3}
                                className="w-full p-2 rounded-lg bg-[#050608] border border-[#252A33] text-[11px] text-[#F5F5F5] font-mono leading-relaxed outline-none focus:border-[#C6F11D]/50 transition-all resize-none"
                                placeholder="Camera move..."
                              />
                            </div>

                            <button
                              onClick={() => handleSaveSceneEdits(s.scene_index)}
                              className="bg-[#C6F11D] text-[#050608] hover:bg-[#b5dc1a] font-bold rounded-lg w-full py-1.5 text-[10px] transition-all"
                            >
                              Save Caption & Visuals
                            </button>
                          </div>
                        )}
                      </div>
                      <div className="flex flex-col gap-1.5 shrink-0">
                        <button
                          onClick={() => setPromptEdit(s.scene_index, { expanded: !isTweaking, text: s.visual_description || '', narration: s.narration || '', dirty: false })}
                          className={`neo-btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 text-[10px] ${isTweaking ? 'border-[#C6F11D] text-[#C6F11D]' : ''}`}
                          title="Tweak visual prompt"
                        >
                          {isTweaking ? <EyeOff className="h-3 w-3" /> : <Pencil className="h-3 w-3" />}
                          {isTweaking ? 'Hide' : 'Tweak'}
                        </button>
                        <button
                          onClick={() => handleRegenScene(s.scene_index, isTweaking ? effectiveText : null)}
                          disabled={isRegenerating}
                          className="neo-btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 text-[10px] disabled:opacity-50"
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
                <span>After regenerating scenes, rebuild final video</span>
              </div>
              <div className="flex gap-2">
                <button onClick={onClose} className="neo-btn-ghost px-3 py-1.5 text-xs">Close</button>
                <button
                  onClick={handleReassemble}
                  disabled={reassembleStatus === 'running'}
                  className="neo-btn-primary px-4 py-1.5 text-xs flex items-center gap-2"
                >
                  {reassembleStatus === 'running' ? (
                    <Spinner className="h-3 w-3 animate-spin" />
                  ) : (
                    'Re-assemble Final'
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* SEO TAB */}
        {tab === 'seo' && (
          <div className="p-5 space-y-4">
            {seoMsg.text && (
              <div className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border text-[11px] ${
                seoMsg.type === 'success' ? 'bg-[rgba(107,255,100,0.06)] border-[rgba(107,255,100,0.3)] text-[#6BFF64]' : 'bg-[rgba(255,87,87,0.06)] border-[rgba(255,87,87,0.3)] text-[#FF5757]'
              }`}>
                <span>{seoMsg.text}</span>
              </div>
            )}
            {!uploadRecord && !video.upload?.id ? (
              <div className="text-center py-10 bg-[#0E1116] border border-[#252A33] rounded-2xl p-5">
                <Youtube className="h-10 w-10 mx-auto text-[#FF0000] mb-3 opacity-60" />
                <button
                  onClick={handleCreateUploadDraft}
                  disabled={seoLoading}
                  className="neo-btn-primary px-5 py-2 text-xs flex items-center gap-2 mx-auto"
                >
                  Generate SEO Draft
                </button>
              </div>
            ) : seoLoading ? (
              <div className="text-center py-10">
                <Spinner className="h-6 w-6 mx-auto animate-spin text-[#C6F11D]" />
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="text-[11px] text-[#9AA0A6] block mb-1">YouTube Video Title</label>
                  <input
                    type="text"
                    value={seoTitle}
                    onChange={e => setSeoTitle(e.target.value)}
                    className="w-full p-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-xs text-[#F5F5F5] outline-none"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-[#9AA0A6] block mb-1">Video Description</label>
                  <textarea
                    value={seoDescription}
                    onChange={e => setSeoDescription(e.target.value)}
                    rows={4}
                    className="w-full p-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-xs text-[#F5F5F5] outline-none resize-none"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-[#9AA0A6] block mb-1">Tags / Hashtags</label>
                  <input
                    type="text"
                    value={seoTags}
                    onChange={e => setSeoTags(e.target.value)}
                    className="w-full p-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-xs text-[#F5F5F5] outline-none"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4 p-3 bg-[#131722]/50 border border-[#252A33]/50 rounded-xl">
                  <div>
                    <label className="text-[10px] text-[#9AA0A6] block mb-1">Scheduled Time</label>
                    <input
                      type="datetime-local"
                      value={scheduledFor}
                      onChange={e => setScheduledFor(e.target.value)}
                      className="w-full p-2 rounded-lg bg-[#0E1116] border border-[#252A33] text-[11px] text-[#F5F5F5]"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-[#9AA0A6] block mb-1">Status</label>
                    <div className="text-xs font-semibold px-2 py-2.5 rounded-lg bg-[#0E1116] border border-[#252A33] text-[#F5F5F5]">
                      {uploadRecord.status}
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-between pt-2 border-t border-[#252A33]">
                  <button onClick={handleRegenSeo} disabled={regeneratingSeo} className="neo-btn-ghost px-3 py-1.5 text-xs">
                    AI Regenerate SEO
                  </button>
                  <div className="flex gap-2">
                    <button onClick={handleSaveSeo} disabled={seoSaving} className="neo-btn-ghost px-4 py-1.5 text-xs">
                      Save & Schedule
                    </button>
                    <button onClick={handleUploadNow} disabled={uploadingNow} className="bg-[#FF0000] text-white rounded-xl px-4 py-1.5 text-xs">
                      Upload Now
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default EditVideoModal;
