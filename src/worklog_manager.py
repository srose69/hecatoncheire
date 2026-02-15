"""
WorkLog Manager - file-based state synchronization between Writer and Validator chats.
Creates .worklog/ directory with checkpoint files for coordination.
Uses append-only log architecture for multiple concurrent projects.
"""

import os
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime


class WorkLogManager:
    """Manages .worklog/ directory with append-only state log for multi-chat coordination"""

    def __init__(self, project_root: str = None, session_id: str = None):
        """Initialize worklog manager with isolated session directory"""
        if project_root is None:
            # Default to /app in container (where MCP server runs)
            project_root = os.getcwd()

        self.project_root = project_root

        # Generate unique project ID for this session
        self.project_id = session_id if session_id else str(uuid.uuid4())[:8]

        # Each session gets its own isolated directory: .worklog/{timestamp}_{project_id}/
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dirname = f"{timestamp}_{self.project_id}"
        self.worklog_dir = os.path.join(project_root, ".worklog", session_dirname)

        # Append-only state log file in session directory
        self.state_log_file = os.path.join(self.worklog_dir, "state_log.jsonl")
        self.workflow_log_file = os.path.join(self.worklog_dir, "workflow.log")

        print(f"[WorkLog] Initialized with project_root: {project_root}")
        print(f"[WorkLog] Project ID: {self.project_id}")
        print(f"[WorkLog] Session directory: {self.worklog_dir}")
        print(f"[WorkLog] State log: {self.state_log_file}")

        self._ensure_worklog_dir()
        self._init_state_log()

    def _ensure_worklog_dir(self):
        """Create .worklog directory if it doesn't exist"""
        os.makedirs(self.worklog_dir, exist_ok=True)
        print(f"[WorkLog] Directory created/verified: {self.worklog_dir}")

    def _init_state_log(self):
        """Initialize state log if it doesn't exist"""
        if not os.path.exists(self.state_log_file):
            # Create initial empty state
            initial_state = {
                "project_id": self.project_id,
                "timestamp": datetime.now().isoformat(),
                "event": "init",
                "state": {
                    "writer_id": None,
                    "validator_id": None,
                    "writer_ready": False,
                    "validator_ready": False,
                    "current_task": None,
                    "acceptance_criteria": None,
                    "implementation_plan": None,
                    "plan_approved": False,
                    "checkpoints": [],
                    "current_code": None,
                    "feedback": None,
                    "validator_waiting": False,
                    "awaiting_user_input": False,
                    "user_input_context": None,
                },
            }
            with open(self.state_log_file, "w") as f:
                f.write(json.dumps(initial_state) + "\n")
            print(f"[WorkLog] State log initialized: {self.state_log_file}")

    def save_state(self, state: Dict[str, Any]):
        """Append state update to append-only log"""
        print(f"[WorkLog] save_state called with keys: {list(state.keys())}")
        log_entry = {
            "project_id": self.project_id,
            "timestamp": datetime.now().isoformat(),
            "event": "state_update",
            "state": state,
        }
        with open(self.state_log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        print("[WorkLog] State appended to log")

    def load_state(self) -> Dict[str, Any]:
        """Load current agent state by replaying append-only log"""
        if not os.path.exists(self.state_log_file):
            print("[WorkLog] State log not found, returning default state")
            # Return default empty state
            return {
                "writer_id": None,
                "validator_id": None,
                "writer_ready": False,
                "validator_ready": False,
                "current_task": None,
                "acceptance_criteria": None,
                "implementation_plan": None,
                "plan_approved": False,
                "checkpoints": [],
                "current_code": None,
                "feedback": None,
                "validator_waiting": False,
                "awaiting_user_input": False,
                "user_input_context": None,
            }

        # Replay log to get current state
        current_state = None
        with open(self.state_log_file, "r") as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("project_id") == self.project_id:
                    current_state = entry["state"]

        if current_state is None:
            print(
                f"[WorkLog] No state found for project {self.project_id}, using defaults"
            )
            current_state = {
                "writer_id": None,
                "validator_id": None,
                "writer_ready": False,
                "validator_ready": False,
                "current_task": None,
                "acceptance_criteria": None,
                "implementation_plan": None,
                "plan_approved": False,
                "checkpoints": [],
                "current_code": None,
                "feedback": None,
                "validator_waiting": False,
                "awaiting_user_input": False,
                "user_input_context": None,
            }

        print(
            f"[WorkLog] State loaded for project {self.project_id}, keys: {list(current_state.keys())}"
        )
        return current_state

    def save_checkpoint(self, checkpoint_number: int, data: Dict[str, Any]):
        """Save checkpoint to unique file with project_id and timestamp - NEVER overwrite"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint_file = os.path.join(
            self.worklog_dir,
            f"checkpoint_{self.project_id}_{checkpoint_number}_{timestamp}.json",
        )
        checkpoint_data = {
            "project_id": self.project_id,
            "checkpoint_number": checkpoint_number,
            "timestamp": datetime.now().isoformat(),
            **data,
        }
        print(f"[WorkLog] Creating NEW checkpoint file: {checkpoint_file}")
        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint_data, f, indent=2)
        print("[WorkLog] Checkpoint saved (never overwrite)")

    def load_checkpoint(self, checkpoint_number: int) -> Optional[Dict[str, Any]]:
        """Load checkpoint from work_checkpoint_N file"""
        checkpoint_file = os.path.join(
            self.worklog_dir, f"work_checkpoint_{checkpoint_number}"
        )
        if not os.path.exists(checkpoint_file):
            return None

        with open(checkpoint_file, "r") as f:
            return json.load(f)

    def get_all_checkpoints(self) -> list[Dict[str, Any]]:
        """Get all checkpoints in order"""
        checkpoints = []
        i = 1
        while True:
            checkpoint = self.load_checkpoint(i)
            if checkpoint is None:
                break
            checkpoints.append(checkpoint)
            i += 1
        return checkpoints

    def save_log_entry(self, event: str, data: Dict[str, Any]):
        """Append log entry to workflow.log"""
        log_entry = {
            "project_id": self.project_id,
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "data": data,
        }
        print(f"[WorkLog] Logging event: {event} for project {self.project_id}")
        with open(self.workflow_log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        print(f"[WorkLog] Event logged to {self.workflow_log_file}")

    def clear_session(self):
        """Clear current session state - full reset including agent registration"""
        cleared_state = {
            "writer_id": None,
            "validator_id": None,
            "writer_ready": False,
            "validator_ready": False,
            "current_task": None,
            "acceptance_criteria": None,
            "implementation_plan": None,
            "plan_approved": False,
            "checkpoints": [],
            "current_code": None,
            "feedback": None,
            "validator_waiting": False,
            "awaiting_user_input": False,
            "user_input_context": None,
        }
        self.save_state(cleared_state)
        print("[WorkLog] Session cleared - all agents and state reset")
        return cleared_state
