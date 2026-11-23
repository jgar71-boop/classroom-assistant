"""Pruebas del modelo simulado."""

import json

from app.llm import FakeModel
from app.repository import StudentRepository


def test_student_id_wins_over_classroom_and_subject(sample_path):
    model = FakeModel(StudentRepository(sample_path))
    question = "¿STU-0003 está en el salón 101 de historia?"

    completion = model.complete([{"role": "user", "content": question}])

    assert json.loads(completion.text) == {
        "tool": "get_student",
        "args": {"student_id": "STU-0003"},
    }
