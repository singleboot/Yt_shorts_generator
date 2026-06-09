import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Sparkles, Send, CheckCircle, AlertCircle, Loader2, Youtube, ChevronDown, ChevronUp, Hash, Play, Globe, Clock, Archive, FileText, Video, ChevronLeft, ChevronRight, Palette, Mic, Music, Volume2, Square, Captions, Type, Plus, Brush, Trash2, Blend, Calendar } from 'lucide-react';
import api from '../api/client';
import axios from 'axios';
import VideoCard from './VideoCard';
import EditVideoModal from './EditVideoModal';
import ScheduleCalendar from '../components/ScheduleCalendar';
import { CATEGORIES, SUBJECTS } from '../constants/categories';
import { AI_STYLES, VOICES, MUSIC_GENRES, STYLE_LORA_PATHS } from '../constants/production';

const DURATIONS = [
  { label: '30s',  value: 30,  scenes: 5,  perScene: 6,  longForm: false, estMin: 5  },
  { label: '45s',  value: 45,  scenes: 7,  perScene: 6,  longForm: false, estMin: 8  },
  { label: '60s',  value: 60,  scenes: 10, perScene: 6,  longForm: false, estMin: 12 },
  { label: '90s',  value: 90,  scenes: 15, perScene: 6,  longForm: false, estMin: 18 },
  { label: '120s', value: 120, scenes: 20, perScene: 6,  longForm: false, estMin: 24 },
  { label: '180s', value: 180, scenes: 22, perScene: 8,  longForm: true,  estMin: 30 },
  { label: '300s', value: 300, scenes: 30, perScene: 10, longForm: true,  estMin: 45 },
];

// Aspect ratio options. Mirrors ASPECT_RATIOS in backend config.py.
const ASPECT_OPTIONS = [
  { value: 'vertical',       label: 'Vertical 9:16',      dims: '720x1280',   vram: '~7 GB',  longForm: false, hint: 'YouTube Shorts, TikTok, Reels' },
  { value: 'horizontal',     label: 'Horizontal 16:9',   dims: '1280x720',   vram: '~7 GB',  longForm: false, hint: 'YouTube standard' },
  { value: 'horizontal_hd',  label: 'Horizontal HD 16:9',dims: '1920x1080',  vram: '~12 GB', longForm: true,  hint: 'Auto-shortens to 5s/scene' },
];

// Transition style options. Mirrors TRANSITION_STYLES in backend config.py.
const TRANSITION_OPTIONS = [
  { value: 'none',         label: 'None (hard cut)' },
  { value: 'fade',         label: 'Fade' },
  { value: 'fadeblack',    label: 'Fade to black' },
  { value: 'fadewhite',    label: 'Fade to white' },
  { value: 'dissolve',     label: 'Dissolve' },
  { value: 'slide_left',   label: 'Slide left' },
  { value: 'slide_right',  label: 'Slide right' },
  { value: 'slide_up',     label: 'Slide up' },
  { value: 'slide_down',   label: 'Slide down' },
  { value: 'wipe_left',    label: 'Wipe left' },
  { value: 'wipe_right',   label: 'Wipe right' },
  { value: 'zoom_in',      label: 'Zoom in' },
  { value: 'circle_open',  label: 'Circle open' },
  { value: 'circle_close', label: 'Circle close' },
];

const PER_PAGE = 8;

