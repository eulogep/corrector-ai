"""Exceptions métiers utilisées pour exposer des erreurs IA contrôlées à l'API."""

from __future__ import annotations


class AIServiceError(RuntimeError):
    """Erreur attendue provenant d'un service IA ou de sa sortie."""

    status_code = 503
    code = "ai_service_unavailable"

    def __init__(self, provider: str, message: str):
        self.provider = provider
        self.message = message
        super().__init__(message)

    def to_detail(self) -> dict[str, str]:
        return {
            "code": self.code,
            "provider": self.provider,
            "message": self.message,
        }


class AIConfigurationError(AIServiceError):
    """Aucune clé ou aucun fournisseur requis n'est configuré."""

    status_code = 503
    code = "ai_provider_not_configured"


class AIProviderUnavailableError(AIServiceError):
    """Le fournisseur a échoué, expiré ou est indisponible."""

    status_code = 503
    code = "ai_provider_unavailable"


class AIOutputValidationError(AIServiceError):
    """Le fournisseur a répondu mais la sortie ne respecte pas le contrat."""

    status_code = 502
    code = "ai_invalid_response"


class CorrectionInputError(AIServiceError):
    """Le barème ou la demande de correction est incohérent(e)."""

    status_code = 422
    code = "correction_input_invalid"


class SubjectExtractionError(AIServiceError):
    """Le document fourni n'est pas suffisamment lisible pour être traité."""

    status_code = 422
    code = "subject_text_unreadable"
