"""
Storage service.

Uses S3/MinIO when reachable; otherwise transparently falls back to a local
directory so the platform runs with zero external services.
"""
import hashlib
import os
import shutil
import uuid

from fastapi import UploadFile

from app.core.config import settings

try:
    import boto3
    from botocore.config import Config as BotoConfig
    from botocore.exceptions import ClientError
    _BOTO_AVAILABLE = True
except Exception:  # pragma: no cover
    _BOTO_AVAILABLE = False


class LocalStorage:
    """Filesystem-backed storage (default for local development)."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, key: str) -> str:
        path = os.path.join(self.root, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def put(self, key: str, content: bytes, content_type: str = "") -> None:
        with open(self._path(key), "wb") as fh:
            fh.write(content)

    def get(self, key: str) -> bytes:
        path = os.path.join(self.root, key.replace("/", os.sep))
        if not os.path.exists(path):
            raise FileNotFoundError(key)
        with open(path, "rb") as fh:
            return fh.read()

    def delete(self, key: str) -> None:
        path = os.path.join(self.root, key.replace("/", os.sep))
        if os.path.exists(path):
            os.remove(path)

    def exists(self, key: str) -> bool:
        return os.path.exists(os.path.join(self.root, key.replace("/", os.sep)))


class S3Storage:
    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            config=BotoConfig(signature_version="s3v4"),
        )
        self.bucket = settings.S3_BUCKET

    def ensure_bucket(self):
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except Exception:
                pass

    def put(self, key: str, content: bytes, content_type: str = "application/octet-stream"):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str):
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False


def _compute_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class StorageService:
    """Facade over the active backend."""

    def __init__(self):
        self.backend = LocalStorage(settings.LOCAL_STORAGE_DIR)
        self.mode = "local"

        # Prefer S3 when explicitly configured and reachable.
        if _BOTO_AVAILABLE and settings.S3_ENDPOINT:
            try:
                candidate = S3Storage()
                candidate.ensure_bucket()
                self.backend = candidate
                self.mode = "s3"
            except Exception:
                self.mode = "local"

    # ── uploads ───────────────────────────────────────────────────────────────
    async def upload_file(self, file: UploadFile, project_id: uuid.UUID) -> tuple[str, str]:
        content = await file.read()
        sha256 = _compute_hash(content)
        ext = os.path.splitext(file.filename or "")[1].lower()
        key = f"projects/{project_id}/files/{uuid.uuid4()}{ext}"
        self.backend.put(key, content, file.content_type or "application/octet-stream")
        return key, sha256

    def upload_bytes(self, content: bytes, key: str, content_type: str = "application/octet-stream") -> str:
        self.backend.put(key, content, content_type)
        return key

    def upload_generated_document(self, content: bytes, project_id: uuid.UUID, fmt: str, template_version: str) -> str:
        key = f"projects/{project_id}/outputs/{uuid.uuid4()}.{fmt}"
        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if fmt == "docx" else "application/pdf"
        )
        self.backend.put(key, content, content_type)
        return key

    # ── reads ─────────────────────────────────────────────────────────────────
    def download_file(self, storage_key: str) -> bytes:
        return self.backend.get(storage_key)

    def delete_file(self, storage_key: str) -> None:
        self.backend.delete(storage_key)

    def file_exists(self, storage_key: str) -> bool:
        return self.backend.exists(storage_key)

    def local_path(self, storage_key: str) -> str | None:
        """Absolute local path when the local backend is active."""
        if isinstance(self.backend, LocalStorage):
            return os.path.join(self.backend.root, storage_key.replace("/", os.sep))
        return None


_storage_service: StorageService | None = None


def get_storage() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
