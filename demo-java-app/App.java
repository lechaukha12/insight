import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpExchange;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Random;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;
import java.util.logging.Level;

/**
 * Insight Demo Java App — generates traces/metrics/logs via OpenTelemetry Agent
 *
 * Endpoints:
 *   GET /          — Hello page
 *   GET /api/users — Simulates user DB query (~200ms)
 *   GET /api/orders — Simulates order processing (~500ms, sometimes errors)
 *   GET /api/products — Simulates product catalog (~150ms)
 *   GET /health    — Health check
 *
 * A built-in traffic generator calls these endpoints periodically.
 */
public class App {

    private static final Logger logger = Logger.getLogger("demo-java-app");
    private static final Random random = new Random();
    private static final int PORT = Integer.parseInt(System.getenv().getOrDefault("APP_PORT", "8090"));
    private static final DateTimeFormatter fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    public static void main(String[] args) throws IOException {
        logger.info("═══ Demo Java App starting on port " + PORT + " ═══");

        HttpServer server = HttpServer.create(new InetSocketAddress(PORT), 0);
        server.setExecutor(Executors.newFixedThreadPool(10));

        // Register endpoints
        server.createContext("/", new RootHandler());
        server.createContext("/api/users", new UsersHandler());
        server.createContext("/api/orders", new OrdersHandler());
        server.createContext("/api/products", new ProductsHandler());
        server.createContext("/health", new HealthHandler());

        server.start();
        logger.info("Server started on port " + PORT);

        // Start traffic generator
        startTrafficGenerator();
    }

    // ─── Handlers ───

    static class RootHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            logger.info("GET / — homepage request");
            simulateWork(30, 80);
            String response = "{\"service\":\"demo-java-app\",\"status\":\"running\",\"timestamp\":\"" + now() + "\"}";
            sendResponse(exchange, 200, response);
        }
    }

    static class UsersHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            logger.info("GET /api/users — fetching users");
            // Simulate DB query
            simulateWork(150, 300);
            String users = "[{\"id\":1,\"name\":\"Nguyen Van A\",\"email\":\"nva@example.com\"},"
                         + "{\"id\":2,\"name\":\"Tran Thi B\",\"email\":\"ttb@example.com\"},"
                         + "{\"id\":3,\"name\":\"Le Van C\",\"email\":\"lvc@example.com\"}]";
            logger.info("Users query returned 3 results");
            sendResponse(exchange, 200, "{\"users\":" + users + ",\"total\":3}");
        }
    }

    static class OrdersHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            logger.info("GET /api/orders — processing orders");
            // Simulate complex processing
            simulateWork(300, 700);

            // 20% chance of error to generate error traces
            if (random.nextInt(100) < 20) {
                logger.log(Level.SEVERE, "Order processing failed: database connection timeout after 5000ms");
                sendResponse(exchange, 500, "{\"error\":\"Internal Server Error\",\"message\":\"Database connection timeout\"}");
                return;
            }

            // 10% chance of slow response
            if (random.nextInt(100) < 10) {
                logger.log(Level.WARNING, "Order processing slow: query took over 2 seconds");
                simulateWork(1500, 2500);
            }

            String orders = "[{\"id\":1001,\"product\":\"Laptop\",\"amount\":25000000,\"status\":\"completed\"},"
                          + "{\"id\":1002,\"product\":\"Phone\",\"amount\":15000000,\"status\":\"pending\"}]";
            logger.info("Order query completed successfully");
            sendResponse(exchange, 200, "{\"orders\":" + orders + ",\"total\":2}");
        }
    }

    static class ProductsHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            logger.info("GET /api/products — loading product catalog");
            simulateWork(100, 200);

            // 5% chance of error
            if (random.nextInt(100) < 5) {
                logger.log(Level.SEVERE, "Product catalog unavailable: cache miss and upstream timeout");
                sendResponse(exchange, 503, "{\"error\":\"Service Unavailable\",\"message\":\"Product catalog temporarily unavailable\"}");
                return;
            }

            String products = "[{\"id\":1,\"name\":\"Laptop Pro\",\"price\":25000000},"
                            + "{\"id\":2,\"name\":\"Smartphone X\",\"price\":15000000},"
                            + "{\"id\":3,\"name\":\"Tablet Air\",\"price\":12000000}]";
            sendResponse(exchange, 200, "{\"products\":" + products + ",\"total\":3}");
        }
    }

    static class HealthHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            sendResponse(exchange, 200, "{\"status\":\"UP\",\"timestamp\":\"" + now() + "\"}");
        }
    }

    // ─── Helpers ───

    static void simulateWork(int minMs, int maxMs) {
        try {
            int delay = minMs + random.nextInt(maxMs - minMs + 1);
            Thread.sleep(delay);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    static void sendResponse(HttpExchange exchange, int status, String body) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        byte[] bytes = body.getBytes();
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    static String now() {
        return LocalDateTime.now().format(fmt);
    }

    // ─── Traffic Generator ───

    static void startTrafficGenerator() {
        ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(1);
        HttpClient client = HttpClient.newHttpClient();
        String baseUrl = "http://localhost:" + PORT;

        String[] endpoints = {"/", "/api/users", "/api/orders", "/api/products", "/health"};

        scheduler.scheduleWithFixedDelay(() -> {
            try {
                // Pick a random endpoint
                String endpoint = endpoints[random.nextInt(endpoints.length)];
                HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + endpoint))
                    .GET()
                    .build();

                HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
                logger.info("[TrafficGen] " + endpoint + " → " + response.statusCode());
            } catch (Exception e) {
                logger.warning("[TrafficGen] request failed: " + e.getMessage());
            }
        }, 5, 3, TimeUnit.SECONDS);  // Start after 5s, repeat every 3s

        logger.info("Traffic generator started (every 3s)");
    }
}
