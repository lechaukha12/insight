import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;

public class App {
    static final String SERVICE = System.getenv().getOrDefault("SERVICE_NAME", "unknown");
    static final String PEER_URL = System.getenv().getOrDefault("PEER_URL", "");
    static final Random RNG = new Random();
    static int requestCount = 0;

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(8080), 0);
        server.setExecutor(Executors.newFixedThreadPool(4));

        // Health
        server.createContext("/health", ex -> respond(ex, 200, "{\"status\":\"ok\",\"service\":\"" + SERVICE + "\"}"));

        // GET /api/orders or /api/payments
        server.createContext("/api/process", ex -> {
            requestCount++;
            int delay = 20 + RNG.nextInt(80);
            try { Thread.sleep(delay); } catch (InterruptedException ie) { Thread.currentThread().interrupt(); }
            // Sometimes call peer service
            String peerResult = "";
            if (!PEER_URL.isEmpty() && RNG.nextInt(3) == 0) {
                peerResult = callPeer(PEER_URL + "/api/process");
            }
            // Simulate errors 5% of time
            if (RNG.nextInt(20) == 0) {
                respond(ex, 500, "{\"error\":\"internal\",\"service\":\"" + SERVICE + "\"}");
                return;
            }
            respond(ex, 200, "{\"service\":\"" + SERVICE + "\",\"request\":" + requestCount +
                    ",\"latency_ms\":" + delay + ",\"peer\":\"" + peerResult.replace("\"", "'") + "\"}");
        });

        // GET /api/info
        server.createContext("/api/info", ex -> {
            respond(ex, 200, "{\"service\":\"" + SERVICE + "\",\"version\":\"1.0.0\",\"requests\":" + requestCount + "}");
        });

        server.start();
        System.out.println("[" + SERVICE + "] Started on port 8080");

        // Background traffic generator
        ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();
        scheduler.scheduleAtFixedRate(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL("http://localhost:8080/api/process").openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(5000);
                conn.setReadTimeout(5000);
                int code = conn.getResponseCode();
                System.out.println("[" + SERVICE + "] Self-request: " + code);
                conn.disconnect();
            } catch (Exception e) {
                System.out.println("[" + SERVICE + "] Self-request failed: " + e.getMessage());
            }
        }, 10, 15, TimeUnit.SECONDS);
    }

    static void respond(com.sun.net.httpserver.HttpExchange ex, int code, String body) throws IOException {
        ex.getResponseHeaders().set("Content-Type", "application/json");
        byte[] b = body.getBytes();
        ex.sendResponseHeaders(code, b.length);
        ex.getResponseBody().write(b);
        ex.getResponseBody().close();
    }

    static String callPeer(String url) {
        try {
            HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
            conn.setConnectTimeout(3000);
            conn.setReadTimeout(3000);
            BufferedReader r = new BufferedReader(new InputStreamReader(conn.getInputStream()));
            String line = r.readLine();
            r.close();
            conn.disconnect();
            return line != null ? line : "";
        } catch (Exception e) {
            return "error:" + e.getMessage();
        }
    }
}
