FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod ./
COPY *.go ./
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -o /server

FROM alpine:latest
WORKDIR /
COPY --from=builder /server /server
CMD ["/server"]
