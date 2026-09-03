#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Client Abstraction for DBA Copilot
=======================================

Provides an abstract interface for LLM providers and a placeholder
implementation for Claude API integration.

Tier gating (Standard Edition vs Pro Edition)
---------------------------------------------
WatcherDB ships in two commercial editions (see watcherdb-council/docs/FEATURE_MATRIX.md).
LLM-backed Copilot responses are a Pro Edition feature. V3.3 ships the Standard
Edition and MUST NOT invoke an LLM regardless of LLM_ENABLED — clients on the
Std tier did not pay for AI features and Pro clients run V5, not V3.3.

Gating is enforced via the WATCHERDB_EDITION environment variable:
  * WATCHERDB_EDITION=standard (default, safe) — is_llm_enabled() returns False
    and get_llm_client() returns None regardless of LLM_ENABLED/LLM_PROVIDER.
  * WATCHERDB_EDITION=pro — only valid for dev/test environments. Enables the
    Pro code paths. Not for shipped client builds of V3.3.

Rule-based Copilot (pattern matching over cached KPI data) is Standard and
operates unchanged in both editions.

Author: WatcherDB Team
Date: 2026-03-31
Version: 1.1.0 (FIND-20260417-004 Fase 1 — edition guard)
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def get_watcherdb_edition() -> str:
    """
    Return the configured WatcherDB edition — "standard" or "pro".

    Default is "standard" (safe fail-closed behaviour). Any value that is not
    exactly "pro" (case-insensitive) is treated as "standard".
    """
    raw = os.getenv("WATCHERDB_EDITION", "standard").strip().lower()
    return "pro" if raw == "pro" else "standard"


def is_pro_edition() -> bool:
    """True when WATCHERDB_EDITION=pro, False otherwise (incl. unset)."""
    return get_watcherdb_edition() == "pro"


def is_llm_enabled() -> bool:
    """
    Check if LLM integration is enabled.

    Returns True only when BOTH conditions hold:
      1. LLM_ENABLED env var is truthy (true/1/yes)
      2. WATCHERDB_EDITION=pro (tier gate — see module docstring)

    Standard Edition clients get False regardless of LLM_ENABLED. This is the
    commercial tiering guard — clients on Std did not pay for AI features.
    """
    llm_flag = os.getenv("LLM_ENABLED", "false").lower() in ("true", "1", "yes")
    if not llm_flag:
        return False
    if not is_pro_edition():
        logger.info(
            "LLM_ENABLED=true ignored — WATCHERDB_EDITION=%s (LLM requires Pro Edition). "
            "Copilot will operate in rule-based mode.",
            get_watcherdb_edition(),
        )
        return False
    return True


def get_llm_provider() -> str:
    """Return the configured LLM provider name."""
    return os.getenv("LLM_PROVIDER", "none")


class LLMClient(ABC):
    """Abstract interface for LLM provider integrations."""

    @abstractmethod
    async def ask(self, prompt: str, context: Optional[str] = None) -> str:
        """Send a prompt to the LLM and return the response text."""
        ...

    @abstractmethod
    async def ask_with_structured_output(
        self, prompt: str, context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a prompt and expect a structured JSON response."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM provider is reachable and configured."""
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """Return the human-readable provider name."""
        ...


class ClaudeLLMClient(LLMClient):
    """
    Placeholder Claude API client for future LLM integration.

    To enable:
    1. pip install anthropic
    2. Set ANTHROPIC_API_KEY in .env
    3. Set LLM_ENABLED=true in .env
    4. Set LLM_PROVIDER=claude in .env

    Example usage once enabled:
        from anthropic import Anthropic
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system="You are a SQL Server DBA expert...",
            messages=[{"role": "user", "content": prompt}]
        )
    """

    def __init__(self):
        self._api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
        self._available = False

        if self._api_key:
            try:
                import anthropic  # noqa: F401
                self._available = True
                logger.info("Claude LLM client initialized successfully")
            except ImportError:
                logger.warning(
                    "anthropic package not installed. "
                    "Run: pip install anthropic"
                )

    async def ask(self, prompt: str, context: Optional[str] = None) -> str:
        if not self._available:
            raise RuntimeError("Claude LLM client is not available")

        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)

        system_prompt = (
            "You are an expert SQL Server DBA assistant for the WatcherDB monitoring platform. "
            "Provide concise, actionable answers with real T-SQL commands when appropriate. "
            "Focus on SQL Server 2016+ features. Answer in the same language as the question."
        )
        if context:
            system_prompt += f"\n\nCurrent environment context:\n{context}"

        message = client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    async def ask_with_structured_output(
        self, prompt: str, context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Ask and parse JSON from response. Falls back to plain text wrapper."""
        import json

        raw = await self.ask(prompt, context)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"answer": raw, "recommendations": []}

    def is_available(self) -> bool:
        return self._available

    def provider_name(self) -> str:
        return f"Claude ({self._model})"


def get_llm_client() -> Optional[LLMClient]:
    """
    Factory: return the configured LLM client, or None if LLM is disabled.

    Defence in depth — in addition to the is_llm_enabled() check (which already
    gates on WATCHERDB_EDITION), this factory performs an explicit edition
    check so that direct callers cannot bypass the tier guard by constructing
    a provider instance without going through is_llm_enabled().
    """
    if not is_pro_edition():
        logger.debug(
            "get_llm_client() refused — WATCHERDB_EDITION=standard (LLM requires Pro Edition)."
        )
        return None
    if not is_llm_enabled():
        return None

    provider = get_llm_provider()
    if provider == "claude":
        client = ClaudeLLMClient()
        if client.is_available():
            return client
        logger.warning("Claude LLM client not available, falling back to rule-based mode")

    # Add more providers here in the future:
    # elif provider == "openai":
    #     return OpenAILLMClient()

    return None
