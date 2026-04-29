import logging
from typing import Optional

from sentence_transformers import SentenceTransformer

from core.config import settings


logger = logging.getLogger(__name__)


def configure_third_party_logging() -> None:
    """Reduce noisy startup logs from model download/init libraries."""
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers.base.model").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)


def _build_model_kwargs(device: Optional[str]) -> dict:
    kwargs = {}
    resolved_device = device or settings.EMBEDDING_DEVICE or None
    if resolved_device:
        kwargs["device"] = resolved_device
    if settings.HF_TOKEN:
        kwargs["token"] = settings.HF_TOKEN
    return kwargs


def _is_network_error(exc: Exception) -> bool:
    message = str(exc).lower()
    markers = (
        "cannot send a request, as the client has been closed",
        "temporary failure in name resolution",
        "nodename nor servname provided",
        "connection error",
        "max retries exceeded",
        "offline",
    )
    return any(marker in message for marker in markers)


def load_sentence_transformer(
    model_name: str,
    *,
    device: Optional[str] = None,
) -> SentenceTransformer:
    """Load the embedding model with optional auth and device overrides."""
    kwargs = _build_model_kwargs(device)

    try:
        return SentenceTransformer(model_name, **kwargs)
    except TypeError:
        # Older sentence-transformers releases may not accept every kwarg.
        logger.debug("Falling back to default SentenceTransformer init for %s", model_name)
        return SentenceTransformer(model_name)
    except Exception as exc:
        if _is_network_error(exc):
            logger.warning(
                "Embedding model download failed for %s; retrying from local cache only.",
                model_name,
            )
            local_only_kwargs = dict(kwargs)
            local_only_kwargs["local_files_only"] = True
            try:
                return SentenceTransformer(model_name, **local_only_kwargs)
            except TypeError:
                logger.debug("local_files_only unsupported; retrying default init for %s", model_name)
                return SentenceTransformer(model_name)
        raise
