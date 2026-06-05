import React from 'react';
import { Routes, Route, Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, PlusCircle, Settings, Activity, Youtube, Sparkles } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import ProjectWizard from './pages/ProjectWizard';
import SettingsPage from './pages/Settings';
import JobMonitor from './pages/JobMonitor';
import ProjectDetail from './pages/ProjectDetail';

function App() {
  const location = useLocation();
  const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/wizard', label: 'New Project', icon: PlusCircle },
    { path: '/jobs', label: 'Jobs', icon: Activity },
    { path: '/settings', label: 'Settings', icon: Settings },
  ];

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
        
        <div className="p-3 border-t border-[#252A33]">
          <div className="text-[10px] text-[#5F6772] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 text-center">
            v2.0.0
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-auto scrollbar-thin">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/wizard" element={<ProjectWizard />} />
          <Route path="/jobs" element={<JobMonitor />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/project/:id" element={<ProjectDetail />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
