import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, CheckCircle, XCircle, Clock, AlertCircle, RotateCw, Trash2, ArrowLeft } from 'lucide-react';
import api from '../api/client';

function JobMonitor() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    loadJobs();
    const interval = setInterval(loadJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadJobs = async () => {
    try {
      const status = filter === 'all' ? undefined : filter;
      const res = await api.get('/jobs/', { params: status ? { status } : {} });
      setJobs(res.data || []);
    } catch (e) {
      console.error(e);
    }
  };

  const cancelJob = async (id) => {
    try {
      await api.post(`/jobs/${id}/cancel`);
      loadJobs();
    } catch (e) {
      console.error(e);
    }
  };

  const clearFinished = async () => {
    try {
      await api.post('/jobs/clear-finished');
      loadJobs();
    } catch (e) {
      console.error(e);
    }
  };

  const clearAll = async () => {
    try {
      await api.post('/jobs/clear-all');
      loadJobs();
    } catch (e) {
      console.error(e);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle className="h-5 w-5 text-[#6BFF64]" />;
      case 'failed': return <XCircle className="h-5 w-5 text-[#FF5757]" />;
      case 'running': return <RotateCw className="h-5 w-5 text-[#C6F11D] animate-spin" />;
      case 'queued': return <Clock className="h-5 w-5 text-[#FFC845]" />;
      case 'cancelled': return <AlertCircle className="h-5 w-5 text-[#5F6772]" />;
      default: return <Activity className="h-5 w-5 text-[#9AA0A6]" />;
    }
  };

  return (
    <div className="p-8">
      <div className="flex justify-between items-center mb-8">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(-1)}
            className="neo-card-hover p-2 rounded-xl text-[#9AA0A6] hover:text-[#F5F5F5]"
            title="Back"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h2 className="neo-title text-3xl">Job Monitor</h2>
            <p className="text-sm text-[#9AA0A6] mt-1">Track generation and upload progress</p>
          </div>
        </div>
        <div className="flex gap-2">
          {['all', 'running', 'queued', 'completed', 'failed'].map((f) => (
            <button
              key={f}
              onClick={() => { setFilter(f); }}
              className={`px-3 py-2 rounded-xl text-xs capitalize transition-all duration-150 ${
                filter === f
                  ? 'bg-[#C6F11D] text-[#050608] font-bold'
                  : 'neo-btn-secondary'
              }`}
            >
              {f}
            </button>
          ))}
          <div className="border-l border-[#252A33] ml-1" />
          <button
            onClick={clearFinished}
            className="px-3 py-2 rounded-xl text-xs text-[#9AA0A6] hover:text-[#FFC845] hover:bg-[rgba(255,200,69,0.1)] transition-all duration-150 flex items-center gap-1.5"
          >
            <Trash2 className="h-3 w-3" />
            Clear Finished
          </button>
          <button
            onClick={clearAll}
            className="px-3 py-2 rounded-xl text-xs text-[#9AA0A6] hover:text-[#FF5757] hover:bg-[rgba(255,87,87,0.1)] transition-all duration-150 flex items-center gap-1.5"
          >
            <Trash2 className="h-3 w-3" />
            Clear All
          </button>
        </div>
      </div>

      <div className="neo-card overflow-hidden">
        <div className="grid grid-cols-12 gap-4 px-5 py-3 border-b border-[#252A33] text-[11px] font-bold text-[#9AA0A6] uppercase tracking-wider">
          <div className="col-span-1">Status</div>
          <div className="col-span-2">Type</div>
          <div className="col-span-1">Progress</div>
          <div className="col-span-2">Project</div>
          <div className="col-span-3">Created</div>
          <div className="col-span-2">Completed</div>
          <div className="col-span-1">Action</div>
        </div>
        
        <div className="divide-y divide-[#252A33]">
          {jobs.length === 0 && (
            <div className="px-5 py-8 text-center text-[#5F6772]">
              No jobs found.
            </div>
          )}
          {jobs.map((job) => (
            <div key={job.id} className="grid grid-cols-12 gap-4 px-5 py-3.5 items-center hover:bg-[rgba(255,255,255,0.02)] transition-colors">
              <div className="col-span-1">{getStatusIcon(job.status)}</div>
              <div className="col-span-2">
                <span className="capitalize text-sm font-medium text-[#F5F5F5]">{job.job_type}</span>
              </div>
              <div className="col-span-1">
                <div className="neo-progress w-16">
                  <div
                    className="neo-progress-fill"
                    style={{ width: `${job.progress || 0}%` }}
                  />
                </div>
                <span className="text-[10px] text-[#5F6772]">{job.progress || 0}%</span>
              </div>
              <div className="col-span-2 text-sm text-[#9AA0A6]">{job.project_id || '-'}</div>
              <div className="col-span-3 text-sm text-[#5F6772]">
                {job.created_at ? new Date(job.created_at).toLocaleString() : '-'}
              </div>
              <div className="col-span-2 text-sm text-[#5F6772]">
                {job.completed_at ? new Date(job.completed_at).toLocaleString() : '-'}
              </div>
              <div className="col-span-1">
                {(job.status === 'queued' || job.status === 'running') && (
                  <button
                    onClick={() => cancelJob(job.id)}
                    className="text-xs text-[#FF5757] hover:text-[#FF7575] transition-colors"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default JobMonitor;
