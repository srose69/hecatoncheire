FROM nvidia/cuda:12.2.0-devel-ubuntu22.04

ENV HOST=0.0.0.0

# Install dependencies (official llama-cpp-python approach)
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y git build-essential \
    python3 python3-pip gcc wget \
    ocl-icd-opencl-dev opencl-headers clinfo \
    libclblast-dev libopenblas-dev \
    && mkdir -p /etc/OpenCL/vendors && echo "libnvidia-opencl.so.1" > /etc/OpenCL/vendors/nvidia.icd \
    && ln -s /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build settings for CUDA
ENV CUDA_DOCKER_ARCH=all
ENV GGML_CUDA=1

# Install base dependencies with BuildKit cache
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install --upgrade pip pytest cmake scikit-build setuptools

# Install llama-cpp-python with CUDA (cached)
RUN --mount=type=cache,target=/root/.cache/pip \
    CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python[server]

# Install project requirements (copy requirements.txt first for layer caching)
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# Copy application code (these change most frequently - last to maximize cache hits)
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Copy prompts (medium frequency)
COPY prompts/ prompts/

# Copy source code last (changes most often)
COPY src/ src/

ENV PYTHONUNBUFFERED=1

CMD ["/app/entrypoint.sh"]