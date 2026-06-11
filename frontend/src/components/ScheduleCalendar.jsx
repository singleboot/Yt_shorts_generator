import React, { useState, useEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Calendar, Clock, CheckCircle, AlertCircle, Send, Youtube, X } from 'lucide-react';
import api from '../api/client';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

const STATUS_ICON = {
  done: <CheckCircle className="h-3.5 w-3.5 text-[#6BFF64]" />,
  queued: <Send className="h-3.5 w-3.5 text-[#4DA6FF]" />,
  failed: <AlertCircle className="h-3.5 w-3.5 text-[#FF5757]" />,
  processing: <Clock className="h-3.5 w-3.5 text-[#FFC845]" />,
};

function ScheduleCalendar({ projectId, open, onClose }) {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [calendar, setCalendar] = useState({ days: {}, uploads: [] });
  const [selectedDay, setSelectedDay] = useState(today.getDate());
  const [dayUploads, setDayUploads] = useState(null);
  const [detailUpload, setDetailUpload] = useState(null);

  const loadMonth = useCallback(async () => {
    if (!projectId) return;
    try {
      const res = await api.get(`/projects/${projectId}/calendar`, {
        params: { year, month: month + 1 },
      });
      setCalendar(res.data || { days: {}, uploads: [] });
    } catch (e) {
      console.error('Failed to load calendar', e);
    }
  }, [projectId, year, month]);

  useEffect(() => { loadMonth(); }, [loadMonth]);

  // Reset to today's date when the calendar modal is opened
  useEffect(() => {
    if (open) {
      const current = new Date();
      setYear(current.getFullYear());
      setMonth(current.getMonth());
      setSelectedDay(current.getDate());
    }
  }, [open]);

  const [actionLoading, setActionLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState(null);

  // Sync day uploads automatically when calendar updates
  useEffect(() => {
    if (selectedDay) {
      const filtered = calendar.uploads.filter(u => {
        if (!u.scheduled_for) return false;
        const d = new Date(u.scheduled_for);
        return d.getFullYear() === year && d.getMonth() === month && d.getDate() === selectedDay;
      });
      setDayUploads({ uploads: filtered });
    } else {
      setDayUploads(null);
    }
  }, [calendar, selectedDay, year, month]);

  // Keep detailUpload in sync with latest calendar updates
  useEffect(() => {
    if (detailUpload) {
      const updated = calendar.uploads.find(u => u.id === detailUpload.id);
      if (updated) {
        setDetailUpload(updated);
      }
    }
  }, [calendar, detailUpload?.id]);

  // Reset messages when opening a different detail
  useEffect(() => {
    setActionMsg(null);
  }, [detailUpload?.id]);

  const handleCancelUpload = async (uploadId) => {
    if (!window.confirm("Are you sure you want to cancel and delete this upload slot?")) return;
    setActionLoading(true);
    setActionMsg({ type: 'info', text: 'Canceling upload...' });
    try {
      await api.delete(`/uploads/${uploadId}`);
      setActionMsg({ type: 'success', text: 'Upload canceled successfully!' });
      setTimeout(() => {
        setDetailUpload(null);
      }, 1000);
      await loadMonth();
    } catch (e) {
      setActionMsg({ type: 'error', text: e?.response?.data?.detail || 'Failed to cancel upload' });
    } finally {
      setActionLoading(false);
    }
  };

  const handlePostNow = async (uploadId) => {
    if (!window.confirm("Are you sure you want to post this video to YouTube immediately?")) return;
    setActionLoading(true);
    setActionMsg({ type: 'info', text: 'Posting to YouTube now...' });
    try {
      const res = await api.post(`/uploads/${uploadId}/now`);
      setActionMsg({ type: 'success', text: `Successfully posted! YouTube ID: ${res.data.video_id}` });
      await loadMonth();
    } catch (e) {
      setActionMsg({ type: 'error', text: e?.response?.data?.detail || 'Upload failed' });
    } finally {
      setActionLoading(false);
    }
  };

  if (!open) return null;

  const loadDay = (day) => {
    setSelectedDay(day);
  };

  const goTo = (y, m) => {
    setYear(y); setMonth(m); setSelectedDay(null); setDayUploads(null);
  };

  const prevMonth = () => {
    if (month === 0) goTo(year - 1, 11);
    else goTo(year, month - 1);
  };

  const nextMonth = () => {
    if (month === 11) goTo(year + 1, 0);
    else goTo(year, month + 1);
  };

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDow = new Date(year, month, 1).getDay();

  const getDayStatus = (day) => {
    const uploads = calendar.uploads.filter(u => {
      if (!u.scheduled_for) return false;
      const d = new Date(u.scheduled_for);
      return d.getFullYear() === year && d.getMonth() === month && d.getDate() === day;
    });
    if (uploads.length === 0) return null;
    const hasDone = uploads.some(u => u.status === 'done');
    const hasFailed = uploads.some(u => u.status === 'failed');
    const hasProcessing = uploads.some(u => u.status === 'processing');
    if (hasFailed) return { color: '#FF5757', label: 'failed' };
    if (hasProcessing) return { color: '#FFC845', label: 'processing' };
    if (hasDone) return { color: '#6BFF64', label: 'done' };
    return { color: '#4DA6FF', label: 'queued' };
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="neo-card p-6 w-[720px] max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="neo-title text-lg">Schedule Calendar</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-[rgba(255,255,255,0.05)] text-[#5F6772] hover:text-[#F5F5F5] transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex gap-4">
          {/* Calendar */}
          <div className="neo-card p-4 w-[340px] shrink-0">
            <div className="flex items-center justify-between mb-4">
              <button onClick={prevMonth} className="p-1 rounded-lg hover:bg-[rgba(255,255,255,0.05)] text-[#9AA0A6] hover:text-[#F5F5F5] transition-colors">
                <ChevronLeft className="h-4 w-4" />
              </button>
              <h3 className="text-sm font-bold text-[#F5F5F5]">{MONTHS[month]} {year}</h3>
              <button onClick={nextMonth} className="p-1 rounded-lg hover:bg-[rgba(255,255,255,0.05)] text-[#9AA0A6] hover:text-[#F5F5F5] transition-colors">
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
            <div className="grid grid-cols-7 mb-1">
              {WEEKDAYS.map(d => (
                <div key={d} className="text-center text-[10px] text-[#5F6772] font-semibold py-1">{d}</div>
              ))}
            </div>
            <div className="grid grid-cols-7">
              {Array.from({ length: firstDow }).map((_, i) => (
                <div key={`empty-${i}`} className="aspect-square" />
              ))}
              {Array.from({ length: daysInMonth }).map((_, i) => {
                const day = i + 1;
                const isToday = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();
                const isSelected = day === selectedDay;
                const count = calendar.days?.[String(day)] || 0;
                const dayStatus = getDayStatus(day);

                return (
                  <button
                    key={day}
                    onClick={() => loadDay(day)}
                    className={`aspect-square flex flex-col items-center justify-center rounded-lg text-xs transition-all duration-150 relative ${
                      isSelected
                        ? 'bg-[#C6F11D] text-[#050608] font-bold'
                        : isToday
                          ? 'bg-[rgba(198,241,29,0.12)] text-[#C6F11D] font-bold border border-[rgba(198,241,29,0.3)]'
                          : 'text-[#9AA0A6] hover:bg-[rgba(255,255,255,0.05)] hover:text-[#F5F5F5]'
                    }`}
                  >
                    {day}
                    {count > 0 && !isSelected && (
                      <div className="flex items-center gap-0.5 mt-0.5">
                        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: dayStatus?.color || '#5F6772' }} />
                        {count > 1 && <span className="text-[8px] text-[#5F6772]">+{count - 1}</span>}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Day detail */}
          <div className="neo-card p-4 flex-1 min-w-0 min-h-[320px]">
            {!selectedDay ? (
              <div className="flex flex-col items-center justify-center h-full text-[#5F6772]">
                <Calendar className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-xs">Click a day to see scheduled videos</p>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2 mb-4">
                  <Calendar className="h-4 w-4 text-[#C6F11D]" />
                  <h3 className="text-sm font-bold text-[#F5F5F5]">
                    {MONTHS[month]} {selectedDay}, {year}
                  </h3>
                </div>
                {!dayUploads || dayUploads.uploads?.length === 0 ? (
                  <div className="text-center py-8 text-[#5F6772] text-xs">No videos scheduled for this day.</div>
                ) : (
                  <div className="space-y-2">
                    {dayUploads.uploads.map(upload => (
                      <div
                        key={upload.id}
                        onClick={() => setDetailUpload(upload)}
                        className="flex items-center gap-3 p-3 rounded-xl bg-[rgba(255,255,255,0.02)] border border-[#252A33] hover:border-[#C6F11D] transition-all cursor-pointer"
                      >
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center border shrink-0 ${
                          upload.status === 'done' ? 'bg-[rgba(107,255,100,0.1)] border-[rgba(107,255,100,0.3)]' :
                          upload.status === 'failed' ? 'bg-[rgba(255,87,87,0.1)] border-[rgba(255,87,87,0.3)]' :
                          upload.status === 'processing' ? 'bg-[rgba(255,200,69,0.1)] border-[rgba(255,200,69,0.3)]' :
                          'bg-[rgba(77,166,255,0.1)] border-[rgba(77,166,255,0.3)]'
                        }`}>
                          {STATUS_ICON[upload.status] || <Send className="h-3.5 w-3.5 text-[#4DA6FF]" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-semibold text-[#F5F5F5] truncate">{upload.title || 'Untitled'}</p>
                          <div className="flex items-center gap-2 mt-0.5">
                            {upload.time && (
                              <span className="text-[10px] text-[#5F6772] flex items-center gap-1">
                                <Clock className="h-3 w-3" />{upload.time}
                              </span>
                            )}
                            <span className={`text-[10px] capitalize px-1.5 py-0.5 rounded-full ${
                              upload.status === 'done' ? 'bg-[rgba(107,255,100,0.1)] text-[#6BFF64]' :
                              upload.status === 'failed' ? 'bg-[rgba(255,87,87,0.1)] text-[#FF5757]' :
                              upload.status === 'processing' ? 'bg-[rgba(255,200,69,0.1)] text-[#FFC845]' :
                              'bg-[rgba(77,166,255,0.1)] text-[#4DA6FF]'
                            }`}>{upload.status}</span>
                          </div>
                        </div>
                        {upload.youtube_video_id && (
                          <a
                            href={`https://youtube.com/shorts/${upload.youtube_video_id}`}
                            target="_blank" rel="noopener noreferrer"
                            onClick={e => e.stopPropagation()}
                            className="p-1.5 rounded-lg hover:bg-[rgba(255,87,87,0.1)] text-[#5F6772] hover:text-[#FF5757] transition-colors shrink-0"
                            title="View on YouTube"
                          >
                            <Youtube className="h-3.5 w-3.5" />
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {detailUpload && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80" onClick={() => setDetailUpload(null)}>
          <div className="neo-card p-6 w-[500px] max-h-[90vh] overflow-y-auto flex flex-col gap-4 relative" onClick={e => e.stopPropagation()}>
            <button
              onClick={() => setDetailUpload(null)}
              className="absolute top-4 right-4 p-1.5 rounded-lg hover:bg-[rgba(255,255,255,0.05)] text-[#5F6772] hover:text-[#F5F5F5] transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
            
            <h3 className="neo-title text-base pr-8">{detailUpload.title || 'Untitled Video'}</h3>
            
            {detailUpload.video_url ? (
              <div className="rounded-xl overflow-hidden bg-black aspect-[9/16] max-h-[45vh] w-full flex items-center justify-center border border-[#252A33]">
                <video
                  src={detailUpload.video_url}
                  controls
                  className="w-full h-full object-contain"
                  autoPlay
                />
              </div>
            ) : (
              <div className="rounded-xl bg-[rgba(255,255,255,0.02)] border border-[#252A33] aspect-[9/16] max-h-[45vh] w-full flex flex-col items-center justify-center text-[#5F6772] text-xs">
                <Clock className="h-8 w-8 mb-2 opacity-30" />
                No video file available yet
              </div>
            )}

            <div className="space-y-3 mt-2">
              <div>
                <span className="text-[10px] text-[#5F6772] uppercase font-bold tracking-wider">Status</span>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-[10px] capitalize px-2 py-0.5 rounded-full ${
                    detailUpload.status === 'done' ? 'bg-[rgba(107,255,100,0.1)] text-[#6BFF64]' :
                    detailUpload.status === 'failed' ? 'bg-[rgba(255,87,87,0.1)] text-[#FF5757]' :
                    detailUpload.status === 'processing' ? 'bg-[rgba(255,200,69,0.1)] text-[#FFC845]' :
                    'bg-[rgba(77,166,255,0.1)] text-[#4DA6FF]'
                  }`}>{detailUpload.status}</span>
                  {detailUpload.scheduled_for && (
                    <span className="text-[10px] text-[#9AA0A6]">
                      Scheduled: {new Date(detailUpload.scheduled_for).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>

              {detailUpload.description && (
                <div>
                  <span className="text-[10px] text-[#5F6772] uppercase font-bold tracking-wider">Description</span>
                  <p className="text-xs text-[#9AA0A6] mt-1 bg-[rgba(255,255,255,0.02)] p-2.5 rounded-lg border border-[#1E222B] whitespace-pre-wrap max-h-[120px] overflow-y-auto">
                    {detailUpload.description}
                  </p>
                </div>
              )}

              {detailUpload.tags && typeof detailUpload.tags === 'string' && (
                <div>
                  <span className="text-[10px] text-[#5F6772] uppercase font-bold tracking-wider">Tags</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {detailUpload.tags.split(',').map((tag, idx) => (
                      <span key={idx} className="text-[10px] bg-[rgba(198,241,29,0.08)] text-[#C6F11D] border border-[rgba(198,241,29,0.15)] px-2 py-0.5 rounded-full">
                        {tag.trim()}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {actionMsg && (
                <div className={`text-xs p-2.5 rounded-lg border ${
                  actionMsg.type === 'success' ? 'bg-[rgba(107,255,100,0.08)] border-[rgba(107,255,100,0.15)] text-[#6BFF64]' :
                  actionMsg.type === 'error' ? 'bg-[rgba(255,87,87,0.08)] border-[rgba(255,87,87,0.15)] text-[#FF5757]' :
                  'bg-[rgba(77,166,255,0.08)] border-[rgba(77,166,255,0.15)] text-[#4DA6FF]'
                }`}>
                  {actionMsg.text}
                </div>
              )}

              <div className="flex gap-2 pt-2 border-t border-[#252A33]">
                {detailUpload.status !== 'done' && (
                  <button
                    disabled={actionLoading}
                    onClick={() => handlePostNow(detailUpload.id)}
                    className="flex-1 bg-[#C6F11D] text-[#050608] hover:bg-[#b0d51a] disabled:opacity-50 transition-colors font-bold rounded-xl py-2 text-xs flex items-center justify-center gap-1.5"
                  >
                    <Youtube className="h-3.5 w-3.5" />
                    Post Immediately
                  </button>
                )}
                <button
                  disabled={actionLoading}
                  onClick={() => handleCancelUpload(detailUpload.id)}
                  className="flex-1 bg-[rgba(255,87,87,0.1)] text-[#FF5757] border border-[rgba(255,87,87,0.2)] hover:bg-[rgba(255,87,87,0.2)] disabled:opacity-50 transition-colors font-bold rounded-xl py-2 text-xs flex items-center justify-center gap-1.5"
                >
                  <X className="h-3.5 w-3.5" />
                  Cancel Upload
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ScheduleCalendar;
