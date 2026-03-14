FROM eclipse-temurin:21-jdk AS build
WORKDIR /app
COPY App.java .
RUN javac App.java

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/*.class .

# Download OTel Java Agent
ADD https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v2.12.0/opentelemetry-javaagent.jar /app/opentelemetry-javaagent.jar

ENV JAVA_TOOL_OPTIONS="-javaagent:/app/opentelemetry-javaagent.jar"
EXPOSE 8080
CMD ["java", "App"]
