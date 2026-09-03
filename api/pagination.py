"""
Reusable pagination for API list endpoints.

Usage:
    from api.pagination import paginate, PaginationParams

    @router.get("/items")
    async def list_items(pagination: PaginationParams = Depends()):
        all_items = get_all_items()
        return paginate(all_items, pagination)
"""
from typing import Any, List, Optional
from fastapi import Query
from pydantic import BaseModel


class PaginationParams:
    """Dependency-injectable pagination parameters."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    ):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size


class PaginatedResult(BaseModel):
    """Standard paginated response."""
    data: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


def paginate(items: list, params: PaginationParams) -> dict:
    """Apply pagination to a list of items."""
    total = len(items)
    total_pages = max(1, (total + params.page_size - 1) // params.page_size)
    start = params.offset
    end = start + params.page_size

    return {
        "data": items[start:end],
        "total": total,
        "page": params.page,
        "page_size": params.page_size,
        "total_pages": total_pages,
    }
