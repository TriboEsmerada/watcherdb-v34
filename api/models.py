"""Pydantic response models for API endpoints."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: Optional[float] = None
    checks: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    detail: str


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    username: Optional[str] = None
    role: Optional[str] = None
    must_change_password: Optional[bool] = None
    error: Optional[str] = None


class UserInfo(BaseModel):
    username: str
    role: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: bool = False


class UserListResponse(BaseModel):
    success: bool
    users: List[UserInfo]


class DashboardKPI(BaseModel):
    category: str
    kpi_name: str
    value: Any
    status: Optional[str] = None
    trend: Optional[str] = None


class DashboardResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    cached: bool = False
    timestamp: Optional[float] = None


class ServerStatus(BaseModel):
    server_id: str
    status: str
    health_score: Optional[float] = None
    last_check: Optional[str] = None


class CopilotStatusResponse(BaseModel):
    llm_available: bool
    provider: str
    mode: str


class CopilotAnswerResponse(BaseModel):
    answer: str
    recommendations: Optional[List[str]] = None


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""
    success: bool
    data: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


class JobsAnalysisResponse(BaseModel):
    """Response for /api/jobs/server/{id}.

    2026-08-17: `server_id` era obrigatorio e o payload real nao o trazia,
    e sem `extra="allow"` a validacao falhava SEMPRE -> o handler de
    ResponseValidationError devolvia 200 sem dados -> aba Jobs a zeros
    desde 16/04 (264 ocorrencias no log). O modelo documenta o contrato;
    o payload completo (failed_jobs, running_jobs, maintenance_*...) passa.
    """
    model_config = ConfigDict(extra="allow")
    success: bool = True
    server_id: Optional[str] = None
    total_jobs: int = 0
    all_jobs: Any = None  # lista completa (jobs por instancia sao dezenas)
    job_schedules: Optional[List[Dict[str, Any]]] = None
    analysis: Optional[Dict[str, Any]] = None


class BackupStatusResponse(BaseModel):
    server_id: str
    databases: List[Dict[str, Any]]


class SpaceAnalysisResponse(BaseModel):
    server_id: str
    data: List[Dict[str, Any]]


class AlwaysOnOverviewResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None


class ServiceStatusResponse(BaseModel):
    server_id: str
    services: List[Dict[str, Any]]


class ClusterHealthResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None


class NetworkDiagnosticsResponse(BaseModel):
    success: bool
    diagnostics: Optional[Dict[str, Any]] = None


class QueryResultResponse(BaseModel):
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    row_count: Optional[int] = None
    execution_time_ms: Optional[float] = None


class CopilotInsightResponse(BaseModel):
    insights: List[Dict[str, Any]]


class CopilotReportResponse(BaseModel):
    title: str
    content: str
    key_findings: Optional[List[str]] = None


class QuickAnswerItem(BaseModel):
    question: str
    answer: str


class QuickAnswersResponse(BaseModel):
    answers: List[QuickAnswerItem]


# ============================================================
# Response models for additional routers (Item #9 audit)
# ============================================================

class DiskUnallocatedSummaryResponse(BaseModel):
    """Response for /disk-unallocated/summary"""
    success: bool
    count: int
    data: List[Dict[str, Any]]


class DiskUnallocatedServerResponse(BaseModel):
    """Response for /disk-unallocated/server/{server_id}"""
    success: bool
    server_id: str
    data: Dict[str, Any]


class DiagnosticsOverviewResponse(BaseModel):
    """Response for /api/diagnostics/overview"""
    alwayson: Optional[Dict[str, Any]] = None
    queries_available: Optional[List[Dict[str, Any]]] = None
    timestamp: Optional[str] = None


class DatabaseDiscoveryResponse(BaseModel):
    """Response for /discover/server/{server_id}"""
    success: bool
    server_id: str
    database_count: Optional[int] = None
    databases: Optional[Dict[str, Any]] = None
    discovered_at: Optional[str] = None


class OSPerformanceResponse(BaseModel):
    """Response for /api/os/{hostname}/memory and similar OS perf endpoints"""
    success: bool
    hostname: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None


class KPIMetadataItem(BaseModel):
    """Single KPI metadata entry."""
    name: str
    display_name: str
    category: str
    description: str
    avg_duration_ms: float
    max_duration_ms: float
    table_name: str
    is_fast: bool
    collection_interval_minutes: int
    last_update: Optional[str] = None


class SQLServerKPIDashboardResponse(BaseModel):
    """Response for /api/sqlserver-kpis/dashboard"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    performance: Optional[Dict[str, Any]] = None


