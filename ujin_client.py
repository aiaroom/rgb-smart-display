from __future__ import annotations

from typing import Any, Optional

import httpx
from fastapi import HTTPException, status

from settings import settings


class UjinClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or settings.ujin.base_url).rstrip("/")
        self.token = token or settings.ujin.token

    async def _get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not self.base_url or not self.token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ujin API settings are not configured",
            )

        request_params = params.copy() if params else {}
        request_params["token"] = self.token

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{self.base_url}{endpoint}",
                headers={"Authorization": f"Bearer {self.token}"},
                params=request_params,
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Ujin API error: {response.text}",
            )

        data = response.json()

        if data.get("error") not in (None, 0):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=data.get("message") or "Ujin API returned error",
            )

        return data

    async def get_complexes(self) -> list[dict[str, Any]]:
        data = await self._get("/v1/complex/list/")
        return data.get("data", {}).get("items", [])

    async def find_complex_by_id(
        self,
        ujin_complex_id: int | str,
    ) -> dict[str, Any] | None:
        complexes = await self.get_complexes()

        for item in complexes:
            if str(item.get("id")) == str(ujin_complex_id):
                return item

        return None

    async def get_buildings(
        self,
        complex_id: int | str | None = None,
        search: str | None = None,
        per_page: int = 1000,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "per_page": per_page,
            "page": page,
        }

        if complex_id is not None:
            params["complex_id"] = complex_id

        if search:
            params["search"] = search

        data = await self._get("/v1/buildings/get-list-crm/", params)

        return (
            data.get("data", {}).get("buildings")
            or data.get("data", {}).get("items")
            or []
        )

    async def get_news(
        self,
        complexes: list[int] | None = None,
        buildings: list[int] | None = None,
        news_type: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}

        if complexes:
            params["complexes"] = complexes

        if buildings:
            params["buildings"] = buildings

        if news_type:
            params["type"] = news_type

        data = await self._get("/v1/news/list", params)

        return data.get("data", {}).get("items", [])

    async def get_news_detail(self, news_id: int) -> dict[str, Any] | None:
        data = await self._get("/v1/news/view", {"id": news_id})
        return data.get("data", {}).get("item")

    async def get_parking(
        self,
        complexes: list[int] | None = None,
        buildings: list[int] | None = None,
        status_filter: str | None = None,
    ) -> dict[str, Any]:
        endpoints = {
            None: "/api/v1/parking/list",
            "free": "/api/v1/parking/free",
            "occupied": "/api/v1/parking/occupied",
            "public": "/api/v1/parking/public",
            "private": "/api/v1/parking/private",
            "unassigned": "/api/v1/parking/unassigned",
        }

        endpoint = endpoints.get(status_filter)

        if endpoint is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid parking status filter",
            )

        return await self._get(
            endpoint,
            self._array_params(complexes=complexes, buildings=buildings),
        )

    async def get_storage(
        self,
        complexes: list[int] | None = None,
        buildings: list[int] | None = None,
        status_filter: str | None = None,
    ) -> dict[str, Any]:
        endpoints = {
            None: "/api/v1/storage/list",
            "free": "/api/v1/storage/free",
            "occupied": "/api/v1/storage/occupied",
            "public": "/api/v1/storage/public",
            "private": "/api/v1/storage/private",
            "unassigned": "/api/v1/storage/unassigned",
        }

        endpoint = endpoints.get(status_filter)

        if endpoint is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid storage status filter",
            )

        return await self._get(
            endpoint,
            self._array_params(complexes=complexes, buildings=buildings),
        )

    @staticmethod
    def _array_params(
        complexes: list[int] | None = None,
        buildings: list[int] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}

        if complexes:
            params["complexes[]"] = complexes

        if buildings:
            params["buildings[]"] = buildings

        return params