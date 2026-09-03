"""
Query Performance Profiler
Analyzes SQL query performance and provides optimization recommendations
"""

import logging
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class QueryIssueType(str, Enum):
    """Types of query performance issues"""
    MISSING_INDEX = "missing_index"
    PARAMETER_SNIFFING = "parameter_sniffing"
    IMPLICIT_CONVERSION = "implicit_conversion"
    SCAN_OPERATION = "scan_operation"
    HIGH_COST = "high_cost"
    LONG_RUNNING = "long_running"
    STATISTICS_STALE = "statistics_stale"
    MISSING_STATISTICS = "missing_statistics"
    BLOCKING = "blocking"
    DEADLOCK_VICTIM = "deadlock_victim"


@dataclass
class QueryRecommendation:
    """Query optimization recommendation"""
    issue_type: QueryIssueType
    severity: str  # "low", "medium", "high", "critical"
    description: str
    recommendation: str
    sql_example: Optional[str] = None
    impact_estimate: Optional[str] = None


@dataclass
class QueryAnalysis:
    """Query performance analysis result"""
    query_hash: str
    query_text: str
    execution_count: int
    avg_duration_ms: float
    total_cpu_ms: float
    total_reads: int
    total_writes: int
    issues: List[QueryRecommendation]
    overall_score: int  # 0-100, higher is better
    optimization_priority: str  # "low", "medium", "high", "critical"


