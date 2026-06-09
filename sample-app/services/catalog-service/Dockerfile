FROM golang:1.24-bookworm AS builder
WORKDIR /app
COPY go.mod ./
RUN GOFLAGS=-mod=mod go mod download 2>/dev/null || true
COPY . .
RUN GOFLAGS=-mod=mod CGO_ENABLED=0 GOOS=linux go build -o service .

FROM gcr.io/distroless/static-debian12
WORKDIR /app
COPY --from=builder /app/service .
EXPOSE 8081
CMD ["./service"]
