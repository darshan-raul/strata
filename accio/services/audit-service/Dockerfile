FROM golang:1.22-bookworm AS builder
WORKDIR /app
COPY go.mod ./
RUN GOFLAGS=-mod=mod go mod download 2>/dev/null || true
COPY . .
RUN GOFLAGS=-mod=mod CGO_ENABLED=0 GOOS=linux go build -o service .

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/service .
EXPOSE 8085
CMD ["./service"]
