/**
 * Catch-all API proxy route handler.
 * Proxies all /api/* requests from the browser to the backend API server.
 * Uses BACKEND_URL env var at RUNTIME (not build time).
 */

const BACKEND = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

async function handler(request, { params }) {
    const { path } = await params;
    const target = `${BACKEND}/api/${path.join('/')}`;
    const url = new URL(target);

    // Forward query params
    const reqUrl = new URL(request.url);
    reqUrl.searchParams.forEach((v, k) => url.searchParams.set(k, v));

    const headers = new Headers();
    for (const [key, value] of request.headers.entries()) {
        if (['host', 'connection', 'transfer-encoding'].includes(key.toLowerCase())) continue;
        headers.set(key, value);
    }

    try {
        const resp = await fetch(url.toString(), {
            method: request.method,
            headers,
            body: ['GET', 'HEAD'].includes(request.method) ? undefined : await request.text(),
        });

        const responseHeaders = new Headers();
        for (const [key, value] of resp.headers.entries()) {
            if (['transfer-encoding', 'content-encoding'].includes(key.toLowerCase())) continue;
            responseHeaders.set(key, value);
        }

        const body = await resp.arrayBuffer();
        return new Response(body, {
            status: resp.status,
            statusText: resp.statusText,
            headers: responseHeaders,
        });
    } catch (err) {
        console.error(`Proxy error: ${url} →`, err.message);
        return new Response(JSON.stringify({ error: 'Backend unreachable', detail: err.message }), {
            status: 502,
            headers: { 'Content-Type': 'application/json' },
        });
    }
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const DELETE = handler;
export const PATCH = handler;
