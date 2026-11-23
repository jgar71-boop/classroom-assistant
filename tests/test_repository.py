"""Pruebas del repositorio: escritura atómica y altas simultáneas."""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.repository import StudentRepository


def new_student(number):
    """Datos válidos de un alumno nuevo.

    :param number: Número para distinguir el nombre
    :type number: int
    :return: Campos del alumno sin ``id``
    :rtype: dict
    """
    return {
        "name": f"Alumno {number}",
        "subject": "Música",
        "grade": 4,
        "classroom": 120,
    }


def test_failed_write_keeps_the_original_file_and_no_temporary_files(
    sample_path, monkeypatch
):
    original = sample_path.read_text(encoding="utf-8")
    repository = StudentRepository(sample_path)

    def broken_replace(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError):
        repository.add(new_student(1))

    assert sample_path.read_text(encoding="utf-8") == original
    assert [path.name for path in sample_path.parent.iterdir()] == ["students.json"]


def test_concurrent_registrations_never_share_an_id(sample_path):
    repository = StudentRepository(sample_path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        saved = list(pool.map(lambda n: repository.add(new_student(n)), range(20)))

    ids = [student["id"] for student in saved]
    assert len(set(ids)) == 20
    assert max(ids) == "STU-0030"
    assert len(repository.list_all()) == 30
