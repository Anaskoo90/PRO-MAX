"""AI Gateway composition using the existing provider abstractions."""

from __future__ import annotations

from fastapi import FastAPI

from app.ai_gateway.application.service import AiCompletionService
from app.ai_gateway.presentation import deps, router
from app.identity.application.security import RedisRateLimitStore
from app.identity.composition import IdentityModule
from app.identity.infrastructure.seed_data import PermissionSpec
from app.platform_core.ai.anthropic_provider import AnthropicProvider
from app.platform_core.ai.embedding import EmbeddingProvider
from app.platform_core.ai.gateway import AiGateway, ProviderRoute
from app.platform_core.ai.openai_provider import OpenAICompatibleProvider
from app.platform_core.configuration.settings import PlatformSettings
from app.platform_core.di.container import ServiceContainer

AI_PERMISSION_CATALOG: tuple[PermissionSpec, ...] = (
    PermissionSpec("ai", "use", "Use organization AI capabilities"),
)


class AiGatewayModule:
    module_name = "ai_gateway"

    def __init__(
        self,
        settings: PlatformSettings,
        identity_module: IdentityModule,
    ) -> None:
        providers = {}
        self.embedding_provider: EmbeddingProvider | None = None
        if settings.ai_openai_api_key is not None:
            openai_provider = OpenAICompatibleProvider(
                api_key=settings.ai_openai_api_key.get_secret_value(),
                base_url=str(settings.ai_openai_base_url),
                embedding_model=settings.ai_openai_embedding_model,
                embedding_dimensions=settings.ai_openai_embedding_dimensions,
                timeout_seconds=settings.ai_timeout_seconds,
            )
            providers["openai"] = openai_provider
            self.embedding_provider = openai_provider
        if settings.ai_anthropic_api_key is not None:
            providers["anthropic"] = AnthropicProvider(
                api_key=settings.ai_anthropic_api_key.get_secret_value(),
                base_url=str(settings.ai_anthropic_base_url),
                api_version=settings.ai_anthropic_version,
                timeout_seconds=settings.ai_timeout_seconds,
            )
        self._providers = providers

        models = {
            "openai": settings.ai_openai_model,
            "anthropic": settings.ai_anthropic_model,
        }
        primary = (
            None
            if settings.ai_provider == "disabled"
            else ProviderRoute(
                provider=settings.ai_provider,
                model=models[settings.ai_provider],
            )
        )
        fallback = (
            ProviderRoute(
                provider=settings.ai_fallback_provider,
                model=models[settings.ai_fallback_provider],
            )
            if settings.ai_fallback_provider is not None
            else None
        )
        self.gateway = AiGateway(
            providers=providers,
            primary=primary,
            fallback=fallback,
        )
        self.completion_service = AiCompletionService(
            gateway=self.gateway,
            permission_checker=identity_module.permission_evaluator,
            rate_limit_store=RedisRateLimitStore(identity_module.redis_client),
            requests_per_minute=settings.ai_requests_per_minute,
            max_prompt_characters=settings.ai_max_prompt_characters,
            max_output_tokens=settings.ai_max_output_tokens,
        )

    async def shutdown(self) -> None:
        for provider in self._providers.values():
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()

    def register(self, container: ServiceContainer) -> None:
        container.register_instance(AiGateway, self.gateway)
        container.register_instance(AiCompletionService, self.completion_service)
        if self.embedding_provider is not None:
            container.register_instance(EmbeddingProvider, self.embedding_provider)

    def mount(self, app: FastAPI) -> None:
        app.include_router(router.router)
        app.dependency_overrides[deps.get_ai_completion_service] = (
            lambda: self.completion_service
        )


__all__ = ["AI_PERMISSION_CATALOG", "AiGatewayModule"]
