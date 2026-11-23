"""Pasos de los escenarios del registro de alumnos (``features/students.feature``)."""

import json

from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/students.feature")

VALID_STUDENT = {
    "name": "Ana Pérez",
    "subject": "Música",
    "grade": 4,
    "classroom": 120,
}


@given("the registry file does not exist yet", target_fixture="client")
def registry_without_file(students_path, make_client):
    """Cliente sobre una ruta cuyo archivo todavía no existe."""
    assert not students_path.exists()
    return make_client(students_path)


@when(
    parsers.parse("I register a student whose {field} is {value}"),
    target_fixture="response",
)
def register_invalid_student(client, field, value):
    """Registra un alumno válido salvo un campo, que falta o lleva ``value`` (JSON)."""
    payload = dict(VALID_STUDENT)
    if value == "missing":
        del payload[field]
    else:
        payload[field] = json.loads(value)
    return client.post("/students", json=payload)


@when(
    parsers.parse(
        'I list the students of classroom {classroom:d} studying "{subject}"'
    ),
    target_fixture="response",
)
def list_filtered_students(client, classroom, subject):
    """Lista los alumnos con los dos filtros combinados."""
    return client.get(
        "/students", params={"classroom": classroom, "subject": subject}
    )


@when(parsers.parse('I look up the student "{student_id}"'), target_fixture="response")
def look_up_student(client, student_id):
    """Pide un alumno por su id."""
    return client.get(f"/students/{student_id}")


@when(parsers.parse('someone adds the student "{student_id}" directly to the file'))
def add_student_by_hand(students_path, student_id):
    """Edita el archivo sin pasar por la API, como lo haría una persona."""
    students = json.loads(students_path.read_text(encoding="utf-8"))
    students.append({"id": student_id, **VALID_STUDENT})
    students_path.write_text(json.dumps(students), encoding="utf-8")


@then(
    parsers.parse(
        'the saved student has id "{student_id}", name "{name}" '
        'and subject "{subject}"'
    )
)
def saved_student_is(response, student_id, name, subject):
    """Comprueba el alumno devuelto, ya sin espacios en los extremos."""
    body = response.json()
    assert body["id"] == student_id
    assert body["name"] == name
    assert body["subject"] == subject


@then(parsers.parse('the student list is sorted by id and ends with "{student_id}"'))
def list_ends_with(client, student_id):
    """Comprueba el orden de la lista y que el alumno nuevo aparece al final."""
    ids = [student["id"] for student in client.get("/students").json()]
    assert ids == sorted(ids)
    assert ids[-1] == student_id


@then("the registry file exists")
def registry_file_exists(students_path):
    """Comprueba que el primer alta creó el archivo."""
    assert students_path.exists()


@then(parsers.parse("the registry still has {count:d} students"))
def registry_has(client, count):
    """Comprueba que un alta rechazada no guardó nada."""
    assert len(client.get("/students").json()) == count


@then(parsers.parse('the listed ids are "{ids}"'))
def listed_ids_are(response, ids):
    """Comprueba exactamente qué alumnos devolvió la lista."""
    expected = [student_id.strip() for student_id in ids.split(",")]
    assert [student["id"] for student in response.json()] == expected


@then(parsers.parse('the error detail is "{detail}"'))
def error_detail_is(response, detail):
    """Comprueba el mensaje de error de la API."""
    assert response.json() == {"detail": detail}
