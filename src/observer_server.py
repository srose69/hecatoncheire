#!/usr/bin/env python3
"""
Observer Server - Standalone llama-cpp-python server for Observer model.
Loads model ONCE at startup, exposes OpenAI-compatible HTTP API.
Reads all config from config.yaml.
"""

import os
import yaml

if __name__ == "__main__":
    # Load config
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    model_config = config.get("model", {})
    MODEL_PATH = model_config.get("path")
    N_CTX = str(model_config.get("n_ctx"))
    N_THREADS = str(model_config.get("n_threads"))
    N_GPU_LAYERS = str(model_config.get("n_gpu_layers"))
    TENSOR_SPLIT = model_config.get("tensor_split", "")
    SPLIT_MODE = str(
        model_config.get(
            "split_mode",
        )
    )

    print("Starting Observer Server...")
    print(f"Model: {MODEL_PATH}")
    print(f"GPU layers: {N_GPU_LAYERS}, Context: {N_CTX}, Threads: {N_THREADS}")
    if TENSOR_SPLIT:
        print(f"Tensor split: {TENSOR_SPLIT}, Mode: {SPLIT_MODE}")

    # Build CLI arguments
    args = [
        "python",
        "-m",
        "llama_cpp.server",
        "--model",
        MODEL_PATH,
        "--n_ctx",
        N_CTX,
        "--n_threads",
        N_THREADS,
        "--n_gpu_layers",
        N_GPU_LAYERS,
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]

    # Add tensor split if configured (split comma-separated into space-separated args)
    if TENSOR_SPLIT:
        args.append("--tensor_split")
        # CLI expects: --tensor_split 7 3 (not "7,3")
        for value in TENSOR_SPLIT.split(","):
            args.append(value.strip())
        args.extend(["--split_mode", SPLIT_MODE])

    # Debug: print full command
    print(f"[DEBUG] Command: {' '.join(args)}")

    # Run llama-cpp-python server using CLI
    os.execvp("python", args)
