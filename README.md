# Hecatoncheire MCP

Multi-agent continuous development system with local LLM orchestration.

**[English](#english)** | **[Русский](#русский)**

---

<a id="english"></a>

## English

### Overview

Hecatoncheire is an MCP (Model Context Protocol) server implementing a continuous multi-agent workflow where specialized AI agents collaborate on code development tasks. The system uses role separation and intelligent feedback loops to prevent common issues like scope creep and unnecessary complexity.

### Problem Statement

Single-agent development suffers from inherent limitations:
- Cognitive bias when the same agent both writes and reviews code
- Tendency toward "improvement for improvement's sake"
- Lack of objective alignment checking

### Solution

Multi-agent architecture with strict role separation:

**Writer Agent**: Implements code based on acceptance criteria  
**Validator Agent**: Reviews code and provides targeted feedback  
**Observer Agent**: Local LLM that decomposes tasks and checks alignment

### Architecture

```
User Request
    ↓
Observer (Local LLM)
    └─ Decomposes into acceptance criteria
    └─ Defines success conditions
    ↓
Writer
    └─ Implements code
    └─ Submits for review
    ↓
Validator
    └─ Reviews against criteria
    └─ Approves OR provides feedback
    ↓
[Loop until approved or max iterations]
```

### Core Components

#### Observer Agent
- Local LLM server (llama-cpp-python)
- Runs in background, loads model once
- Exposes OpenAI-compatible HTTP API
- Functions:
  - Task decomposition into structured criteria
  - Alignment verification (prevents scope creep)
  - Objective evaluation of code against original intent

#### Writer Agent (Chat 1)
- Receives structured acceptance criteria
- Implements code solution
- Submits via `write_code()` tool
- Iterates based on validator feedback

#### Validator Agent (Chat 2)
- Reviews submitted code
- Checks alignment with acceptance criteria
- Provides specific, actionable feedback
- Approves only when criteria are met

### Workflow

#### 1. Task Initialization

```bash
start_task("Create recursive factorial function in Python")
```

Observer decomposes into:
- REQUIREMENTS: Function signature, base cases, recursive call
- FORBIDDEN: Iterative approaches, external libraries
- MINIMUM_VIABLE: Basic working implementation
- SUCCESS_CRITERIA: Correct results for n=0,1,5

#### 2. Implementation Phase

Writer implements based on criteria and submits:

```python
write_code(
    code="def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n-1)",
    description="Recursive factorial with base case"
)
```

#### 3. Validation Phase

Validator reviews and either:
- Approves (task complete)
- Provides feedback (Writer iterates)

```python
review_code(
    feedback="Missing docstring and type hints",
    approved=False
)
```

#### 4. Iteration

Writer addresses feedback and resubmits. Loop continues until approval or max iterations reached.

### Configuration

All configuration centralized in `config.yaml`:

#### Model Configuration
```yaml
model:
  path: "/models/model.gguf"
  n_ctx: 4096
  n_threads: 8
  n_gpu_layers: -1
  tensor_split: "2,8"  # Multi-GPU split
  split_mode: 1
```

#### Observer Configuration
```yaml
observer:
  api_url: "http://localhost:8000"
  temperature: 0.65
  top_k: 40
  top_p: 0.9
  min_p: 0.05
  repeat_penalty: 1.1
  max_tokens: 512
```

#### Prompts

All prompts stored as YAML files in `prompts/`:

- `system.yaml`: Observer role definition
- `decompose.yaml`: Task decomposition template
- `check_alignment.yaml`: Alignment verification template

### Installation

#### Requirements
- Docker with NVIDIA GPU support
- CUDA-compatible GPU with 8GB+ VRAM
- NVIDIA Container Toolkit

#### Setup

1. Clone repository:
```bash
git clone https://github.com/srose69/hecatoncheire.git
cd hecatoncheire
```

2. Configure model path in `config.yaml`:
```yaml
model:
  path: "/models/your-model.gguf"
```

3. Update model mount in `docker-compose.yml`:
```yaml
volumes:
  - /path/to/your/model.gguf:/models/your-model.gguf:ro
  - ./config.yaml:/app/config.yaml:ro
```

4. Build and run:
```bash
docker compose build
docker compose up -d
```

5. Configure MCP client (see `mcp_config_example.json`):
```json
{
  "mcpServers": {
    "hecatoncheire": {
      "command": "docker",
      "args": ["exec", "-i", "hecatoncheire", "python", "src/hecatoncheire.py"]
    }
  }
}
```

### Container Architecture

Single unified container running two services:

1. **Observer Server** (llama-cpp-python on port 8000)
2. **MCP Server** (connects to localhost:8000)

Sequential startup managed by `entrypoint.sh`:
- Starts Observer server in background
- Waits for health check
- Container stays alive, MCP client connects via `docker exec`

### Testing

#### Verify Observer API

```bash
curl http://localhost:8000/v1/models

curl -X POST http://localhost:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Test prompt", "max_tokens": 50}'
```

#### Monitor Resources

```bash
docker logs hecatoncheire
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv -l 1
```

### Debugging

**Observer not responding:**
```bash
docker logs hecatoncheire | grep "Observer Server"
docker port hecatoncheire 8000
```

**Out of memory:**
- Reduce `n_ctx` in config.yaml
- Adjust `tensor_split` for multi-GPU setups
- Lower `n_gpu_layers` to offload less to GPU

**MCP connection issues:**
- Verify container is running: `docker ps`
- Check MCP client config path
- Review container logs for startup errors

### Design Principles

- **Role Separation** — each agent has single, well-defined responsibility
- **Continuous Flow** — seamless handoffs without stop-restart cycles
- **Alignment Checking** — constant verification against original intent
- **Local Processing** — no external API dependencies
- **Configuration as Code** — all settings in version-controlled YAML

### Limitations

- Maximum iterations configurable (default: 3)
- Requires GPU with adequate VRAM for model
- State does not persist across container restarts
- Observer quality depends on local model capabilities

---

<a id="русский"></a>

## Русский

### Обзор

Hecatoncheire — MCP-сервер (Model Context Protocol), реализующий непрерывный мультиагентный рабочий процесс разработки. Специализированные AI-агенты совместно работают над задачами, используя разделение ролей и обратную связь для предотвращения расползания скоупа и избыточной сложности.

### Проблема

Одноагентная разработка страдает от врождённых ограничений:
- Когнитивное искажение: один и тот же агент пишет и ревьюит код
- Склонность к «улучшениям ради улучшений»
- Отсутствие объективной проверки соответствия задаче

### Решение

Мультиагентная архитектура со строгим разделением ролей:

**Writer** — реализует код по критериям приёмки  
**Validator** — ревьюит код и даёт обратную связь  
**Observer** — локальная LLM, декомпозирует задачи и проверяет соответствие

### Архитектура

```
Запрос пользователя
    ↓
Observer (локальная LLM)
    └─ Декомпозиция в критерии приёмки
    └─ Определение условий успеха
    ↓
Writer
    └─ Реализация кода
    └─ Отправка на ревью
    ↓
Validator
    └─ Ревью по критериям
    └─ Одобрение ИЛИ обратная связь
    ↓
[Цикл до одобрения или лимита итераций]
```

### Компоненты

#### Observer
- Локальный LLM-сервер (llama-cpp-python)
- Работает в фоне, модель загружается один раз
- OpenAI-совместимый HTTP API
- Декомпозиция задач, проверка alignment, объективная оценка кода

#### Writer (Чат 1)
- Получает структурированные критерии приёмки
- Реализует решение
- Отправляет через `write_code()`
- Итерирует по фидбеку Validator

#### Validator (Чат 2)
- Ревьюит код
- Проверяет соответствие критериям
- Даёт конкретный, actionable фидбек
- Одобряет только при выполнении всех критериев

### Установка

#### Требования
- Docker с поддержкой NVIDIA GPU
- CUDA-совместимая GPU с 8GB+ VRAM
- NVIDIA Container Toolkit

#### Настройка

1. Клонировать репозиторий:
```bash
git clone https://github.com/srose69/hecatoncheire.git
cd hecatoncheire
```

2. Указать путь к модели в `config.yaml`:
```yaml
model:
  path: "/models/your-model.gguf"
```

3. Обновить маунт модели в `docker-compose.yml`:
```yaml
volumes:
  - /path/to/your/model.gguf:/models/your-model.gguf:ro
  - ./config.yaml:/app/config.yaml:ro
```

4. Собрать и запустить:
```bash
docker compose build
docker compose up -d
```

5. Настроить MCP-клиент (см. `mcp_config_example.json`):
```json
{
  "mcpServers": {
    "hecatoncheire": {
      "command": "docker",
      "args": ["exec", "-i", "hecatoncheire", "python", "src/hecatoncheire.py"]
    }
  }
}
```

### Отладка

**Observer не отвечает:**
```bash
docker logs hecatoncheire | grep "Observer Server"
docker port hecatoncheire 8000
```

**Нехватка памяти:**
- Уменьшить `n_ctx` в config.yaml
- Настроить `tensor_split` для мульти-GPU
- Снизить `n_gpu_layers`

**Проблемы с MCP:**
- Проверить контейнер: `docker ps`
- Проверить конфиг MCP-клиента
- Логи контейнера: `docker logs hecatoncheire`

### Принципы

- **Разделение ролей** — каждый агент отвечает за одну задачу
- **Непрерывный поток** — бесшовные переходы между агентами
- **Проверка alignment** — постоянная верификация соответствия исходному запросу
- **Локальная обработка** — никаких внешних API
- **Конфигурация как код** — все настройки в версионируемых YAML

### Ограничения

- Максимум итераций настраивается (по умолчанию: 3)
- Требуется GPU с достаточным VRAM
- Состояние не сохраняется между перезапусками контейнера
- Качество Observer зависит от возможностей локальной модели

---

## License

This project is licensed under the **PolyForm Shield License 1.0.0**. See [LICENSE](LICENSE) for details.

Commercial use, competition, and redistribution for commercial purposes are **not permitted**.