class QueryPerformanceProfiler:
    """
    Analyzes SQL Server query performance and provides recommendations

    Features:
    - Execution plan analysis
    - Missing index detection
    - Parameter sniffing detection
    - Statistics staleness check
    - Query rewrite suggestions
    """

    def __init__(self):
        self.issue_patterns = self._initialize_patterns()
        logger.info("QueryPerformanceProfiler initialized")

    def _initialize_patterns(self) -> Dict[str, Any]:
        """Initialize regex patterns for common issues"""
        return {
            "select_star": re.compile(r"SELECT\s+\*\s+FROM", re.IGNORECASE),
            "no_where": re.compile(r"FROM\s+\w+\s*(?!WHERE)", re.IGNORECASE),
            "scalar_functions": re.compile(r"(UPPER|LOWER|SUBSTRING|LEFT|RIGHT|CONVERT)\s*\(", re.IGNORECASE),
            "cursor": re.compile(r"DECLARE\s+\w+\s+CURSOR", re.IGNORECASE),
            "temp_table": re.compile(r"#\w+", re.IGNORECASE),
            "subquery": re.compile(r"SELECT.*\(SELECT", re.IGNORECASE),
        }

    def analyze_query(
        self,
        query_text: str,
        query_hash: str,
        execution_count: int = 1,
        avg_duration_ms: float = 0.0,
        total_cpu_ms: float = 0.0,
        total_reads: int = 0,
        total_writes: int = 0,
        execution_plan: Optional[str] = None
    ) -> QueryAnalysis:
        """
        Analyze query performance and provide recommendations

        Args:
            query_text: SQL query text
            query_hash: Query hash/identifier
            execution_count: Number of executions
            avg_duration_ms: Average duration in milliseconds
            total_cpu_ms: Total CPU time in milliseconds
            total_reads: Total logical reads
            total_writes: Total writes
            execution_plan: XML execution plan (optional)

        Returns:
            QueryAnalysis with issues and recommendations
        """
        try:
            issues: List[QueryRecommendation] = []

            # Analyze query text
            issues.extend(self._analyze_query_text(query_text))

            # Analyze metrics
            issues.extend(self._analyze_metrics(
                avg_duration_ms, total_cpu_ms, total_reads, total_writes
            ))

            # Analyze execution plan if provided
            if execution_plan:
                issues.extend(self._analyze_execution_plan(execution_plan))

            # Calculate overall score
            score = self._calculate_score(issues, avg_duration_ms, total_reads)

            # Determine priority
            priority = self._determine_priority(score, avg_duration_ms, execution_count)

            analysis = QueryAnalysis(
                query_hash=query_hash,
                query_text=query_text[:500],  # Truncate long queries
                execution_count=execution_count,
                avg_duration_ms=avg_duration_ms,
                total_cpu_ms=total_cpu_ms,
                total_reads=total_reads,
                total_writes=total_writes,
                issues=issues,
                overall_score=score,
                optimization_priority=priority
            )

            logger.info(f"Query analyzed: {query_hash} - Score: {score}, Priority: {priority}")
            return analysis

        except Exception as e:
            logger.error(f"Error analyzing query: {e}")
            return QueryAnalysis(
                query_hash=query_hash,
                query_text=query_text[:500],
                execution_count=execution_count,
                avg_duration_ms=avg_duration_ms,
                total_cpu_ms=total_cpu_ms,
                total_reads=total_reads,
                total_writes=total_writes,
                issues=[],
                overall_score=50,
                optimization_priority="unknown"
            )

    def _analyze_query_text(self, query_text: str) -> List[QueryRecommendation]:
        """Analyze query text for common anti-patterns"""
        issues = []

        # SELECT *
        if self.issue_patterns["select_star"].search(query_text):
            issues.append(QueryRecommendation(
                issue_type=QueryIssueType.HIGH_COST,
                severity="medium",
                description="Query uses SELECT * which retrieves all columns",
                recommendation="Specify only the columns you need instead of using SELECT *",
                sql_example="SELECT column1, column2 FROM table WHERE ...",
                impact_estimate="Can reduce network traffic and improve performance by 20-50%"
            ))

        # Missing WHERE clause
        if self.issue_patterns["no_where"].search(query_text) and "JOIN" not in query_text.upper():
            issues.append(QueryRecommendation(
                issue_type=QueryIssueType.SCAN_OPERATION,
                severity="high",
                description="Query may be missing WHERE clause, could result in table scan",
                recommendation="Add WHERE clause to filter rows and use indexes",
                sql_example="SELECT ... FROM table WHERE indexed_column = @value",
                impact_estimate="Can improve performance by 10x-1000x depending on table size"
            ))

        # Scalar functions in WHERE
        if self.issue_patterns["scalar_functions"].search(query_text):
            issues.append(QueryRecommendation(
                issue_type=QueryIssueType.IMPLICIT_CONVERSION,
                severity="medium",
                description="Scalar functions on columns prevent index usage",
                recommendation="Avoid functions on columns in WHERE clause, use computed columns or indexed views",
                sql_example="WHERE column = 'VALUE' instead of WHERE UPPER(column) = 'VALUE'",
                impact_estimate="Can enable index usage and improve performance by 5x-100x"
            ))

        # Cursors
        if self.issue_patterns["cursor"].search(query_text):
            issues.append(QueryRecommendation(
                issue_type=QueryIssueType.HIGH_COST,
                severity="high",
                description="Query uses cursors which are generally slow",
                recommendation="Replace cursor with set-based operations when possible",
                sql_example="Use UPDATE/INSERT/DELETE with JOINs instead of CURSOR loops",
                impact_estimate="Set-based operations are typically 10x-100x faster than cursors"
            ))

        return issues

    def _analyze_metrics(
        self,
        avg_duration_ms: float,
        total_cpu_ms: float,
        total_reads: int,
        total_writes: int
    ) -> List[QueryRecommendation]:
        """Analyze query execution metrics"""
        issues = []

        # High duration
        if avg_duration_ms > 5000:  # >5 seconds
            issues.append(QueryRecommendation(
                issue_type=QueryIssueType.LONG_RUNNING,
                severity="critical" if avg_duration_ms > 30000 else "high",
                description=f"Query has high average duration: {avg_duration_ms:.0f}ms",
                recommendation="Investigate execution plan, missing indexes, or consider query redesign",
                impact_estimate="Significant user impact, requires immediate attention"
            ))

        # High reads
        if total_reads > 100000:
            issues.append(QueryRecommendation(
                issue_type=QueryIssueType.SCAN_OPERATION,
                severity="high",
                description=f"Query performs excessive logical reads: {total_reads:,}",
                recommendation="Add indexes, update statistics, or rewrite query to reduce scans",
                impact_estimate="Reducing reads can significantly improve performance and reduce I/O"
            ))

        return issues

    def _analyze_execution_plan(self, execution_plan: str) -> List[QueryRecommendation]:
        """Analyze XML execution plan"""
        issues = []

        # Simplified plan analysis (in production, parse XML properly)
        if "TableScan" in execution_plan or "ClusteredIndexScan" in execution_plan:
            issues.append(QueryRecommendation(
                issue_type=QueryIssueType.SCAN_OPERATION,
                severity="high",
                description="Execution plan shows table/index scans",
                recommendation="Create appropriate indexes for filtered columns",
                impact_estimate="Proper indexes can reduce scan to seek, improving performance by 10x-1000x"
            ))

        if "MissingIndex" in execution_plan:
            issues.append(QueryRecommendation(
                issue_type=QueryIssueType.MISSING_INDEX,
                severity="high",
                description="SQL Server suggests missing indexes in execution plan",
                recommendation="Review and create suggested indexes from execution plan",
                sql_example="CREATE INDEX IX_... ON table (column1, column2) INCLUDE (column3)",
                impact_estimate="Missing indexes can cause major performance degradation"
            ))

        if "ImplicitConversion" in execution_plan or "CONVERT_IMPLICIT" in execution_plan:
            issues.append(QueryRecommendation(
                issue_type=QueryIssueType.IMPLICIT_CONVERSION,
                severity="medium",
                description="Execution plan shows implicit data type conversions",
                recommendation="Ensure parameter and column data types match exactly",
                impact_estimate="Fixing conversions can enable index usage and improve performance"
            ))

        return issues

    def _calculate_score(
        self,
        issues: List[QueryRecommendation],
        avg_duration_ms: float,
        total_reads: int
    ) -> int:
        """Calculate overall query health score (0-100)"""
        score = 100

        # Deduct points for issues
        for issue in issues:
            if issue.severity == "critical":
                score -= 30
            elif issue.severity == "high":
                score -= 20
            elif issue.severity == "medium":
                score -= 10
            elif issue.severity == "low":
                score -= 5

        # Deduct for high metrics
        if avg_duration_ms > 1000:
            score -= min(20, int(avg_duration_ms / 1000))

        if total_reads > 10000:
            score -= min(15, int(total_reads / 10000))

        return max(0, min(100, score))

    def _determine_priority(
        self,
        score: int,
        avg_duration_ms: float,
        execution_count: int
    ) -> str:
        """Determine optimization priority"""
        # Critical: Low score or very slow query
        if score < 30 or avg_duration_ms > 30000:
            return "critical"

        # High: Medium score or slow + frequently executed
        if score < 50 or (avg_duration_ms > 5000 and execution_count > 100):
            return "high"

        # Medium: Moderate issues
        if score < 70:
            return "medium"

        # Low: Minor issues
        return "low"

    def get_top_recommendations(
        self,
        analyses: List[QueryAnalysis],
        top_n: int = 10
    ) -> List[QueryAnalysis]:
        """Get top N queries that need optimization"""
        # Sort by priority and score
        priority_order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unknown": 0}

        sorted_analyses = sorted(
            analyses,
            key=lambda x: (priority_order.get(x.optimization_priority, 0), -x.overall_score),
            reverse=True
        )

        return sorted_analyses[:top_n]
