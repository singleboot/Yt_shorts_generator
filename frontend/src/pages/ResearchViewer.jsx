import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Globe, RefreshCw, Filter, Search, Copy, ExternalLink,
  AlertCircle, CheckCircle, Clock, Trash2, ChevronDown, ChevronRight, Sparkles, Link2, FileText, ChevronLeft, ArrowLeft
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';

const POLL_INTERVAL_MS = 3000;

function ResearchViewer() {
  const navigate = useNavigate();
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [projects, setProjects] = useState([]);
  const [filterProject, setFilterProject] = useState('all');
  const [filterSource, setFilterSource] = useState('all');
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState(new Set());
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [error, setError] = useState(null);
  const [copyToast, setCopyToast] = useState(null);
  const [selected, setSelected] = useState(null); // currently expanded log id for full view

  const loadAll = async () => {
    try {
      const [logsRes, statsRes, projectsRes] = await Promise.all([
        api.get('/research/', { params: { limit: 200 } }),
        api.get('/research/stats/summary'),
        api.get('/projects/'),
      ]);
      setLogs(logsRes.data?.items || []);
      setStats(statsRes.data || null);
      setProjects(projectsRes.data || []);
      setError(null);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Failed to load research');
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

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return logs.filter((l) => {
      if (filterProject !== 'all' && String(l.project_id) !== filterProject) return false;
      if (filterSource !== 'all' && l.source_type !== filterSource) return false;
      if (q) {
        const hay = `${l.query || ''} ${l.topic_used || ''} ${l.source_url || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [logs, filterProject, filterSource, search]);

  const projectName = (id) => projects.find((p) => p.id === id)?.name || `Project ${id}`;

  const toggle = (id) => {
    setExpanded((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  };

  const onCopy = (text) => {
    navigator.clipboard?.writeText(text || '');
    setCopyToast('Copied!');
    setTimeout(() => setCopyToast(null), 1500);
  };

  const onDelete = async (id) => {
    if (!confirm('Delete this research log?')) return;
    try {
      await api.delete(`/research/?project_id=&before=`);
      // Simpler: delete one by id by recreating the row-level delete would need an endpoint.
      // For now just reload - we expose bulk delete only.
      loadAll();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    }
  };

  const onClearAll = async () => {
    if (!confirm('Delete ALL research logs? This cannot be undone.')) return;
    try {
      await api.delete('/research/');
      loadAll();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    }
  };

  const openFull = (log) => {
    setSelected(log);
  };

  if (selected) {
    return <ResearchDetail log={selected} onBack={() => setSelected(null)} onCopy={onCopy} />;
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <div className="max-w-6xl mx-auto">
        {/* Back button */}
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] text-slate-300 hover:text-white bg-slate-800/50 hover:bg-slate-800 rounded-lg border border-slate-700/50 transition-colors mb-4"
          title="Go back to previous page"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back
        </button>
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <Globe className="w-7 h-7 text-cyan-400" />
              Research
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              What the AI found on the web before writing your script
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={loadAll}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700"
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <label className="flex items-center gap-2 text-sm text-slate-400 select-none cursor-pointer">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="accent-cyan-500"
              />
              Auto-refresh
            </label>
            <button
              onClick={onClearAll}
              className="flex items-center gap-1 px-3 py-2 rounded-lg bg-red-900/40 hover:bg-red-900 border border-red-800 text-sm"
            >
              <Trash2 className="w-4 h-4" />
              Clear All
            </button>
          </div>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <StatCard label="Total searches" value={stats.total} color="cyan" />
            <StatCard label="Completed" value={stats.completed} color="green" />
            <StatCard label="Failed" value={stats.failed} color="red" />
            <StatCard label="Results fetched" value={stats.total_search_results} color="yellow" />
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 mb-4 bg-slate-900 border border-slate-800 rounded-lg p-3">
          <Filter className="w-4 h-4 text-slate-500" />
          <select
            value={filterProject}
            onChange={(e) => setFilterProject(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm"
          >
            <option value="all">All projects</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <select
            value={filterSource}
            onChange={(e) => setFilterSource(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm"
          >
            <option value="all">All sources</option>
            <option value="auto_research">Auto-research</option>
            <option value="url">URL</option>
            <option value="topic">Topic</option>
          </select>
          <div className="flex-1 flex items-center gap-2 bg-slate-800 border border-slate-700 rounded px-2 py-1 min-w-[200px]">
            <Search className="w-4 h-4 text-slate-500" />
            <input
              type="text"
              placeholder="Search query, topic, or URL..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-transparent flex-1 text-sm focus:outline-none"
            />
          </div>
          <span className="text-xs text-slate-500">
            {filtered.length} of {logs.length} entries
          </span>
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-800 text-red-300 rounded-lg p-3 mb-4 text-sm">
            {error}
          </div>
        )}

        {/* Logs */}
        {filtered.length === 0 ? (
          <div className="text-center py-16 text-slate-500">
            <Globe className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>No research yet.</p>
            <p className="text-sm mt-1">Run a project with auto_research or URL source to see web searches here.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((l) => (
              <ResearchRow
                key={l.id}
                log={l}
                projectName={projectName(l.project_id)}
                expanded={expanded.has(l.id)}
                onToggle={() => toggle(l.id)}
                onOpen={() => openFull(l)}
                onCopy={onCopy}
              />
            ))}
          </div>
        )}

        {copyToast && (
          <div className="fixed bottom-6 right-6 bg-cyan-600 text-white px-4 py-2 rounded-lg shadow-lg text-sm">
            {copyToast}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color }) {
  const colors = {
    cyan: 'border-cyan-700/50 bg-cyan-950/30 text-cyan-300',
    green: 'border-green-700/50 bg-green-950/30 text-green-300',
    red: 'border-red-700/50 bg-red-950/30 text-red-300',
    yellow: 'border-yellow-700/50 bg-yellow-950/30 text-yellow-300',
  };
  return (
    <div className={`rounded-lg border p-3 ${colors[color] || 'border-slate-700 bg-slate-900'}`}>
      <div className="text-xs uppercase tracking-wider opacity-80">{label}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
    </div>
  );
}

function ResearchRow({ log, projectName, expanded, onToggle, onOpen, onCopy }) {
  const isFailed = log.status === 'failed';
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full text-left p-3 flex items-center gap-3 hover:bg-slate-800/50 transition"
      >
        {expanded ? <ChevronDown className="w-4 h-4 text-slate-500" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
              log.source_type === 'url' ? 'bg-purple-900/40 text-purple-300 border border-purple-800' :
              log.source_type === 'auto_research' ? 'bg-cyan-900/40 text-cyan-300 border border-cyan-800' :
              'bg-slate-800 text-slate-300 border border-slate-700'
            }`}>
              {log.source_type}
            </span>
            <span className="text-slate-200 font-medium truncate">
              {log.query || log.source_url || log.topic_used || '—'}
            </span>
            {isFailed && (
              <span className="px-2 py-0.5 rounded text-xs bg-red-900/40 text-red-300 border border-red-800">
                FAILED
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
            <span>{projectName}</span>
            {log.video_index !== null && log.video_index !== undefined && (
              <span>Video #{log.video_index + 1}</span>
            )}
            <span>{log.result_count} result{log.result_count === 1 ? '' : 's'}</span>
            {log.duration_ms != null && log.duration_ms > 0 && (
              <span>{log.duration_ms}ms</span>
            )}
            <span>{log.created_at ? new Date(log.created_at).toLocaleString() : ''}</span>
          </div>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onOpen(); }}
          className="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700"
        >
          View full
        </button>
      </button>
      {expanded && (
        <div className="border-t border-slate-800 p-4 bg-slate-950/50 space-y-3">
          {log.context_preview && (
            <div>
              <div className="text-xs uppercase text-slate-500 mb-1 flex items-center gap-1">
                <FileText className="w-3 h-3" /> Context blob (sent to LLM)
              </div>
              <pre className="text-xs text-slate-300 bg-slate-900 border border-slate-800 rounded p-3 max-h-48 overflow-auto whitespace-pre-wrap font-mono">
                {log.context_preview}
                {log.context_preview.length >= 400 ? '…' : ''}
              </pre>
              <button onClick={() => onCopy(log.context_preview)} className="text-xs text-cyan-400 hover:text-cyan-300 mt-1 flex items-center gap-1">
                <Copy className="w-3 h-3" /> Copy preview
              </button>
            </div>
          )}
          {log.search_results_preview && log.search_results_preview.length > 0 && (
            <div>
              <div className="text-xs uppercase text-slate-500 mb-1 flex items-center gap-1">
                <Link2 className="w-3 h-3" /> Search results ({log.search_results_preview.length} of {log.result_count} shown)
              </div>
              <div className="space-y-2">
                {log.search_results_preview.map((r, i) => (
                  <div key={i} className="bg-slate-900 border border-slate-800 rounded p-2">
                    <div className="text-sm font-medium text-cyan-300 truncate flex items-center gap-1">
                      <a href={r.href} target="_blank" rel="noreferrer" className="hover:underline">
                        {r.title}
                      </a>
                      <ExternalLink className="w-3 h-3 opacity-60" />
                    </div>
                    <div className="text-xs text-slate-500 truncate">{r.href}</div>
                    {r.body && <div className="text-xs text-slate-400 mt-1 line-clamp-3">{r.body}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
          {log.error && (
            <div className="text-xs text-red-400 bg-red-950/30 border border-red-900 rounded p-2 font-mono">
              {log.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ResearchDetail({ log, onBack, onCopy }) {
  const [full, setFull] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/research/${log.id}`).then((r) => {
      setFull(r.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [log.id]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={onBack}
            className="flex items-center gap-1 text-slate-400 hover:text-slate-200 text-sm"
          >
            <ChevronLeft className="w-4 h-4" /> Back to list
          </button>
          <div className="text-xs text-slate-500">Research #{log.id}</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 mb-4">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
              log.source_type === 'url' ? 'bg-purple-900/40 text-purple-300 border border-purple-800' :
              log.source_type === 'auto_research' ? 'bg-cyan-900/40 text-cyan-300 border border-cyan-800' :
              'bg-slate-800 text-slate-300 border border-slate-700'
            }`}>
              {log.source_type}
            </span>
            <span className="text-xs text-slate-500">
              {log.created_at ? new Date(log.created_at).toLocaleString() : ''}
            </span>
            <span className="text-xs text-slate-500">{log.duration_ms}ms</span>
            <span className="text-xs text-slate-500">{log.result_count} results</span>
          </div>
          {log.query && (
            <div className="mb-2">
              <div className="text-xs uppercase text-slate-500">Query sent to DuckDuckGo</div>
              <code className="text-cyan-300 font-mono text-sm">{log.query}</code>
            </div>
          )}
          {log.topic_used && (
            <div className="mb-2">
              <div className="text-xs uppercase text-slate-500">Topic used</div>
              <div className="text-slate-200">{log.topic_used}</div>
            </div>
          )}
          {log.source_url && (
            <div>
              <div className="text-xs uppercase text-slate-500">Source URL</div>
              <a href={log.source_url} target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline text-sm flex items-center gap-1">
                {log.source_url} <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          )}
        </div>

        {loading ? (
          <div className="text-center text-slate-500 py-8">Loading…</div>
        ) : full ? (
          <div className="space-y-4">
            {full.search_results && full.search_results.length > 0 && (
              <section>
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-lg font-semibold flex items-center gap-2">
                    <Link2 className="w-5 h-5 text-cyan-400" />
                    Search Results ({full.search_results.length})
                  </h2>
                  <button
                    onClick={() => onCopy(JSON.stringify(full.search_results, null, 2))}
                    className="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 flex items-center gap-1"
                  >
                    <Copy className="w-3 h-3" /> Copy as JSON
                  </button>
                </div>
                <div className="space-y-2">
                  {full.search_results.map((r, i) => (
                    <div key={i} className="bg-slate-900 border border-slate-800 rounded-lg p-3">
                      <a href={r.href} target="_blank" rel="noreferrer" className="text-cyan-300 hover:underline font-medium flex items-center gap-1">
                        {r.title} <ExternalLink className="w-3 h-3" />
                      </a>
                      <div className="text-xs text-slate-500 mt-0.5">{r.href}</div>
                      {r.body && <p className="text-sm text-slate-300 mt-2">{r.body}</p>}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {full.context_text && (
              <section>
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-lg font-semibold flex items-center gap-2">
                    <FileText className="w-5 h-5 text-cyan-400" />
                    Context blob (sent to LLM)
                  </h2>
                  <button
                    onClick={() => onCopy(full.context_text)}
                    className="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 flex items-center gap-1"
                  >
                    <Copy className="w-3 h-3" /> Copy
                  </button>
                </div>
                <pre className="text-xs text-slate-300 bg-slate-900 border border-slate-800 rounded-lg p-4 max-h-96 overflow-auto whitespace-pre-wrap font-mono">
                  {full.context_text}
                </pre>
              </section>
            )}

            {full.web_content && (
              <section>
                <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
                  <Globe className="w-5 h-5 text-purple-400" />
                  Webpage Content (first 8000 chars)
                </h2>
                <pre className="text-xs text-slate-300 bg-slate-900 border border-slate-800 rounded-lg p-4 max-h-96 overflow-auto whitespace-pre-wrap font-mono">
                  {full.web_content}
                </pre>
              </section>
            )}

            {full.error && (
              <section>
                <h2 className="text-lg font-semibold mb-2 flex items-center gap-2 text-red-400">
                  <AlertCircle className="w-5 h-5" /> Error
                </h2>
                <pre className="text-xs text-red-300 bg-red-950/30 border border-red-900 rounded-lg p-4 whitespace-pre-wrap font-mono">
                  {full.error}
                </pre>
              </section>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default ResearchViewer;
