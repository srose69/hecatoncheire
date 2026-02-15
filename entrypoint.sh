#!/bin/bash
set -e

echo "Starting Observer llama-cpp-python server..."
python -u src/observer_server.py &
OBSERVER_PID=$!

echo "Waiting for Observer server to be ready..."
until python -c "import httpx; httpx.get('http://localhost:8000/v1/models', timeout=1)" 2>/dev/null; do
  sleep 2
done

echo "Observer server ready. Container ready for MCP connections."
echo "To start MCP server, Windsurf will run: docker exec -i hecatoncheire python3 -m src.hecatoncheire"

# Keep container alive by following Observer logs
tail -f /dev/null
