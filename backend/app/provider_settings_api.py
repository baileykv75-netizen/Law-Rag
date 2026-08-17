from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from .provider_settings import (
    ProviderConfigurationError,
    ProviderConfigurationOverview,
    ProviderName,
    ProviderSaveRequest,
    ProviderTestRequest,
    ProviderTestResult,
    delete_provider_configuration,
    mark_setup_complete,
    provider_overview,
    save_provider_configuration,
    test_provider_connection,
)

router = APIRouter()


@router.get("/api/config/providers", response_model=ProviderConfigurationOverview)
def get_provider_configuration() -> ProviderConfigurationOverview:
    try:
        return provider_overview()
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.put("/api/config/providers", response_model=ProviderConfigurationOverview)
def put_provider_configuration(request: ProviderSaveRequest) -> ProviderConfigurationOverview:
    try:
        return save_provider_configuration(request)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/api/config/providers/test", response_model=ProviderTestResult)
def probe_provider_configuration(request: ProviderTestRequest) -> ProviderTestResult:
    try:
        return test_provider_connection(request)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.delete("/api/config/providers/{provider}", response_model=ProviderConfigurationOverview)
def remove_provider_configuration(provider: ProviderName) -> ProviderConfigurationOverview:
    try:
        return delete_provider_configuration(provider)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/api/config/providers/skip", response_model=ProviderConfigurationOverview)
def skip_provider_setup() -> ProviderConfigurationOverview:
    mark_setup_complete()
    return provider_overview()
