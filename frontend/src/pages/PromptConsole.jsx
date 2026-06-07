import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Terminal, RefreshCw, Filter, Search, Copy, ExternalLink,
  AlertCircle, CheckCircle, Clock, RotateCw, Trash2, ChevronDown, ChevronRight, Sparkles, ArrowLeft
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';

const POLL_INTERVAL_MS = 2000;

function PromptConsole() {
  const navigate = useNavigate();
  const [prompts, setPrompts] = useState([]);
  const [stats, setStats] = useState(null);
  const [projects, setProjects] = useState([]);
  const [filterProject, setFilterProject] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterJob, setFilterJob] = useState('all');
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState(new Set());
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [error, setError] = useState(null);
  const [copyToast, setCopyToast] = useState(null);
  const expandedRef = useRef(new Set());

  // Persist expansion across refreshes
  useEffect(() => { expandedRef.current = expanded; }, [expanded]);

  const loadAll = async () => {
    try {
      const [promptsRes, statsRes, projectsRes] = await Promise.all([
        api.get('/prompts/', { params: { limit: 200 } }),
        api.get('/prompts/stats/summary'),
        api.get('/projects/'),
      ]);
      setPrompts(promptsRes.data || []);
      setStats(statsRes.data || null);
      setProjects(projectsRes.data || []);
      setError(null);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Failed to load prompts');
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(loadAll, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [autoRefresh]);

  // Unique job IDs for the filter dropdown
  const jobIds = useMemo(() => {
    const ids = new Set();
    prompts.forEach(p => { if (p.job_id != null) ids.add(p.job_id); });
    return Array.from(ids).sort((a, b) => b - a);
  }, [prompts]);

  // Filter
  const filtered = useMemo(() => {
    return prompts.filter(p => {
      if (filterProject !== 'all' && String(p.project_id) !== String(filterProject)) return false;
      if (filterStatus !== 'all' && p.status !== filterStatus) return false;
      if (filterJob !== 'all' && String(p.job_id) !== String(filterJob)) return false;
      if (search) {
        const s = search.toLowerCase();
        const hay = `${p.final_prompt || ''} ${p.sanitized_visual_description || ''} ${p.narration_text || ''}`.toLowerCase();
        if (!hay.includes(s)) return false;
      }
      return true;
    });
  }, [prompts, filterProject, filterStatus, filterJob, search]);

  // The currently-running prompt (sticky header)
  const activePrompt = useMemo(() => {
    return prompts.find(p => p.status === 'running') || null;
  }, [prompts]);

  const toggleExpand = (id) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const copyText = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopyToast(label);
      setTimeout(() => setCopyToast(null), 1500);
    } catch (e) {
      setCopyToast('Copy failed');
      setTimeout(() => setCopyToast(null), 1500);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this prompt log row?')) return;
    try {
      await api.delete(`/prompts/${id}`);
      loadAll();
    } catch (e) {
      alert('Delete failed: ' + (e?.response?.data?.detail || e.message));
    }
  };

  const handleClearAll = async () => {
    if (!confirm('Delete ALL prompt log rows? This cannot be undone.')) return;
    try {
      await api.delete('/prompts/');
      loadAll();
    } catch (e) {
      alert('Clear failed: ' + (e?.response?.data?.detail || e.message));
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'completed':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[rgba(107,255,100,0.12)] text-[#6BFF64] border border-[rgba(107,255,100,0.3)]"><CheckCircle className="h-2.5 w-2.5" />DONE</span>;
      case 'failed':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[rgba(255,87,87,0.12)] text-[#FF5757] border border-[rgba(255,87,87,0.3)]"><AlertCircle className="h-2.5 w-2.5" />FAIL</span>;
      case 'running':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[rgba(198,241,29,0.12)] text-[#C6F11D] border border-[rgba(198,241,29,0.3)]"><RotateCw className="h-2.5 w-2.5 animate-spin" />RUN</span>;
      case 'queued':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[rgba(255,200,69,0.12)] text-[#FFC845] border border-[rgba(255,200,69,0.3)]"><Clock className="h-2.5 w-2.5" />QUEUE</span>;
      default:
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[rgba(154,160,166,0.12)] text-[#9AA0A6] border border-[rgba(154,160,166,0.3)]">{status}</span>;
    }
  };

  const getProjectName = (id) => {
    const p = projects.find(x => String(x.id) === String(id));
    return p?.name || `Project #${id}`;
  };

  const formatTime = (iso) => {
    if (!iso) return '-';
    const d = new Date(iso);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return `${Math.floor(diff)}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return d.toLocaleString();
  };

  // Highlight the trigger words / prefix in the final prompt
  const renderFinalPrompt = (p) => {
    const fp = p.final_prompt || '';
    const triggers = p.trigger_words;
    if (!triggers) return <span className="text-[#F5F5F5]">{fp}</span>;
    const triggerList = triggers.split(',').map(s => s.trim()).filter(Boolean);
    if (triggerList.length === 0) return <span className="text-[#F5F5F5]">{fp}</span>;
    // Find the prefix end (everything up to and including the first comma after triggers)
    const triggersEnd = fp.toLowerCase().indexOf(triggerList[0].toLowerCase()) + triggerList[0].length;
    if (triggersEnd < triggerList[0].length) return <span className="text-[#F5F5F5]">{fp}</span>;
    // Find next comma after triggers end
    const nextComma = fp.indexOf(',', triggersEnd);
    const prefixEnd = nextComma > 0 ? nextComma + 1 : triggersEnd;
    const prefix = fp.substring(0, prefixEnd);
    const rest = fp.substring(prefixEnd);
    return (
      <>
        <span className="text-[#C6F11D] font-semibold">{prefix}</span>
        <span className="text-[#F5F5F5]">{rest}</span>
      </>
    );
  };

  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      {/* Back button */}
      <button
        onClick={() => navigate(-1)}
        className="neo-btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-[11px] mb-4"
        title="Go back to previous page"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back
      </button>
      {/* Header */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <h2 className="neo-title text-3xl flex items-center gap-2">
            <Terminal className="h-7 w-7 text-[#C6F11D]" />
            Prompt Console
          </h2>
          <p className="text-sm text-[#9AA0A6] mt-1">Inspect every prompt sent to ComfyUI in real time</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-[11px] text-[#9AA0A6] cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="accent-[#C6F11D]"
            />
            Auto-refresh
          </label>
          <button
            onClick={loadAll}
            className="neo-btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-[11px]"
          >
            <RefreshCw className="h-3 w-3" />
            Refresh
          </button>
          <button
            onClick={handleClearAll}
            className="px-3 py-1.5 rounded-xl text-[11px] text-[#9AA0A6] hover:text-[#FF5757] hover:bg-[rgba(255,87,87,0.1)] transition-all duration-150 flex items-center gap-1.5"
          >
            <Trash2 className="h-3 w-3" />
            Clear All
          </button>
        </div>
      </div>

      {/* Stats summary */}
      {stats && (
        <div className="grid grid-cols-5 gap-3 mb-5">
          <div className="neo-card p-3">
            <div className="text-[10px] text-[#9AA0A6] uppercase tracking-wider">Total</div>
            <div className="text-2xl font-bold text-[#F5F5F5] mt-1">{stats.total}</div>
          </div>
          <div className="neo-card p-3">
            <div className="text-[10px] text-[#9AA0A6] uppercase tracking-wider">Running</div>
            <div className="text-2xl font-bold text-[#C6F11D] mt-1 flex items-center gap-1.5">
              {stats.running > 0 && <RotateCw className="h-4 w-4 animate-spin" />}
              {stats.running}
            </div>
          </div>
          <div className="neo-card p-3">
            <div className="text-[10px] text-[#9AA0A6] uppercase tracking-wider">Completed</div>
            <div className="text-2xl font-bold text-[#6BFF64] mt-1">{stats.completed}</div>
          </div>
          <div className="neo-card p-3">
            <div className="text-[10px] text-[#9AA0A6] uppercase tracking-wider">Failed</div>
            <div className="text-2xl font-bold text-[#FF5757] mt-1">{stats.failed}</div>
          </div>
          <div className="neo-card p-3">
            <div className="text-[10px] text-[#9AA0A6] uppercase tracking-wider">Queued</div>
            <div className="text-2xl font-bold text-[#FFC845] mt-1">{stats.queued}</div>
          </div>
        </div>
      )}

      {/* Active prompt sticky */}
      {activePrompt && (
        <div className="neo-card p-4 mb-5 border-l-4 border-[#C6F11D] bg-[rgba(198,241,29,0.04)]">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="h-4 w-4 text-[#C6F11D] animate-pulse" />
            <span className="text-[11px] font-bold text-[#C6F11D] uppercase tracking-wider">Currently Generating</span>
            <span className="text-[10px] text-[#9AA0A6]">Scene {activePrompt.scene_number} • {getProjectName(activePrompt.project_id)} • Job #{activePrompt.job_id}</span>
          </div>
          <div className="text-[12px] text-[#F5F5F5] font-mono break-words leading-relaxed">
            {activePrompt.final_prompt}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="neo-card p-3 mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-[11px] text-[#9AA0A6]">
          <Filter className="h-3 w-3" />
          <span>Filter:</span>
        </div>
        <select
          value={filterProject}
          onChange={(e) => setFilterProject(e.target.value)}
          className="bg-[#0E1116] border border-[#252A33] rounded-lg px-2 py-1 text-[11px] text-[#F5F5F5] focus:outline-none focus:border-[#C6F11D]"
        >
          <option value="all">All Projects</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="bg-[#0E1116] border border-[#252A33] rounded-lg px-2 py-1 text-[11px] text-[#F5F5F5] focus:outline-none focus:border-[#C6F11D]"
        >
          <option value="all">All Statuses</option>
          <option value="running">Running</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="queued">Queued</option>
        </select>
        <select
          value={filterJob}
          onChange={(e) => setFilterJob(e.target.value)}
          className="bg-[#0E1116] border border-[#252A33] rounded-lg px-2 py-1 text-[11px] text-[#F5F5F5] focus:outline-none focus:border-[#C6F11D]"
        >
          <option value="all">All Jobs</option>
          {jobIds.map(j => <option key={j} value={j}>Job #{j}</option>)}
        </select>
        <div className="flex items-center gap-1.5 bg-[#0E1116] border border-[#252A33] rounded-lg px-2 py-1 flex-1 min-w-[200px] focus-within:border-[#C6F11D]">
          <Search className="h-3 w-3 text-[#5F6772]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search prompts, narration, descriptions..."
            className="bg-transparent text-[11px] text-[#F5F5F5] flex-1 outline-none"
          />
        </div>
        <span className="text-[10px] text-[#5F6772] ml-auto">{filtered.length} of {prompts.length}</span>
      </div>

      {/* Error */}
      {error && (
        <div className="neo-card p-3 mb-4 border-l-4 border-[#FF5757] bg-[rgba(255,87,87,0.06)]">
          <div className="flex items-center gap-2 text-[12px] text-[#FF5757]">
            <AlertCircle className="h-4 w-4" />
            {error}
          </div>
        </div>
      )}

      {/* Prompt list */}
      <div className="space-y-2">
        {filtered.length === 0 && !error && (
          <div className="neo-card p-8 text-center text-[#5F6772]">
            <Terminal className="h-12 w-12 mx-auto mb-3 opacity-30" />
            <div className="text-sm">No prompts yet. Run a video generation to see them here.</div>
          </div>
        )}

        {filtered.map(p => {
          const isOpen = expanded.has(p.id);
          return (
            <div key={p.id} className="neo-card overflow-hidden">
              {/* Collapsed row */}
              <button
                onClick={() => toggleExpand(p.id)}
                className="w-full px-4 py-3 flex items-center gap-3 hover:bg-[rgba(255,255,255,0.02)] transition-colors text-left"
              >
                {isOpen ? <ChevronDown className="h-3.5 w-3.5 text-[#9AA0A6]" /> : <ChevronRight className="h-3.5 w-3.5 text-[#9AA0A6]" />}
                <span className="text-[11px] font-mono text-[#9AA0A6] w-8">#{p.id}</span>
                <span className="text-[11px] font-bold text-[#C6F11D] w-16">Scene {p.scene_number}</span>
                {getStatusBadge(p.status)}
                <span className="text-[11px] text-[#9AA0A6] flex-1 truncate">
                  {p.sanitized_visual_description || p.raw_visual_description || '(no description)'}
                </span>
                <span className="text-[10px] text-[#5F6772]">Job #{p.job_id || '-'}</span>
                <span className="text-[10px] text-[#5F6772]">{getProjectName(p.project_id)}</span>
                <span className="text-[10px] text-[#5F6772] w-16 text-right">{formatTime(p.created_at)}</span>
              </button>

              {/* Expanded */}
              {isOpen && (
                <div className="border-t border-[#252A33] p-4 space-y-3 bg-[#0A0C10]">
                  {/* Narration */}
                  {p.narration_text && (
                    <div>
                      <div className="text-[10px] font-bold text-[#9AA0A6] uppercase tracking-wider mb-1">Narration</div>
                      <div className="text-[12px] text-[#F5F5F5] italic">"{p.narration_text}"</div>
                    </div>
                  )}

                  {/* Trigger words */}
                  {p.trigger_words && (
                    <div>
                      <div className="text-[10px] font-bold text-[#9AA0A6] uppercase tracking-wider mb-1">LoRA Trigger Words</div>
                      <div className="flex flex-wrap gap-1.5">
                        {p.trigger_words.split(',').map((t, i) => (
                          <span key={i} className="px-2 py-0.5 rounded-md text-[10px] font-mono bg-[rgba(198,241,29,0.12)] text-[#C6F11D] border border-[rgba(198,241,29,0.3)]">
                            {t.trim()}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Pipeline: raw → sanitized → final */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <div className="text-[10px] font-bold text-[#9AA0A6] uppercase tracking-wider">Raw (LLM Output)</div>
                        <button onClick={() => copyText(p.raw_visual_description || '', 'Raw')} className="text-[10px] text-[#5F6772] hover:text-[#C6F11D]"><Copy className="h-2.5 w-2.5" /></button>
                      </div>
                      <div className="text-[11px] text-[#9AA0A6] font-mono break-words leading-relaxed bg-[#050608] border border-[#252A33] rounded-lg p-2 max-h-32 overflow-y-auto">
                        {p.raw_visual_description || <span className="opacity-50">(none)</span>}
                      </div>
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <div className="text-[10px] font-bold text-[#9AA0A6] uppercase tracking-wider">Sanitized</div>
                        <button onClick={() => copyText(p.sanitized_visual_description || '', 'Sanitized')} className="text-[10px] text-[#5F6772] hover:text-[#C6F11D]"><Copy className="h-2.5 w-2.5" /></button>
                      </div>
                      <div className="text-[11px] text-[#6BFF64] font-mono break-words leading-relaxed bg-[#050608] border border-[#252A33] rounded-lg p-2 max-h-32 overflow-y-auto">
                        {p.sanitized_visual_description || <span className="opacity-50">(none)</span>}
                      </div>
                    </div>
                  </div>

                  {/* Final prompt (with trigger word highlight) */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <div className="text-[10px] font-bold text-[#9AA0A6] uppercase tracking-wider">Final Prompt (sent to ComfyUI node 6)</div>
                      <button onClick={() => copyText(p.final_prompt || '', 'Final')} className="text-[10px] text-[#5F6772] hover:text-[#C6F11D] flex items-center gap-1"><Copy className="h-2.5 w-2.5" />Copy</button>
                    </div>
                    <div className="text-[12px] font-mono break-words leading-relaxed bg-[#050608] border border-[#252A33] rounded-lg p-3 max-h-48 overflow-y-auto">
                      {renderFinalPrompt(p)}
                    </div>
                  </div>

                  {/* Metadata grid */}
                  <div className="grid grid-cols-4 gap-3 text-[10px]">
                    <div>
                      <div className="text-[#5F6772] uppercase tracking-wider">LoRA</div>
                      <div className="text-[#F5F5F5] font-mono mt-0.5 break-all">{p.lora_name || '-'}</div>
                    </div>
                    <div>
                      <div className="text-[#5F6772] uppercase tracking-wider">Strength (model/clip)</div>
                      <div className="text-[#F5F5F5] font-mono mt-0.5">
                        {p.lora_strength_model ?? '-'} / {p.lora_strength_clip ?? '-'}
                      </div>
                    </div>
                    <div>
                      <div className="text-[#5F6772] uppercase tracking-wider">Seed</div>
                      <div className="text-[#F5F5F5] font-mono mt-0.5">{p.seed ?? '-'}</div>
                    </div>
                    <div>
                      <div className="text-[#5F6772] uppercase tracking-wider">Frames / Dims</div>
                      <div className="text-[#F5F5F5] font-mono mt-0.5">
                        {p.frame_count ?? '-'} @ {p.width}x{p.height}
                      </div>
                    </div>
                    <div>
                      <div className="text-[#5F6772] uppercase tracking-wider">ComfyUI ID</div>
                      <div className="text-[#F5F5F5] font-mono mt-0.5 truncate">{p.comfyui_prompt_id || '-'}</div>
                    </div>
                    <div>
                      <div className="text-[#5F6772] uppercase tracking-wider">Duration</div>
                      <div className="text-[#F5F5F5] font-mono mt-0.5">{p.duration_seconds ?? '-'}s</div>
                    </div>
                    <div>
                      <div className="text-[#5F6772] uppercase tracking-wider">Created</div>
                      <div className="text-[#F5F5F5] font-mono mt-0.5">{p.created_at ? new Date(p.created_at).toLocaleTimeString() : '-'}</div>
                    </div>
                    <div>
                      <div className="text-[#5F6772] uppercase tracking-wider">Completed</div>
                      <div className="text-[#F5F5F5] font-mono mt-0.5">{p.completed_at ? new Date(p.completed_at).toLocaleTimeString() : '-'}</div>
                    </div>
                  </div>

                  {/* Error */}
                  {p.error && (
                    <div className="bg-[rgba(255,87,87,0.06)] border border-[rgba(255,87,87,0.3)] rounded-lg p-2 text-[11px] text-[#FF5757] font-mono break-words">
                      {p.error}
                    </div>
                  )}

                  {/* Output path */}
                  {p.output_path && (
                    <div className="text-[10px] text-[#5F6772] font-mono break-all">
                      Output: {p.output_path}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-2 pt-2 border-t border-[#252A33]">
                    <button
                      onClick={() => copyText(JSON.stringify(p, null, 2), 'JSON')}
                      className="neo-btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-[11px]"
                    >
                      <Copy className="h-3 w-3" />
                      Copy as JSON
                    </button>
                    <button
                      onClick={() => handleDelete(p.id)}
                      className="px-3 py-1.5 rounded-xl text-[11px] text-[#9AA0A6] hover:text-[#FF5757] hover:bg-[rgba(255,87,87,0.1)] transition-all duration-150 flex items-center gap-1.5"
                    >
                      <Trash2 className="h-3 w-3" />
                      Delete
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Copy toast */}
      {copyToast && (
        <div className="fixed bottom-6 right-6 neo-card px-4 py-2 text-[12px] text-[#C6F11D] flex items-center gap-2 border-l-4 border-[#C6F11D] z-50">
          <CheckCircle className="h-4 w-4" />
          Copied {copyToast}
        </div>
      )}
    </div>
  );
}

export default PromptConsole;
