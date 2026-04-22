"""Tests de backup/restore/list contra S3 mockeado con moto (AR.2)."""

from __future__ import annotations

import gzip
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from moto import mock_aws

from modules.db import (
    S3Config,
    backup_to_s3,
    list_backups,
    restore_from_s3,
)

_BUCKET = "scanner-test-bucket"


def _write_sample_db(path: Path) -> None:
    """Crea un SQLite mínimo con 1 tabla y 1 fila."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t(id INTEGER, v TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'hello')")
    conn.commit()
    conn.close()


def _s3_config() -> S3Config:
    return S3Config(
        endpoint_url=None,  # moto atrapa el default
        bucket=_BUCKET,
        access_key_id="testing",
        secret_access_key="testing",
        region="us-east-1",
        key_prefix="scanner-backups/",
    )


@pytest.fixture
def mock_s3():
    """Moto bucket lifecycle — crear al arrancar, teardown auto."""
    import boto3

    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket=_BUCKET,
        )
        yield


class TestBackup:
    @pytest.mark.asyncio
    async def test_uploads_compressed_snapshot(
        self, tmp_path: Path, mock_s3,
    ) -> None:
        db_path = tmp_path / "scanner.db"
        _write_sample_db(db_path)

        when = datetime(2026, 4, 22, 10, 30, 0)
        result = await backup_to_s3(db_path, _s3_config(), when=when)

        assert result["bucket"] == _BUCKET
        assert result["key"] == "scanner-backups/scanner-20260422-103000.db.gz"
        assert result["size_bytes_gz"] < result["size_bytes_raw"]
        assert result["timestamp"] == "2026-04-22T10:30:00Z"

        # Verificar que el objeto existe en el bucket y es gz-decodificable
        import boto3
        client = boto3.client("s3", region_name="us-east-1")
        obj = client.get_object(Bucket=_BUCKET, Key=result["key"])
        raw = gzip.decompress(obj["Body"].read())
        # Primeros bytes del snapshot SQLite empiezan con el header estándar
        assert raw.startswith(b"SQLite format 3\x00")

    @pytest.mark.asyncio
    async def test_missing_db_raises(self, tmp_path: Path, mock_s3) -> None:
        with pytest.raises(FileNotFoundError):
            await backup_to_s3(tmp_path / "ghost.db", _s3_config())

    @pytest.mark.asyncio
    async def test_custom_key_prefix(
        self, tmp_path: Path, mock_s3,
    ) -> None:
        """El key_prefix del config se respeta en la key final."""
        db_path = tmp_path / "scanner.db"
        _write_sample_db(db_path)

        cfg = S3Config(
            bucket=_BUCKET,
            access_key_id="testing",
            secret_access_key="testing",
            key_prefix="production/",
        )
        result = await backup_to_s3(db_path, cfg)
        assert result["key"].startswith("production/scanner-")


class TestRestore:
    @pytest.mark.asyncio
    async def test_downloads_to_sibling_file(
        self, tmp_path: Path, mock_s3,
    ) -> None:
        db_path = tmp_path / "scanner.db"
        _write_sample_db(db_path)

        # Primero subo un backup
        upload = await backup_to_s3(db_path, _s3_config())
        # Modifico la DB operativa — el restore NO debería tocarla
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO t VALUES (2, 'modified')")
        conn.commit()
        conn.close()

        # Restore
        when = datetime(2026, 4, 22, 11, 0, 0)
        result = await restore_from_s3(
            db_path, _s3_config(), upload["key"], when=when,
        )

        assert result["bucket"] == _BUCKET
        assert result["key"] == upload["key"]
        restored_path = Path(result["restored_path"])
        import asyncio as _asyncio
        assert await _asyncio.to_thread(restored_path.is_file)
        assert restored_path.name == "scanner.db.restored-20260422-110000.db"

        # La DB operativa sigue teniendo la fila nueva (no fue pisada)
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT COUNT(*) FROM t").fetchone()
        conn.close()
        assert rows[0] == 2

        # La DB restaurada tiene solo la fila original
        conn = sqlite3.connect(restored_path)
        rows = conn.execute("SELECT COUNT(*) FROM t").fetchone()
        conn.close()
        assert rows[0] == 1

    @pytest.mark.asyncio
    async def test_restore_missing_key_raises(
        self, tmp_path: Path, mock_s3,
    ) -> None:
        from botocore.exceptions import ClientError

        db_path = tmp_path / "scanner.db"
        _write_sample_db(db_path)
        with pytest.raises(ClientError):
            await restore_from_s3(
                db_path, _s3_config(), "scanner-backups/ghost.db.gz",
            )


class TestListBackups:
    @pytest.mark.asyncio
    async def test_empty_bucket(self, mock_s3) -> None:
        objects = await list_backups(_s3_config())
        assert objects == []

    @pytest.mark.asyncio
    async def test_returns_sorted_by_key_desc(
        self, tmp_path: Path, mock_s3,
    ) -> None:
        """Orden desc por key — el naming YYYYMMDD-HHMMSS coincide con
        el orden cronológico del snapshot."""
        db_path = tmp_path / "scanner.db"
        _write_sample_db(db_path)
        for i in range(3):
            await backup_to_s3(
                db_path, _s3_config(),
                when=datetime(2026, 4, 20 + i, 10, 0, 0),
            )
        objects = await list_backups(_s3_config())
        assert len(objects) == 3
        assert "20260422" in objects[0]["key"]
        assert "20260421" in objects[1]["key"]
        assert "20260420" in objects[2]["key"]
        # Shape
        for obj in objects:
            assert set(obj.keys()) == {"key", "size_bytes", "last_modified"}

    @pytest.mark.asyncio
    async def test_prefix_filter_applied(
        self, tmp_path: Path, mock_s3,
    ) -> None:
        """Otros objetos del bucket con prefix distinto se omiten."""
        import boto3

        db_path = tmp_path / "scanner.db"
        _write_sample_db(db_path)
        await backup_to_s3(db_path, _s3_config())

        # Pongo una basura en otra ruta
        client = boto3.client("s3", region_name="us-east-1")
        client.put_object(
            Bucket=_BUCKET, Key="other/junk.txt", Body=b"junk",
        )

        objects = await list_backups(_s3_config())
        assert len(objects) == 1
        assert objects[0]["key"].startswith("scanner-backups/")


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_backup_then_restore_preserves_data(
        self, tmp_path: Path, mock_s3,
    ) -> None:
        """Backup → upload → download → decompress debe reproducir la DB."""
        db_path = tmp_path / "scanner.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t(id INTEGER, v TEXT)")
        for i in range(10):
            conn.execute("INSERT INTO t VALUES (?, ?)", (i, f"row-{i}"))
        conn.commit()
        conn.close()

        upload = await backup_to_s3(db_path, _s3_config())
        result = await restore_from_s3(db_path, _s3_config(), upload["key"])

        conn = sqlite3.connect(result["restored_path"])
        rows = conn.execute("SELECT id, v FROM t ORDER BY id").fetchall()
        conn.close()
        assert rows == [(i, f"row-{i}") for i in range(10)]
