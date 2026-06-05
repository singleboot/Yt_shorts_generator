import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Plus, Film, Calendar, Sparkles, Trash2, ExternalLink, Send, CheckCircle, AlertCircle, Loader2, Clock, Activity, Youtube } from 'lucide-react';
import api from '../api/client';

const STATUS_COLORS = {
  active: 'border-l-[#6BFF64]',
  generating: 'border-l-[#FFC845]',
  failed: 'border-l-[#FF5757]',
};

const STATUS_BADGES = {
  active: 'neo-badge-green',
  generating: 'neo-badge-amber',
  failed: 'neo-badge-red',
};

function Dashboard() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [uploads, setUploads] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 3000);
    return () => clearInterval(interval);
  }, []);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  const loadData = async () => {
    try {
      const [projRes, uploadRes, jobRes] = await Promise.all([
        api.get('/projects/').catch(() => ({ data: [] })),
        api.get('/uploads/').catch(() => ({ data: [] })),
        api.get('/jobs/').catch(() => ({ data: [] }))
      ]);
      setProjects(projRes.data || []);
      setUploads(uploadRes.data || []);
      setJobs(jobRes.data || []);
    } catch (e) {
      console.error('Failed to load dashboard', e);
    }
  };

  const triggerBatch = async (id, name) => {
    try {
      const res = await api.post(`/projects/${id}/batch`);
      showToast(`Started ${res.data.video_count} video(s) for "${name}"`);
      loadData();
    } catch (e) {
      showToast('Failed to start generation', 'error');
    }
  };

  const postProject = async (id, name) => {
    try {
      const res = await api.post(`/projects/${id}/post`);
      if (res.data.scheduled > 0) {
        showToast(`Scheduled ${res.data.scheduled} video(s) for "${name}"`);
      } else {
        showToast(`No ready videos for "${name}". Generate first.`, 'warning');
      }
      loadData();
    } catch (e) {
      showToast('Failed to post', 'error');
    }
  };

  const deleteProject = async (id, name) => {
    if (!confirm(`Delete "${name}"?`)) return;
    try {
      await api.delete(`/projects/${id}`);
      showToast(`Deleted "${name}"`);
      loadData();
    } catch (e) {
      showToast('Failed to delete', 'error');
    }
  };

  const getProjectJobs = (projectId) => jobs.filter(j => j.project_id === projectId);

  return (
    <div className="p-8 min-h-screen relative" style={{background:'#050608'}}>
      {toast && (
        <div className={`fixed top-6 right-6 z-50 flex items-center gap-3 px-5 py-3 rounded-2xl shadow-2xl transition-all duration-150 ${
          toast.type === 'error' ? 'bg-[#FF5757] text-white' :
          toast.type === 'warning' ? 'bg-[#FFC845] text-[#050608]' :
          'bg-[#C6F11D] text-[#050608]'
        }`}>
          {toast.type === 'error' ? <AlertCircle className="h-5 w-5" /> :
           toast.type === 'warning' ? <AlertCircle className="h-5 w-5" /> :
           <CheckCircle className="h-5 w-5" />}
          <span className="text-sm font-bold">{toast.message}</span>
        </div>
      )}

      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="neo-title text-3xl">Dashboard</h1>
          <p className="text-[#9AA0A6] text-sm mt-1">Manage your AI Shorts production</p>
        </div>
        <Link
          to="/wizard"
          className="neo-btn-primary flex items-center gap-2 px-5 py-2.5 text-sm"
        >
          <Plus className="h-4 w-4" />
          New Project
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="neo-card p-5">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-xl" style={{background:'rgba(198,241,29,0.08)', border:'1px solid rgba(198,241,29,0.2)'}}>
              <Film className="h-5 w-5 text-[#C6F11D]" />
            </div>
            <div>
              <p className="text-xs text-[#9AA0A6] uppercase tracking-wider">Projects</p>
              <p className="neo-stat text-2xl">{projects.length}</p>
            </div>
          </div>
        </div>
        <div className="neo-card p-5">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-xl" style={{background:'rgba(255,200,69,0.08)', border:'1px solid rgba(255,200,69,0.2)'}}>
              <Activity className="h-5 w-5 text-[#FFC845]" />
            </div>
            <div>
              <p className="text-xs text-[#9AA0A6] uppercase tracking-wider">Generating</p>
              <p className="neo-stat text-2xl">{jobs.filter(j => j.status === 'running').length}</p>
            </div>
          </div>
        </div>
        <div className="neo-card p-5">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-xl" style={{background:'rgba(77,166,255,0.08)', border:'1px solid rgba(77,166,255,0.2)'}}>
              <Send className="h-5 w-5 text-[#4DA6FF]" />
            </div>
            <div>
              <p className="text-xs text-[#9AA0A6] uppercase tracking-wider">Queued</p>
              <p className="neo-stat text-2xl">{uploads.filter(u => u.status === 'queued').length}</p>
            </div>
          </div>
        </div>
        <div className="neo-card p-5">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-xl" style={{background:'rgba(107,255,100,0.08)', border:'1px solid rgba(107,255,100,0.2)'}}>
              <Calendar className="h-5 w-5 text-[#6BFF64]" />
            </div>
            <div>
              <p className="text-xs text-[#9AA0A6] uppercase tracking-wider">Uploaded</p>
              <p className="neo-stat text-2xl">{uploads.filter(u => u.status === 'done').length}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Projects Grid */}
      {projects.length === 0 ? (
        <div className="neo-card p-12 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-[rgba(198,241,29,0.08)] flex items-center justify-center border border-[rgba(198,241,29,0.2)]">
            <Sparkles className="h-8 w-8 text-[#C6F11D]" />
          </div>
          <h3 className="text-lg font-bold text-[#F5F5F5] mb-2">No projects yet</h3>
          <p className="text-[#9AA0A6] text-sm mb-6">Create your first AI-powered Shorts project</p>
          <Link
            to="/wizard"
            className="neo-btn-primary inline-flex items-center gap-2 px-6 py-3 text-sm"
          >
            <Plus className="h-4 w-4" />
            Create Project
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => {
            const vs = project.visual_settings || {};
            const projectJobs = getProjectJobs(project.id);
            const runningJobs = projectJobs.filter(j => j.status === 'running');
            const isGenerating = runningJobs.length > 0;
            const queuedCount = uploads.filter(u => u.project_id === project.id && u.status === 'queued').length;
            const doneCount = uploads.filter(u => u.project_id === project.id && u.status === 'done').length;
            const statusKey = isGenerating ? 'generating' : project.status === 'active' ? 'active' : 'failed';

            return (
              <div
                key={project.id}
                onClick={() => navigate(`/project/${project.id}`)}
                className={`neo-card overflow-hidden cursor-pointer transition-all duration-150 hover:bg-[#161A20] hover:border-[#C6F11D] ${STATUS_COLORS[statusKey] || 'border-l-[#252A33]'} border-l-[3px]`}
              >
                {/* Accent strip */}
                <div className="p-4">
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="font-bold text-[#F5F5F5] text-sm truncate flex-1">{project.name}</h3>
                    <span className={`neo-badge ${STATUS_BADGES[statusKey] || 'neo-badge-gray'} ml-2 shrink-0`}>
                      {isGenerating ? `${runningJobs.length} running` : project.status}
                    </span>
                  </div>

                  <p className="text-xs text-[#9AA0A6] mb-3 capitalize">{project.category}</p>

                  {/* Style badge */}
                  {vs.ai_style && vs.ai_style !== 'none' && (
                    <span className="neo-badge neo-badge-green inline-block mb-3">
                      {vs.ai_style.replace(/_/g, ' ')}
                    </span>
                  )}

                  {/* Upload counts */}
                  <div className="flex gap-2 text-xs">
                    {queuedCount > 0 && (
                      <span className="px-2 py-0.5 rounded-full bg-[rgba(77,166,255,0.1)] text-[#4DA6FF] border border-[rgba(77,166,255,0.3)]">
                        {queuedCount} queued
                      </span>
                    )}
                    {doneCount > 0 && (
                      <span className="px-2 py-0.5 rounded-full bg-[rgba(107,255,100,0.1)] text-[#6BFF64] border border-[rgba(107,255,100,0.3)]">
                        {doneCount} posted
                      </span>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 mt-4">
                    <button
                      onClick={(e) => { e.stopPropagation(); postProject(project.id, project.name); }}
                      disabled={isGenerating}
                      className="neo-btn-secondary flex-1 flex items-center justify-center gap-1.5 py-2 text-xs"
                    >
                      <Send className="h-3 w-3" />
                      Post
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); triggerBatch(project.id, project.name); }}
                      disabled={isGenerating}
                      className="neo-btn-primary flex-1 flex items-center justify-center gap-1.5 py-2 text-xs"
                    >
                      {isGenerating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                      {isGenerating ? 'Working...' : 'Generate'}
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteProject(project.id, project.name); }}
                      disabled={isGenerating}
                      className="p-2 rounded-lg hover:bg-[rgba(255,87,87,0.1)] text-[#5F6772] hover:text-[#FF5757] transition-colors disabled:opacity-50"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Recent Uploads */}
      {uploads.length > 0 && (
        <div className="mt-8">
          <h2 className="neo-title text-lg mb-4">Recent Uploads</h2>
          <div className="neo-card overflow-hidden">
            {uploads.slice(0, 5).map((upload) => (
              <div key={upload.id} className="px-5 py-4 flex items-center justify-between hover:bg-[rgba(255,255,255,0.03)] transition-colors border-b border-[#252A33] last:border-b-0">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center border ${
                    upload.status === 'done' ? 'bg-[rgba(107,255,100,0.08)] border-[rgba(107,255,100,0.2)]' :
                    upload.status === 'queued' ? 'bg-[rgba(77,166,255,0.08)] border-[rgba(77,166,255,0.2)]' :
                    'bg-[rgba(95,103,114,0.1)] border-[rgba(95,103,114,0.2)]'
                  }`}>
                    {upload.status === 'done' ? <CheckCircle className="h-4 w-4 text-[#6BFF64]" /> :
                     upload.status === 'queued' ? <Send className="h-4 w-4 text-[#4DA6FF]" /> :
                     <Clock className="h-4 w-4 text-[#5F6772]" />}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-[#F5F5F5]">{upload.title || 'Untitled'}</p>
                    <p className="text-xs text-[#9AA0A6]">
                      {upload.scheduled_for ? `Scheduled: ${new Date(upload.scheduled_for).toLocaleString()}` : ''} • {upload.status}
                    </p>
                  </div>
                </div>
                {upload.youtube_video_id && (
                  <a 
                    href={`https://youtube.com/shorts/${upload.youtube_video_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs text-[#C6F11D] hover:text-[#D9FF3D]"
                  >
                    <Youtube className="h-3.5 w-3.5" />
                    YouTube
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default Dashboard;
