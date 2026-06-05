import React, { useState, useEffect, useRef } from 'react';
import { Send, Settings, Clock, Loader2, Play, RefreshCw, Archive, Eye, X, Mic, Music, Sparkles } from 'lucide-react';
import { VOICES, MUSIC_GENRES } from '../constants/production';

function formatDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' })
    + ' · ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function VideoCard({ video, project, getStepLabel, onPost, onEdit, mode, onRegenScript, onRemovePlaceholder }) {
  const { index, script, upload, job, overrides } = video;
  const isRunning = job?.status === 'running';
  const isComplete = job?.status === 'completed';
  const isFailed = job?.status === 'failed';
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

  useEffect(() => {
    if (isRunning) {
      if (!startRef.current) startRef.current = Date.now();
      const interval = setInterval(() => {
        if (startRef.current) setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
      }, 1000);
      return () => clearInterval(interval);
    } else if (isComplete || isFailed) {
      startRef.current = null;
      setElapsed(0);
    }
  }, [isRunning, isComplete, isFailed]);

  const formatTime = (secs) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const eta = progress > 5 && elapsed > 0 ? Math.floor(elapsed * (100 / progress - 1)) : 0;

  // SCRIPT MODE preview
  if (mode === 'script') {
    if (video.generating) {
      return (
        <div className="neo-card overflow-hidden flex flex-col aspect-[5/8] transition-all duration-150 origin-center scale-[0.7] relative">
          <div className="neo-titlebar-queued flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <span className="neo-dot neo-dot-clip animate-pulse" />
              GENERATING
            </span>
            <span className="text-[10px] opacity-70">#{index + 1}</span>
          </div>
          <div className="flex-1 flex flex-col items-center justify-center p-8">
            <Loader2 className="h-10 w-10 text-[#C6F11D] animate-spin mb-4" />
            <p className="text-xs text-[#9AA0A6] text-center">
              Script #{index + 1} is being generated...
            </p>
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
        </div>
      </div>

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
          <div className="absolute inset-0 flex items-center justify-center bg-[#0E1116]">
            <div className="text-center">
              <div className="w-16 h-16 mx-auto mb-3 rounded-2xl bg-[rgba(107,255,100,0.08)] border border-[rgba(107,255,100,0.2)] flex items-center justify-center">
                <Play className="h-8 w-8 text-[#6BFF64] ml-0.5" />
              </div>
              <p className="text-[11px] text-[#9AA0A6]">Video ready</p>
            </div>
          </div>
        ) : isFailed ? (
          <div className="absolute inset-0 flex items-center justify-center bg-[#0E1116]">
            <div className="text-center">
              <div className="w-16 h-16 mx-auto mb-3 rounded-2xl bg-[rgba(255,87,87,0.08)] border border-[rgba(255,87,87,0.2)] flex items-center justify-center">
                <span className="text-3xl">!</span>
              </div>
              <p className="text-[11px] text-[#FF5757]">Failed</p>
            </div>
          </div>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center bg-[#0E1116]">
            <div className="text-center">
              <div className="w-16 h-16 mx-auto mb-3 rounded-2xl bg-[rgba(95,103,114,0.1)] border border-[rgba(95,103,114,0.2)] flex items-center justify-center">
                <Clock className="h-8 w-8 text-[#5F6772]" />
              </div>
              <p className="text-[11px] text-[#5F6772]">Queued</p>
            </div>
          </div>
        )}

        {isComplete && (
          <div className="absolute bottom-2 right-2 bg-[#050608]/80 text-white text-[11px] font-medium px-1.5 py-0.5 rounded border border-[#252A33]">
            <span className="inline-flex items-center gap-1">
              <Play className="h-2.5 w-2.5 fill-white" />
              0:45
            </span>
          </div>
        )}

        {isArchived && (
          <div className="absolute top-2 left-2 bg-[rgba(198,241,29,0.12)] text-[#C6F11D] text-[10px] font-semibold px-2 py-0.5 rounded-full border border-[rgba(198,241,29,0.3)] flex items-center gap-1">
            <Archive className="h-3 w-3" />
            Archived
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
          {canPost && (
            <button
              onClick={onPost}
              className="neo-btn-secondary p-1.5"
              title="Post now"
            >
              <Send className="h-3.5 w-3.5" />
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
