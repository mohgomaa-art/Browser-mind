import re
import time
from typing import Dict, List, Any

# Import from core
from core.executor import ActionExecutor, TaskResult
from core.task_decomposer import TaskDecomposer, Task, ActionType

class PipelineOrchestrator:
    def __init__(self, executor: ActionExecutor, headless: bool = True):
        self.executor = executor
        self.buffer: Dict[str, str] = {}
        self.history: List[Dict] = []
        self.decomposer = TaskDecomposer()

    def _inject_buffer(self, goal_template: str) -> str:
        """Replace {key} in template with self.buffer[key], truncated to 800 chars."""
        # Find all placeholders like {key}
        keys = re.findall(r'\{([^}]+)\}', goal_template)
        injected = goal_template
        for key in keys:
            if key in self.buffer:
                val = str(self.buffer[key])
                if len(val) > 800:
                    val = val[:797] + "..."
                injected = injected.replace(f"{{{key}}}", val)
            else:
                print(f"[warning] Key '{key}' not found in buffer during injection.")
        return injected

    def _extract_text_from_result(self, result: TaskResult) -> str:
        """Extract text from result.extracted_data up to 2000 chars."""
        if not result.extracted_data:
            return ""
            
        parts = []
        for v in result.extracted_data.values():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and "text" in item:
                        parts.append(item["text"])
                    elif isinstance(item, str):
                        parts.append(item)
            elif isinstance(v, str):
                parts.append(v)
                
        joined = "\n".join(parts)
        if len(joined) > 2000:
            joined = joined[:1997] + "..."
        return joined

    async def run_pipeline(self, pipeline_def: dict) -> dict:
        print(f"[Pipeline] Starting '{pipeline_def.get('name', 'Unknown')}'")
        
        for step_idx, step in enumerate(pipeline_def.get("steps", [])):
            raw_goal = step.get("goal", "")
            url = step.get("url", "")
            save_as = step.get("save_as")
            required = step.get("required", True)
            max_retries = step.get("max_retries", 1)
            
            # Default action type logic
            action_type_str = step.get("action_type")
            if not action_type_str:
                action_type_str = "extract" if save_as else "click"
            
            goal = self._inject_buffer(raw_goal)
            
            print(f"\n[Pipeline] Step {step_idx+1}: {goal[:100]}...")
            
            # Decompose to task
            task = self.decomposer.decompose(intent="generic", user_type="bot", query=goal, url=url)
            
            # Override first non-OPEN_URL action
            try:
                override_type = ActionType(action_type_str)
                for action in task.actions:
                    if action.action_type != ActionType.OPEN_URL:
                        action.action_type = override_type
                        break
            except ValueError:
                print(f"[warning] Unknown action type '{action_type_str}' requested, keeping original.")
            
            success = False
            result = None
            
            for attempt in range(max_retries):
                if attempt > 0:
                    print(f"[Pipeline] Retry {attempt}/{max_retries-1} for step {step_idx+1}")
                
                result = await self.executor.execute_task(task)
                success = result.success
                if success:
                    break
            
            # Process result
            extracted_text = ""
            if success and save_as:
                extracted_text = self._extract_text_from_result(result)
                self.buffer[save_as] = extracted_text
                print(f"[Pipeline] Saved {len(extracted_text)} chars to buffer['{save_as}']")
            
            # Log history
            self.history.append({
                "step_index": step_idx + 1,
                "goal": goal,
                "url": url,
                "success": success,
                "saved_as": save_as,
                "extracted_length": len(extracted_text) if success and save_as else 0,
                "error": result.error if result and not success else None
            })
            
            if not success and required:
                print(f"[Pipeline] Required step {step_idx+1} failed. Aborting pipeline.")
                return {"success": False, "buffer": self.buffer, "history": self.history}
                
        print(f"\n[Pipeline] Completed successfully.")
        return {"success": True, "buffer": self.buffer, "history": self.history}
