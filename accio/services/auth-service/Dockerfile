FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod ./
RUN go mod download
COPY *.go ./
RUN CGO_ENABLED=0 GOOS=linux go build -o /server

FROM alpine:latest
WORKDIR /
COPY --from=builder /server /server
EXPOSE 8081
CMD ["/server"]
