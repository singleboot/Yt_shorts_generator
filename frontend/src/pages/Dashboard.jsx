import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Plus, Film, Calendar, Sparkles, Trash2, CheckCircle, AlertCircle, Clock, Activity, Youtube, Archive, RotateCcw, Power, PowerOff, Send } from 'lucide-react';
import api from '../api/client';

const STATUS_COLORS = {
  active: 'border-[#6BFF64]',
  paused: 'border-[#5F6772]',
  generating: 'border-[#FFC845]',
  archived: 'border-[#4DA6FF]',
  failed: 'border-[#FF5757]',
};

const STATUS_BADGES = {
  active: 'neo-badge-green',
  paused: 'neo-badge-gray',
  generating: 'neo-badge-amber',
  archived: 'neo-badge-blue',
  failed: 'neo-badge-red',
};

function Dashboard() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [uploads, setUploads] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [toast, setToast] = useState(null);
  const [showDeleteModal, setShowDeleteModal] = useState(null);

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

  const toggleStatus = async (project) => {
    const newStatus = project.status === 'active' ? 'paused' : 'active';
    try {
      await api.put(`/projects/${project.id}`, { status: newStatus });
      showToast(newStatus === 'active' ? `Activated "${project.name}"` : `Deactivated "${project.name}"`);
      loadData();
    } catch (e) {
      showToast('Failed to update status', 'error');
    }
  };

  const confirmDelete = async (action) => {
    const project = showDeleteModal;
    if (!project) return;
    if (project.status === 'active' && action === 'delete') {
      showToast('Deactivate the project before deleting it', 'warning');
      setShowDeleteModal(null);
      return;
    }
    try {
      await api.delete(`/projects/${project.id}?action=${action}`);
      const msg = action === 'archive' ? `Archived "${project.name}"` : `Deleted "${project.name}"`;
      showToast(msg);
      setShowDeleteModal(null);
      loadData();
    } catch (e) {
      showToast('Operation failed', 'error');
      setShowDeleteModal(null);
    }
  };

  const restoreProject = async (id, name) => {
    try {
      await api.post(`/projects/${id}/restore`);
      showToast(`Restored "${name}"`);
      loadData();
    } catch (e) {
      showToast('Failed to restore', 'error');
    }
  };

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
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-3">
          {projects.map((project) => {
            const isGenerating = jobs.filter(j => j.project_id === project.id && j.status === 'running').length > 0;
            const isArchived = project.status === 'archived';
            const isPaused = project.status === 'paused';
            const displayStatus = isArchived ? 'archived' : isGenerating ? 'generating' : isPaused ? 'paused' : 'active';

            return (
              <div
                key={project.id}
                className={`neo-card aspect-square flex flex-col items-center justify-center text-center p-3 cursor-pointer transition-all duration-150 hover:bg-[#161A20] hover:border-[#C6F11D] relative border ${STATUS_COLORS[displayStatus] || 'border-[#252A33]'}`}
                onClick={() => navigate(`/project/${project.id}`)}
              >
                <h3 className="font-bold text-[#F5F5F5] text-xs truncate w-full mb-1.5">{project.name}</h3>
                <span className={`neo-badge ${STATUS_BADGES[displayStatus]} text-[10px] mb-2`}>
                  {isGenerating ? 'generating' : project.status}
                </span>
                <div className="flex items-center gap-1.5 mt-auto">
                  {/* Restore for archived */}
                  {isArchived && (
                    <button
                      onClick={(e) => { e.stopPropagation(); restoreProject(project.id, project.name); }}
                      className="p-1.5 rounded-lg hover:bg-[rgba(107,255,100,0.1)] text-[#5F6772] hover:text-[#6BFF64] transition-colors"
                      title="Restore"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {/* Deactivate/Activate toggle */}
                  {!isArchived && (
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleStatus(project); }}
                      className={`p-1.5 rounded-lg transition-colors ${
                        isPaused
                          ? 'hover:bg-[rgba(107,255,100,0.1)] text-[#5F6772] hover:text-[#6BFF64]'
                          : 'hover:bg-[rgba(95,103,114,0.15)] text-[#9AA0A6] hover:text-[#5F6772]'
                      }`}
                      title={isPaused ? 'Activate' : 'Deactivate'}
                    >
                      {isPaused ? <Power className="h-3.5 w-3.5" /> : <PowerOff className="h-3.5 w-3.5" />}
                    </button>
                  )}
                  {/* Delete */}
                  <button
                    onClick={(e) => { e.stopPropagation(); setShowDeleteModal(project); }}
                    className="p-1.5 rounded-lg hover:bg-[rgba(255,87,87,0.1)] text-[#5F6772] hover:text-[#FF5757] transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
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

      {/* Delete / Archive confirmation modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowDeleteModal(null)}>
          <div className="neo-card p-6 max-w-md w-full mx-4" onClick={e => e.stopPropagation()}>
            {showDeleteModal.status === 'active' ? (
              <>
                <h3 className="neo-title text-lg mb-2">Cannot Delete Active Project</h3>
                <p className="text-[#9AA0A6] text-sm mb-1">
                  <span className="text-[#F5F5F5] font-semibold">"{showDeleteModal.name}"</span> is currently <span className="neo-badge neo-badge-green text-[10px]">active</span>.
                </p>
                <p className="text-[#9AA0A6] text-sm mb-6">Deactivate it first using the power button on the project card, then delete.</p>
                <button
                  onClick={() => setShowDeleteModal(null)}
                  className="neo-btn-secondary py-2.5 w-full flex items-center justify-center gap-2"
                >
                  Got it
                </button>
              </>
            ) : (
              <>
                <h3 className="neo-title text-lg mb-2">Delete Project</h3>
                <p className="text-[#9AA0A6] text-sm mb-1">
                  Deleting <span className="text-[#F5F5F5] font-semibold">"{showDeleteModal.name}"</span> will permanently remove all its data.
                </p>
                <p className="text-[#9AA0A6] text-sm mb-6">What would you like to do?</p>
                <div className="flex flex-col gap-2">
                  <button
                    onClick={() => confirmDelete('archive')}
                    className="neo-btn-secondary py-2.5 flex items-center justify-center gap-2"
                  >
                    <Archive className="h-4 w-4" />
                    Archive (compress & keep for later)
                  </button>
                  <button
                    onClick={() => confirmDelete('delete')}
                    className="py-2.5 rounded-xl font-bold text-sm flex items-center justify-center gap-2 text-white"
                    style={{background:'#FF5757'}}
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete Permanently
                  </button>
                  <button
                    onClick={() => setShowDeleteModal(null)}
                    className="neo-btn-ghost py-2 text-sm text-[#9AA0A6]"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default Dashboard;
