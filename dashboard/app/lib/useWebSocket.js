'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * WebSocket hook for real-time dashboard updates.
 * Auto-reconnects with exponential backoff.
 */
export function useWebSocket(url) {
    const [lastMessage, setLastMessage] = useState(null);
    const [isConnected, setIsConnected] = useState(false);
    const wsRef = useRef(null);
    const reconnectTimer = useRef(null);
    const retryCount = useRef(0);

    const connect = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return;

        try {
            const ws = new WebSocket(url);
            wsRef.current = ws;

            ws.onopen = () => {
                setIsConnected(true);
                retryCount.current = 0;
                console.log('[WS] Connected');
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type !== 'pong') {
                        setLastMessage(data);
                    }
                } catch (e) {
                    console.warn('[WS] Parse error:', e);
                }
            };

            ws.onclose = () => {
                setIsConnected(false);
                console.log('[WS] Disconnected');
                // Reconnect with backoff: 1s, 2s, 4s, 8s, max 30s
                const delay = Math.min(1000 * Math.pow(2, retryCount.current), 30000);
                retryCount.current++;
                reconnectTimer.current = setTimeout(connect, delay);
            };

            ws.onerror = () => {
                ws.close();
            };
        } catch (e) {
            console.error('[WS] Connection error:', e);
        }
    }, [url]);

    useEffect(() => {
        connect();
        // Ping every 30s to keep alive
        const pingInterval = setInterval(() => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
                wsRef.current.send('ping');
            }
        }, 30000);

        return () => {
            clearInterval(pingInterval);
            clearTimeout(reconnectTimer.current);
            wsRef.current?.close();
        };
    }, [connect]);

    return { lastMessage, isConnected };
}
