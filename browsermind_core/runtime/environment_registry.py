"""
Environment Registry — single source of truth for all known environments.

Add new environments here. The registry is used by:
  - prompt_parse, open_browser (Runtime layer)
  - sites.py (Experiments layer — derived, not stored independently)
  - harness.py, wr_g_evaluator, p3_replay_experiment (via both layers)

WR-X.5 Unification: EnvironmentEntry is the canonical environment definition.
BenchmarkMeta is an optional overlay for environments that participate in
benchmark / experiment runs. sites.py derives EXPERIMENT_SITES from this registry.

# TODO (post-P4): Extract BenchmarkMeta to a separate BenchmarkRegistry.
#
# Current design mixes Runtime concerns (start_url, family, aliases) with
# Experiment concerns (suggested_workflow, operator_hint, phase) inside a
# single EnvironmentEntry. This is acceptable now (WR-X.5) but will become
# a problem once the environment set grows beyond benchmark sites.
#
# Target architecture:
#   EnvironmentRegistry  -> EnvironmentEntry (runtime only)
#   BenchmarkRegistry    -> BenchmarkMeta    (experiment overlay, keyed by env key)
#   sites.py             -> adapter joining both registries
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class BenchmarkMeta:
    """
    Experiment/benchmark metadata for an environment.
    Present only on environments that are used in benchmark runs.
    None = this environment is known but not part of the benchmark suite.

    TODO (post-P4): Move this to a standalone BenchmarkRegistry so that
    EnvironmentEntry contains only runtime-layer concerns.
    """
    label: str              # human-readable display name
    suggested_workflow: str # default template name for this environment
    operator_hint: str      # instruction shown to operator during recording
    phase: str = "validation"   # baseline | validation | hard | wrx
    is_gate: bool = False   # whether this site is a resolution-rate gate site


@dataclass
class EnvironmentEntry:
    key: str                        # canonical key, e.g. "huggingface"
    start_url: str                  # where to navigate on open
    aliases: list[str] = field(default_factory=list)  # natural language aliases
    family: str = "generic"         # capability family hint
    login_url: Optional[str] = None # direct login page if known
    description: str = ""
    benchmark: Optional[BenchmarkMeta] = None  # None = not a benchmark site


# -- Registry ------------------------------------------------------------------

_REGISTRY: list[EnvironmentEntry] = [
    EnvironmentEntry(
        key="huggingface",
        start_url="https://huggingface.co/",
        aliases=["hf", "hugging face", "hugging-face"],
        family="ml_platform",
        login_url="https://huggingface.co/login",
        description="HuggingFace -- model hub, datasets, spaces",
        benchmark=BenchmarkMeta(
            label="HuggingFace",
            suggested_workflow="exp_huggingface_nav",
            operator_hint="Repeat the validated logout/login or model search flow.",
            phase="hard",
        ),
    ),
    EnvironmentEntry(
        key="linkedin",
        start_url="https://www.linkedin.com/",
        aliases=["linked in", "linked-in"],
        family="professional_network",
        login_url="https://www.linkedin.com/login",
        description="LinkedIn -- professional network, jobs",
    ),
    EnvironmentEntry(
        key="github",
        start_url="https://github.com/",
        aliases=["gh"],
        family="dev_platform",
        login_url="https://github.com/login",
        description="GitHub -- code hosting",
        benchmark=BenchmarkMeta(
            label="GitHub",
            suggested_workflow="exp_github_nav",
            operator_hint="Navigate a logged-in flow: open a repo, star/unstar, or open Issues.",
            phase="hard",
        ),
    ),
    EnvironmentEntry(
        key="google",
        start_url="https://www.google.com/",
        aliases=["gmail", "google search"],
        family="search",
        description="Google search and services",
    ),
    EnvironmentEntry(
        key="twitter",
        start_url="https://twitter.com/",
        aliases=["x", "x.com", "twitter.com"],
        family="social",
        login_url="https://twitter.com/i/flow/login",
        description="Twitter / X -- social platform",
    ),
    EnvironmentEntry(
        key="facebook",
        start_url="https://www.facebook.com/",
        aliases=["fb"],
        family="social",
        login_url="https://www.facebook.com/",
        description="Facebook -- social platform",
    ),
    EnvironmentEntry(
        key="saucedemo",
        start_url="https://www.saucedemo.com/",
        aliases=["sauce", "saucelabs demo"],
        family="ecommerce_test",
        description="SauceDemo -- e-commerce test site",
        benchmark=BenchmarkMeta(
            label="SauceDemo",
            suggested_workflow="exp_saucedemo_checkout",
            operator_hint="Log in (standard_user / secret_sauce), add item to cart, open cart, checkout.",
            phase="validation",
            is_gate=True,
        ),
    ),
    EnvironmentEntry(
        key="static_baseline",
        start_url="https://en.wikipedia.org/wiki/Main_Page",
        aliases=["wikipedia", "wiki", "static baseline"],
        family="static_baseline",
        description="Wikipedia -- known-good baseline for replay validation",
        benchmark=BenchmarkMeta(
            label="STATIC_BASELINE (Wikipedia)",
            suggested_workflow="exp_static_wikipedia_search",
            operator_hint="Search for a term (e.g. 'BrowserMind'), submit, open the first result link.",
            phase="baseline",
            is_gate=True,
        ),
    ),
    EnvironmentEntry(
        key="demoqa",
        start_url="https://demoqa.com/text-box",
        aliases=["demo qa", "demo-qa"],
        family="forms_test",
        description="DemoQA -- forms, widgets, and practice site",
        benchmark=BenchmarkMeta(
            label="DemoQA",
            suggested_workflow="exp_demoqa_form",
            operator_hint="Open Elements > Text Box (or Web Tables), fill and submit a simple form.",
        ),
    ),
    EnvironmentEntry(
        key="aria_internet",
        start_url="https://the-internet.herokuapp.com/",
        aliases=["the internet", "aria", "herokuapp"],
        family="aria_test",
        login_url="https://the-internet.herokuapp.com/login",
        description="The Internet -- simple ARIA-friendly test pages",
        benchmark=BenchmarkMeta(
            label="Simple ARIA (The Internet)",
            suggested_workflow="exp_aria_login",
            operator_hint="Use the login form at /login (tomsmith / SuperSecretPassword!).",
        ),
    ),
    EnvironmentEntry(
        key="reddit",
        start_url="https://www.reddit.com/",
        aliases=[],
        family="social",
        description="Reddit -- forums and communities",
    ),
    EnvironmentEntry(
        key="amazon",
        start_url="https://www.amazon.com/",
        aliases=["amazon.com"],
        family="ecommerce",
        login_url="https://www.amazon.com/ap/signin",
        description="Amazon -- e-commerce",
    ),
    EnvironmentEntry(
        key="controlled_drift",
        start_url="http://127.0.0.1:8080/",
        aliases=["drift"],
        family="experimental",
        description="Controlled Drift Harness",
        benchmark=BenchmarkMeta(
            label="Controlled Drift Harness",
            suggested_workflow="exp_controlled_drift",
            operator_hint="Local mock server.",
        ),
    ),
    # -- WR-X Validation Matrix environments -----------------------------------
    EnvironmentEntry(
        key="duckduckgo",
        start_url="https://duckduckgo.com/",
        aliases=["ddg", "duck duck go"],
        family="search",
        description="DuckDuckGo -- privacy search engine",
        benchmark=BenchmarkMeta(
            label="DuckDuckGo",
            suggested_workflow="exp_ddg_search_baseline",
            operator_hint="Search for a term on DuckDuckGo.",
            phase="wrx",
        ),
    ),
    EnvironmentEntry(
        key="brave_search",
        start_url="https://search.brave.com/",
        aliases=["brave", "brave search"],
        family="search",
        description="Brave Search -- privacy-focused search",
        benchmark=BenchmarkMeta(
            label="Brave Search",
            suggested_workflow="exp_ddg_search_baseline",
            operator_hint="Search for a term on Brave Search.",
            phase="wrx",
        ),
    ),
    EnvironmentEntry(
        key="python_org",
        start_url="https://www.python.org/",
        aliases=["python.org", "python docs"],
        family="documentation",
        description="Python.org -- official Python documentation and downloads",
        benchmark=BenchmarkMeta(
            label="Python.org",
            suggested_workflow="exp_python_search_baseline",
            operator_hint="Search for a term on Python.org.",
            phase="wrx",
        ),
    ),
    EnvironmentEntry(
        key="mdn",
        start_url="https://developer.mozilla.org/",
        aliases=["mdn docs", "mozilla developer", "mdn web docs"],
        family="documentation",
        description="MDN Web Docs -- web standards reference",
        benchmark=BenchmarkMeta(
            label="MDN Web Docs",
            suggested_workflow="exp_mdn_search_baseline",
            operator_hint="Search for a term on MDN Web Docs.",
            phase="wrx",
        ),
    ),
    EnvironmentEntry(
        key="pypi",
        start_url="https://pypi.org/",
        aliases=["pypi.org", "python package index"],
        family="package_registry",
        description="PyPI -- Python Package Index",
        benchmark=BenchmarkMeta(
            label="PyPI",
            suggested_workflow="exp_pypi_search_baseline",
            operator_hint="Search for a package on PyPI.",
            phase="wrx",
        ),
    ),
    EnvironmentEntry(
        key="greenhouse",
        start_url="https://www.asm.com/open-vacancies/senior-engineer-global-product-support-4763867101?gh_jid=4763867101",
        aliases=["green house", "greenhouse.io"],
        family="greenhouse",
        description="Greenhouse Job Application Platform",
        benchmark=BenchmarkMeta(
            label="Greenhouse",
            suggested_workflow="asm_apply_greenhouse_v2",
            operator_hint="Apply to a job vacancy on Greenhouse.",
            phase="validation",
        ),
    ),
    EnvironmentEntry(
        key="lever",
        start_url="https://jobs.lever.co/",
        aliases=["lever.co", "lever jobs"],
        family="lever",
        description="Lever Job Application Platform",
    ),
    EnvironmentEntry(
        key="workday",
        start_url="https://myworkdayjobs.com/",
        aliases=["workday jobs", "myworkdayjobs"],
        family="workday",
        description="Workday Job Application Platform",
    ),
]

# -- Lookup --------------------------------------------------------------------

_INDEX: dict[str, EnvironmentEntry] = {}

def _build_index():
    for e in _REGISTRY:
        _INDEX[e.key] = e
        for alias in e.aliases:
            _INDEX[alias.lower()] = e

_build_index()


def resolve(text: str) -> Optional[EnvironmentEntry]:
    """
    Resolve natural-language text to an EnvironmentEntry.
    Returns None if no match found (never falls back silently).
    """
    lower = text.lower().strip()

    # Exact key or alias match
    if lower in _INDEX:
        return _INDEX[lower]

    # Substring match against keys and aliases — min 3 chars to prevent
    # single-letter aliases ("x") from matching unrelated keys ("xing", "matrix")
    for key, entry in _INDEX.items():
        if len(key) >= 3 and key in lower:
            return entry

    return None


def get_all() -> list[EnvironmentEntry]:
    return list(_REGISTRY)


def get_benchmark_sites() -> list[EnvironmentEntry]:
    """Return all environments that have BenchmarkMeta (participate in experiments)."""
    return [e for e in _REGISTRY if e.benchmark is not None]


def get_gate_sites() -> list[str]:
    """Return keys of sites that are resolution-rate gate sites."""
    return [e.key for e in _REGISTRY if e.benchmark and e.benchmark.is_gate]


def register(entry: EnvironmentEntry):
    """Register a new environment at runtime."""
    _REGISTRY.append(entry)
    _INDEX[entry.key] = entry
    for alias in entry.aliases:
        _INDEX[alias.lower()] = entry


def profile_dir(entry: EnvironmentEntry, store_dir: Path, persona_name: str) -> Path:
    """
    Return an isolated profile directory for a (Persona, Environment) pair.
    Guarantees Persona isolation at filesystem level.
    """
    safe_persona = persona_name.lower().replace(" ", "_")
    return store_dir / "profiles" / safe_persona / entry.key
