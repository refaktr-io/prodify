# Runs inside the site owner's account (see app.py). Everything is pinned:
# this image is pulled by stacks in other accounts, so builds must be reproducible.
FROM public.ecr.aws/lambda/python:3.14-arm64@sha256:4f7579c9c34916dc01053e97d2476a29e1970d5320ce0a71dfc1ac8582828851

ARG NODE_VERSION=22.23.2
ARG BUN_VERSION=1.4.2

RUN dnf install -y tar gzip unzip && \
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-arm64.tar.gz" | tar -xz -C /usr/local --strip-components=1 && \
    curl -fsSL https://bun.sh/install | BUN_INSTALL=/usr/local bash -s "bun-v${BUN_VERSION}" && \
    dnf clean all && rm -rf /var/cache/dnf

RUN node --version && npm --version && bun --version

COPY app.py ${LAMBDA_TASK_ROOT}/

CMD ["app.handler"]
