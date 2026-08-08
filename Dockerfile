FROM ubuntu:22.04

RUN apt-get update && apt-get install -y ca-certificates && update-ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY yyb-go /app/yyb-go
COPY resource /app/resource

EXPOSE 8002

ENTRYPOINT ["/app/yyb-go"]
CMD ["-host", "0.0.0.0", "-port", "8002", "-resource-root", "/app/resource"]
