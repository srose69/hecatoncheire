"""
Hecatoncheire MCP Server - Continuous agentic development flow.
Observer analyzes, Writer writes, Validator validates, repeat until success.
"""

import asyncio
from typing import Dict, Any, List
from dotenv import load_dotenv

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .observer_agent import ObserverAgent
from .worklog_manager import WorkLogManager

load_dotenv()

# Global worklog manager - file-based state synchronization between chats
worklog = WorkLogManager()


def create_mcp_server() -> Server:
    """Create MCP server with Observer agent and file-based state sync"""
    server = Server("hecatoncheire")

    # Initialize Observer agent (loads config.yaml itself)
    observer = ObserverAgent()

    @server.list_tools()
    async def list_tools() -> List[Tool]:
        return [
            Tool(
                name="fetch_state",
                description="Read current workflow state. ALWAYS call this BEFORE register_agent to check which roles are already taken. Returns complete state including writer_id, validator_id, plan_approved, etc.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="register_agent",
                description="Register as Writer or Validator agent. CRITICAL: Call fetch_state FIRST to check which role is available. First chat registers as writer, second as validator.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "role": {
                            "type": "string",
                            "enum": ["writer", "validator"],
                            "description": "Agent role: 'writer' or 'validator'",
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Unique session identifier for this chat",
                        },
                    },
                    "required": ["role", "session_id"],
                },
            ),
            Tool(
                name="announce_ready",
                description="[STEP 2 - Validator] Validator announces readiness to Writer. Call after registering as Validator.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="acknowledge_task",
                description="[STEP 3 - Writer] Writer acknowledges Validator is ready and task accepted. Call after Validator announces ready.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="start_task",
                description="[STEP 4 - Writer] Request task decomposition from Observer. Returns acceptance criteria.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_prompt": {
                            "type": "string",
                            "description": "Original user request for what to build",
                        },
                    },
                    "required": ["user_prompt"],
                },
            ),
            Tool(
                name="submit_plan",
                description="[STEP 5 - Writer] Submit implementation plan for Validator review.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "plan": {
                            "type": "string",
                            "description": "Implementation plan with steps and approach",
                        },
                    },
                    "required": ["plan"],
                },
            ),
            Tool(
                name="approve_plan",
                description="[STEP 6 - Validator] Approve or reject Writer's implementation plan.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "approved": {
                            "type": "boolean",
                            "description": "True if plan is approved, False if rejected",
                        },
                        "feedback": {
                            "type": "string",
                            "description": "Feedback: approval message or specific issues to address",
                        },
                    },
                    "required": ["approved", "feedback"],
                },
            ),
            Tool(
                name="report_checkpoint",
                description="[STEP 7 - Writer] Report completion of implementation checkpoint.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "checkpoint_number": {
                            "type": "integer",
                            "description": "Current checkpoint number",
                        },
                        "total_checkpoints": {
                            "type": "integer",
                            "description": "Total number of planned checkpoints",
                        },
                        "code": {
                            "type": "string",
                            "description": "Code for this checkpoint",
                        },
                        "description": {
                            "type": "string",
                            "description": "What was implemented in this checkpoint",
                        },
                    },
                    "required": [
                        "checkpoint_number",
                        "total_checkpoints",
                        "code",
                        "description",
                    ],
                },
            ),
            Tool(
                name="request_judgment",
                description="[STEP 7 - Validator] Request objective judgment from Observer when uncertain about alignment.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Code to evaluate",
                        },
                        "question": {
                            "type": "string",
                            "description": "Specific question or concern about alignment",
                        },
                    },
                    "required": ["code", "question"],
                },
            ),
            Tool(
                name="write_code",
                description="Writer agent writes code based on criteria and optional feedback. This triggers Validator to review. **Only Writer (Chat 1) calls this**.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Code implementation",
                        },
                        "description": {
                            "type": "string",
                            "description": "Brief description of what was implemented",
                        },
                    },
                    "required": ["code", "description"],
                },
            ),
            Tool(
                name="review_code",
                description="Validator agent reviews code and provides feedback. Does NOT write code. **Only Validator (Chat 2) calls this**.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "feedback": {
                            "type": "string",
                            "description": "Review feedback: what needs to be fixed or improved",
                        },
                        "approved": {
                            "type": "boolean",
                            "description": "True if code meets criteria, False if needs changes",
                        },
                    },
                    "required": ["feedback", "approved"],
                },
            ),
            Tool(
                name="get_task_status",
                description="Get current task status and what each agent should do next. Any agent can call this.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="force_stop",
                description="User-triggered emergency stop. Returns best current code. **Only user should trigger this**.",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> List[TextContent]:
        """Handle tool calls"""
        print(f"[MCP] Tool called: {name} with arguments: {arguments}")

        # Helper function to check caller role
        def check_caller_role(
            state: Dict, required_role: str, tool_name: str
        ) -> tuple[bool, str]:
            """Returns (is_valid, error_message). If valid, error_message is empty."""
            caller_id = arguments.get("session_id") or arguments.get("caller_id")

            if required_role == "writer":
                if not state.get("writer_id"):
                    return (
                        False,
                        f"❌ ERROR: No Writer registered. Call register_agent with role='writer' first before using {tool_name}.",
                    )
                # Check if caller is the registered writer (if caller_id provided)
                if caller_id and caller_id != state["writer_id"]:
                    return (
                        False,
                        f"❌ ERROR: {tool_name} can only be called by Writer. You are registered as Validator. **Correct action:** Writer should call this tool.",
                    )
            elif required_role == "validator":
                if not state.get("validator_id"):
                    return (
                        False,
                        f"❌ ERROR: No Validator registered. Call register_agent with role='validator' first before using {tool_name}.",
                    )
                # Check if caller is the registered validator (if caller_id provided)
                if caller_id and caller_id != state["validator_id"]:
                    return (
                        False,
                        f"❌ ERROR: {tool_name} can only be called by Validator. You are registered as Writer. **Correct action:** Validator should call this tool.",
                    )

            return True, ""

        if name == "fetch_state":
            print("[MCP] fetch_state called - reading current workflow state")
            state = worklog.load_state()
            print(f"[MCP] State fetched, keys: {list(state.keys())}")

            # Format state for display
            result = f"""📋 Current Workflow State

**Agents:**
- Writer ID: {state.get('writer_id', 'None')}
- Writer Ready: {state.get('writer_ready', False)}
- Validator ID: {state.get('validator_id', 'None')}
- Validator Ready: {state.get('validator_ready', False)}

**Task Status:**
- Task Defined: {'Yes' if state.get('current_task') else 'No'}
- Plan Submitted: {'Yes' if state.get('implementation_plan') else 'No'}
- Plan Approved: {state.get('plan_approved', False)}
- Checkpoints: {len(state.get('checkpoints', []))}

**Next Action:**
- Writer available: {not state.get('writer_id')}
- Validator available: {not state.get('validator_id')}
"""
            return [TextContent(type="text", text=result)]

        elif name == "register_agent":
            role = arguments["role"]
            session_id = arguments["session_id"]

            print(f"[MCP] Registering {role} with session {session_id}")
            state = worklog.load_state()

            # STRICT VALIDATION: Check if role already taken
            if role == "writer":
                if state.get("writer_id"):
                    print(
                        f"[MCP] ERROR: Writer role already taken by {state['writer_id']}"
                    )
                    return [
                        TextContent(
                            type="text",
                            text=f"❌ ERROR: Writer already registered (ID: {state['writer_id']}). Only one Writer allowed.\n\n**You should be Validator.** Call fetch_state to confirm, then register_agent with role='validator'.",
                        )
                    ]
                state["writer_id"] = session_id
                state["writer_ready"] = True
                worklog.save_state(state)
                worklog.save_log_entry(
                    "register_agent", {"role": role, "session_id": session_id}
                )
                print("[MCP] Writer registered successfully")
                return [
                    TextContent(
                        type="text",
                        text=f"✅ Writer registered (session: {session_id}).\n\n**NEXT STEP:** Wait for Validator to join. Do NOT proceed until Validator calls announce_ready.",
                    )
                ]

            elif role == "validator":
                if state.get("validator_id"):
                    print(
                        f"[MCP] ERROR: Validator role already taken by {state['validator_id']}"
                    )
                    return [
                        TextContent(
                            type="text",
                            text=f"❌ ERROR: Validator already registered (ID: {state['validator_id']}). Only one Validator allowed.\n\n**You should be Writer.** Call fetch_state to confirm, then register_agent with role='writer'.",
                        )
                    ]
                if not state.get("writer_id"):
                    print("[MCP] WARNING: Validator registering before Writer")
                    return [
                        TextContent(
                            type="text",
                            text="⚠️ WARNING: No Writer registered yet. Validator should join AFTER Writer.\n\n**Action:** Wait for Writer to register first, then try again.",
                        )
                    ]
                state["validator_id"] = session_id
                state["validator_ready"] = True
                worklog.save_state(state)
                worklog.save_log_entry(
                    "register_agent", {"role": role, "session_id": session_id}
                )
                print("[MCP] Validator registered successfully")
                return [
                    TextContent(
                        type="text",
                        text=f"✅ Validator registered (session: {session_id}).\n\n**NEXT STEP (MANDATORY):** Call announce_ready to notify Writer you are ready.",
                    )
                ]

        elif name == "announce_ready":
            state = worklog.load_state()

            # ROLE CHECK: Only Validator can announce_ready
            is_valid, error_msg = check_caller_role(
                state, "validator", "announce_ready"
            )
            if not is_valid:
                return [TextContent(type="text", text=error_msg)]

            if not state["validator_ready"]:
                return [
                    TextContent(
                        type="text",
                        text="ERROR: Validator not registered. Call register_agent first.",
                    )
                ]

            if not state["writer_ready"]:
                return [
                    TextContent(
                        type="text", text="⏳ Writer not yet registered. Waiting..."
                    )
                ]

            worklog.save_log_entry(
                "announce_ready", {"validator_id": state["validator_id"]}
            )
            return [
                TextContent(
                    type="text",
                    text="✅ Validator ready and active. Writer has been notified. Writer should call acknowledge_task next.",
                )
            ]

        elif name == "acknowledge_task":
            state = worklog.load_state()

            # ROLE CHECK: Only Writer can acknowledge_task
            is_valid, error_msg = check_caller_role(state, "writer", "acknowledge_task")
            if not is_valid:
                return [TextContent(type="text", text=error_msg)]

            if not state["writer_ready"]:
                return [TextContent(type="text", text="ERROR: Writer not registered.")]

            if not state["validator_ready"]:
                return [
                    TextContent(
                        type="text", text="⏳ Validator not ready yet. Please wait..."
                    )
                ]

            worklog.save_log_entry(
                "acknowledge_task", {"writer_id": state["writer_id"]}
            )
            return [
                TextContent(
                    type="text",
                    text="✅ Task accepted. Validator confirmed. Proceeding to planning phase. Call start_task with user's task description.",
                )
            ]

        elif name == "submit_plan":
            plan = arguments["plan"]
            print(f"[MCP] submit_plan called with plan: {plan[:50]}...")
            state = worklog.load_state()

            # ROLE CHECK: Only Writer can submit_plan
            is_valid, error_msg = check_caller_role(state, "writer", "submit_plan")
            if not is_valid:
                return [TextContent(type="text", text=error_msg)]

            # PROTECTION: Prevent plan resubmission after approval
            if state.get("plan_approved"):
                return [
                    TextContent(
                        type="text",
                        text="❌ ERROR: Plan already approved. Cannot resubmit plan after approval. **Correct action:** Proceed with report_checkpoint to implement the approved plan.",
                    )
                ]

            # PROTECTION: Warn about overwriting existing plan
            if (
                state.get("implementation_plan")
                and state.get("plan_approved") is not False
            ):
                return [
                    TextContent(
                        type="text",
                        text="❌ ERROR: Plan already submitted and awaiting review. Cannot overwrite. **Correct action:** Wait for Validator to call approve_plan, or if plan was rejected, you can submit a revised plan.",
                    )
                ]

            state["implementation_plan"] = plan
            state["plan_approved"] = None  # Reset approval status on new submission
            print("[MCP] Saving plan to state...")
            worklog.save_state(state)
            print("[MCP] Logging submit_plan event...")
            worklog.save_log_entry("submit_plan", {"plan": plan})
            print("[MCP] submit_plan completed")

            return [
                TextContent(
                    type="text",
                    text=f"""📋 Implementation Plan Submitted

Plan:
{plan}

---
**Validator**: Review this plan against acceptance criteria. Call approve_plan with your decision.""",
                )
            ]

        elif name == "approve_plan":
            approved = arguments["approved"]
            feedback = arguments["feedback"]

            print(f"[MCP] approve_plan called: approved={approved}")
            state = worklog.load_state()

            # ROLE CHECK: Only Validator can approve_plan
            is_valid, error_msg = check_caller_role(state, "validator", "approve_plan")
            if not is_valid:
                return [TextContent(type="text", text=error_msg)]

            # CHECK: Plan must be submitted first
            if not state.get("implementation_plan"):
                return [
                    TextContent(
                        type="text",
                        text="❌ ERROR: No plan submitted yet. **Correct action:** Wait for Writer to call submit_plan first.",
                    )
                ]

            # PROTECTION: Prevent re-approval/rejection
            if state.get("plan_approved") is not None:
                current_status = (
                    "approved" if state.get("plan_approved") else "rejected"
                )
                return [
                    TextContent(
                        type="text",
                        text=f"❌ ERROR: Plan already {current_status}. Cannot change decision. **Correct action:** If {current_status}, Writer should {'proceed with implementation' if state.get('plan_approved') else 'submit revised plan'}.",
                    )
                ]

            state["plan_approved"] = approved
            state["feedback"] = feedback
            print("[MCP] Saving plan approval to state...")
            worklog.save_state(state)
            print("[MCP] Logging approve_plan event...")
            worklog.save_log_entry(
                "approve_plan", {"approved": approved, "feedback": feedback}
            )
            print("[MCP] approve_plan completed")

            if approved:
                return [
                    TextContent(
                        type="text",
                        text=f"""✅ Plan Approved

{feedback}

---
**Writer**: Plan approved. Begin implementation. Report checkpoints using report_checkpoint.""",
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text",
                        text=f"""❌ Plan Rejected

{feedback}

---
**Writer**: Plan rejected. Revise plan and resubmit with submit_plan.""",
                    )
                ]

        elif name == "report_checkpoint":
            checkpoint_number = arguments["checkpoint_number"]
            total = arguments["total_checkpoints"]
            code = arguments["code"]
            description = arguments["description"]

            # Check if plan was approved before allowing checkpoints
            state = worklog.load_state()

            # ROLE CHECK: Only Writer can report_checkpoint
            is_valid, error_msg = check_caller_role(
                state, "writer", "report_checkpoint"
            )
            if not is_valid:
                return [TextContent(type="text", text=error_msg)]

            if not state.get("plan_approved", False):
                return [
                    TextContent(
                        type="text",
                        text="❌ ERROR: Cannot report checkpoint without approved plan. Validator must call approve_plan first.",
                    )
                ]

            # NUMBER VALIDATION: checkpoint_number must be positive and <= total
            if checkpoint_number < 1:
                return [
                    TextContent(
                        type="text",
                        text=f"❌ ERROR: Invalid checkpoint_number={checkpoint_number}. Must be >= 1. **Correct action:** Use checkpoint_number starting from 1.",
                    )
                ]

            if total < 1:
                return [
                    TextContent(
                        type="text",
                        text=f"❌ ERROR: Invalid total_checkpoints={total}. Must be >= 1. **Correct action:** Set total_checkpoints to a positive number representing planned checkpoints.",
                    )
                ]

            if checkpoint_number > total:
                return [
                    TextContent(
                        type="text",
                        text=f"❌ ERROR: checkpoint_number ({checkpoint_number}) exceeds total_checkpoints ({total}). **Correct action:** Ensure checkpoint_number <= total_checkpoints, or increase total_checkpoints if more checkpoints are needed.",
                    )
                ]

            checkpoint = {
                "number": checkpoint_number,
                "total": total,
                "code": code,
                "description": description,
            }
            print(f"[MCP] report_checkpoint called: {checkpoint_number}/{total}")
            state["checkpoints"].append(checkpoint)
            print("[MCP] Saving checkpoint to state...")
            worklog.save_state(state)
            print("[MCP] Saving checkpoint file...")
            worklog.save_checkpoint(checkpoint_number, checkpoint)
            print("[MCP] Logging checkpoint event...")
            worklog.save_log_entry("report_checkpoint", checkpoint)
            print("[MCP] report_checkpoint completed")

            return [
                TextContent(
                    type="text",
                    text=f"""📍 Checkpoint {checkpoint_number}/{total} Completed

Description: {description}

Code:
```
{code[:500]}{'...' if len(code) > 500 else ''}
```

---
**Validator**: Review this checkpoint. Call review_code with feedback or use request_judgment if uncertain.""",
                )
            ]

        elif name == "request_judgment":
            code = arguments["code"]
            question = arguments["question"]
            state = worklog.load_state()

            # ROLE CHECK: Only Validator can request_judgment
            is_valid, error_msg = check_caller_role(
                state, "validator", "request_judgment"
            )
            if not is_valid:
                return [TextContent(type="text", text=error_msg)]

            if not state["acceptance_criteria"]:
                return [
                    TextContent(
                        type="text",
                        text="ERROR: No acceptance criteria available. Writer must call start_task first.",
                    )
                ]

            # Observer checks alignment
            alignment = observer.check_alignment(code, state["acceptance_criteria"])
            worklog.save_log_entry(
                "request_judgment", {"question": question, "alignment": alignment}
            )

            return [
                TextContent(
                    type="text",
                    text=f"""⚖️ Observer Judgment

Question: {question}

Alignment Status: {'✅ ALIGNED' if alignment['aligned'] else '❌ NOT ALIGNED'}
Reasoning: {alignment.get('reasoning', 'N/A')}

---
**Validator**: Use this objective assessment in your review.""",
                )
            ]

        elif name == "start_task":
            user_prompt = arguments["user_prompt"]
            print(f"[MCP] start_task called with: {user_prompt}")

            state = worklog.load_state()

            # REGISTRATION CHECK: At least Writer should be registered
            if not state.get("writer_id"):
                return [
                    TextContent(
                        type="text",
                        text="❌ ERROR: No Writer registered. **Correct action:** Call register_agent with role='writer' first, then start_task.",
                    )
                ]

            # ROLE CHECK: Only Writer can start_task
            is_valid, error_msg = check_caller_role(state, "writer", "start_task")
            if not is_valid:
                return [TextContent(type="text", text=error_msg)]

            # Observer decomposes prompt
            print("[MCP] Calling observer.decompose_prompt...")
            criteria = observer.decompose_prompt(user_prompt)
            print(f"[MCP] decompose_prompt returned: {criteria}")

            print("[MCP] Loading state from worklog...")
            print("[MCP] State loaded, updating with criteria...")
            state["current_task"] = criteria
            state["acceptance_criteria"] = criteria

            print("[MCP] Saving state...")
            worklog.save_state(state)
            print("[MCP] Logging event...")
            worklog.save_log_entry(
                "start_task", {"user_prompt": user_prompt, "criteria": criteria}
            )
            print("[MCP] start_task completed")

            result = f"""🎯 Task Decomposed by Observer

ACCEPTANCE CRITERIA:
Requirements: {', '.join(criteria.get('requirements', []))}
Forbidden: {', '.join(criteria.get('forbidden', []))}
Minimum Viable: {criteria.get('minimum_viable', '')}
Success Criteria: {criteria.get('success_criteria', '')}

---
**Writer**: Create implementation plan based on these criteria. Use submit_plan when ready.
**Validator**: Wait for Writer's plan submission.
"""

            return [TextContent(type="text", text=result)]

        elif name == "write_code":
            code = arguments["code"]
            description = arguments["description"]
            state = worklog.load_state()

            # ROLE CHECK: Only Writer can write_code
            is_valid, error_msg = check_caller_role(state, "writer", "write_code")
            if not is_valid:
                return [TextContent(type="text", text=error_msg)]

            # PROTECTION: Check if previous code is awaiting review
            if state.get("validator_waiting"):
                return [
                    TextContent(
                        type="text",
                        text="❌ ERROR: Previous code submission awaiting Validator review. Cannot submit new code. **Correct action:** Wait for Validator to call review_code first.",
                    )
                ]

            state["current_code"] = code
            state["validator_waiting"] = True  # Mark that validator should review
            worklog.save_state(state)
            worklog.save_log_entry("write_code", {"description": description})

            # Check alignment with Observer
            if state["current_task"]:
                alignment = observer.check_alignment(code, state["current_task"])
                is_viable = observer.check_viability(code)

                if alignment["aligned"] and is_viable:
                    result = f"""✅ CODE ACCEPTED!

Description: {description}

Observer verdict: ALIGNED and VIABLE
Reason: {alignment['reason']}

Task complete! Code meets original user requirements.

Final code:
```
{code}
```
"""
                    return [TextContent(type="text", text=result)]

            # Not aligned yet - trigger Validator
            result = f"""Code submitted: {description}

**Validator (Chat 2)**: Review this code against acceptance criteria.

Criteria:
{_format_criteria(state.get('current_task', {}))}

Code to review:
```
{code}
```

Use review_code() to provide feedback.
"""

            return [TextContent(type="text", text=result)]

        elif name == "review_code":
            feedback = arguments["feedback"]
            approved = arguments["approved"]
            state = worklog.load_state()

            # ROLE CHECK: Only Validator can review_code
            is_valid, error_msg = check_caller_role(state, "validator", "review_code")
            if not is_valid:
                return [TextContent(type="text", text=error_msg)]

            # CHECK: Code must be submitted first
            if not state.get("current_code"):
                return [
                    TextContent(
                        type="text",
                        text="❌ ERROR: No code to review. **Correct action:** Wait for Writer to call write_code first.",
                    )
                ]

            # PROTECTION: Prevent multiple reviews without new code submission
            if not state.get("validator_waiting"):
                return [
                    TextContent(
                        type="text",
                        text="❌ ERROR: Code already reviewed. Cannot review same code multiple times. **Correct action:** Wait for Writer to submit new code with write_code, or proceed to next workflow step.",
                    )
                ]

            state["validator_waiting"] = False  # Mark review as completed
            worklog.save_log_entry(
                "review_code", {"approved": approved, "feedback": feedback}
            )
            worklog.save_state(state)
            worklog.save_log_entry(
                "review_code", {"approved": approved, "feedback": feedback}
            )

            if approved:
                result = f"""✅ Validator approved!

Feedback: {feedback}

Running final Observer check...
"""
                # Observer final check
                if state["current_code"] and state["current_task"]:
                    alignment = observer.check_alignment(
                        state["current_code"], state["current_task"]
                    )
                    is_viable = observer.check_viability(state["current_code"])

                    if alignment["aligned"] and is_viable:
                        result += """
Observer verdict: ALIGNED and VIABLE

✅ TASK COMPLETE!
"""
                    else:
                        result += f"""
Observer verdict: NOT ALIGNED
Reason: {alignment['reason']}

**Writer (Chat 1)**: Observer found issues. Please revise code.
"""
            else:
                result = f"""Validator feedback: {feedback}

**Writer (Chat 1)**: Address this feedback and submit revised code with write_code().
"""

            return [TextContent(type="text", text=result)]

        elif name == "get_task_status":
            state = worklog.load_state()

            if not state["current_task"]:
                return [
                    TextContent(
                        type="text",
                        text="No active task. Use start_task() to begin.",
                    )
                ]

            status = f"""Current task status:

Criteria: {_format_criteria(state['current_task'])}

Current code: {'Present' if state['current_code'] else 'Not yet submitted'}
Latest feedback: {state.get('feedback', 'None')}

Next action:
"""
            if not state["current_code"]:
                status += "**Writer (Chat 1)**: Submit code with write_code()"
            elif not state["feedback"]:
                status += "**Validator (Chat 2)**: Review code and provide feedback with review_code()"
            else:
                status += "**Writer (Chat 1)**: Address feedback and resubmit code"

            return [TextContent(type="text", text=status)]

        elif name == "force_stop":
            # Emergency stop - return current state and FULL CLEANUP
            state = worklog.load_state()
            current_code = state.get("current_code", "")
            checkpoints = state.get("checkpoints", [])
            best_code = current_code

            if not best_code and checkpoints:
                best_code = checkpoints[-1].get("code", "")

            # FULL SESSION CLEANUP - clear all agents and state
            worklog.save_log_entry(
                "force_stop", {"reason": "User requested", "final_code": best_code}
            )
            worklog.clear_session()

            return [
                TextContent(
                    type="text",
                    text=f""" Emergency Stop - Session Cleared

Best current code:
```
{best_code if best_code else "No code written yet"}
```

Checkpoints completed: {len(checkpoints)}
Plan approved: {state.get('plan_approved', False)}

**Session fully reset:** All agents unregistered, state cleared. Ready for new workflow.
""",
                )
            ]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


def _format_criteria(criteria: Dict[str, Any]) -> str:
    """Format criteria for display"""
    if not criteria:
        return "No criteria"
    return f"""
- Requirements: {', '.join(criteria.get('requirements', []))}
- Forbidden: {', '.join(criteria.get('forbidden', []))}
- Minimum Viable: {criteria.get('minimum_viable', '')}
- Success: {criteria.get('success_criteria', '')}
"""


async def main():
    """Run Hecatoncheire MCP server"""
    print("Initializing Hecatoncheire MCP server...")

    # ObserverAgent loads config.yaml itself
    server = create_mcp_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
