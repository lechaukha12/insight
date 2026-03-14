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

export default function AIChatbot() {
    const { user } = useAuth();
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [position, setPosition] = useState({ x: -1, y: -1 });
    const [dragging, setDragging] = useState(false);
    const messagesEndRef = useRef(null);
    const chatRef = useRef(null);
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

    // Drag handlers using refs to avoid stale closures
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
            {/* Floating Robot Button */}
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
                    filter: `drop-shadow(0 4px 12px rgba(0,0,0,0.3))${isOpen ? ' brightness(1.1)' : ''}`,
                    animation: isOpen ? 'none' : 'ai-bot-pulse 3s ease-in-out infinite',
                }}
            >
                <img
                    src="/images/oppa.png"
                    alt="AI Assistant"
                    style={{ width: '100%', height: '100%', borderRadius: '50%', objectFit: 'cover', pointerEvents: 'none' }}
                    draggable={false}
                />
                {/* Online indicator */}
                <span style={{
                    position: 'absolute', bottom: 2, right: 2, width: 14, height: 14,
                    background: '#22c55e', borderRadius: '50%', border: '2px solid white',
                }} />
            </div>

            {/* Chat Window */}
            {isOpen && (
                <div
                    ref={chatRef}
                    className="ai-chat-window"
                    style={{
                        position: 'fixed',
                        right: 20,
                        bottom: 20,
                        width: 400,
                        height: 520,
                        background: 'var(--color-bg-card, #1e293b)',
                        borderRadius: 16,
                        border: '1px solid var(--color-border, rgba(255,255,255,0.1))',
                        boxShadow: '0 20px 60px rgba(0,0,0,0.4), 0 0 40px rgba(59,130,246,0.1)',
                        display: 'flex',
                        flexDirection: 'column',
                        zIndex: 9999,
                        overflow: 'hidden',
                        animation: 'ai-chat-slide-up 0.3s ease',
                    }}
                >
                    {/* Header */}
                    <div style={{
                        padding: '14px 16px',
                        background: 'linear-gradient(135deg, #1e40af 0%, #7c3aed 100%)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                    }}>
                        <img src="/images/oppa.png" alt="" style={{ width: 32, height: 32, borderRadius: '50%', objectFit: 'cover' }} />
                        <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 700, fontSize: 14, color: '#fff' }}>Insight AI Assistant</div>
                            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.7)' }}>Powered by Gemini</div>
                        </div>
                        <button
                            onClick={() => setMessages([])}
                            style={{
                                background: 'rgba(255,255,255,0.15)', border: 'none', color: '#fff',
                                width: 28, height: 28, borderRadius: 6, cursor: 'pointer', fontSize: 12,
                            }}
                            title="Clear chat"
                        >✕</button>
                        <button
                            onClick={() => setIsOpen(false)}
                            style={{
                                background: 'rgba(255,255,255,0.15)', border: 'none', color: '#fff',
                                width: 28, height: 28, borderRadius: 6, cursor: 'pointer', fontSize: 14, fontWeight: 700,
                            }}
                        >—</button>
                    </div>

                    {/* Messages */}
                    <div style={{
                        flex: 1,
                        overflowY: 'auto',
                        padding: '12px 14px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 10,
                    }}>
                        {messages.length === 0 && (
                            <div style={{
                                textAlign: 'center', padding: '40px 20px',
                                color: 'var(--text-muted, rgba(255,255,255,0.4))',
                            }}>
                                <div style={{ fontSize: 40, marginBottom: 12 }}>🤖</div>
                                <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>Xin chào, Admin!</div>
                                <div style={{ fontSize: 12, lineHeight: 1.5 }}>
                                    Tôi là Insight AI Assistant. Hỏi tôi bất cứ điều gì về hệ thống monitoring của bạn.
                                </div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'center', marginTop: 16 }}>
                                    {['Hệ thống có vấn đề gì?', 'Top services chậm nhất?', 'Agent nào offline?'].map(q => (
                                        <button
                                            key={q}
                                            onClick={() => { setInput(q); }}
                                            style={{
                                                background: 'var(--bg-input, rgba(255,255,255,0.05))',
                                                border: '1px solid var(--color-border, rgba(255,255,255,0.1))',
                                                borderRadius: 20, padding: '6px 12px', fontSize: 11,
                                                color: 'var(--text-secondary, rgba(255,255,255,0.6))',
                                                cursor: 'pointer', transition: 'all 0.2s',
                                            }}
                                            onMouseEnter={e => { e.target.style.background = 'rgba(59,130,246,0.2)'; e.target.style.borderColor = 'rgba(59,130,246,0.4)'; }}
                                            onMouseLeave={e => { e.target.style.background = 'var(--bg-input, rgba(255,255,255,0.05))'; e.target.style.borderColor = 'var(--color-border, rgba(255,255,255,0.1))'; }}
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
                                }}
                            >
                                <div style={{
                                    maxWidth: '85%',
                                    padding: '10px 14px',
                                    borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                                    background: msg.role === 'user'
                                        ? 'linear-gradient(135deg, #2563eb, #7c3aed)'
                                        : 'var(--bg-input, rgba(255,255,255,0.06))',
                                    color: msg.role === 'user' ? '#fff' : 'var(--color-text, #e2e8f0)',
                                    fontSize: 13,
                                    lineHeight: 1.5,
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                }}>
                                    {msg.content}
                                </div>
                            </div>
                        ))}
                        {loading && (
                            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                                <div style={{
                                    padding: '10px 14px',
                                    borderRadius: '14px 14px 14px 4px',
                                    background: 'var(--bg-input, rgba(255,255,255,0.06))',
                                    color: 'var(--text-muted, rgba(255,255,255,0.4))',
                                    fontSize: 13,
                                }}>
                                    <span className="ai-typing-dots">
                                        <span>●</span><span>●</span><span>●</span>
                                    </span>
                                </div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>

                    {/* Input */}
                    <div style={{
                        padding: '10px 14px',
                        borderTop: '1px solid var(--color-border, rgba(255,255,255,0.1))',
                        display: 'flex',
                        gap: 8,
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
                                background: 'var(--bg-input, rgba(255,255,255,0.06))',
                                border: '1px solid var(--color-border, rgba(255,255,255,0.1))',
                                borderRadius: 10, color: 'var(--color-text, #e2e8f0)',
                                fontSize: 13, outline: 'none',
                            }}
                        />
                        <button
                            onClick={sendMessage}
                            disabled={!input.trim() || loading}
                            style={{
                                padding: '0 16px',
                                background: input.trim() && !loading ? 'linear-gradient(135deg, #2563eb, #7c3aed)' : 'rgba(255,255,255,0.06)',
                                border: 'none', borderRadius: 10,
                                color: input.trim() && !loading ? '#fff' : 'var(--text-muted, rgba(255,255,255,0.3))',
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
            `}</style>
        </>
    );
}
