"""Tests du cache Redis de barèmes de sujets sans dépendre d'un serveur Redis réel."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.schemas.ai_outputs import SubjectRubric
from backend.services.subject_cache import SubjectExtractionCache


VALID_RUBRIC = SubjectRubric.model_validate(
    {
        "matiere_detectee": "Mathématiques",
        "niveau_detecte": "4ème",
        "total_points": 10.0,
        "exercices": [
            {
                "numero": 1,
                "enonce": "Calculer 1 + 1",
                "reponse_attendue": "2",
                "points_max": 10.0,
                "sous_questions": [],
                "type": "calcul",
            }
        ],
        "confiance": 0.9,
        "remarques": "",
    }
)


class FakeSubjectCache:
    """Double de test en mémoire pour vérifier le contrat du cache de sujet."""

    def __init__(self, payload=None):
        self.enabled = True
        self.payload = payload
        self.key_for_file = AsyncMock(return_value="cache-key")
        self.get = AsyncMock(return_value=payload)
        self.set = AsyncMock()
        self.delete = AsyncMock()


@pytest.mark.asyncio
async def test_cache_key_isolated_per_professor_namespace(tmp_path):
    """Le même fichier doit produire des clés distinctes pour deux professeurs."""
    document = tmp_path / "sujet.pdf"
    document.write_bytes(b"meme-contenu")
    cache = SubjectExtractionCache(redis_url="")

    key_prof_a = await cache.key_for_file(str(document), "professor:1")
    key_prof_b = await cache.key_for_file(str(document), "professor:2")

    assert key_prof_a != key_prof_b
    assert "meme-contenu" not in key_prof_a
    assert "professor:1" not in key_prof_a


@pytest.mark.asyncio
async def test_parse_subject_returns_validated_cache_hit_without_reextracting(tmp_path):
    """Un barème Redis valide évite Docling, OCR et le LLM."""
    from backend.services import subject_parser

    document = tmp_path / "sujet.pdf"
    document.write_bytes(b"contenu")
    cache = FakeSubjectCache(
        {
            "rubric": VALID_RUBRIC.model_dump(),
            "source_extraction": "docling",
            "llm_used": "claude",
        }
    )

    with patch.object(subject_parser, "subject_cache", cache), patch.object(
        subject_parser, "_extract_text", new=AsyncMock()
    ) as extract_text:
        result = await subject_parser.parse_subject(
            str(document), cache_namespace="professor:42"
        )

    assert result["cache_hit"] is True
    assert result["source_extraction"] == "cache"
    assert result["llm_used"] == "claude"
    extract_text.assert_not_awaited()
    cache.key_for_file.assert_awaited_once_with(str(document), "professor:42")


@pytest.mark.asyncio
async def test_parse_subject_stores_a_validated_result_after_cache_miss(tmp_path):
    """Une analyse fraîche est sérialisée dans Redis avec les métadonnées minimales."""
    from backend.services import subject_parser

    document = tmp_path / "sujet.pdf"
    document.write_bytes(b"contenu")
    cache = FakeSubjectCache(payload=None)

    with patch.object(subject_parser, "subject_cache", cache), patch.object(
        subject_parser, "_extract_text", new=AsyncMock(return_value=("texte sujet", "docling"))
    ), patch.object(
        subject_parser,
        "_generate_bareme_with_fallback",
        new=AsyncMock(return_value=(VALID_RUBRIC, "claude")),
    ):
        result = await subject_parser.parse_subject(
            str(document), cache_namespace="professor:42"
        )

    assert result["cache_hit"] is False
    cache.set.assert_awaited_once()
    stored_key, stored_payload = cache.set.await_args.args
    assert stored_key == "cache-key"
    assert stored_payload["rubric"] == VALID_RUBRIC.model_dump()
    assert stored_payload["llm_used"] == "claude"


@pytest.mark.asyncio
async def test_invalid_cache_entry_is_deleted_and_rebuilt(tmp_path):
    """Une entrée Redis corrompue ne peut pas contourner la validation Pydantic."""
    from backend.services import subject_parser

    document = tmp_path / "sujet.pdf"
    document.write_bytes(b"contenu")
    cache = FakeSubjectCache(payload={"rubric": {"matiere_detectee": "incomplet"}})

    with patch.object(subject_parser, "subject_cache", cache), patch.object(
        subject_parser, "_extract_text", new=AsyncMock(return_value=("texte sujet", "docling"))
    ), patch.object(
        subject_parser,
        "_generate_bareme_with_fallback",
        new=AsyncMock(return_value=(VALID_RUBRIC, "deepseek")),
    ):
        result = await subject_parser.parse_subject(
            str(document), cache_namespace="professor:42"
        )

    cache.delete.assert_awaited_once_with("cache-key")
    assert result["cache_hit"] is False
    assert result["llm_used"] == "deepseek"
