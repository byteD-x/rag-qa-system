FROM golang:1.25-bookworm AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY . .
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/go-api ./cmd/server

FROM gcr.io/distroless/static-debian12
COPY --from=builder /out/go-api /go-api
EXPOSE 8080
USER nonroot:nonroot
ENTRYPOINT ["/go-api"]

