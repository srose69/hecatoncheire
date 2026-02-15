"""Observer Agent - task decomposition and alignment checking"""

import os
import re
import threading
import yaml
import httpx
from typing import Dict, Any


class ObserverAgent:
    """Observer Agent connects to Observer server via HTTP. Loads all config from YAML files."""

    def __init__(self, config_path: str = None):
        """Initialize Observer HTTP client - loads config.yaml and prompts/*.yaml"""
        # Load config
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")

        config = self._load_config(config_path)
        observer_config = config.get("observer", {})

        # Set parameters from config
        self.api_url = observer_config.get("api_url", "http://observer-server:8000")
        self.temperature = observer_config.get("temperature", 0.65)
        self.top_k = observer_config.get("top_k", 40)
        self.top_p = observer_config.get("top_p", 0.9)
        self.min_p = observer_config.get("min_p", 0.05)
        self.repeat_penalty = observer_config.get("repeat_penalty", 1.1)
        self.max_tokens = observer_config.get("max_tokens", 512)

        self.client = httpx.Client(timeout=5.0)
        self.prompts = self._load_prompts()

        # Thread lock to prevent concurrent API calls
        self._api_lock = threading.Lock()

        # Don't print on startup to avoid blocking MCP initialization
        # print(f"Observer client initialized: {self.api_url}")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load config.yaml"""
        if not os.path.exists(config_path):
            print(f"[WARNING] Config not found: {config_path}, using defaults")
            return {}

        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _load_prompts(self) -> Dict[str, Dict[str, str]]:
        """Load all prompts from prompts/*.yaml"""
        prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts")
        prompts = {}

        if not os.path.exists(prompts_dir):
            print(f"[ERROR] Prompts directory not found: {prompts_dir}")
            return prompts

        for filename in os.listdir(prompts_dir):
            if filename.endswith(".yaml"):
                filepath = os.path.join(prompts_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    key = filename.replace(".yaml", "")
                    prompts[key] = data

        return prompts

    def _generate(
        self,
        prompt: str,
        max_tokens: int = None,
        temperature: float = None,
        stop: list = None,
        use_system: bool = True,
    ) -> str:
        """Make chat completion request to Observer server using chat API - THREAD SAFE"""
        with self._api_lock:
            try:
                print(
                    f"[DEBUG] _generate called, use_system={use_system}, LOCK ACQUIRED"
                )
                messages = []

                # Add system prompt if available and requested
                if use_system and "system" in self.prompts:
                    messages.append(
                        {
                            "role": self.prompts["system"]["role"],
                            "content": self.prompts["system"]["content"],
                        }
                    )
                    print("[DEBUG] Added system prompt")

                # Add user prompt
                messages.append({"role": "user", "content": prompt})
                print(f"[DEBUG] Sending request to {self.api_url}/v1/chat/completions")

                payload = {
                    "messages": messages,
                    "max_tokens": max_tokens or self.max_tokens,
                    "temperature": temperature or self.temperature,
                    "top_k": self.top_k,
                    "top_p": self.top_p,
                    "min_p": self.min_p,
                    "repeat_penalty": self.repeat_penalty,
                }
                # Only add stop tokens if explicitly provided
                if stop is not None:
                    payload["stop"] = stop

                response = self.client.post(
                    f"{self.api_url}/v1/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                print(
                    f"[DEBUG] Received response, length: {len(content)} chars, LOCK RELEASED"
                )
                return content
            except Exception as e:
                print(f"[ERROR] Observer API call failed: {e}, LOCK RELEASED")
                import traceback

                traceback.print_exc()
                return ""

    def decompose_prompt(self, user_prompt: str) -> Dict[str, Any]:
        """Decompose user prompt into clear acceptance criteria using decompose.yaml"""
        print(f"[DEBUG] decompose_prompt called with: {user_prompt}")

        if "decompose" not in self.prompts:
            print("[ERROR] decompose.yaml prompt not found")
            return {
                "requirements": [],
                "forbidden": [],
                "minimum_viable": "",
                "success_criteria": "",
            }

        prompt_template = self.prompts["decompose"]["content"]
        prompt = prompt_template.format(user_prompt=user_prompt)
        print(f"[DEBUG] Formatted prompt length: {len(prompt)} chars")

        raw_text = self._generate(prompt, use_system=True)
        print(f"[DEBUG] Observer decompose_prompt raw output:\n{raw_text}\n")

        result = self._parse_decomposition(raw_text)
        print(f"[DEBUG] Parsed result: {result}")
        return result

    def check_alignment(
        self, code: str, original_criteria: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check if code aligns with original user intent using check_alignment.yaml"""
        if "check_alignment" not in self.prompts:
            print("[ERROR] check_alignment.yaml prompt not found")
            return {"aligned": True, "reason": "Prompt not found, assuming aligned"}

        original_request = original_criteria.get("user_request", "")
        prompt_template = self.prompts["check_alignment"]["content"]
        prompt = prompt_template.format(original_request=original_request, code=code)

        raw_text = self._generate(prompt, temperature=0.3, use_system=True)
        print(f"[DEBUG] Observer check_alignment raw output:\n{raw_text}\n")

        aligned = "YES" in raw_text.upper() and "ALIGNED" in raw_text.upper()
        reason_match = re.search(r"REASON:\s*(.+)", raw_text, re.IGNORECASE)
        reason = reason_match.group(1).strip() if reason_match else raw_text

        return {"aligned": aligned, "reason": reason}

    def check_viability(self, code: str) -> bool:
        """
        Check if code is viable (syntactically correct, no placeholders).
        Simple heuristic check for TODO, FIXME, placeholder patterns.
        """
        if not code or not code.strip():
            return False

        # Check for common placeholder patterns
        placeholder_patterns = [
            "TODO",
            "FIXME",
            "...",
            "pass  # TODO",
            "raise NotImplementedError",
            "# placeholder",
            "# stub",
        ]

        code_lower = code.lower()
        for pattern in placeholder_patterns:
            if pattern.lower() in code_lower:
                print(f"[DEBUG] check_viability: Found placeholder pattern '{pattern}'")
                return False

        # Code looks viable
        return True

    def _parse_decomposition(self, text: str) -> Dict[str, Any]:
        """Parse LLM output into structured criteria - fallback to raw text if parsing fails"""
        lines = text.strip().split("\n")
        criteria = {
            "requirements": [],
            "forbidden": [],
            "minimum_viable": "",
            "success_criteria": "",
        }

        current_section = None
        for line in lines:
            line = line.strip()
            if "REQUIREMENTS" in line.upper():
                current_section = "requirements"
            elif "FORBIDDEN" in line.upper():
                current_section = "forbidden"
            elif "MINIMUM_VIABLE" in line.upper() or "MINIMUM VIABLE" in line.upper():
                current_section = "minimum_viable"
            elif (
                "SUCCESS_CRITERIA" in line.upper() or "SUCCESS CRITERIA" in line.upper()
            ):
                current_section = "success_criteria"
            elif line and current_section:
                if current_section in ["requirements", "forbidden"]:
                    criteria[current_section].append(line.lstrip("- "))
                else:
                    criteria[current_section] += line + " "

        # Fallback: if no sections found, return raw text
        if not any(criteria[k] for k in criteria):
            print(
                "[DEBUG] Parser failed to find sections, using raw output as fallback"
            )
            return {
                "requirements": [text.strip()],
                "forbidden": [],
                "minimum_viable": "",
                "success_criteria": "",
            }

        return criteria

    def _parse_alignment(self, text: str) -> Dict[str, Any]:
        """Parse alignment check output"""
        aligned = "ALIGNED" in text and "NOT_ALIGNED" not in text
        return {
            "aligned": aligned,
            "reason": text.strip(),
            "missing": [],
            "extra": [],
        }

    def _format_criteria(self, criteria: Dict[str, Any]) -> str:
        """Format criteria for prompt"""
        return f"""
Requirements: {', '.join(criteria.get('requirements', []))}
Forbidden: {', '.join(criteria.get('forbidden', []))}
Minimum Viable: {criteria.get('minimum_viable', '')}
Success Criteria: {criteria.get('success_criteria', '')}
"""
