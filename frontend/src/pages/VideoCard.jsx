import React, { useState, useEffect, useRef } from 'react';
import { Send, Settings, Clock, Loader2, Play, RefreshCw, Archive, Eye, X, Mic, Music, Sparkles, Trash2, Ban, StopCircle, Video } from 'lucide-react';
import api from '../api/client';
import { VOICES, MUSIC_GENRES } from '../constants/production';

function formatDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' })
    + ' · ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function VideoCard({ video, project, getStepLabel, onPost, onEdit, onDelete, mode, onRegenScript, onRemovePlaceholder, onGenerateVideo, onCleanScenes }) {
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState('');

  const handleCancel = async () => {
    if (!job?.id) return;
    if (!window.confirm(`Cancel video ${serial}?\n\nThis stops the running ComfyUI generation. Partial work will be lost.`)) return;
    setCancelling(true);
    setCancelError('');
    try {
      await api.post(`/jobs/${job.id}/cancel`);
      // The video card will re-render with status='cancelled' on next poll
    } catch (e) {
      setCancelError(e.response?.data?.detail || e.message || 'Cancel failed');
    } finally {
      setCancelling(false);
    }
  };

  const { index, script, upload, job, overrides, generatingDuration } = video;
  const isRunning = job?.status === 'running';
  const isComplete = job?.status === 'completed';
  const isFailed = job?.status === 'failed';
  const isCancelled = job?.status === 'cancelled';
  const isQueued = !job || job?.status === 'queued';
  const progress = job?.progress || 0;
  const canPost = isComplete || upload?.status === 'queued';
  const isArchived = !!upload?.archived_at;
  const vs = project.visual_settings || {};
  const displayStyle = overrides?.ai_style || vs.ai_style || 'default';

  const serial = script?.global_serial || video.global_serial || (index + 1);
  const dateStr = formatDateTime(script?.created_at || job?.created_at);

  // Elapsed timer
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(null);
  // Smoothed velocity (percent per second) for stable ETA
  const velocityRef = useRef(null);          // EMA-smoothed %/s
  const lastProgressRef = useRef(0);
  const lastProgressAtRef = useRef(null);
  const lastEtaRef = useRef(null);            // last computed ETA (for monotonic display)

  useEffect(() => {
    if (isRunning) {
      if (!startRef.current) startRef.current = Date.now();
      if (lastProgressAtRef.current === null) lastProgressAtRef.current = Date.now();
      const interval = setInterval(() => {
        if (startRef.current) {
          const nowElapsed = Math.floor((Date.now() - startRef.current) / 1000);
          setElapsed(nowElapsed);
        }
      }, 1000);
      return () => clearInterval(interval);
    } else if (isComplete || isFailed) {
      startRef.current = null;
      velocityRef.current = null;
      lastProgressRef.current = 0;
      lastProgressAtRef.current = null;
      lastEtaRef.current = null;
      setElapsed(0);
    }
  }, [isRunning, isComplete, isFailed]);

  const formatTime = (secs) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  // --- ETA: smooth, monotonically decreasing -------------------------
  // Backend progress updates are coarse (5, 15, 30, 55, 70, 80, 100)
  // so a naive (elapsed * 100/progress) makes ETA jump UP between
  // backend updates as elapsed grows. Solution: track velocity only
  // at the moments progress actually changes, EMA-smooth it, and
  // only ever DECREASE the displayed ETA unless a faster stage
  // actually completed.
  const computeEta = (prog, el) => {
    if (!isRunning) return 0;
    if (prog >= 100) return 0;
    if (el <= 0) return 0;

    const now = Date.now();
    const lastProg = lastProgressRef.current;
    const lastAt = lastProgressAtRef.current;

    // If progress moved, update velocity (instantaneous)
    if (prog !== lastProg && lastAt !== null && now > lastAt) {
      const dt = (now - lastAt) / 1000;
      const dp = prog - lastProg;
      if (dt > 0 && dp >= 0) {
        const inst = dp / dt; // %/s
        if (velocityRef.current === null) {
          velocityRef.current = inst;
        } else {
          // EMA: 0.4 weight to new sample (responsive but stable)
          velocityRef.current = 0.4 * inst + 0.6 * velocityRef.current;
        }
      }
      lastProgressRef.current = prog;
      lastProgressAtRef.current = now;
    }

    const v = velocityRef.current;
    if (!v || v <= 0.001) {
      // No velocity yet (just started) — fall back to a conservative estimate
      // Assume the whole job takes ~2 minutes based on typical LTX runs
      return Math.max(0, 120 - el);
    }

    const remaining = (100 - prog) / v;
    // Clamp to a sane range so a tiny velocity doesn't blow ETA up
    return Math.max(0, Math.min(remaining, 1800));
  };

  const rawEta = computeEta(progress, elapsed);

  // Monotonic-decreasing display: never let the shown ETA go up
  // (unless a clearly-faster stage just started)
  let displayEta = rawEta;
  if (lastEtaRef.current !== null) {
    const drift = lastEtaRef.current - rawEta;
    if (drift < -3) {
      // New ETA is more than 3s higher than the last one — a slow stage
      // finished and the new sample is artificially high. Hold the old ETA.
      displayEta = lastEtaRef.current;
    } else {
      displayEta = rawEta;
    }
  }
  // Decay displayed ETA slowly while we wait for the next progress update,
  // so the displayed number keeps trending down even between backend ticks.
  if (displayEta > 0 && rawEta > 0 && lastEtaRef.current !== null) {
    const decay = Math.max(0, lastEtaRef.current - 1); // -1s per tick
    displayEta = Math.min(displayEta, decay);
  }
  lastEtaRef.current = displayEta;

  const eta = Math.floor(displayEta);

  // SCRIPT MODE preview
  if (mode === 'script') {
    if (video.generating) {
      return (
        <div className="neo-card overflow-hidden flex flex-col aspect-[5/8] transition-all duration-150 relative">
          <div className="neo-titlebar-queued flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <span className="neo-dot neo-dot-clip animate-pulse" />
              GENERATING
            </span>
            <span className="text-[10px] opacity-70">#{index + 1}</span>
          </div>
          <div className="flex-1 flex flex-col items-center justify-center p-8 gap-3">
            <Loader2 className="h-10 w-10 text-[#C6F11D] animate-spin" />
            {generatingDuration && (
              <div className="text-center">
                <div className="text-[11px] text-[#C6F11D] font-semibold">{generatingDuration}s video</div>
                <div className="text-[10px] text-[#5F6772] mt-0.5">~{Math.ceil(generatingDuration / 60 * 2)}–{Math.ceil(generatingDuration / 60 * 4)} min</div>
              </div>
            )}
          </div>
          {onRemovePlaceholder && (
            <button
              onClick={() => onRemovePlaceholder(index)}
              className="absolute top-2 right-2 p-1.5 rounded-lg bg-[rgba(0,0,0,0.5)] text-[#9AA0A6] hover:text-[#FF5757] hover:bg-[rgba(255,87,87,0.15)] transition-colors z-10"
              title="Cancel this slot"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      );
    }
    return (
      <div className="neo-card overflow-hidden flex flex-col aspect-[5/8] transition-all duration-150 hover:border-[#C6F11D]">
        <div className="neo-titlebar-queued flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <span className="neo-dot neo-dot-clip" />
            SCRIPT
          </span>
          <span className="text-[10px] opacity-70">#{serial}</span>
        </div>
        <div className="p-4 flex flex-col gap-3 flex-1">
          <div>
            <h3 className="text-sm font-bold text-[#F5F5F5] line-clamp-2 leading-snug">
              {script?.title || `Video ${index + 1}`}
            </h3>
            {dateStr && <p className="text-[10px] text-[#5F6772] mt-1">{dateStr}</p>}
          </div>
          <p className="text-[11px] text-[#9AA0A6] line-clamp-4 leading-relaxed">
            {script?.content?.substring(0, 300) || 'No script yet'}
          </p>
          <div className="flex items-center gap-3 text-[10px] text-[#5F6772] mt-auto flex-wrap">
            <span>{script?.scenes?.length || 0} scenes</span>
            {displayStyle && displayStyle !== 'none' && (
              <span className="text-[#C6F11D] capitalize">{displayStyle.replace(/_/g, ' ')}</span>
            )}
            {overrides?.voice_id && (() => {
              const v = VOICES.find(x => x.id === overrides.voice_id);
              return v ? <span className="text-[#6BFF64]">{v.name}</span> : null;
            })()}
            {overrides?.music_genre && (() => {
              const m = MUSIC_GENRES.find(x => x.id === overrides.music_genre);
              return m ? <span>{m.emoji} {m.name}</span> : null;
            })()}
            {overrides?.music_prompt && (
              <span className="text-[#9AA0A6]">🎼 custom prompt</span>
            )}
          </div>
        </div>
        <div className="px-4 pb-3 flex gap-2">
          {onGenerateVideo && (
            <button
              onClick={() => onGenerateVideo(video.index)}
              className="neo-btn-primary flex items-center gap-1.5 px-3 py-1.5 text-[11px]"
            >
              <Video className="h-3 w-3" />
              Generate Video
            </button>
          )}
          {onRegenScript && (
            <button
              onClick={() => onRegenScript(video.index)}
              className="neo-btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-[11px]"
            >
              <RefreshCw className="h-3 w-3" />
              Regen Script
            </button>
          )}
          {onEdit && (
            <button
              onClick={onEdit}
              className="neo-btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-[11px]"
            >
              <Settings className="h-3 w-3" />
              Settings
            </button>
          )}
        </div>
      </div>
    );
  }

  // VIDEO MODE (existing behavior with enhancements)
  let titlebarClass = 'neo-titlebar-queued';
  let titlebarLabel = 'QUEUED';
  let dotType = 'model';
  if (isRunning) {
    if (progress < 15) { titlebarClass = 'neo-titlebar-generating'; titlebarLabel = 'RESEARCH'; dotType = 'clip'; }
    else if (progress < 30) { titlebarClass = 'neo-titlebar-generating'; titlebarLabel = 'SCRIPT'; dotType = 'model'; }
    else if (progress < 55) { titlebarClass = 'neo-titlebar-generating'; titlebarLabel = 'KSAMPLER'; dotType = 'latent'; }
    else if (progress < 70) { titlebarClass = 'neo-titlebar-audio'; titlebarLabel = 'AUDIO'; dotType = 'audio'; }
    else { titlebarClass = 'neo-titlebar-generating'; titlebarLabel = 'ASSEMBLE'; dotType = 'video'; }
  } else if (isComplete) {
    titlebarClass = 'neo-titlebar-ready';
    titlebarLabel = upload?.status === 'queued' || upload?.status === 'done' ? 'UPLOADED' : 'COMPLETE';
    dotType = 'video';
  } else if (isFailed) {
    titlebarClass = 'neo-titlebar-error';
    titlebarLabel = 'ERROR';
    dotType = 'model';
  } else if (isCancelled) {
    titlebarClass = 'neo-titlebar-error';
    titlebarLabel = 'CANCELLED';
    dotType = 'model';
  }

  return (
    <div className="neo-card overflow-hidden flex flex-col transition-all duration-150 hover:border-[#C6F11D] relative">
      {/* Titlebar */}
      <div className={`${titlebarClass} flex items-center justify-between`}>
        <span className="flex items-center gap-1.5">
          <span className={`neo-dot neo-dot-${dotType}`} />
          {titlebarLabel}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] opacity-70 font-mono">#{serial}</span>
          {isRunning && <span className="text-[10px] opacity-70">{formatTime(elapsed)}</span>}
          {isRunning && job?.id && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="ml-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-[rgba(255,87,87,0.18)] text-[#FF5757] border border-[rgba(255,87,87,0.35)] hover:bg-[rgba(255,87,87,0.3)] disabled:opacity-50 transition-colors"
              title="Cancel generation (stops ComfyUI)"
            >
              <StopCircle className="h-3 w-3" />
              {cancelling ? 'Stopping…' : 'Cancel'}
            </button>
          )}
        </div>
      </div>
      {cancelError && (
        <div className="px-3 py-1.5 text-[10px] text-[#FF5757] bg-[rgba(255,87,87,0.08)] border-b border-[rgba(255,87,87,0.2)]">
          {cancelError}
        </div>
      )}

      {/* Preview area */}
      <div className="relative aspect-[5/8] bg-[#050608] overflow-hidden">
        {isRunning ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center p-4">
            <div className="relative w-14 h-14 mb-3">
              <div className="absolute inset-0 rounded-full border-3 border-[rgba(255,255,255,0.06)]" />
              <div className="absolute inset-0 rounded-full border-3 border-transparent border-t-[#C6F11D] border-r-[rgba(198,241,29,0.5)] animate-spin" />
            </div>
            <div className="w-full space-y-2">
              <div className="flex justify-between text-[11px]">
                <span className="text-[#9AA0A6]">{job?.logs?.split(' - ')[0] || 'Processing...'}</span>
                <span className="text-[#F5F5F5] font-semibold">{progress}%</span>
              </div>
              <div className="neo-progress">
                <div className="neo-progress-fill" style={{ width: `${progress}%` }} />
              </div>
              <div className="flex justify-between text-[10px] text-[#5F6772]">
                <span>ETA {eta > 0 ? formatTime(eta) : '--:--'}</span>
                <span>{formatTime(elapsed)}</span>
              </div>
            </div>
          </div>
        ) : isComplete ? (
          upload?.video_url ? (
            <video
              src={upload.video_url}
              controls
              className="absolute inset-0 w-full h-full object-cover"
              poster={undefined}
              preload="metadata"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center bg-[#0E1116]">
              <div className="w-16 h-16 rounded-2xl bg-[rgba(107,255,100,0.08)] border border-[rgba(107,255,100,0.2)] flex items-center justify-center">
                <Play className="h-8 w-8 text-[#6BFF64] ml-0.5" />
              </div>
            </div>
          )
        ) : isFailed ? (
          <div className="absolute inset-0 flex items-center justify-center bg-[#0E1116]">
            <div className="w-16 h-16 rounded-2xl bg-[rgba(255,87,87,0.08)] border border-[rgba(255,87,87,0.2)] flex items-center justify-center">
              <span className="text-3xl text-[#FF5757]">!</span>
            </div>
          </div>
        ) : isCancelled && onGenerateVideo ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#0E1116] gap-3">
            <div className="w-14 h-14 rounded-2xl bg-[rgba(95,103,114,0.1)] border border-[rgba(95,103,114,0.2)] flex items-center justify-center">
              <Ban className="h-7 w-7 text-[#5F6772]" />
            </div>
            <p className="text-xs text-[#9AA0A6]">Cancelled</p>
            <button
              onClick={() => onGenerateVideo(video.index)}
              className="neo-btn-primary flex items-center gap-1.5 px-3 py-1.5 text-[11px]"
              title="Retry video generation"
            >
              <Video className="h-3 w-3" />
              Retry Generation
            </button>
          </div>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center bg-[#0E1116]">
            <div className="w-16 h-16 rounded-2xl bg-[rgba(95,103,114,0.1)] border border-[rgba(95,103,114,0.2)] flex items-center justify-center">
              <Clock className="h-8 w-8 text-[#5F6772]" />
            </div>
          </div>
        )}

        {isArchived && (
          <div className="absolute top-2 left-2 w-7 h-7 rounded-full bg-[rgba(198,241,29,0.2)] text-[#C6F11D] flex items-center justify-center border border-[rgba(198,241,29,0.4)]" title="Archived">
            <Archive className="h-3.5 w-3.5" />
          </div>
        )}
      </div>

      {isComplete && (
        <div className="absolute right-0 top-1/2 -translate-y-1/2 -mr-[5px]">
          <span className={`neo-dot neo-dot-${dotType}`} />
        </div>
      )}

      {/* Meta section */}
      <div className="p-3 flex gap-3 items-start">
        <div className="shrink-0">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border ${
            isComplete ? 'bg-[rgba(107,255,100,0.1)] text-[#6BFF64] border-[rgba(107,255,100,0.3)]' :
            isRunning ? 'bg-[rgba(255,200,69,0.1)] text-[#FFC845] border-[rgba(255,200,69,0.3)]' :
            isFailed ? 'bg-[rgba(255,87,87,0.1)] text-[#FF5757] border-[rgba(255,87,87,0.3)]' :
            'bg-[rgba(95,103,114,0.1)] text-[#5F6772] border-[rgba(95,103,114,0.3)]'
          }`}>
            {serial}
          </div>
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-bold text-[#F5F5F5] line-clamp-2 leading-snug">
            {script?.title || `Video ${index + 1}`}
          </h3>
          {dateStr && <p className="text-[10px] text-[#5F6772] mt-0.5">{dateStr}</p>}
          <p className="text-[11px] text-[#9AA0A6] mt-0.5 truncate">
            {displayStyle && displayStyle !== 'default' && displayStyle !== 'none' && (
              <span className="text-[#C6F11D]">{displayStyle.replace(/_/g, ' ')}</span>
            )}
          </p>
        </div>
        <div className="shrink-0 flex items-center gap-1">
          {onCleanScenes && isComplete && !overrides?.intermediate_cleaned && (
            <button
              onClick={onCleanScenes}
              className="neo-btn-ghost p-1.5"
              title="Free disk space: delete scene clips and audio (keeps final video)"
            >
              <Archive className="h-3.5 w-3.5 text-[#FFC845]" />
            </button>
          )}
          {onCleanScenes && overrides?.intermediate_cleaned && (
            <span
              className="neo-btn-ghost p-1.5 cursor-default"
              title={`Intermediate scenes cleaned at ${overrides.intermediate_cleaned_at || 'unknown'}`}
            >
              <Archive className="h-3.5 w-3.5 text-[#5F6772]" />
            </span>
          )}
          {onDelete && (
            <button
              onClick={onDelete}
              className="neo-btn-danger p-1.5"
              title="Delete video"
            >
              <Trash2 className="h-3.5 w-3.5 text-[#FF5757]" />
            </button>
          )}
          {canPost && (
            <button
              onClick={onPost}
              className="neo-btn-secondary p-1.5"
              title="Post now"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          )}
          {onGenerateVideo && (!video.job || video.job?.status === 'cancelled' || video.job?.status === 'failed') && (
            <button
              onClick={() => onGenerateVideo(video.index)}
              className="neo-btn-primary p-1.5"
              title="Generate video for this script"
            >
              <Video className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={onEdit}
            disabled={isRunning}
            className="neo-btn-ghost p-1.5 disabled:opacity-30"
            title="Edit style, voice, music"
          >
            <Settings className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Override badges */}
      {overrides && (overrides.ai_style || overrides.voice_id || overrides.music_genre || overrides.music_prompt || overrides.lora_strength != null) && (
        <div className="px-3 pb-3 flex gap-1.5 flex-wrap">
          {overrides?.ai_style && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[rgba(198,241,29,0.08)] text-[#C6F11D] border border-[rgba(198,241,29,0.2)] capitalize flex items-center gap-1">
              <Sparkles className="h-2.5 w-2.5" />
              {overrides.ai_style.replace(/_/g, ' ')}
            </span>
          )}
          {overrides?.voice_id && (() => {
            const v = VOICES.find(x => x.id === overrides.voice_id);
            const label = v ? v.name : overrides.voice_id;
            return (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[rgba(107,255,100,0.08)] text-[#6BFF64] border border-[rgba(107,255,100,0.2)] flex items-center gap-1">
                <Mic className="h-2.5 w-2.5" />
                {label}
              </span>
            );
          })()}
          {overrides?.music_genre && (() => {
            const m = MUSIC_GENRES.find(x => x.id === overrides.music_genre);
            const label = m ? `${m.emoji} ${m.name}` : overrides.music_genre;
            return (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[rgba(255,200,69,0.08)] text-[#FFC845] border border-[rgba(255,200,69,0.2)] flex items-center gap-1">
                <Music className="h-2.5 w-2.5" />
                {label}
              </span>
            );
          })()}
          {overrides?.music_prompt && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[rgba(95,103,114,0.1)] text-[#9AA0A6] border border-[#252A33] flex items-center gap-1 max-w-[140px]">
              <Music className="h-2.5 w-2.5 shrink-0" />
              <span className="truncate">Custom prompt</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default VideoCard;
