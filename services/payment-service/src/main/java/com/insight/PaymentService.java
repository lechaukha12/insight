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
 * Payment Service — processes payments, validates with external APIs.
 * Auto-instrumented by OTEL Java Agent.
 */
public class PaymentService {
    private static final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    private static final Random random = new Random();
    private static final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2);

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(8082), 0);
        server.createContext("/healthz", PaymentService::healthCheck);
        server.createContext("/api/payments/process", PaymentService::processPayment);
        server.createContext("/api/payments/verify", PaymentService::verifyPayment);
        server.createContext("/api/payments/refund", PaymentService::refundPayment);
        server.setExecutor(Executors.newFixedThreadPool(10));
        server.start();
        System.out.println("[payment-service] Started on port 8082");

        // Auto-generate standalone payment traces every 5-15s
        scheduler.scheduleAtFixedRate(PaymentService::autoGenerateTraces, 10, 2, TimeUnit.SECONDS);
    }

    private static void healthCheck(HttpExchange exchange) throws IOException {
        respond(exchange, 200, "{\"status\":\"ok\",\"service\":\"payment-service\"}");
    }

    private static void processPayment(HttpExchange exchange) throws IOException {
        String query = exchange.getRequestURI().getQuery();
        String orderId = getParam(query, "orderId", "UNKNOWN");
        String amountStr = getParam(query, "amount", "0");

        // Simulate payment gateway processing (50-200ms)
        sleep(50 + random.nextInt(150));

        // Call external fraud check (40% chance)
        if (random.nextInt(100) < 40) {
            callExternal("https://httpbin.org/post", "POST");
        }

        // Call external currency conversion (25% chance)
        if (random.nextInt(100) < 25) {
            callExternal("https://httpbin.org/get?currency=USD&amount=" + amountStr, "GET");
        }

        // Simulate payment errors (12% chance)
        if (random.nextInt(100) < 12) {
            int errorType = random.nextInt(3);
            switch (errorType) {
                case 0:
                    respond(exchange, 402, "{\"status\":\"declined\",\"orderId\":\"" + orderId + "\",\"reason\":\"Insufficient funds\"}");
                    return;
                case 1:
                    respond(exchange, 503, "{\"status\":\"gateway_timeout\",\"orderId\":\"" + orderId + "\",\"reason\":\"Payment gateway unavailable\"}");
                    return;
                case 2:
                    respond(exchange, 500, "{\"status\":\"processing_error\",\"orderId\":\"" + orderId + "\",\"reason\":\"Internal payment error\"}");
                    return;
            }
        }

        String txnId = "TXN-" + System.currentTimeMillis();
        respond(exchange, 200, "{\"status\":\"approved\",\"orderId\":\"" + orderId
                + "\",\"transactionId\":\"" + txnId + "\",\"amount\":" + amountStr + "}");
    }

    private static void verifyPayment(HttpExchange exchange) throws IOException {
        sleep(20 + random.nextInt(40));
        // Call external verification
        if (random.nextInt(100) < 50) {
            callExternal("https://httpbin.org/get?verify=true", "GET");
        }
        // 3% error rate
        if (random.nextInt(100) < 3) {
            respond(exchange, 500, "{\"error\":\"Verification service error\"}");
            return;
        }
        respond(exchange, 200, "{\"verified\":true}");
    }

    private static void refundPayment(HttpExchange exchange) throws IOException {
        sleep(80 + random.nextInt(120));
        // Always calls external refund gateway
        callExternal("https://httpbin.org/post", "POST");
        // 10% error
        if (random.nextInt(100) < 10) {
            respond(exchange, 500, "{\"error\":\"Refund processing failed\"}");
            return;
        }
        respond(exchange, 200, "{\"status\":\"refunded\",\"refundId\":\"REF-" + System.currentTimeMillis() + "\"}");
    }

    private static void autoGenerateTraces() {
        try {
            int action = random.nextInt(10);
            String baseUrl = "http://localhost:8082";

            if (action < 4) {
                // Verify payment
                HttpRequest req = HttpRequest.newBuilder()
                        .uri(URI.create(baseUrl + "/api/payments/verify?txnId=TXN-" + System.currentTimeMillis()))
                        .build();
                client.send(req, HttpResponse.BodyHandlers.ofString());
            } else if (action < 6) {
                // Refund
                HttpRequest req = HttpRequest.newBuilder()
                        .uri(URI.create(baseUrl + "/api/payments/refund?txnId=TXN-" + System.currentTimeMillis()))
                        .POST(HttpRequest.BodyPublishers.noBody())
                        .build();
                client.send(req, HttpResponse.BodyHandlers.ofString());
            }
            // rest: do nothing (order-service drives the main traffic)
        } catch (Exception e) {
            // Traces still captured
        }
    }

    private static String callExternal(String url, String method) {
        try {
            HttpRequest.Builder builder = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(5));
            if ("POST".equals(method)) {
                builder.POST(HttpRequest.BodyPublishers.ofString("{\"check\":true}"));
                builder.header("Content-Type", "application/json");
            }
            HttpResponse<String> resp = client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
            return resp.body().length() > 100 ? resp.body().substring(0, 100) : resp.body();
        } catch (Exception e) {
            return "{\"error\":\"" + e.getMessage() + "\"}";
        }
    }

    private static String getParam(String query, String key, String def) {
        if (query == null) return def;
        for (String p : query.split("&")) {
            String[] kv = p.split("=", 2);
            if (kv.length == 2 && kv[0].equals(key)) return kv[1];
        }
        return def;
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