function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState(null);
  const [videos, setVideos] = useState([]);
  const [videoCount, setVideoCount] = useState(1);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const [editingVideo, setEditingVideo] = useState(null);
  const [channels, setChannels] = useState([]);
  const [channelMenuOpen, setChannelMenuOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generatingScripts, setGeneratingScripts] = useState(false);
  const [formOpen, setFormOpen] = useState(true);
  const [page, setPage] = useState(1);
  const [phase, setPhase] = useState('setup');
  const initialLoadDone = useRef(false);
  const generatingScriptsRef = useRef(false);
  const cancelScriptRef = useRef(null);
  const prevPhaseRef = useRef('setup');

  // Generate form state
  const [sourceType, setSourceType] = useState('topic');
  const [category, setCategory] = useState('');
  const [topic, setTopic] = useState('');
  // Caption settings
  const [captionStyle, setCaptionStyle] = useState('standard');
  const [captionFont, setCaptionFont] = useState('Arial-Bold');
  const [captionFontSize, setCaptionFontSize] = useState(48);
  const [captionColor, setCaptionColor] = useState('#FFFFFF');
  const [captionStrokeColor, setCaptionStrokeColor] = useState('#000000');
  const [captionStrokeWidth, setCaptionStrokeWidth] = useState(3);
  const [captionAnimation, setCaptionAnimation] = useState('word_by_word');
  const [url, setUrl] = useState('');
  const [genCount, setGenCount] = useState(1);
  const [duration, setDuration] = useState(45);

  // Suggestions & trending
  const [suggestedTopics, setSuggestedTopics] = useState([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [trending, setTrending] = useState(false);
  const [trendingTopics, setTrendingTopics] = useState([]);
  const [loadingTrending, setLoadingTrending] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const subjectRef = useRef(null);
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

  // Production settings (style/voice/music)
  const [productionTab, setProductionTab] = useState(null);
  const [showCalendar, setShowCalendar] = useState(false);
  const [selectedStyle, setSelectedStyle] = useState('none');
  const [loraStrength, setLoraStrength] = useState(0.8);
  const [selectedVoice, setSelectedVoice] = useState('en-US-AriaNeural');
  const [selectedMusic, setSelectedMusic] = useState('ambient');
  const [voiceCustom, setVoiceCustom] = useState('');    // custom voice description
  const [musicCustom, setMusicCustom] = useState('');    // custom ACE tag string
  const [trendingNowLoading, setTrendingNowLoading] = useState(false);

  // Aspect ratio + transitions (long-form / horizontal video support)
  const [aspectRatio, setAspectRatio] = useState('vertical');
  const [transitionStyle, setTransitionStyle] = useState('none');
  const [transitionDuration, setTransitionDuration] = useState(0.4);
  const [audioTransition, setAudioTransition] = useState('match_video');

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  // ── LocalStorage draft ──────────────────────────────────────────────────
  const DRAFT_KEY = `project_draft_${id}`;
  const saveDraft = () => {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ sourceType, category, topic, url, genCount, duration }));
    } catch {}
  };
  const loadDraft = () => {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (!raw) return;
      const d = JSON.parse(raw);
      if (d.sourceType) setSourceType(d.sourceType);
      if (d.category) setCategory(d.category);
      if (d.topic) setTopic(d.topic);
      if (d.url) setUrl(d.url);
      if (d.genCount) setGenCount(d.genCount);
      if (d.duration) setDuration(d.duration);
    } catch {}
  };
  const clearDraft = () => {
    try { localStorage.removeItem(DRAFT_KEY); } catch {}
  };
  // Persist draft on every relevant state change
  useEffect(() => { saveDraft(); }, [sourceType, category, topic, url, genCount, duration]);

  // Load project on mount + 2s polling; restore localStorage draft once project loads
  useEffect(() => {
    loadProject();
    api.get('/settings/youtube/channels').then(res => setChannels(res.data || [])).catch(() => setChannels([]));
    const interval = setInterval(loadProject, 2000);
    return () => clearInterval(interval);
  }, [id]);
  useEffect(() => { if (project) loadDraft(); }, [project]);

  // ── Debounced auto-save for production settings ─────────────────────────
  const autoSaveTimerRef = useRef(null);
  const autoSaveRef = useRef(null);
  const autoSaveProductionSettings = () => {
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    autoSaveTimerRef.current = setTimeout(() => {
      if (autoSaveRef.current) return; // already saving
      (async () => {
        autoSaveRef.current = true;
        try {
          const newVS = {
            ...(project?.visual_settings || {}),
            ai_style: selectedStyle,
            lora_strength: loraStrength,
            aspect_ratio: aspectRatio,
            transition_style: transitionStyle,
            transition_duration: transitionDuration,
            audio_transition: audioTransition,
          };
          const newASRaw = { ...(project?.audio_settings || {}), voice_id: selectedVoice, voice_custom: voiceCustom || undefined, music_genre: selectedMusic, music_custom: musicCustom || undefined };
          const newAS = Object.fromEntries(Object.entries(newASRaw).filter(([, v]) => v !== undefined));
          const newCS = { style: captionStyle, font: captionFont, font_size: captionFontSize, color: captionColor, stroke_color: captionStrokeColor, stroke_width: captionStrokeWidth, animation: captionAnimation };
          await api.put(`/projects/${id}`, { visual_settings: newVS, audio_settings: newAS, caption_settings: newCS });
        } catch (e) {
          console.error('Auto-save failed', e);
        } finally {
          autoSaveRef.current = false;
        }
      })();
    }, 800); // debounce 800ms
  };

  useEffect(() => {
    if (!project) return;
    autoSaveProductionSettings();
  }, [selectedStyle, loraStrength, selectedVoice, selectedMusic, voiceCustom, musicCustom, captionStyle, captionFont, captionFontSize, captionColor, captionStrokeColor, captionStrokeWidth, captionAnimation]);

  const fetchSuggestions = async (cat) => {
    if (!cat) { setSuggestedTopics([]); return; }
    setLoadingSuggestions(true);
    try {
      const res = await api.post('/projects/suggest-topics', { category: cat, seed: topic });
      if (res.data?.topics) setSuggestedTopics(res.data.topics);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingSuggestions(false);
    }
  };

  const fetchTrendingTopics = async () => {
    if (!category) { showToast('Select a category first', 'warning'); return; }
    setLoadingTrending(true);
    setTrendingTopics([]);
    try {
      const res = await api.post('/projects/trending-topics', { category });
      if (res.data?.topics?.length) {
        setTrendingTopics(res.data.topics);
        setTopic(res.data.topics[0]);
      } else {
        setTrendingTopics([]);
      }
    } catch (e) {
      showToast('Failed to fetch trending topics', 'error');
    } finally {
      setLoadingTrending(false);
    }
  };

  useEffect(() => {
    loadProject();
    api.get('/settings/youtube/channels').then(res => setChannels(res.data || [])).catch(() => setChannels([]));
    const interval = setInterval(loadProject, 2000);
    return () => clearInterval(interval);
  }, [id]);

  const loadProject = async () => {
    try {
      const [projRes, vidRes] = await Promise.all([
        api.get(`/projects/${id}`).catch(() => null),
        api.get(`/projects/${id}/videos`).catch(() => null),
      ]);
      if (projRes) {
        setProject(projRes.data);
          if (!initialLoadDone.current) {
            initialLoadDone.current = true;
            if (projRes.data.category && projRes.data.category !== 'general') {
              setCategory(projRes.data.category);
            }
            if (projRes.data.source_value && projRes.data.source_type === 'url') {
              setUrl(projRes.data.source_value);
              setSourceType('url');
            } else if (projRes.data.source_value) {
              setTopic(projRes.data.source_value);
            }
            const vs = projRes.data.visual_settings || {};
            const as = projRes.data.audio_settings || {};
            if (vs.total_duration && !DURATIONS.find(d => d.value === vs.total_duration)) {
              const closest = DURATIONS.reduce((a, b) => Math.abs(b.value - vs.total_duration) < Math.abs(a.value - vs.total_duration) ? b : a);
              setDuration(closest.value);
            } else if (vs.total_duration) {
              setDuration(vs.total_duration);
            }
            setSelectedStyle(vs.ai_style || 'none');
            setLoraStrength(vs.lora_strength ?? 0.8);
            setSelectedVoice(as.voice_id || 'en-US-AriaNeural');
            setSelectedMusic(as.music_genre || 'ambient');
            setVoiceCustom(as.voice_custom || '');
            setMusicCustom(as.music_custom || '');
            // Aspect ratio + transitions (with safe defaults for legacy projects)
            setAspectRatio(vs.aspect_ratio || 'vertical');
            setTransitionStyle(vs.transition_style || 'none');
            setTransitionDuration(vs.transition_duration ?? 0.4);
            setAudioTransition(vs.audio_transition || 'match_video');
            const cs = projRes.data.caption_settings || {};
            setCaptionStyle(cs.style || 'standard');
            setCaptionFont(cs.font || 'Arial-Bold');
            setCaptionFontSize(cs.font_size || 48);
            setCaptionColor(cs.color || '#FFFFFF');
            setCaptionStrokeColor(cs.stroke_color || '#000000');
            setCaptionStrokeWidth(cs.stroke_width ?? 3);
            setCaptionAnimation(cs.animation || 'word_by_word');
          }
      }
      if (vidRes && vidRes.data) {
        // Always merge: preserve local regenerating/generating flags while overlaying backend data
        const incomingVideos = vidRes.data.videos || [];
        const incomingIndices = new Set(incomingVideos.map(v => v.index));
        setVideos(prev => {
          const merge = [];
          for (const inc of incomingVideos) {
            const local = prev.find(v => v.index === inc.index);
            if (local && (local.regenerating || local.generating)) {
              // Keep the spinner card, skip backend overlay
              merge.push(local);
            } else {
              merge.push(inc);
            }
          }
          // Preserve any local-only cards that aren't in the backend yet
          for (const v of prev) {
            if (!incomingIndices.has(v.index) && (v.generating || v.regenerating)) {
              merge.push(v);
            }
          }
          // Sort by index to maintain order
          merge.sort((a, b) => a.index - b.index);
          return merge;
        });
          // Always derive videoCount from the actual list length - never trust
          // the backend's video_count field (it can drift from schedule_settings).
          // Fall back to the backend's hint only if the list is empty.
        setVideoCount(incomingVideos.length > 0 ? incomingVideos.length : (vidRes.data.video_count || 1));
        // Detect phase based on whether any video has a job (t2v started)
          const hasJob = (vidRes.data.videos || []).some(v => v.job);
          const hasScript = (vidRes.data.videos || []).some(v => v.script);
          let newPhase;
          if (hasJob) newPhase = 'videos';
          else if (hasScript) newPhase = 'scripts';
          else newPhase = 'setup';
          // Don't override phase to 'videos' while the user is actively adding
          // new scripts. handleAddNewVideos sets phase='scripts' before this
          // loadProject() call returns — we must NOT clobber it back to 'videos'
          // just because an old video has a completed job sitting in the DB.
          if (generatingScriptsRef.current) {
            newPhase = 'scripts';
          }
          // Only auto-collapse/expand on PHASE TRANSITION, not on every poll —
          // otherwise the 2s poll would re-collapse a form the user just opened.
          if (newPhase !== prevPhaseRef.current) {
            if (newPhase === 'videos') setFormOpen(false);
            else if (prevPhaseRef.current === 'videos') setFormOpen(true);
            prevPhaseRef.current = newPhase;
          }
          setPhase(newPhase);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handlePost = async (videoIndex) => {
    try {
      const res = await api.post(`/projects/${id}/videos/${videoIndex}/post`);
      if (res.data.status === 'success') {
        showToast(`Video ${videoIndex + 1} scheduled!`);
      } else {
        showToast(res.data.message || 'Nothing to post', 'warning');
      }
      loadProject();
    } catch (e) {
      showToast('Failed to post', 'error');
    }
  };

  const handleSaveOverrides = async (videoIndex, overrides) => {
    try {
      await api.put(`/projects/${id}/videos/${videoIndex}/settings`, overrides);
      showToast(`Regenerating Video ${videoIndex + 1}...`);
      setEditingVideo(null);
      loadProject();
    } catch (e) {
      showToast('Failed to save settings', 'error');
    }
  };

  const changeChannel = async (channelId) => {
    setChannelMenuOpen(false);
    try {
      await api.put(`/projects/${id}`, { youtube_channel_id: channelId });
      showToast(channelId ? 'Channel updated' : 'Channel removed');
      loadProject();
    } catch (e) {
      showToast('Failed to update channel', 'error');
    }
  };

  const handleGenerateScripts = async () => {
    if (trending) {
      await handleTrendingNow();
      return;
    }
    if (sourceType === 'topic' && !(topic||'').trim()) {
      showToast('Enter a subject', 'warning');
      return;
    }
    if (sourceType === 'url' && !(url||'').trim()) {
      showToast('Enter a URL', 'warning');
      return;
    }
    // Create placeholder cards immediately
    const maxIdx = videos.reduce((max, v) => Math.max(max, v.index != null ? v.index : 0), -1);
    const placeholders = Array.from({ length: genCount }, (_, i) => ({
      index: maxIdx + 1 + i,
      generating: true,
      generatingDuration: duration,
      script: null, upload: null, job: null, overrides: null,
    }));
    setVideos(prev => [...prev, ...placeholders]);
    setPhase('scripts');
    setGeneratingScripts(true);
    generatingScriptsRef.current = true;
    const controller = new AbortController();
    cancelScriptRef.current = controller;
    try {
      const payload = { video_count: genCount, duration, source_type: 'topic', category };
      if (sourceType === 'topic') {
        payload.category = category;
        payload.topic = (topic||'').trim();
      } else {
        payload.url = url.trim();
        payload.category = category || 'tech';
      }
      const res = await api.post(`/projects/${id}/generate-scripts`, payload, { signal: controller.signal });
      if (res.data.status === 'success') {
        showToast(`${res.data.scripts.length} script(s) generated!`);
        clearDraft(); // clear form draft now that scripts are committed
        generatingScriptsRef.current = false;
        setPage(1);
        // Replace videos with the response data directly (avoids race with 2s poll returning stale video_count)
        setVideoCount(res.data.video_count || 1);
        setVideos(res.data.scripts.map(s => ({
          index: s.index,
          script: s,
          upload: null,
          job: null,
          overrides: null,
        })));
        setPhase('scripts');
      }
    } catch (e) {
      if (axios.isCancel(e) || e?.code === 'ERR_CANCELED') {
        showToast('Script generation cancelled', 'warning');
      } else {
        showToast('Script generation failed', 'error');
      }
      setVideos(prev => prev.filter(v => !v.generating));
    } finally {
      generatingScriptsRef.current = false;
      setGeneratingScripts(false);
      cancelScriptRef.current = null;
    }
  };

  const handleAddNewVideos = async () => {
    if (sourceType === 'topic' && !(topic||'').trim()) {
      showToast('Enter a subject', 'warning');
      return;
    }
    if (sourceType === 'url' && !(url||'').trim()) {
      showToast('Enter a URL', 'warning');
      return;
    }

    // Create placeholder cards immediately so the user sees cards appear
    const maxIdx = videos.reduce((max, v) => Math.max(max, v.index != null ? v.index : 0), -1);
    const placeholders = Array.from({ length: genCount }, (_, i) => ({
      index: maxIdx + 1 + i,
      generating: true,
      generatingDuration: duration,
      script: null, upload: null, job: null, overrides: null,
    }));
    setVideos(prev => [...prev, ...placeholders]);
    setPhase('scripts');
    setGeneratingScripts(true);
    generatingScriptsRef.current = true;

    const controller = new AbortController();
    cancelScriptRef.current = controller;

    try {
      const payload = { video_count: genCount, duration, source_type: 'topic', category };
      if (sourceType === 'topic') {
        payload.category = category;
        payload.topic = (topic||'').trim();
      } else {
        payload.url = url.trim();
        payload.category = category || 'tech';
      }
      const res = await api.post(`/projects/${id}/generate-scripts`, payload, { signal: controller.signal });
      if (res.data.status === 'success') {
        showToast(`+ ${res.data.scripts.length} new script(s) ready. Review, then click Generate Video on each.`);
        generatingScriptsRef.current = false;
        setPage(1);
        setVideoCount(res.data.video_count || 1);
        // Replace placeholder cards with real script data
        setVideos(res.data.scripts.map(s => ({
          index: s.index,
          script: s,
          upload: null,
          job: null,
          overrides: null,
        })));
        setPhase('scripts');
        await loadProject();
      }
    } catch (e) {
      if (axios.isCancel(e) || e?.code === 'ERR_CANCELED') {
        showToast('Script generation cancelled', 'warning');
      } else {
        const msg = e?.response?.data?.detail || 'Failed to add scripts';
        showToast(msg, 'error');
      }
      setVideos(prev => prev.filter(v => !v.generating));
    } finally {
      generatingScriptsRef.current = false;
      setGeneratingScripts(false);
      cancelScriptRef.current = null;
    }
  };

  const handleGenerateOrCancel = () => {
    if (generatingScripts) {
      handleCancelScripts();
      return;
    }
    if (generating) {
      handleCancelVideos();
      return;
    }
    const hasScripts = videos.filter(v => v.script).length > 0;
    const hasVideos = videos.filter(v => v.upload || v.job).length > 0;
    if (!hasScripts) {
      handleGenerateScripts();
    } else if (!hasVideos) {
      handleGenerateVideos();
    } else {
      handleAddNewVideos();
    }
  };

  const handleRegenScript = async (videoIndex) => {
    // Set regenerating flag so the card shows a spinner instead of disappearing
    setVideos(prev => prev.map(v =>
      v.index === videoIndex ? { ...v, regenerating: true } : v
    ));
    try {
      const res = await api.post(`/projects/${id}/videos/${videoIndex}/regenerate-script`);
      if (res.data.status === 'success') {
        showToast(`Script #${videoIndex + 1} regenerated!`);
        // Replace with new script data immediately
        setVideos(prev => prev.map(v =>
          v.index === videoIndex ? {
            index: v.index,
            script: { ...res.data.script, scenes: res.data.script?.scenes || [] },
            upload: v.upload,
            job: null,
            overrides: v.overrides,
            regenerating: false,
          } : v
        ));
        loadProject();
      }
    } catch (e) {
      showToast('Regeneration failed', 'error');
      setVideos(prev => prev.map(v =>
        v.index === videoIndex ? { ...v, regenerating: false } : v
      ));
    }
  };

  const handleGenerateSingleVideo = async (videoIndex) => {
    try {
      await api.post(`/projects/${id}/videos/${videoIndex}/generate`);
      showToast(`Generating video #${videoIndex + 1}...`);
      setPhase('videos');
      loadProject();
    } catch (e) {
      showToast('Failed to start video generation', 'error');
    }
  };

  const handleGenerateVideos = async () => {
    setGenerating(true);
    try {
      await api.post(`/projects/${id}/batch`, { video_count: genCount });
      showToast(`Generating ${videoCount} video(s)...`);
      setPhase('videos');
      loadProject();
    } catch (e) {
      showToast('Failed to start generation', 'error');
    } finally {
      setGenerating(false);
    }
  };

  const handleCancelScripts = () => {
    if (cancelScriptRef.current) {
      cancelScriptRef.current.abort();
    }
  };

  const handleRemovePlaceholder = (videoIndex) => {
    if (!window.confirm(`Remove placeholder for slot #${videoIndex + 1}? The slot will be cancelled if still generating.`)) return;
    setVideos(prev => prev.filter(v => !(v.generating && v.index === videoIndex)));
    if (generatingScriptsRef.current && cancelScriptRef.current) {
      cancelScriptRef.current.abort();
    }
  };

  const handleDeleteVideo = async (videoIndex) => {
    if (!window.confirm(`Delete video #${videoIndex + 1}? This will remove the script, assets, and video file permanently.`)) return;
    try {
      const res = await api.delete(`/projects/${id}/videos/${videoIndex}`);
      if (res.data.status === 'success') {
        showToast(`Video #${videoIndex + 1} deleted`);
        loadProject();
      } else {
        showToast(res.data.message || 'Delete failed', 'warning');
      }
    } catch (e) {
      showToast('Failed to delete video', 'error');
    }
  };

  const handleCleanScenes = async (videoIndex) => {
    const bytesApprox = 100;  // hint for the prompt
    if (!window.confirm(
      `Clean intermediate scenes for video #${videoIndex + 1}?\n\n` +
      `This deletes the per-scene ComfyUI clips and voiceover chunks from disk ` +
      `to free up ~${bytesApprox}MB+ per video. The final video and script ` +
      `are kept. After cleanup, per-scene regeneration on this video will be ` +
      `disabled until you re-render the full video.`
    )) return;
    try {
      const res = await api.post(`/projects/${id}/videos/${videoIndex}/clean-scenes`);
      if (res.data.status === 'success') {
        const mb = (res.data.bytes_freed / 1024 / 1024).toFixed(1);
        showToast(`Cleaned ${res.data.files_deleted} files, freed ${mb} MB`);
        loadProject();
      } else {
        showToast(res.data.message || 'Clean failed', 'warning');
      }
    } catch (e) {
      showToast('Failed to clean scenes', 'error');
    }
  };

  const handleCancelVideos = async () => {
    try {
      await api.post(`/projects/${id}/cancel-all`);
      showToast('Video generation cancelled', 'warning');
      loadProject();
    } catch (e) {
      showToast('Failed to cancel', 'error');
    }
  };

  const saveProductionSettings = async () => {
    try {
      const newVS = {
        ...(project.visual_settings || {}),
        ai_style: selectedStyle,
        lora_strength: loraStrength,
        aspect_ratio: aspectRatio,
        transition_style: transitionStyle,
        transition_duration: transitionDuration,
        audio_transition: audioTransition,
      };
      const newASRaw = { ...(project.audio_settings || {}), voice_id: selectedVoice, voice_custom: voiceCustom || undefined, music_genre: selectedMusic, music_custom: musicCustom || undefined };
      const newAS = Object.fromEntries(Object.entries(newASRaw).filter(([, v]) => v !== undefined));
      await api.put(`/projects/${id}`, { visual_settings: newVS, audio_settings: newAS });
      setProject(prev => ({ ...prev, visual_settings: newVS, audio_settings: newAS }));
    } catch (e) {
      console.error('Failed to save production settings', e);
    }
  };

  const handleSaveProject = async () => {
    try {
      const newVS = {
        ...(project.visual_settings || {}),
        ai_style: selectedStyle,
        lora_strength: loraStrength,
        total_duration: duration,
        aspect_ratio: aspectRatio,
        transition_style: transitionStyle,
        transition_duration: transitionDuration,
        audio_transition: audioTransition,
      };
      const newASRaw = { ...(project.audio_settings || {}), voice_id: selectedVoice, voice_custom: voiceCustom || undefined, music_genre: selectedMusic, music_custom: musicCustom || undefined };
      const newAS = Object.fromEntries(Object.entries(newASRaw).filter(([, v]) => v !== undefined));
      const newCS = { style: captionStyle, font: captionFont, font_size: captionFontSize, color: captionColor, stroke_color: captionStrokeColor, stroke_width: captionStrokeWidth, animation: captionAnimation };
      const newSS = { ...(project.schedule_settings || {}), video_count: genCount };
      await api.post(`/projects/${id}/save`, {
        source_type: sourceType,
        source_value: sourceType === 'topic' ? topic : url,
        category,
        visual_settings: newVS,
        audio_settings: newAS,
        caption_settings: newCS,
        schedule_settings: newSS,
        youtube_channel_id: project.youtube_channel_id,
      });
      showToast('Project saved!');
      loadProject();
    } catch (e) {
      showToast('Failed to save project', 'error');
    }
  };

  const handleTrendingNow = async () => {
    if (!category) { showToast('Select a category first', 'warning'); return; }
    setTrendingNowLoading(true);
    try {
      const res = await api.post(`/projects/${id}/trending-now`, {
        category, video_count: genCount, duration,
      });
      if (res.data.status === 'success') {
        showToast(`Trending: "${res.data.trending_topic}" - generating ${res.data.video_count} videos...`);
        setPhase('videos');
        setPage(1);
        loadProject();
      } else {
        showToast(res.data.message || 'Trending Now failed', 'error');
      }
    } catch (e) {
      showToast('Trending Now failed', 'error');
    } finally {
      setTrendingNowLoading(false);
    }
  };

  const handleArchiveNow = async () => {
    try {
      const res = await api.post(`/projects/${id}/archive`);
      if (res.data.status === 'success') {
        showToast(`${res.data.archived} video(s) archived!`);
        loadProject();
      }
    } catch (e) {
      showToast('Archive failed', 'error');
    }
  };

  const handlePostAll = async () => {
    if (readyCount === 0) {
      showToast('No videos ready to post', 'warning');
      return;
    }
    try {
      const res = await api.post(`/projects/${id}/post`);
      if (res.data.status === 'success') {
        showToast(`${res.data.scheduled || readyCount} video(s) scheduled!`);
        loadProject();
      } else {
        showToast(res.data.message || 'Post failed', 'error');
      }
    } catch (e) {
      showToast('Post all failed', 'error');
    }
  };

  const getStepLabel = (progress) => {
    if (!progress || progress === 0) return 'Queued';
    if (progress < 15) return 'Researching';
    if (progress < 30) return 'Writing script';
    if (progress < 55) return 'Generating visuals';
    if (progress < 70) return 'Creating voiceover';
    if (progress < 100) return 'Assembling video';
    return 'Complete';
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{background:'#050608'}}>
        <Loader2 className="h-8 w-8 text-[#C6F11D] animate-spin" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{background:'#050608'}}>
        <div className="text-center">
          <p className="text-[#9AA0A6]">Project not found</p>
          <button onClick={() => navigate('/')} className="mt-4 text-[#C6F11D] hover:text-[#D9FF3D]">Back to Dashboard</button>
        </div>
      </div>
    );
  }

  const vs = project.visual_settings || {};
  const readyCount = videos.filter(v => v.upload?.status === 'queued' || v.upload?.status === 'done').length;
  const postedCount = videos.filter(v => v.upload?.status === 'done').length;
  const archivedCount = videos.filter(v => v.upload?.archived_at).length;
  const hasVideos = videos.some(v => v.script || v.generating);
  const currentSubjects = SUBJECTS[category] || [];
  const currentDuration = DURATIONS.find(d => d.value === duration) || DURATIONS[1];

  // Pagination
  const totalPages = Math.ceil(videos.length / PER_PAGE) || 1;
  const safePage = Math.min(page, totalPages);
  const pagedVideos = videos.slice((safePage - 1) * PER_PAGE, safePage * PER_PAGE);

  return (
      <div className="min-h-screen p-8 relative" style={{background:'#050608'}}>
      <audio ref={audioRef} onEnded={() => setPreviewPlaying(null)} className="hidden" />
      {toast && (
        <div className={`fixed top-6 right-6 z-50 flex items-center gap-3 px-5 py-3 rounded-2xl shadow-2xl transition-all duration-150 ${
          toast.type === 'error' ? 'bg-[#FF5757] text-white' :
          toast.type === 'warning' ? 'bg-[#FFC845] text-[#050608]' :
          'bg-[#C6F11D] text-[#050608]'
        }`}>
          {toast.type === 'error' ? <AlertCircle className="h-5 w-5" /> :
           toast.type === 'warning' ? <AlertCircle className="h-5 w-5" /> :
           <CheckCircle className="h-5 w-5" />}
          <span className="text-sm font-bold">{toast.msg}</span>
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <button
            onClick={() => navigate('/')}
            className="neo-btn-ghost flex items-center gap-1.5 text-sm mb-3"
          >
            <ArrowLeft className="h-4 w-4" />
            Dashboard
          </button>
          <h1 className="neo-title text-3xl">{project.name}</h1>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            {category && (
              <span className="neo-badge neo-badge-green capitalize">
                {category.replace(/_/g, ' ')}
              </span>
            )}
            {vs.ai_style && vs.ai_style !== 'none' && (
              <span className="neo-badge neo-badge-blue capitalize">
                {vs.ai_style.replace(/_/g, ' ')}
              </span>
            )}
            {duration && (
              <span className="neo-badge neo-badge-amber flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {duration}s
              </span>
            )}
            {project.source_type === 'url' && (
              <span className="neo-badge neo-badge-blue flex items-center gap-1">
                <Globe className="h-3 w-3" />
                URL
              </span>
            )}
            <span className={`neo-badge flex items-center gap-1 ${phase === 'videos' ? 'neo-badge-green' : phase === 'scripts' ? 'neo-badge-amber' : 'neo-badge-gray'}`}>
              {phase === 'videos' ? <Video className="h-3 w-3" /> : phase === 'scripts' ? <FileText className="h-3 w-3" /> : null}
              {phase === 'setup' ? 'Setup' : phase === 'scripts' ? 'Scripts' : 'Videos'}
            </span>
            <button
              onClick={() => setShowCalendar(true)}
              className="neo-card-hover flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm text-[#9AA0A6] hover:text-[#F5F5F5] mr-1"
            >
              <Calendar className="h-4 w-4" />
              Schedule
            </button>
            <button onClick={handleSaveProject} className="neo-btn-primary flex items-center gap-1.5 text-sm px-3 py-1.5">
              <CheckCircle className="h-4 w-4" />
              Save
            </button>
            {/* Channel selector */}
            <div className="relative">
              <button
                onClick={() => setChannelMenuOpen(o => !o)}
                className="neo-btn-secondary flex items-center gap-1.5 text-[11px] px-2 py-1"
              >
                <Youtube className="h-3 w-3" />
                {project.youtube_channel ? (
                  <span className="truncate max-w-[100px]">{project.youtube_channel.name}</span>
                ) : 'Set channel'}
                <ChevronDown className="h-3 w-3" />
              </button>
              {channelMenuOpen && (
                <div className="absolute top-full left-0 mt-1 w-72 neo-card p-1 shadow-2xl z-30">
                  <button
                    onClick={() => changeChannel(null)}
                    className="w-full text-left px-3 py-2 text-xs text-[#9AA0A6] hover:bg-[rgba(255,255,255,0.03)] rounded-lg"
                  >
                    No channel (skip uploads)
                  </button>
                  {channels.length === 0 ? (
                    <div className="px-3 py-2 text-xs text-[#5F6772]">No channels linked. <button onClick={() => navigate('/settings')} className="text-[#C6F11D] underline hover:text-[#D9FF3D] inline">Link one</button></div>
                  ) : channels.map(ch => (
                    <button
                      key={ch.id}
                      onClick={() => changeChannel(ch.id)}
                      className={`w-full flex items-center gap-2 px-3 py-2 text-xs rounded-lg transition-all ${
                        project.youtube_channel?.id === ch.id ? 'bg-[rgba(198,241,29,0.08)] text-[#C6F11D]' : 'text-[#9AA0A6] hover:bg-[rgba(255,255,255,0.03)]'
                      }`}
                    >
                      {ch.thumbnail_url ? (
                        <img src={ch.thumbnail_url} alt="" className="w-6 h-6 rounded-full" />
                      ) : (
                        <div className="w-6 h-6 rounded-full bg-[rgba(198,241,29,0.1)] flex items-center justify-center">
                          <Youtube className="h-3 w-3 text-[#C6F11D]" />
                        </div>
                      )}
                      <div className="flex-1 text-left min-w-0">
                        <p className="font-medium truncate">{ch.name}</p>
                        <p className="text-[10px] text-[#5F6772] truncate">{ch.channel_title}</p>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="text-right flex flex-col items-end gap-2">
          <p className="text-sm font-semibold text-[#F5F5F5]">{readyCount}/{videoCount} videos ready</p>
          <p className="text-xs text-[#9AA0A6]">{postedCount} posted{archivedCount > 0 ? ` · ${archivedCount} archived` : ''}</p>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {/* Create Script button — always visible */}
            <button
              onClick={generatingScripts ? handleCancelScripts : handleAddNewVideos}
              disabled={generatingScripts ? false : !!(trendingNowLoading || (sourceType === 'topic' && (!(topic||'').trim() || !category)))}
              className={`neo-btn-primary flex items-center gap-1.5 px-3 py-1.5 text-[11px] ${generatingScripts ? 'border-[#FF5757] text-[#FF5757] hover:bg-[rgba(255,87,87,0.1)]' : ''}`}
            >
              {generatingScripts ? <Loader2 className="h-3 w-3 animate-spin" /> : <FileText className="h-3 w-3" />}
              {generatingScripts ? 'Cancel' : `Create Script (${genCount})`}
            </button>
            {/* Create Video button — always visible (generates all pending scripts) */}
            {(
              <button
                onClick={generating ? handleCancelVideos : handleGenerateVideos}
                disabled={generating ? false : videos.filter(v => v.script && !v.job).length === 0}
                className={`neo-btn-primary flex items-center gap-1.5 px-3 py-1.5 text-[11px] ${generating ? 'border-[#FF5757] text-[#FF5757] hover:bg-[rgba(255,87,87,0.1)]' : ''}`}
              >
                {generating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Video className="h-3 w-3" />}
                {generating ? 'Cancel' : `Create Video (${videos.filter(v => v.script && !v.job).length})`}
              </button>
            )}
            {readyCount > 0 && (
              <button
                onClick={handlePostAll}
                className="neo-btn-primary flex items-center gap-1.5 px-3 py-1.5 text-[11px]"
              >
                <Send className="h-3 w-3" /> Post All ({readyCount})
              </button>
            )}
            {postedCount > 0 && (
              <button
                onClick={handleArchiveNow}
                className="neo-btn-secondary flex items-center gap-1.5 px-3 py-1.5 text-[11px]"
              >
                <Archive className="h-3 w-3" />
                Archive Now
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Generate Form — always visible, auto-collapsed in videos phase */}
      {(phase === 'setup' || phase === 'scripts' || phase === 'videos') && (
        <div className="neo-card mb-6 overflow-hidden">
          <button
            onClick={() => setFormOpen(o => !o)}
            className="w-full flex items-center justify-between px-5 py-3 hover:bg-[rgba(255,255,255,0.02)] transition-colors"
          >
            <span className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-[#C6F11D]" />
              <span className="text-sm font-bold text-[#F5F5F5]">Generate Videos</span>
              {phase === 'videos' && (
                <span className="text-[10px] text-[#5F6772] font-normal">(settings for next batch)</span>
              )}
            </span>
            {formOpen ? <ChevronUp className="h-4 w-4 text-[#9AA0A6]" /> : <ChevronDown className="h-4 w-4 text-[#9AA0A6]" />}
          </button>
          {formOpen && (
            <div className="px-5 pb-5 space-y-5">
              {/* Source type toggle */}
              <div className="flex items-center gap-2 flex-wrap">
                <div className="flex gap-1 p-1 rounded-xl bg-[#050608] border border-[#252A33] w-fit">
                  <button
                    onClick={() => { setSourceType('topic'); setTrending(false); }}
                    className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
                      sourceType === 'topic' && !trending ? 'bg-[#C6F11D] text-[#050608]' : 'text-[#9AA0A6] hover:text-[#F5F5F5]'
                    }`}
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    Topic
                  </button>
                  <button
                    onClick={() => { setSourceType('url'); setTrending(false); }}
                    className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
                      sourceType === 'url' ? 'bg-[#C6F11D] text-[#050608]' : 'text-[#9AA0A6] hover:text-[#F5F5F5]'
                    }`}
                  >
                    <Globe className="h-3.5 w-3.5" />
                    URL
                  </button>
                </div>
              </div>

              {sourceType === 'topic' && (
                <>
                  <div>
                    <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">Category</label>
                    <div className="flex gap-1.5 overflow-x-auto pb-1">
                      {CATEGORIES.map((cat) => (
                        <button
                          key={cat.id}
                          onClick={() => { setCategory(cat.id); if (trending) fetchTrendingTopics(); else fetchSuggestions(cat.id); }}
                          className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-medium whitespace-nowrap transition-all duration-150 shrink-0 ${
                            category === cat.id ? 'bg-[#C6F11D] text-[#050608]' : 'bg-[#0E1116] text-[#9AA0A6] border border-[#252A33] hover:border-[#C6F11D] hover:text-[#F5F5F5]'
                          }`}
                        >
                          <span className="text-sm">{cat.emoji}</span>
                          {cat.name}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Trending toggle — inside Topic */}
                  {category && (
                    <div>
                      <button
                        onClick={() => {
                          setTrending(!trending);
                          if (!trending) fetchTrendingTopics();
                          else { setTrendingTopics([]); setTopic(''); }
                        }}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-150 ${
                          trending ? 'bg-[#FFC845] text-[#050608]' : 'bg-[#0E1116] text-[#9AA0A6] border border-[#252A33] hover:border-[#FFC845] hover:text-[#F5F5F5]'
                        }`}
                      >
                        {loadingTrending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Globe className="h-3.5 w-3.5" />}
                        Trending{trending ? ' ON' : ''}
                      </button>
                    </div>
                  )}

                  {trending ? (
                    <div>
                      <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">
                        Trending in {CATEGORIES.find(c => c.id === category)?.name || category}
                      </label>
                      {loadingTrending ? (
                        <div className="flex items-center gap-2 text-xs text-[#9AA0A6] py-3">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Searching trending topics...
                        </div>
                      ) : trendingTopics.length > 0 ? (
                        <>
                          <div className="flex flex-wrap gap-2">
                            {trendingTopics.map((t, i) => (
                              <button
                                key={i}
                                onClick={() => setTopic(t)}
                                className={`px-3 py-2 rounded-lg text-xs font-medium transition-all duration-150 ${
                                  topic === t
                                    ? 'bg-[#C6F11D] text-[#050608]'
                                    : 'bg-[#0E1116] text-[#9AA0A6] border border-[#252A33] hover:border-[#C6F11D] hover:text-[#F5F5F5]'
                                }`}
                              >
                                {t}
                              </button>
                            ))}
                          </div>
                          <div className="mt-2">
                            <input
                              value={topic}
                              onChange={(e) => setTopic(e.target.value)}
                              placeholder="Or type your own..."
                              className="w-full px-4 py-2 rounded-xl bg-[#0E1116] text-xs"
                            />
                          </div>
                        </>
                      ) : (
                        <p className="text-xs text-[#5F6772] py-2">
                          {category ? 'Click Trending to search' : 'Select a category first'}
                        </p>
                      )}
                    </div>
                  ) : (
                    <div className="relative">
                      <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">Subject</label>
                      <div className="relative flex items-center gap-2">
                        <input
                          ref={subjectRef}
                          value={topic}
                          onChange={(e) => setTopic(e.target.value)}
                          onFocus={() => { if (suggestedTopics.length > 0) setShowSuggestions(true); }}
                          onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
                          placeholder={category ? `e.g., ${currentSubjects[0] || 'Enter a subject'}` : 'Select a category first'}
                          disabled={!category}
                          className="w-full px-4 py-2.5 rounded-xl bg-[#0E1116] pr-10"
                        />
                        {category && (
                          <button
                            onClick={() => fetchSuggestions(category)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-[#9AA0A6] hover:text-[#C6F11D] transition-colors"
                            title="Suggest ideas"
                          >
                            {loadingSuggestions ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                          </button>
                        )}
                      </div>
                      {showSuggestions && suggestedTopics.length > 0 && (
                        <div className="absolute z-20 mt-1 w-full neo-card p-1.5 shadow-2xl max-h-48 overflow-y-auto">
                          {suggestedTopics.map((s, i) => (
                            <button
                              key={i}
                              onClick={() => { setTopic(s); setShowSuggestions(false); }}
                              className="w-full text-left px-3 py-2 text-xs text-[#9AA0A6] hover:bg-[rgba(198,241,29,0.08)] hover:text-[#F5F5F5] rounded-lg transition-all duration-150"
                            >
                              {s}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}

              {sourceType === 'url' && (
                <div>
                  <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">Website URL</label>
                  <input
                    type="url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://en.wikipedia.org/wiki/..."
                    className="w-full px-4 py-2.5 rounded-xl bg-[#0E1116]"
                  />
                  <p className="text-[11px] text-[#5F6772] mt-1">Paste any URL — the system will scrape and research from it</p>
                </div>
              )}

              {/* Video count + Duration row */}
              <div className="flex items-end gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">Videos</label>
                  <div className="flex items-center gap-3">
                    <input
                      type="number"
                      min="1"
                      max="32"
                      step="1"
                      value={genCount}
                      onChange={(e) => {
                        const raw = e.target.value;
                        if (raw === '') { setGenCount(''); return; }
                        let v = parseInt(raw, 10);
                        if (isNaN(v)) v = 1;
                        v = Math.max(1, Math.min(32, v));
                        setGenCount(v);
                      }}
                      onBlur={() => { if (genCount === '' || genCount < 1) setGenCount(1); }}
                      className="w-24 px-4 py-2.5 rounded-xl text-center bg-[#0E1116]"
                    />
                    <span className="text-xs text-[#5F6772]">
                      {genCount} · {(genCount / PER_PAGE).toFixed(0)} page{(genCount / PER_PAGE) > 1 ? 's' : ''}
                    </span>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2 text-right">Duration</label>
                  <div className="flex gap-1 flex-wrap">
                    {DURATIONS.map((d) => (
                      <button
                        key={d.value}
                        onClick={() => setDuration(d.value)}
                        className={`relative px-3 py-2 rounded-lg text-xs font-semibold transition-all duration-150 ${
                          duration === d.value
                            ? 'bg-[#C6F11D] text-[#050608]'
                            : 'bg-[#0E1116] text-[#9AA0A6] hover:text-[#F5F5F5] border border-[#252A33]'
                        }`}
                      >
                        {d.label}
                        {d.longForm && (
                          <span className="absolute -top-1.5 -right-1.5 px-1.5 py-0.5 rounded-full text-[8px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">
                            LONG
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                  <p className="text-[10px] text-[#5F6772] text-right mt-1">
                    {currentDuration.scenes} scenes · ~{currentDuration.estMin} min render
                  </p>
                </div>
              </div>

              {/* Aspect ratio + Transitions row */}
              <div className="border-t border-[#252A33] pt-4 grid grid-cols-2 gap-4">
                <div>
                  <label className="flex items-center gap-1.5 text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">
                    <Square className="h-3.5 w-3.5" />
                    Aspect Ratio
                  </label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {ASPECT_OPTIONS.map((a) => (
                      <button
                        key={a.value}
                        onClick={() => setAspectRatio(a.value)}
                        title={`${a.dims} · ${a.vram} · ${a.hint}`}
                        className={`px-2 py-2 rounded-lg text-[10px] font-semibold transition-all duration-150 ${
                          aspectRatio === a.value
                            ? 'bg-[#C6F11D] text-[#050608]'
                            : 'bg-[#0E1116] text-[#9AA0A6] hover:text-[#F5F5F5] border border-[#252A33]'
                        }`}
                      >
                        <div className="leading-tight">{a.label}</div>
                        <div className={`text-[9px] mt-0.5 ${aspectRatio === a.value ? 'text-[#050608]/70' : 'text-[#5F6772]'}`}>
                          {a.dims}
                        </div>
                      </button>
                    ))}
                  </div>
                  <p className="text-[10px] text-[#5F6772] mt-1.5">
                    {ASPECT_OPTIONS.find(a => a.value === aspectRatio)?.hint}
                  </p>
                </div>

                <div>
                  <label className="flex items-center gap-1.5 text-xs font-semibold text-[#9AA0A6] uppercase tracking-wider mb-2">
                    <Blend className="h-3.5 w-3.5" />
                    Transition
                  </label>
                  <div className="flex gap-2">
                    <select
                      value={transitionStyle}
                      onChange={(e) => setTransitionStyle(e.target.value)}
                      className="flex-1 px-2 py-2 rounded-lg text-xs bg-[#0E1116] border border-[#252A33] text-[#F5F5F5]"
                    >
                      {TRANSITION_OPTIONS.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <input
                      type="range"
                      min="0"
                      max="1.5"
                      step="0.1"
                      value={transitionDuration}
                      onChange={(e) => setTransitionDuration(parseFloat(e.target.value))}
                      disabled={transitionStyle === 'none'}
                      className="flex-1 accent-[#C6F11D] disabled:opacity-30"
                    />
                    <span className="text-[10px] text-[#5F6772] w-12 text-right">
                      {transitionStyle === 'none' ? '—' : `${transitionDuration.toFixed(1)}s`}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-[10px] text-[#5F6772]">Audio:</span>
                    {['match_video', 'none'].map((opt) => (
                      <button
                        key={opt}
                        onClick={() => setAudioTransition(opt)}
                        disabled={transitionStyle === 'none'}
                        className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all ${
                          audioTransition === opt
                            ? 'bg-[#C6F11D] text-[#050608]'
                            : 'bg-[#0E1116] text-[#9AA0A6] border border-[#252A33] disabled:opacity-30'
                        }`}
                      >
                        {opt === 'match_video' ? 'Match video' : 'Hard cut'}
                      </button>
                    ))}
                  </div>
                  {transitionStyle !== 'none' && (
                    <p className="text-[10px] text-amber-400/80 mt-1.5">
                      {currentDuration.scenes - 1} cuts × {transitionDuration.toFixed(1)}s = {((currentDuration.scenes - 1) * transitionDuration).toFixed(1)}s trimmed
                    </p>
                  )}
                </div>
              </div>

              {/* Production tabs: Style / Voice / Music */}
              <div className="border-t border-[#252A33] pt-4">
                <div className="flex gap-2 mb-3">
                  <button
                    onClick={() => setProductionTab(productionTab === 'style' ? null : 'style')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-150 ${
                      productionTab === 'style' ? 'bg-[#C6F11D] text-[#050608]' : 'bg-[#0E1116] text-[#9AA0A6] border border-[#252A33] hover:border-[#C6F11D]'
                    }`}
                  >
                    <Palette className="h-3.5 w-3.5" />
                    Style {AI_STYLES.find(s => s.id === selectedStyle)?.name || selectedStyle}
                  </button>
                  <button
                    onClick={() => setProductionTab(productionTab === 'voice' ? null : 'voice')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-150 ${
                      productionTab === 'voice' ? 'bg-[#C6F11D] text-[#050608]' : 'bg-[#0E1116] text-[#9AA0A6] border border-[#252A33] hover:border-[#C6F11D]'
                    }`}
                  >
                    <Mic className="h-3.5 w-3.5" />
                    Voice {VOICES.find(v => v.id === selectedVoice)?.name || selectedVoice}
                  </button>
                  <button
                    onClick={() => setProductionTab(productionTab === 'music' ? null : 'music')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-150 ${
                      productionTab === 'music' ? 'bg-[#C6F11D] text-[#050608]' : 'bg-[#0E1116] text-[#9AA0A6] border border-[#252A33] hover:border-[#C6F11D]'
                    }`}
                  >
                    <Music className="h-3.5 w-3.5" />
                    Music {MUSIC_GENRES.find(m => m.id === selectedMusic)?.name || selectedMusic}
                  </button>
                  <button
                    onClick={() => setProductionTab(productionTab === 'caption' ? null : 'caption')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-150 ${
                      productionTab === 'caption' ? 'bg-[#C6F11D] text-[#050608]' : 'bg-[#0E1116] text-[#9AA0A6] border border-[#252A33] hover:border-[#C6F11D]'
                    }`}
                  >
                    <Captions className="h-3.5 w-3.5" />
                    Captions {captionStyle !== 'standard' ? `(${captionStyle})` : ''}
                  </button>
                  <button
                    onClick={() => setProductionTab(productionTab === 'calendar' ? null : 'calendar')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-150 ${
                      productionTab === 'calendar' ? 'bg-[#C6F11D] text-[#050608]' : 'bg-[#0E1116] text-[#9AA0A6] border border-[#252A33] hover:border-[#C6F11D]'
                    }`}
                  >
                    <Calendar className="h-3.5 w-3.5" />
                    Schedule
                  </button>
                </div>

                {productionTab === 'style' && (
                  <div className="mb-4">
                    <div className="grid grid-cols-4 gap-2">
                      {AI_STYLES.map(style => (
                        <button
                          key={style.id}
                          onClick={() => setSelectedStyle(style.id)}
                          className={`flex flex-col items-center gap-1 p-2 rounded-lg text-[10px] font-medium transition-all duration-150 ${
                            selectedStyle === style.id
                              ? 'bg-[rgba(198,241,29,0.12)] text-[#C6F11D] border border-[rgba(198,241,29,0.3)]'
                              : 'bg-[#050608] text-[#9AA0A6] border border-[#252A33] hover:border-[#C6F11D] hover:text-[#F5F5F5]'
                          }`}
                        >
                          <span className="text-lg">{style.icon}</span>
                          <span className="text-center leading-tight">{style.name}</span>
                        </button>
                      ))}
                    </div>
                    {selectedStyle !== 'none' && (
                      <div className="mt-2">
                        <label className="text-[10px] text-[#9AA0A6] block mb-1">LoRA Strength: {loraStrength.toFixed(1)}</label>
                        <input
                          type="range" min="0" max="1.5" step="0.1"
                          value={loraStrength}
                          onChange={(e) => setLoraStrength(parseFloat(e.target.value))}
                          className="w-full max-w-xs accent-[#C6F11D]"
                        />
                        <div className="text-[10px] text-[#5F6772] mt-1.5 flex items-center gap-1.5 font-mono">
                          <Palette className="h-3 w-3 shrink-0" />
                          <span className="shrink-0 text-[#9AA0A6]">→</span>
                          <span className="truncate">{STYLE_LORA_PATHS[selectedStyle] || 'unknown style'}</span>
                          <span className="shrink-0">@</span>
                          <span className="shrink-0 text-[#C6F11D]">{loraStrength.toFixed(1)}</span>
                          <span className="shrink-0">strength</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {productionTab === 'voice' && (
                  <div className="mb-4">
                    <div className="flex items-center gap-2">
                      <select
                        value={selectedVoice}
                        onChange={(e) => setSelectedVoice(e.target.value)}
                        className="w-full max-w-xs px-3 py-2 rounded-xl bg-[#0E1116] border border-[#252A33] text-xs text-[#F5F5F5] outline-none focus:border-[#C6F11D]/50"
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
                          className={`flex items-center gap-1 px-2.5 py-2 rounded-xl text-[11px] font-medium border transition-all duration-150 ${
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
                        className="w-full mt-2 p-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-xs text-[#F5F5F5] outline-none focus:border-[#C6F11D]/50 resize-none"
                      />
                    )}
                  </div>
                )}

                {productionTab === 'music' && (
                  <div className="mb-4">
                    <div className="flex flex-wrap gap-2">
                      {MUSIC_GENRES.map(m => (
                        <div key={m.id} className="flex items-center">
                          <button
                            onClick={() => setSelectedMusic(m.id)}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-l-xl text-[11px] font-medium border border-r-0 transition-all duration-150 ${
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
                            className={`px-2 py-1.5 rounded-r-xl text-[11px] border transition-all duration-150 ${
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
                      <div key="custom" className="flex items-center">
                        <button
                          onClick={() => setSelectedMusic("__custom__")}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-l-xl text-[11px] font-medium border border-r-0 transition-all duration-150 ${
                            selectedMusic === "__custom__"
                              ? 'border-[#C6F11D] bg-[rgba(198,241,29,0.1)] text-[#C6F11D]'
                              : 'border-[#252A33] bg-transparent text-[#9AA0A6] hover:bg-[rgba(255,255,255,0.03)]'
                          }`}
                        >
                          ✏️ Custom
                        </button>
                        <div className="h-full min-h-[32px] w-px bg-[#252A33]" />
                      </div>
                    </div>
                    {selectedMusic === '__custom__' && (
                      <textarea
                        value={musicCustom}
                        onChange={e => setMusicCustom(e.target.value)}
                        placeholder="e.g. epic, cinematic, orchestral, dramatic, 120 BPM, E minor"
                        rows={2}
                        className="w-full mt-2 p-2.5 rounded-xl bg-[#0E1116] border border-[#252A33] text-xs text-[#F5F5F5] outline-none focus:border-[#C6F11D]/50 resize-none"
                      />
                    )}
                  </div>
                )}

                {productionTab === 'caption' && (
                  <div className="mb-4 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-[10px] text-[#9AA0A6] block mb-1">Style</label>
                        <div className="flex gap-1.5 flex-wrap">
                          {[
                            { id: 'standard', name: 'Standard' },
                            { id: 'bold', name: 'Bold' },
                            { id: 'minimal', name: 'Minimal' },
                            { id: 'boxed', name: 'Boxed' },
                            { id: 'karaoke', name: 'Karaoke' },
                          ].map(s => (
                            <button
                              key={s.id}
                              onClick={() => setCaptionStyle(s.id)}
                              className={`px-2.5 py-1.5 rounded-lg text-[11px] font-medium border transition-all duration-150 ${
                                captionStyle === s.id
                                  ? 'bg-[rgba(198,241,29,0.12)] text-[#C6F11D] border-[rgba(198,241,29,0.3)]'
                                  : 'border-[#252A33] bg-[#0E1116] text-[#9AA0A6] hover:border-[#C6F11D]'
                              }`}
                            >
                              {s.name}
                            </button>
                          ))}
                        </div>
                      </div>
                      <div>
                        <label className="text-[10px] text-[#9AA0A6] block mb-1">Animation</label>
                        <div className="flex gap-1.5 flex-wrap">
                          {[
                            { id: 'none', name: 'None' },
                            { id: 'word_by_word', name: 'Word' },
                            { id: 'fade', name: 'Fade' },
                            { id: 'pop', name: 'Pop' },
                            { id: 'typewriter', name: 'Type' },
                          ].map(a => (
                            <button
                              key={a.id}
                              onClick={() => setCaptionAnimation(a.id)}
                              className={`px-2.5 py-1.5 rounded-lg text-[11px] font-medium border transition-all duration-150 ${
                                captionAnimation === a.id
                                  ? 'bg-[rgba(198,241,29,0.12)] text-[#C6F11D] border-[rgba(198,241,29,0.3)]'
                                  : 'border-[#252A33] bg-[#0E1116] text-[#9AA0A6] hover:border-[#C6F11D]'
                              }`}
                            >
                              {a.name}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-[10px] text-[#9AA0A6] block mb-1">Font</label>
                        <select
                          value={captionFont}
                          onChange={e => setCaptionFont(e.target.value)}
                          className="w-full px-3 py-2 rounded-xl bg-[#0E1116] border border-[#252A33] text-xs text-[#F5F5F5] outline-none focus:border-[#C6F11D]/50"
                        >
                          {['Arial-Bold','Arial','Impact','Helvetica-Bold','Verdana-Bold','Trebuchet-MS','Comic-Sans-MS','Courier-New-Bold','Times-New-Roman-Bold','Georgia-Bold'].map(f => (
                            <option key={f} value={f} className="bg-[#0E1116] text-[#F5F5F5]">{f}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="text-[10px] text-[#9AA0A6] block mb-1">Size: {captionFontSize}px</label>
                        <input
                          type="range" min="24" max="96" step="2"
                          value={captionFontSize}
                          onChange={(e) => setCaptionFontSize(parseInt(e.target.value))}
                          className="w-full accent-[#C6F11D]"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-[10px] text-[#9AA0A6] block mb-1">Text Color</label>
                        <div className="flex items-center gap-2">
                          <input
                            type="color"
                            value={captionColor}
                            onChange={(e) => setCaptionColor(e.target.value)}
                            className="w-10 h-9 rounded-lg bg-[#0E1116] border border-[#252A33] cursor-pointer"
                          />
                          <input
                            type="text"
                            value={captionColor}
                            onChange={(e) => setCaptionColor(e.target.value)}
                            className="flex-1 px-2 py-1.5 rounded-lg bg-[#0E1116] border border-[#252A33] text-xs text-[#F5F5F5] outline-none focus:border-[#C6F11D]/50 font-mono"
                          />
                        </div>
                      </div>
                      <div>
                        <label className="text-[10px] text-[#9AA0A6] block mb-1">Stroke Color</label>
                        <div className="flex items-center gap-2">
                          <input
                            type="color"
                            value={captionStrokeColor}
                            onChange={(e) => setCaptionStrokeColor(e.target.value)}
                            className="w-10 h-9 rounded-lg bg-[#0E1116] border border-[#252A33] cursor-pointer"
                          />
                          <input
                            type="text"
                            value={captionStrokeColor}
                            onChange={(e) => setCaptionStrokeColor(e.target.value)}
                            className="flex-1 px-2 py-1.5 rounded-lg bg-[#0E1116] border border-[#252A33] text-xs text-[#F5F5F5] outline-none focus:border-[#C6F11D]/50 font-mono"
                          />
                        </div>
                      </div>
                    </div>
                    <div>
                      <label className="text-[10px] text-[#9AA0A6] block mb-1">Stroke Width: {captionStrokeWidth}px</label>
                      <input
                        type="range" min="0" max="8" step="1"
                        value={captionStrokeWidth}
                        onChange={(e) => setCaptionStrokeWidth(parseInt(e.target.value))}
                        className="w-full accent-[#C6F11D]"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Videos phase — compact bar */}
      {phase === 'videos' && (
        <div className="neo-card mb-4 px-4 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-3 text-xs">
            <span className="text-[#9AA0A6]">Phase: <span className="text-[#C6F11D] font-bold">Video Generation</span></span>
            <span className="text-[#5F6772]">|</span>
            <span className="text-[#9AA0A6]">{readyCount}/{videoCount} ready</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCancelVideos}
              className="neo-btn-secondary flex items-center gap-1.5 px-3 py-1.5 text-[11px] border-[#FF5757] text-[#FF5757] hover:bg-[rgba(255,87,87,0.1)]"
            >
              <Square className="h-3 w-3" />
              Cancel All
            </button>
            <button
              onClick={handleArchiveNow}
              disabled={postedCount === 0}
              className="neo-btn-secondary flex items-center gap-1.5 px-3 py-1.5 text-[11px] disabled:opacity-30"
            >
              <Archive className="h-3 w-3" />
              Archive
            </button>
          </div>
        </div>
      )}

      {/* Waiting banner while scripts are being generated */}
      {generatingScripts && (
        <div className="mb-4 px-4 py-3 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center gap-3">
          <Loader2 className="h-4 w-4 text-amber-400 animate-spin shrink-0" />
          <div className="text-xs">
            <span className="text-amber-300 font-semibold">Generating scripts…</span>
            <span className="text-amber-200/60 ml-2">
              This takes 2–5 min for standard videos, longer for 180s/300s.
              The script card will appear here automatically — then click it to review
              and click <span className="text-amber-300 font-semibold">Generate Video</span> to start rendering.
            </span>
          </div>
        </div>
      )}

      {/* Video / Script Grid */}
      {hasVideos ? (
        <>
          <div className="grid grid-cols-4 gap-4">
            {pagedVideos.map((video) => (
              <VideoCard
                key={video.index}
                video={video}
                project={project}
                getStepLabel={getStepLabel}
                onPost={() => handlePost(video.index)}
                onDelete={() => handleDeleteVideo(video.index)}
                onEdit={() => setEditingVideo(video)}
                mode={phase === 'scripts' ? 'script' : 'video'}
                onRegenScript={phase === 'scripts' ? handleRegenScript : null}
                onGenerateVideo={!video.job || video.job.status === 'cancelled' || video.job.status === 'failed' ? handleGenerateSingleVideo : null}
                onRemovePlaceholder={generatingScripts ? handleRemovePlaceholder : null}
                onCleanScenes={phase === 'videos' ? () => handleCleanScenes(video.index) : null}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 mt-6">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={safePage <= 1}
                className="neo-btn-ghost p-2 disabled:opacity-30"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={`w-8 h-8 rounded-lg text-xs font-semibold transition-all duration-150 ${
                    p === safePage ? 'bg-[#C6F11D] text-[#050608]' : 'bg-[#0E1116] text-[#9AA0A6] border border-[#252A33] hover:border-[#C6F11D]'
                  }`}
                >
                  {p}
                </button>
              ))}
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={safePage >= totalPages}
                className="neo-btn-ghost p-2 disabled:opacity-30"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="neo-card p-12 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-[rgba(198,241,29,0.08)] flex items-center justify-center border border-[rgba(198,241,29,0.2)]">
            <Play className="h-8 w-8 text-[#C6F11D] ml-0.5" />
          </div>
          <h3 className="text-lg font-bold text-[#F5F5F5] mb-2">No content yet</h3>
          <p className="text-sm text-[#9AA0A6]">Pick a category, enter a subject, and generate scripts first.</p>
        </div>
      )}

      {/* Edit Modal */}
      {editingVideo && (
        <EditVideoModal
          video={editingVideo}
          project={project}
          onClose={() => setEditingVideo(null)}
          onSave={(overrides) => handleSaveOverrides(editingVideo.index, overrides)}
          onSceneRegen={async (videoIndex, sceneIndex) => {
            // Refresh project videos so the new clip is reflected.
            // The endpoint returns {status, videos, video_count} so we
            // MUST pull out .videos — passing the wrapper object crashes
            // every videos.some/filter/length call on the next render
            // and unmounts the page.
            try {
              const res = await api.get(`/projects/${project.id}/videos`);
              const payload = res.data || {};
              if (Array.isArray(payload.videos)) {
                setVideos(payload.videos);
                if (typeof payload.video_count === 'number') {
                  setVideoCount(payload.video_count);
                }
              } else if (Array.isArray(payload)) {
                setVideos(payload);
              }
            } catch (e) {
              console.error('Failed to refresh videos after scene regen:', e);
            }
          }}
          onReassemble={async (videoIndex) => {
            // Same wrapper-object trap as onSceneRegen — see comment above.
            try {
              const res = await api.get(`/projects/${project.id}/videos`);
              const payload = res.data || {};
              if (Array.isArray(payload.videos)) {
                setVideos(payload.videos);
                if (typeof payload.video_count === 'number') {
                  setVideoCount(payload.video_count);
                }
              } else if (Array.isArray(payload)) {
                setVideos(payload);
              }
            } catch (e) {
              console.error('Failed to refresh videos after reassemble:', e);
            }
          }}
        />
      )}

      <ScheduleCalendar projectId={id} open={showCalendar} onClose={() => setShowCalendar(false)} />
    </div>
  );
}

export default ProjectDetail;
