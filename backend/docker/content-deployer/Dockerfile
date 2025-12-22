FROM public.ecr.aws/lambda/python:3.13-arm64

# Install Node.js 20 for ARM64
RUN dnf install -y tar gzip && \
    curl -sL https://nodejs.org/dist/v20.18.1/node-v20.18.1-linux-arm64.tar.gz | tar -xz -C /usr/local --strip-components=1 && \
    dnf clean all

# Verify installation
RUN node --version && npm --version

# Copy Lambda handler
COPY app.py ${LAMBDA_TASK_ROOT}/

CMD ["app.handler"]
