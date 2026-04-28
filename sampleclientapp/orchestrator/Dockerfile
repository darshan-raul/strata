FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod ./
COPY . .
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -o orchestrator main.go

FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/orchestrator .
EXPOSE 8080
CMD ["./orchestrator"]
