import uuid

import boto3
from botocore.config import Config

from app.config import settings

_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )
    return _s3_client


def build_r2_key(course_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> str:
    return f"courses/{course_id}/documents/{document_id}/{filename}"


def upload_file(r2_key: str, file_data: bytes, content_type: str) -> None:
    client = get_s3_client()
    client.put_object(
        Bucket=settings.r2_bucket_name,
        Key=r2_key,
        Body=file_data,
        ContentType=content_type,
    )


def download_file(r2_key: str) -> bytes:
    client = get_s3_client()
    response = client.get_object(Bucket=settings.r2_bucket_name, Key=r2_key)
    return response["Body"].read()


def delete_file(r2_key: str) -> None:
    client = get_s3_client()
    client.delete_object(Bucket=settings.r2_bucket_name, Key=r2_key)


def generate_presigned_url(r2_key: str, expiration: int = 3600) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": r2_key},
        ExpiresIn=expiration,
    )
