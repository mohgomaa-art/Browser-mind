from enum import Enum
from typing import Optional, Dict, Any

class ResourceClass(str, Enum):
    DOCUMENT = "Document"
    IDENTITY = "Identity"
    SECRET = "Secret"
    VERIFICATION = "Verification"  # OTP, email confirmation — Resource Acquisition Problems
    AUTHORITY = "Authority"        # Captcha, age gate, terms acceptance — Authority Challenges

class ResourceClassifier:
    """
    P7A Resource Classifier.
    Maps a resource identifier key or capability hint to its canonical ResourceClass.
    """
    MAPPING = {
        "resume": ResourceClass.DOCUMENT,
        "transcript": ResourceClass.DOCUMENT,
        "dummy_pdf": ResourceClass.DOCUMENT,
        
        "username": ResourceClass.IDENTITY,
        "email_address": ResourceClass.IDENTITY,
        "linkedin_profile": ResourceClass.IDENTITY,
        "github_profile": ResourceClass.IDENTITY,
        "portfolio_url": ResourceClass.IDENTITY,
        "phone_number": ResourceClass.IDENTITY,
        
        "password": ResourceClass.SECRET,
        "api_key": ResourceClass.SECRET,
        "auth_token": ResourceClass.SECRET,
        
        "captcha_solving": ResourceClass.AUTHORITY,
        "captcha": ResourceClass.AUTHORITY,
        "terms_acceptance": ResourceClass.AUTHORITY,
        "age_gate": ResourceClass.AUTHORITY,
        
        "email_verification": ResourceClass.VERIFICATION,
        "otp_verification": ResourceClass.VERIFICATION,
        "otp": ResourceClass.VERIFICATION,
        "otp_code": ResourceClass.VERIFICATION,
    }

    @classmethod
    def classify(
        cls,
        resource_key: Optional[str] = None,
        resource_binding: Any = None,
        capability_hint: Optional[str] = None,
        workflow_role: Optional[str] = None
    ) -> ResourceClass:
        # Gather classification candidates in order of priority
        candidates = []
        if resource_key:
            candidates.append(str(resource_key))
        if resource_binding:
            if isinstance(resource_binding, dict):
                for v in resource_binding.values():
                    candidates.append(str(v))
            else:
                candidates.append(str(resource_binding))
        if capability_hint:
            candidates.append(str(capability_hint))
        if workflow_role:
            candidates.append(str(workflow_role))
            
        for cand in candidates:
            # Standardize key
            k = cand.lower().strip()
            if not k:
                continue
            if k in cls.MAPPING:
                return cls.MAPPING[k]
            
            # Heuristics based on common naming patterns
            if any(x in k for x in ("pdf", "doc", "file", "transcript", "resume")):
                return ResourceClass.DOCUMENT
            if any(x in k for x in ("profile", "url", "email", "user", "phone", "identity")):
                return ResourceClass.IDENTITY
            if any(x in k for x in ("pass", "secret", "token", "key")):
                return ResourceClass.SECRET
            if any(x in k for x in ("captcha", "terms", "gate", "consent", "authority")):
                return ResourceClass.AUTHORITY
            if any(x in k for x in ("otp", "verification", "code", "passcode")):
                return ResourceClass.VERIFICATION
                
        return ResourceClass.IDENTITY # Default fallback
