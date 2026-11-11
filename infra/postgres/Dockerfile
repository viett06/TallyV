FROM postgres:16-alpine AS build
ARG PGVECTOR_VERSION=0.8.2
RUN apk add --no-cache build-base curl \
    && curl -fsSL "https://codeload.github.com/pgvector/pgvector/tar.gz/refs/tags/v${PGVECTOR_VERSION}" | tar -xz -C /tmp \
    && make -C "/tmp/pgvector-${PGVECTOR_VERSION}" with_llvm=no OPTFLAGS="" \
    && make -C "/tmp/pgvector-${PGVECTOR_VERSION}" with_llvm=no DESTDIR=/install install

FROM postgres:16-alpine
COPY --from=build /install/usr/local/ /usr/local/
