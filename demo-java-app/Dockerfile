# ─── Stage 1: Compile ───
FROM eclipse-temurin:17-jdk AS builder
WORKDIR /build
COPY App.java .
RUN javac App.java

# ─── Stage 2: Download OTel Agent ───
FROM eclipse-temurin:17-jdk AS otel-download
RUN curl -L -o /opentelemetry-javaagent.jar \
    https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v2.12.0/opentelemetry-javaagent.jar

# ─── Stage 3: Runtime ───
FROM eclipse-temurin:17-jre
WORKDIR /app

COPY --from=builder /build/*.class /app/
COPY --from=otel-download /opentelemetry-javaagent.jar /app/opentelemetry-javaagent.jar

# Default env vars (can be overridden by K8s)
ENV APP_PORT=8090
ENV JAVA_TOOL_OPTIONS="-javaagent:/app/opentelemetry-javaagent.jar"

EXPOSE 8090

CMD ["java", "App"]
