"""
Object storage module for ff-storage.
Provides abstract interface and implementations for object/blob storage.
"""

from .azure_blob import AzureBlobObjectStorage
from .base import ObjectStorage
from .local import LocalObjectStorage
from .s3 import S3ObjectStorage

__all__ = [
    "ObjectStorage",
    "LocalObjectStorage",
    "S3ObjectStorage",
    "AzureBlobObjectStorage",
]
