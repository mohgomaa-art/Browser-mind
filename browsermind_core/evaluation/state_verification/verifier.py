import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any
from browsermind_core.evaluation.state_verification.schemas import StateRule, StateVerifierConfig, VerificationReport

class StateVerifier:
    def __init__(self, page):
        self.page = page

    async def evaluate_rule(self, rule: StateRule) -> Dict[str, Any]:
        result = {
            "rule": rule.model_dump(),
            "passed": False,
            "error": None,
            "actual_value": None
        }

        try:
            if rule.type == "url_equals":
                actual_url = self.page.url
                result["actual_value"] = actual_url
                result["passed"] = (actual_url == rule.value)

            elif rule.type == "url_contains":
                actual_url = self.page.url
                result["actual_value"] = actual_url
                result["passed"] = (rule.value in actual_url)

            elif rule.type == "element_exists":
                if not rule.selector:
                    raise ValueError("selector is required for element_exists")
                count = await self.page.locator(rule.selector).count()
                result["actual_value"] = count
                result["passed"] = (count > 0)

            elif rule.type == "element_visible":
                if not rule.selector:
                    raise ValueError("selector is required for element_visible")
                locator = self.page.locator(rule.selector).first
                if await locator.count() > 0:
                    is_visible = await locator.is_visible()
                    result["actual_value"] = is_visible
                    result["passed"] = is_visible
                else:
                    result["actual_value"] = False
                    result["passed"] = False

            elif rule.type == "text_present":
                # Check if text is present anywhere in the body
                body_text = await self.page.locator("body").inner_text()
                result["actual_value"] = "Text extracted"
                result["passed"] = (rule.value in body_text)

            elif rule.type == "attribute_equals":
                if not rule.selector or not rule.attribute:
                    raise ValueError("selector and attribute are required for attribute_equals")
                locator = self.page.locator(rule.selector).first
                if await locator.count() > 0:
                    attr_value = await locator.get_attribute(rule.attribute)
                    result["actual_value"] = attr_value
                    result["passed"] = (attr_value == rule.value)
                else:
                    result["actual_value"] = None
                    result["passed"] = False

            elif rule.type == "count_equals":
                if not rule.selector:
                    raise ValueError("selector is required for count_equals")
                count = await self.page.locator(rule.selector).count()
                result["actual_value"] = count
                result["passed"] = (count == rule.value)

            else:
                result["error"] = f"Unknown rule type: {rule.type}"

        except Exception as e:
            result["error"] = str(e)
            result["passed"] = False

        return result

    async def verify(self, config: StateVerifierConfig) -> VerificationReport:
        rule_results = []
        all_passed = True

        for rule in config.success:
            res = await self.evaluate_rule(rule)
            rule_results.append(res)
            if not res["passed"]:
                all_passed = False

        return VerificationReport(
            workflow=config.workflow,
            state_match=all_passed,
            rule_results=rule_results,
            verifier_result=all_passed,
            human_result=None,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
