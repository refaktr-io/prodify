# Runs inside the site owner's account (see app.py). Everything is pinned:
# this image is pulled by stacks in other accounts, so builds must be reproducible.
FROM public.ecr.aws/lambda/python:3.13-arm64@sha256:790178a0fca178964c62db55f3f8f3319cbcafd125192cd18729a11a0ec01ea6

ARG NODE_VERSION=22.23.2
ARG BUN_VERSION=1.4.2

RUN dnf install -y tar gzip unzip && \
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-arm64.tar.gz" | tar -xz -C /usr/local --strip-components=1 && \
    curl -fsSL https://bun.sh/install | BUN_INSTALL=/usr/local bash -s "bun-v${BUN_VERSION}" && \
    dnf clean all && rm -rf /var/cache/dnf

RUN node --version && npm --version && bun --version

COPY app.py ${LAMBDA_TASK_ROOT}/

CMD ["app.handler"]
