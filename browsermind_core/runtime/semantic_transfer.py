import copy
from typing import Optional
from browsermind_core.ontology.p1_schemas import WorkflowTemplate

class SemanticTransferLayer:
    """
    WR-X Cross-Site Semantic Transfer Layer.
    Translates a WorkflowTemplate recorded on a source environment
    to execute successfully on a target environment using abstract intents.
    """
    
    @staticmethod
    def transfer(
        template: WorkflowTemplate,
        target_start_url: str,
        source_start_url: Optional[str] = None,
        strict_intent_forcing: bool = True
    ) -> WorkflowTemplate:
        """
        Creates a transferred copy of the given template.
        """
        transferred = copy.deepcopy(template)
        transferred.name = f"{template.name}_transferred"
        
        # Determine source url from the first navigate step if not provided
        if not source_start_url:
            for step in transferred.steps:
                if step.get("action_type") == "navigate":
                    source_start_url = step.get("url")
                    break
        
        for step in transferred.steps:
            # 1. URL Mapping
            if step.get("action_type") == "navigate":
                url = step.get("url")
                if url and source_start_url and url.startswith(source_start_url):
                    step["url"] = url.replace(source_start_url, target_start_url, 1)
                elif url and not source_start_url:
                    step["url"] = target_start_url
                    
            # 2. Strict Transfer Mode (Identity Stripping)
            # Remove environment-specific identity signals to test if Intent alone survives.
            if strict_intent_forcing:
                step["target_selector"] = ""
                
                if "descriptor" in step:
                    desc = step["descriptor"]
                    identity_keys = [
                        "target_selector", "dom_path", "css_selector", 
                        "xpath", "data_testid", "id", "placeholder"
                    ]
                    for key in identity_keys:
                        desc.pop(key, None)
                        
        return transferred
