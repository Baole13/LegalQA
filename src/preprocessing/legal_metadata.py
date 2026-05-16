from __future__ import annotations

from dataclasses import dataclass

from src.utils.text import infer_document_title, normalize_text


@dataclass(frozen=True)
class LegalMetadata:
    cid: str
    doc_name: str | None
    doc_number: str | None
    chapter: str | None
    article: str | None
    clause: str | None
    issued_date: str | None
    effective_date: str | None
    expiry_date: str | None
    validity_status: str | None
    source_path: str | None
    source_type: str | None


CANONICAL_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "cid": ("cid", "id", "doc_id"),
    "text": ("text", "content", "body", "document_text"),
    "doc_name": ("doc_name", "document_name", "title", "law_name", "ten_luat", "ten_van_ban"),
    "doc_number": ("doc_number", "document_number", "law_number", "so_hieu", "so_van_ban"),
    "chapter": ("chapter", "chuong"),
    "article": ("article", "dieu"),
    "clause": ("clause", "khoan"),
    "issued_date": ("issued_date", "date_issued", "ngay_ban_hanh"),
    "effective_date": ("effective_date", "ngay_hieu_luc"),
    "expiry_date": ("expiry_date", "ngay_het_hieu_luc"),
    "validity_status": ("validity_status", "status", "trang_thai_hieu_luc"),
    "source_path": ("source_path", "file_path", "path"),
    "source_type": ("source_type", "file_type", "format"),
}


def normalize_legal_record(record: dict) -> dict:
    normalized: dict[str, object] = {}
    for canonical_name, aliases in CANONICAL_FIELD_ALIASES.items():
        value = _first_present_value(record, aliases)
        if isinstance(value, str) and canonical_name != "text":
            value = normalize_text(value)
        normalized[canonical_name] = value

    normalized["cid"] = str(normalized.get("cid") or "")
    normalized["text"] = str(normalized.get("text") or "")
    normalized["doc_name"] = normalized.get("doc_name") or infer_document_title(normalized["text"])
    normalized["source_type"] = normalized.get("source_type") or infer_source_type(normalized.get("source_path"))
    normalized["validity_status"] = normalize_validity_status(normalized.get("validity_status"))
    return normalized


def build_legal_metadata(record: dict, article: str | None = None, clause: str | None = None) -> LegalMetadata:
    normalized = normalize_legal_record(record)
    return LegalMetadata(
        cid=str(normalized.get("cid") or ""),
        doc_name=_none_if_empty(normalized.get("doc_name")),
        doc_number=_none_if_empty(normalized.get("doc_number")),
        chapter=_none_if_empty(normalized.get("chapter")),
        article=article or _none_if_empty(normalized.get("article")),
        clause=clause or _none_if_empty(normalized.get("clause")),
        issued_date=_none_if_empty(normalized.get("issued_date")),
        effective_date=_none_if_empty(normalized.get("effective_date")),
        expiry_date=_none_if_empty(normalized.get("expiry_date")),
        validity_status=_none_if_empty(normalized.get("validity_status")),
        source_path=_none_if_empty(normalized.get("source_path")),
        source_type=_none_if_empty(normalized.get("source_type")),
    )


def metadata_to_dict(metadata: LegalMetadata) -> dict:
    return {
        "cid": metadata.cid,
        "doc_name": metadata.doc_name,
        "doc_number": metadata.doc_number,
        "chapter": metadata.chapter,
        "article": metadata.article,
        "clause": metadata.clause,
        "issued_date": metadata.issued_date,
        "effective_date": metadata.effective_date,
        "expiry_date": metadata.expiry_date,
        "validity_status": metadata.validity_status,
        "source_path": metadata.source_path,
        "source_type": metadata.source_type,
    }


def infer_source_type(source_path: object) -> str | None:
    path = str(source_path or "").lower()
    if not path:
        return None
    if path.endswith(".pdf"):
        return "pdf"
    if path.endswith(".doc") or path.endswith(".docx"):
        return "word"
    if path.endswith(".parquet"):
        return "parquet"
    if path.endswith(".txt"):
        return "text"
    return None


def normalize_validity_status(status: object) -> str | None:
    raw = normalize_text(str(status or "")).lower()
    if not raw:
        return None
    if raw in {"con hieu luc", "active", "valid", "hieu luc"}:
        return "con_hieu_luc"
    if raw in {"het hieu luc", "expired", "invalid"}:
        return "het_hieu_luc"
    if raw in {"sap co hieu luc", "pending", "future"}:
        return "sap_co_hieu_luc"
    return raw.replace(" ", "_")


def _first_present_value(record: dict, aliases: tuple[str, ...]) -> object | None:
    for name in aliases:
        if name in record and record[name] not in {None, ""}:
            return record[name]
    return None


def _none_if_empty(value: object) -> str | None:
    text = normalize_text(str(value or ""))
    return text or None
