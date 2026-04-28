FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod ./
COPY . .
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -o notification main.go

FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/notification .
CMD ["./notification"]