class SQLServerKPIResponse(BaseModel):
    """Generic response for individual SQL Server KPI endpoints"""
    success: bool
    data: Optional[Dict[str, Any]] = None


# ============================================================
# Generic / Auth / Utility response models (Item #9 expansion)
# ============================================================

class GenericResponse(BaseModel):
    """Generic response for endpoints that return varied structures."""
    model_config = ConfigDict(extra="allow")
    success: Optional[bool] = None
    data: Optional[Any] = None
    error: Optional[str] = None


class MessageResponse(BaseModel):
    """Response for endpoints that return a success flag and optional message."""
    success: bool
    message: Optional[str] = None


class TokenValidationResponse(BaseModel):
    """Response for token validation endpoint."""
    valid: bool
    user: Optional[Dict[str, Any]] = None


class SuccessResponse(BaseModel):
    """Response for toggle/status endpoints."""
    success: bool
    error: Optional[str] = None


class ServiceLogsResponse(BaseModel):
    """Response for service logs endpoint."""
    server_id: str
    service_name: str
    hours: int
    logs: List[Dict[str, Any]]
    total_logs: int
    sources_used: Optional[List[str]] = None


class ServicesOverviewResponse(BaseModel):
    """Response for services overview endpoint."""
    total_servers: int
    healthy_servers: Optional[int] = None
    servers_with_issues: Optional[int] = None
    servers_with_critical_down: Optional[int] = None
    servers: Optional[Dict[str, Any]] = None


class ClusterEventsResponse(BaseModel):
    """Response for cluster events endpoint."""
    success: bool
    events: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    message: Optional[str] = None


class ClusterSummaryResponse(BaseModel):
    """Response for cluster summary endpoint."""
    model_config = ConfigDict(extra="allow")
    health: Optional[Dict[str, Any]] = None


class DiagnosticsHealthResponse(BaseModel):
    """Response for diagnostics health check."""
    alwayson_checker: bool
    queries_module: bool
    status: str


class NetworkQuickTestResponse(BaseModel):
    """Response for quick network test."""
    success: bool
    server_id: str
    reachable: Optional[bool] = None
    tcp_time_ms: Optional[float] = None
    port: Optional[int] = None
    port_source: Optional[str] = None
    error: Optional[str] = None


class JobTrendsResponse(BaseModel):
    """Response for job trends endpoint.

    2026-08-17: `success` era obrigatorio e o endpoint nao o enviava ->
    validacao falhava -> handler engolia o payload (ver JobsAnalysisResponse).
    """
    model_config = ConfigDict(extra="allow")
    success: bool = True
    server_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class JobConflictsResponse(BaseModel):
    """Response for job schedule conflicts endpoint (mesma correccao 2026-08-17)."""
    model_config = ConfigDict(extra="allow")
    success: bool = True
    server_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class AuthLogResponse(BaseModel):
    """Response for auth log endpoint."""
    success: bool
    logs: List[Dict[str, Any]]
    count: int
    error: Optional[str] = None


class SessionsResponse(BaseModel):
    """Response for active sessions endpoint."""
    success: bool
    sessions: List[Dict[str, Any]]
    count: int
    error: Optional[str] = None


class OnlineUsersResponse(BaseModel):
    """Response for online users endpoint."""
    success: bool
    online: List[Dict[str, Any]]
    count: int


class PreferencesResponse(BaseModel):
    """Response for user preferences endpoint."""
    success: bool
    preferences: Optional[Dict[str, Any]] = None


class SavePreferencesResponse(BaseModel):
    """Response for save preferences endpoint."""
    success: bool
    saved: int
    errors: Optional[List[str]] = None


class DeletePreferenceResponse(BaseModel):
    """Response for delete preference endpoint."""
    success: bool
    deleted: bool


class SystemConfigResponse(BaseModel):
    """Response for system config endpoint."""
    success: bool
    config: Dict[str, Any]


class UserRoleUpdateResponse(BaseModel):
    """Response for user role update."""
    success: bool
    username: str
    role: str
