package com.insight;

import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpExchange;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;

/**
 * Order Service — generates traces calling payment-service and external APIs.
 * Auto-instrumented by OTEL Java Agent.
 */
public class OrderService {
    private static final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    private static final Random random = new Random();
    private static final String PAYMENT_URL = System.getenv().getOrDefault("PAYMENT_SERVICE_URL", "http://payment-service:8082");
    private static final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(4);

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(8081), 0);
        server.createContext("/healthz", OrderService::healthCheck);
        server.createContext("/api/orders", OrderService::createOrder);
        server.createContext("/api/orders/list", OrderService::listOrders);
        server.createContext("/api/orders/status", OrderService::orderStatus);
        server.setExecutor(Executors.newFixedThreadPool(10));
        server.start();
        System.out.println("[order-service] Started on port 8081");

        // Auto-generate traces every 3-8 seconds
        scheduler.scheduleAtFixedRate(OrderService::autoGenerateTraces, 5, 1, TimeUnit.SECONDS);
    }

    private static void healthCheck(HttpExchange exchange) throws IOException {
        respond(exchange, 200, "{\"status\":\"ok\",\"service\":\"order-service\"}");
    }

    private static void createOrder(HttpExchange exchange) throws IOException {
        String orderId = "ORD-" + System.currentTimeMillis();
        double amount = 10 + random.nextDouble() * 990;

        // Simulate order validation (20-80ms)
        sleep(20 + random.nextInt(60));

        // Call payment-service
        String paymentResult;
        try {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(PAYMENT_URL + "/api/payments/process?orderId=" + orderId + "&amount=" + String.format("%.2f", amount)))
                    .POST(HttpRequest.BodyPublishers.noBody())
                    .timeout(Duration.ofSeconds(10))
                    .build();
            HttpResponse<String> resp = client.send(req, HttpResponse.BodyHandlers.ofString());
            paymentResult = resp.body();
        } catch (Exception e) {
            paymentResult = "{\"status\":\"payment_failed\",\"error\":\"" + e.getMessage() + "\"}";
        }

        // Random: call external API for enrichment (30% chance)
        String enrichment = "{}";
        if (random.nextInt(100) < 30) {
            enrichment = callExternal("https://httpbin.org/get?order=" + orderId);
        }

        // Random error (8% chance)
        if (random.nextInt(100) < 8) {
            respond(exchange, 500, "{\"error\":\"Internal order processing error\",\"orderId\":\"" + orderId + "\"}");
            return;
        }

        respond(exchange, 201, "{\"orderId\":\"" + orderId + "\",\"amount\":" + String.format("%.2f", amount)
                + ",\"payment\":" + paymentResult + ",\"status\":\"created\"}");
    }

    private static void listOrders(HttpExchange exchange) throws IOException {
        sleep(15 + random.nextInt(30));
        // Call external API for currency rates
        if (random.nextInt(100) < 20) {
            callExternal("https://httpbin.org/json");
        }
        respond(exchange, 200, "{\"orders\":[],\"total\":0}");
    }

    private static void orderStatus(HttpExchange exchange) throws IOException {
        sleep(10 + random.nextInt(20));
        // 5% chance of error
        if (random.nextInt(100) < 5) {
            respond(exchange, 404, "{\"error\":\"Order not found\"}");
            return;
        }
        respond(exchange, 200, "{\"status\":\"completed\"}");
    }

    private static void autoGenerateTraces() {
        try {
            // Create varied requests to generate different trace patterns
            int action = random.nextInt(10);
            String baseUrl = "http://localhost:8081";

            if (action < 5) {
                // POST create order (most frequent)
                HttpRequest req = HttpRequest.newBuilder()
                        .uri(URI.create(baseUrl + "/api/orders"))
                        .POST(HttpRequest.BodyPublishers.noBody())
                        .build();
                client.send(req, HttpResponse.BodyHandlers.ofString());
            } else if (action < 8) {
                // GET list orders
                HttpRequest req = HttpRequest.newBuilder()
                        .uri(URI.create(baseUrl + "/api/orders/list"))
                        .build();
                client.send(req, HttpResponse.BodyHandlers.ofString());
            } else {
                // GET order status
                HttpRequest req = HttpRequest.newBuilder()
                        .uri(URI.create(baseUrl + "/api/orders/status?id=ORD-" + System.currentTimeMillis()))
                        .build();
                client.send(req, HttpResponse.BodyHandlers.ofString());
            }
        } catch (Exception e) {
            // Silently ignore — traces still captured by OTEL agent
        }
    }

    private static String callExternal(String url) {
        try {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(5))
                    .build();
            HttpResponse<String> resp = client.send(req, HttpResponse.BodyHandlers.ofString());
            return resp.body().length() > 200 ? resp.body().substring(0, 200) : resp.body();
        } catch (Exception e) {
            return "{\"error\":\"" + e.getMessage() + "\"}";
        }
    }

    private static void sleep(int ms) {
        try { Thread.sleep(ms); } catch (InterruptedException ignored) {}
    }

    private static void respond(HttpExchange exchange, int code, String body) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        byte[] bytes = body.getBytes();
        exchange.sendResponseHeaders(code, bytes.length);
        exchange.getResponseBody().write(bytes);
        exchange.getResponseBody().close();
    }
}
