"""
Phase B2: Dataset Compiler - Task Template Library
Maps deterministic targets directly to rigid natural language templates.
"""
from typing import Dict, Any

class TaskTemplateLibrary:
    def __init__(self):
        # Strict mapping: role -> template
        self.interaction_templates = {
            'button': "Click the '{name}' button",
            'link': "Navigate to '{name}'",
            'textbox': "Enter text into the '{name}' field",
            'checkbox': "Toggle the '{name}' checkbox",
            'searchbox': "Search using the '{name}' box",
            'combobox': "Select an option from the '{name}' dropdown",
            'menuitem': "Select the '{name}' menu item"
        }
        
        self.extraction_templates = {
            'article': "Extract the content of the '{name}' article",
            'list': "Extract all items from the '{name}' list",
            'table': "Extract the rows from the '{name}' table",
            'heading': "Extract the '{name}' heading text",
            'main': "Extract the main content of the page"
        }

    def generate_interaction_goal(self, target: Dict[str, Any]) -> str:
        """Generates an interaction goal strictly from a template."""
        role = target.get('role', '')
        name = target.get('name', 'element')
        
        template = self.interaction_templates.get(role)
        if template:
            return template.format(name=name)
        
        # Fallback strict template
        return f"Interact with the '{name}' {role}"

    def generate_extraction_goal(self, target: Dict[str, Any]) -> str:
        """Generates an extraction goal strictly from a template."""
        role = target.get('role', '')
        name = target.get('name', 'content')
        
        template = self.extraction_templates.get(role)
        if template:
            return template.format(name=name)
            
        # Fallback strict template
        return f"Extract information from the '{name}' {role}"
