FROM golang:1.24.8-bookworm AS builder
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN go install -ldflags='-s -w' github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z
RUN go install -ldflags='-s -w' github.com/minio/mc@RELEASE.2025-08-13T08-35-41Z

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home minio \
    && mkdir /data && chown minio:minio /data
COPY --from=builder /go/bin/minio /go/bin/mc /usr/local/bin/
COPY init.sh /usr/local/bin/init-storage
USER minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
