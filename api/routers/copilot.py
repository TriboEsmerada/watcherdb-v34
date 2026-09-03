#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Router — DBA Copilot
============================

Endpoints for the DBA Copilot feature.
Provides AI-assisted (or rule-based) DBA knowledge, insights, and reports.

Endpoints:
    GET  /copilot/status        — Copilot status and mode info
    GET  /copilot/quick-answers — Pre-defined Q&A pairs for quick buttons
    GET  /copilot/insights      — Proactive insights (data-driven or rule-based)
    POST /copilot/ask           — Ask a DBA question
    POST /copilot/report        — Generate a summary report

Author: WatcherDB Team
Date: 2026-03-31
Version: 1.0.0
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import logging
import time

from api.models import CopilotStatusResponse, CopilotAnswerResponse, QuickAnswersResponse, CopilotInsightResponse, CopilotReportResponse
from api.versioning import COPILOT_PREFIX
from api.error_helpers import safe_http_error

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=COPILOT_PREFIX,
    tags=["DBA Copilot"],
    responses={500: {"description": "Internal Server Error"}},
)

# ========================================
# Service initialization (lazy singleton)
# ========================================
_copilot_service = None


def _get_service():
    """Lazy-init the CopilotService singleton."""
    global _copilot_service
    if _copilot_service is None:
        from services.copilot_service import CopilotService
        _copilot_service = CopilotService()
    return _copilot_service


def _get_kpi_cache_data():
    """
    Try to read cached KPI data from the intelligence_kpis dashboard cache.
    Returns None if cache is not available or expired.
    """
    try:
        from api.routers.intelligence_kpis import _get_cached_dashboard
        cached = _get_cached_dashboard()
        if cached:
            return cached
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Could not read KPI cache: {e}")
    return None


# ========================================
# Pydantic Models
# ========================================
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Pergunta do utilizador")
    include_recommendations: bool = Field(True, description="Incluir recomendacoes na resposta")
    language: Optional[str] = Field("pt-BR", description="Idioma da resposta")


class ReportRequest(BaseModel):
    report_type: str = Field(..., description="Tipo: daily_summary ou health_check")
    period_hours: int = Field(24, ge=1, le=168, description="Periodo em horas")
    format: Optional[str] = Field("markdown", description="Formato de saida")


# ========================================
# Endpoints
# ========================================

@router.get("/status", response_model=CopilotStatusResponse)
@router.post("/status", response_model=CopilotStatusResponse)
async def copilot_status():
    """
    Return copilot operational status.
    Reports whether LLM is available or operating in rule-based mode.
    """
    try:
        service = _get_service()
        return JSONResponse(content=service.get_status())
    except Exception as e:
        logger.error(f"Error getting copilot status: {e}", exc_info=True)
        raise safe_http_error(500, e, "copilot operation")


@router.get("/quick-answers", response_model=QuickAnswersResponse)
async def copilot_quick_answers():
    """
    Return pre-defined Q&A pairs for quick action buttons.
    These are the most common DBA questions with ready-made answers.
    """
    try:
        service = _get_service()
        return JSONResponse(content=service.get_quick_answers())
    except Exception as e:
        logger.error(f"Error getting quick answers: {e}", exc_info=True)
        raise safe_http_error(500, e, "copilot operation")


@router.get("/insights", response_model=CopilotInsightResponse)
async def copilot_insights():
    """
    Return proactive insights based on monitoring data.
    Uses real KPI data when available, otherwise provides rule-based tips.
    """
    try:
        service = _get_service()
        kpi_data = _get_kpi_cache_data()
        insights = service.get_insights(kpi_data)
        return JSONResponse(content=insights)
    except Exception as e:
        logger.error(f"Error getting insights: {e}", exc_info=True)
        raise safe_http_error(500, e, "copilot operation")


@router.post("/ask", response_model=CopilotAnswerResponse)
async def copilot_ask(request: AskRequest):
    """
    Ask the DBA Copilot a question.
    Pattern-matches against knowledge base topics and returns relevant answers.

    [2026-05-05 FIND-013-B] Pro-only feature (V6+). NOT registered in V3.3 build
    via ``app.include_router(copilot_router)`` exclusion in ``watcherdb_main.py``.
    Source preserved here for paridade with V6+ Pro tiers (regra superset
    V6 superset V5.5 superset V5 superset V3.3).

    Pre-2026-05-05 narrative kept for historical reference:
    Standard Edition: rule-based only. LLM delegation is gated to Pro
    Edition via ``is_pro_edition()`` in ``services/llm_client.py``.
    """
    start = time.time()
    try:
        service = _get_service()
        result = await service.ask_question(
            question=request.question,
            include_recommendations=request.include_recommendations,
        )
        elapsed = time.time() - start
        logger.info(
            f"Copilot ask: '{request.question[:80]}...' "
            f"source={result.get('source', 'unknown')} "
            f"time={elapsed:.2f}s"
        )
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error in copilot ask: {e}", exc_info=True)
        raise safe_http_error(500, e, "copilot operation")


@router.post("/report", response_model=CopilotReportResponse)
async def copilot_report(request: ReportRequest):
    """
    Generate a summary report.
    Supports: daily_summary, health_check.
    Uses real monitoring data when available.
    """
    start = time.time()
    try:
        service = _get_service()
        kpi_data = _get_kpi_cache_data()
        result = await service.generate_report(
            report_type=request.report_type,
            kpi_data=kpi_data,
            period_hours=request.period_hours,
        )
        elapsed = time.time() - start
        logger.info(
            f"Copilot report: type={request.report_type} time={elapsed:.2f}s"
        )
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        raise safe_http_error(500, e, "copilot operation")
