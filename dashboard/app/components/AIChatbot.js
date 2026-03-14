'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useAuth } from './AuthProvider';

const API_BASE = '';

async function chatAPI(endpoint, opts = {}) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('insight_token') : null;
    const headers = { 'Content-Type': 'application/json', ...opts.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}${endpoint}`, { headers, ...opts });
    if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.detail || `Error ${res.status}`);
    }
    return res.json();
}

/* Simple markdown-like renderer for bot messages */
function renderMarkdown(text) {
    if (!text) return '';
    return text
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code style="background:rgba(0,0,0,0.3);padding:1px 5px;border-radius:3px;font-size:12px">$1</code>')
        .replace(/^### (.+)$/gm, '<div style="font-weight:700;font-size:14px;margin:8px 0 4px;color:#60a5fa">$1</div>')
        .replace(/^## (.+)$/gm, '<div style="font-weight:700;font-size:15px;margin:10px 0 4px;color:#60a5fa">$1</div>')
        .replace(/^# (.+)$/gm, '<div style="font-weight:700;font-size:16px;margin:10px 0 6px;color:#60a5fa">$1</div>')
        .replace(/^- (.+)$/gm, '<div style="padding-left:12px">• $1</div>')
        .replace(/^(\d+)\. (.+)$/gm, '<div style="padding-left:12px">$1. $2</div>')
        .replace(/\n/g, '<br/>');
}

export default function AIChatbot() {
    const { user } = useAuth();
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [position, setPosition] = useState({ x: -1, y: -1 });
    const [dragging, setDragging] = useState(false);
    const messagesEndRef = useRef(null);
    const botRef = useRef(null);
    const hasMovedRef = useRef(false);
    const dragOffsetRef = useRef({ x: 0, y: 0 });

    // Initialize position on mount
    useEffect(() => {
        if (position.x === -1) {
            setPosition({ x: window.innerWidth - 90, y: window.innerHeight - 90 });
        }
    }, [position.x]);

    // Auto-scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // Drag + click handlers
    const handleMouseDown = useCallback((e) => {
        if (e.target.closest('.ai-chat-window')) return;
        const rect = botRef.current?.getBoundingClientRect();
        if (rect) {
            dragOffsetRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        }
        hasMovedRef.current = false;
        setDragging(true);
        e.preventDefault();
    }, []);

    const handleTouchStart = useCallback((e) => {
        if (e.target.closest('.ai-chat-window')) return;
        const touch = e.touches[0];
        const rect = botRef.current?.getBoundingClientRect();
        if (rect) {
            dragOffsetRef.current = { x: touch.clientX - rect.left, y: touch.clientY - rect.top };
        }
        hasMovedRef.current = false;
        setDragging(true);
    }, []);

    useEffect(() => {
        if (!dragging) return;
        const onMove = (e) => {
            hasMovedRef.current = true;
            const off = dragOffsetRef.current;
            setPosition({
                x: Math.max(0, Math.min(window.innerWidth - 70, e.clientX - off.x)),
                y: Math.max(0, Math.min(window.innerHeight - 70, e.clientY - off.y)),
            });
        };
        const onTouchMove = (e) => {
            hasMovedRef.current = true;
            const touch = e.touches[0];
            const off = dragOffsetRef.current;
            setPosition({
                x: Math.max(0, Math.min(window.innerWidth - 70, touch.clientX - off.x)),
                y: Math.max(0, Math.min(window.innerHeight - 70, touch.clientY - off.y)),
            });
        };
        const onEnd = () => {
            setDragging(false);
            if (!hasMovedRef.current) {
                setIsOpen(prev => !prev);
            }
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onEnd);
        window.addEventListener('touchmove', onTouchMove);
        window.addEventListener('touchend', onEnd);
        return () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onEnd);
            window.removeEventListener('touchmove', onTouchMove);
            window.removeEventListener('touchend', onEnd);
        };
    }, [dragging]);

    // Send message
    const sendMessage = async () => {
        if (!input.trim() || loading) return;
        const userMsg = input.trim();
        setInput('');
        setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
        setLoading(true);

        try {
            const history = messages.map(m => ({ role: m.role, content: m.content }));
            const res = await chatAPI('/api/v1/chat', {
                method: 'POST',
                body: JSON.stringify({ message: userMsg, history }),
            });
            setMessages(prev => [...prev, { role: 'model', content: res.reply }]);
        } catch (err) {
            setMessages(prev => [...prev, { role: 'model', content: `⚠️ ${err.message}` }]);
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    // Only render for admin
    if (!user || user.role !== 'admin') return null;
    if (position.x === -1) return null;

    return (
        <>
            {/* Floating Robot Button — HIDDEN when chat is open */}
            {!isOpen && (
                <div
                    ref={botRef}
                    onMouseDown={handleMouseDown}
                    onTouchStart={handleTouchStart}
                    style={{
                        position: 'fixed',
                        left: position.x,
                        top: position.y,
                        width: 60,
                        height: 60,
                        borderRadius: '50%',
                        cursor: dragging ? 'grabbing' : 'pointer',
                        zIndex: 10000,
                        userSelect: 'none',
                        transition: dragging ? 'none' : 'box-shadow 0.3s ease',
                        filter: 'drop-shadow(0 4px 12px rgba(0,0,0,0.3))',
                        animation: 'ai-bot-pulse 3s ease-in-out infinite',
                    }}
                >
                    <img
                        src="/images/oppa.png"
                        alt="AI Assistant"
                        style={{ width: '100%', height: '100%', borderRadius: '50%', objectFit: 'cover', pointerEvents: 'none' }}
                        draggable={false}
                    />
                    <span style={{
                        position: 'absolute', bottom: 2, right: 2, width: 14, height: 14,
                        background: '#22c55e', borderRadius: '50%', border: '2px solid white',
                    }} />
                </div>
            )}

            {/* Chat Window */}
            {isOpen && (
                <div
                    className="ai-chat-window"
                    style={{
                        position: 'fixed',
                        right: 24,
                        bottom: 24,
                        width: 440,
                        height: 560,
                        background: '#0f172a',
                        borderRadius: 20,
                        border: '1px solid rgba(99,102,241,0.3)',
                        boxShadow: '0 25px 60px rgba(0,0,0,0.5), 0 0 40px rgba(99,102,241,0.1)',
                        display: 'flex',
                        flexDirection: 'column',
                        zIndex: 10001,
                        overflow: 'hidden',
                        animation: 'ai-chat-slide-up 0.3s ease',
                    }}
                >
                    {/* Header */}
                    <div style={{
                        padding: '14px 16px',
                        background: 'linear-gradient(135deg, #1e3a5f 0%, #312e81 50%, #4c1d95 100%)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        borderBottom: '1px solid rgba(99,102,241,0.2)',
                    }}>
                        <img src="/images/oppa.png" alt="" style={{ width: 36, height: 36, borderRadius: '50%', objectFit: 'cover', border: '2px solid rgba(255,255,255,0.2)' }} />
                        <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 700, fontSize: 14, color: '#f1f5f9' }}>Insight AI Assistant</div>
                            <div style={{ fontSize: 11, color: 'rgba(148,163,184,0.8)', display: 'flex', alignItems: 'center', gap: 4 }}>
                                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#22c55e', display: 'inline-block' }} />
                                MCP Server · Online
                            </div>
                        </div>
                        <button
                            onClick={() => setMessages([])}
                            style={{
                                background: 'rgba(255,255,255,0.08)', border: 'none', color: '#94a3b8',
                                width: 30, height: 30, borderRadius: 8, cursor: 'pointer', fontSize: 13,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}
                            title="Clear chat"
                        >🗑</button>
                        <button
                            onClick={() => setIsOpen(false)}
                            style={{
                                background: 'rgba(255,255,255,0.08)', border: 'none', color: '#94a3b8',
                                width: 30, height: 30, borderRadius: 8, cursor: 'pointer', fontSize: 16, fontWeight: 700,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}
                        >✕</button>
                    </div>

                    {/* Messages */}
                    <div style={{
                        flex: 1,
                        overflowY: 'auto',
                        padding: '14px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 12,
                        background: '#0f172a',
                    }}>
                        {messages.length === 0 && (
                            <div style={{
                                textAlign: 'center', padding: '36px 20px',
                                color: '#64748b',
                            }}>
                                <img src="/images/oppa.png" alt="" style={{ width: 56, height: 56, borderRadius: '50%', margin: '0 auto 12px', display: 'block', opacity: 0.8 }} />
                                <div style={{ fontWeight: 600, fontSize: 15, color: '#cbd5e1', marginBottom: 6 }}>Xin chào, Admin!</div>
                                <div style={{ fontSize: 12, lineHeight: 1.6, color: '#64748b', marginBottom: 16 }}>
                                    Tôi là Insight AI — sử dụng MCP Server<br/>để truy vấn dữ liệu monitoring an toàn.
                                </div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'center' }}>
                                    {['Hệ thống có vấn đề gì?', 'Top services chậm nhất?', 'Agent nào offline?'].map(q => (
                                        <button
                                            key={q}
                                            onClick={() => { setInput(q); }}
                                            style={{
                                                background: 'rgba(99,102,241,0.1)',
                                                border: '1px solid rgba(99,102,241,0.25)',
                                                borderRadius: 20, padding: '7px 14px', fontSize: 11,
                                                color: '#818cf8',
                                                cursor: 'pointer', transition: 'all 0.2s',
                                            }}
                                            onMouseEnter={e => { e.target.style.background = 'rgba(99,102,241,0.2)'; e.target.style.borderColor = 'rgba(99,102,241,0.5)'; }}
                                            onMouseLeave={e => { e.target.style.background = 'rgba(99,102,241,0.1)'; e.target.style.borderColor = 'rgba(99,102,241,0.25)'; }}
                                        >{q}</button>
                                    ))}
                                </div>
                            </div>
                        )}
                        {messages.map((msg, i) => (
                            <div
                                key={i}
                                style={{
                                    display: 'flex',
                                    justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                                    gap: 8,
                                    alignItems: 'flex-start',
                                }}
                            >
                                {msg.role !== 'user' && (
                                    <img src="/images/oppa.png" alt="" style={{ width: 28, height: 28, borderRadius: '50%', objectFit: 'cover', flexShrink: 0, marginTop: 2 }} />
                                )}
                                <div style={{
                                    maxWidth: '82%',
                                    padding: '10px 14px',
                                    borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                                    background: msg.role === 'user'
                                        ? 'linear-gradient(135deg, #4f46e5, #7c3aed)'
                                        : '#1e293b',
                                    color: msg.role === 'user' ? '#f1f5f9' : '#e2e8f0',
                                    fontSize: 13,
                                    lineHeight: 1.6,
                                    wordBreak: 'break-word',
                                    border: msg.role === 'user' ? 'none' : '1px solid rgba(51,65,85,0.6)',
                                }}>
                                    {msg.role === 'user' ? (
                                        msg.content
                                    ) : (
                                        <div dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
                                    )}
                                </div>
                            </div>
                        ))}
                        {loading && (
                            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                                <img src="/images/oppa.png" alt="" style={{ width: 28, height: 28, borderRadius: '50%', objectFit: 'cover', flexShrink: 0, marginTop: 2 }} />
                                <div style={{
                                    padding: '10px 14px',
                                    borderRadius: '16px 16px 16px 4px',
                                    background: '#1e293b',
                                    border: '1px solid rgba(51,65,85,0.6)',
                                    color: '#64748b',
                                    fontSize: 13,
                                }}>
                                    <span className="ai-typing-dots">
                                        <span>●</span><span>●</span><span>●</span>
                                    </span>
                                    <span style={{ fontSize: 11, marginLeft: 8, color: '#475569' }}>Đang truy vấn MCP...</span>
                                </div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>

                    {/* Input */}
                    <div style={{
                        padding: '12px 14px',
                        borderTop: '1px solid rgba(51,65,85,0.5)',
                        display: 'flex',
                        gap: 8,
                        background: '#0f172a',
                    }}>
                        <input
                            type="text"
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Hỏi về hệ thống..."
                            disabled={loading}
                            style={{
                                flex: 1, padding: '10px 14px',
                                background: '#1e293b',
                                border: '1px solid rgba(51,65,85,0.6)',
                                borderRadius: 12, color: '#e2e8f0',
                                fontSize: 13, outline: 'none',
                            }}
                        />
                        <button
                            onClick={sendMessage}
                            disabled={!input.trim() || loading}
                            style={{
                                padding: '0 18px',
                                background: input.trim() && !loading ? 'linear-gradient(135deg, #4f46e5, #7c3aed)' : 'rgba(51,65,85,0.3)',
                                border: 'none', borderRadius: 12,
                                color: input.trim() && !loading ? '#fff' : '#475569',
                                cursor: input.trim() && !loading ? 'pointer' : 'not-allowed',
                                fontSize: 16, fontWeight: 700,
                                transition: 'all 0.2s',
                            }}
                        >➤</button>
                    </div>
                </div>
            )}

            {/* Styles */}
            <style jsx global>{`
                @keyframes ai-bot-pulse {
                    0%, 100% { transform: scale(1); }
                    50% { transform: scale(1.06); }
                }
                @keyframes ai-chat-slide-up {
                    from { opacity: 0; transform: translateY(20px) scale(0.95); }
                    to { opacity: 1; transform: translateY(0) scale(1); }
                }
                .ai-typing-dots span {
                    animation: ai-dot-bounce 1.4s infinite both;
                    display: inline-block;
                    margin: 0 1px;
                    font-size: 10px;
                }
                .ai-typing-dots span:nth-child(2) { animation-delay: 0.2s; }
                .ai-typing-dots span:nth-child(3) { animation-delay: 0.4s; }
                @keyframes ai-dot-bounce {
                    0%, 80%, 100% { opacity: 0.3; }
                    40% { opacity: 1; }
                }
                .ai-chat-window::-webkit-scrollbar { width: 4px; }
                .ai-chat-window::-webkit-scrollbar-thumb { background: rgba(99,102,241,0.3); border-radius: 4px; }
                .ai-chat-window div::-webkit-scrollbar { width: 4px; }
                .ai-chat-window div::-webkit-scrollbar-thumb { background: rgba(99,102,241,0.3); border-radius: 4px; }
            `}</style>
        </>
    );
}
