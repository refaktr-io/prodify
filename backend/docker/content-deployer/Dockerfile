FROM public.ecr.aws/lambda/python:3.13-arm64

# Install Node.js 20 for ARM64 and Bun
RUN dnf install -y tar gzip unzip && \
    curl -sL https://nodejs.org/dist/v20.18.1/node-v20.18.1-linux-arm64.tar.gz | tar -xz -C /usr/local --strip-components=1 && \
    curl -fsSL https://bun.sh/install | BUN_INSTALL=/usr/local bash && \
    dnf clean all

# Verify installation
RUN node --version && npm --version && bun --version

# Copy Lambda handler
COPY app.py ${LAMBDA_TASK_ROOT}/

CMD ["app.handler"]
