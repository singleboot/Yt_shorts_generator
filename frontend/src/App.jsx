import React, { useState, useEffect } from 'react';
import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom';
import { LayoutDashboard, PlusCircle, Settings, Activity, Youtube, Sparkles, Terminal, Power, PowerOff, Loader2, Cpu, Globe } from 'lucide-react';
import api from './api/client';
import Dashboard from './pages/Dashboard';
import ProjectWizard from './pages/ProjectWizard';
import SettingsPage from './pages/Settings';
import JobMonitor from './pages/JobMonitor';
import ProjectDetail from './pages/ProjectDetail';
import PromptConsole from './pages/PromptConsole';
import ResearchViewer from './pages/ResearchViewer';

function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/wizard', label: 'New Project', icon: PlusCircle },
    { path: '/jobs', label: 'Jobs', icon: Activity },
    { path: '/research', label: 'Research', icon: Globe },
    { path: '/prompts', label: 'Prompts', icon: Terminal },
    { path: '/settings', label: 'Settings', icon: Settings },
  ];

  // Persistent ComfyUI status indicator in sidebar
  const [systemStatus, setSystemStatus] = useState(null);
  const [serviceAction, setServiceAction] = useState(null);
  const [actionToast, setActionToast] = useState(null);

  const checkSystemStatus = async () => {
    try {
      const res = await api.get('/system/status');
      setSystemStatus(res.data);
    } catch (e) {
      setSystemStatus({ comfyui: { running: false }, backend: { running: false }, all_running: false });
    }
  };

  useEffect(() => {
    checkSystemStatus();
    const id = setInterval(checkSystemStatus, 8000);
    return () => clearInterval(id);
  }, []);

  const startComfyUI = async () => {
    setServiceAction('starting');
    setActionToast('Starting ComfyUI...');
    try {
      const res = await api.post('/system/start-comfyui', null, { timeout: 120000 });
      if (res.data.status === 'success' || res.data.status === 'already_running') {
        setActionToast(res.data.status === 'already_running' ? 'Already running' : `ComfyUI ready (${res.data.elapsed_s}s)`);
        await checkSystemStatus();
      } else {
        setActionToast('Failed: ' + (res.data.error || 'unknown'));
      }
    } catch (e) {
      setActionToast('Failed: ' + (e?.response?.data?.error || e.message));
    } finally {
      setServiceAction(null);
      setTimeout(() => setActionToast(null), 4000);
    }
  };

  const stopComfyUI = async () => {
    if (!confirm('Stop ComfyUI? Any in-flight generation will be cancelled.')) return;
    setServiceAction('stopping');
    setActionToast('Stopping ComfyUI...');
    try {
      await api.post('/system/stop-comfyui');
      setActionToast('Stopped');
      await checkSystemStatus();
    } catch (e) {
      setActionToast('Failed: ' + (e?.response?.data?.error || e.message));
    } finally {
      setServiceAction(null);
      setTimeout(() => setActionToast(null), 4000);
    }
  };

  const comfyRunning = systemStatus?.comfyui?.running;
  const onSettings = location.pathname === '/settings';

  return (
    <div className="min-h-screen bg-[#050608] flex overflow-hidden">
      <aside className="w-[72px] hover:w-[240px] group transition-all duration-300 ease-in-out border-r border-[#252A33] bg-[#0E1116] flex flex-col z-50">
        <div className="p-4 flex items-center gap-3 overflow-hidden">
          <div className="min-w-[40px] h-10 rounded-xl bg-[#C6F11D] flex items-center justify-center shrink-0">
            <Sparkles className="h-5 w-5 text-[#050608]" />
          </div>
          <span className="text-sm font-bold text-[#F5F5F5] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 tracking-tight">NE0</span>
        </div>

        <nav className="flex-1 px-3 mt-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-150 ${
                  isActive
                    ? 'bg-[rgba(198,241,29,0.12)] text-[#C6F11D] border-l-[3px] border-[#C6F11D] rounded-l-none'
                    : 'text-[#9AA0A6] hover:text-[#F5F5F5] hover:bg-[rgba(255,255,255,0.03)]'
                }`}
              >
                <Icon className="h-5 w-5 shrink-0" />
                <span className="text-sm font-medium whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* ComfyUI status / Start button - visible from any page */}
        <div className="p-3 border-t border-[#252A33] space-y-2">
          <button
            onClick={comfyRunning ? stopComfyUI : startComfyUI}
            disabled={serviceAction !== null}
            title={comfyRunning ? 'Click to stop ComfyUI' : 'Click to start ComfyUI'}
            className={`w-full flex items-center gap-2 px-2 py-2 rounded-lg text-xs font-semibold transition-all ${
              comfyRunning
                ? 'bg-[rgba(107,255,100,0.08)] text-[#6BFF64] hover:bg-[rgba(107,255,100,0.15)] border border-[rgba(107,255,100,0.25)]'
                : 'bg-[#C6F11D] text-[#050608] hover:bg-[#D9FF3D]'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {serviceAction === 'starting' ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
            ) : serviceAction === 'stopping' ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
            ) : comfyRunning ? (
              <span className="h-2 w-2 rounded-full bg-[#6BFF64] animate-pulse shrink-0" />
            ) : (
              <Power className="h-4 w-4 shrink-0" />
            )}
            <span className="whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200">
              {serviceAction === 'starting' ? 'Starting...' : serviceAction === 'stopping' ? 'Stopping...' : comfyRunning ? 'ComfyUI: ON' : 'Start ComfyUI'}
            </span>
          </button>
          {!onSettings && (
            <button
              onClick={() => navigate('/settings')}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-[10px] text-[#5F6772] hover:text-[#9AA0A6] hover:bg-[rgba(255,255,255,0.03)] transition-all"
              title="Open Services settings"
            >
              <Cpu className="h-3 w-3 shrink-0" />
              <span className="whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200">Manage services</span>
            </button>
          )}
          <div className="text-[9px] text-[#5F6772] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 text-center">
            v2.0.0
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-auto scrollbar-thin">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/wizard" element={<ProjectWizard />} />
          <Route path="/jobs" element={<JobMonitor />} />
          <Route path="/prompts" element={<PromptConsole />} />
          <Route path="/research" element={<ResearchViewer />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/project/:id" element={<ProjectDetail />} />
        </Routes>
      </main>

      {/* Action toast */}
      {actionToast && (
        <div className="fixed bottom-6 right-6 neo-card px-4 py-2.5 text-[12px] flex items-center gap-2 border-l-4 border-[#C6F11D] z-50">
          {serviceAction ? <Loader2 className="h-4 w-4 animate-spin text-[#C6F11D]" /> : <CheckCircle className="h-4 w-4 text-[#C6F11D]" />}
          <span className="text-[#F5F5F5]">{actionToast}</span>
        </div>
      )}
    </div>
  );
}

export default App;
