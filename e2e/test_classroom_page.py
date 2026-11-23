"""Pruebas de punta a punta de la página del Classroom Assistant.

Usan el navegador como una persona: escriben la clave, llenan el formulario,
filtran la lista y conversan con el asistente (modelo simulado). Cada prueba
registra sus propios alumnos con nombres únicos, así no dependen de los datos
iniciales. La clave se lee de la variable E2E_API_KEY, que pone la
verificación; nunca va escrita aquí.
"""

import os
import re
import uuid

from playwright.sync_api import Page, expect

# Palabras que delatan un mensaje de error en español.
SPANISH_ERROR = re.compile(
    r"(revisa|datos|campo|grado|inválid|vacía|pregunta|error|intenta)",
    re.IGNORECASE,
)
# Mensajes en inglés que no deben llegar a la persona.
ENGLISH_ERROR = re.compile(
    r"(field required|input should|value error|unprocessable|not found)",
    re.IGNORECASE,
)
REQUEST_ID = re.compile(r"request_id: (?!desconocido)\S+")
INVALID_KEY_MESSAGE = "Clave inválida"
# Una clave que ningún cliente tiene: no es un secreto.
WRONG_API_KEY = "not-a-valid-key-0000"


def unique_name(prefix: str) -> str:
    """Devuelve un nombre de alumno que no choca con otras pruebas.

    :param prefix: Inicio del nombre
    :type prefix: str
    :return: Nombre con un sufijo aleatorio
    :rtype: str
    """
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def enter_api_key(page: Page, api_key: str) -> None:
    """Escribe la clave en su campo, como lo haría una persona.

    :param page: Página abierta en el producto
    :type page: Page
    :param api_key: Clave que se escribe
    :type api_key: str
    """
    page.get_by_test_id("api-key").fill(api_key)


def open_with_valid_key(page: Page) -> None:
    """Abre la página y escribe la clave válida de la verificación.

    :param page: Página del navegador
    :type page: Page
    """
    page.goto("/")
    enter_api_key(page, os.environ["E2E_API_KEY"])


def register_student(
    page: Page, name: str, grade: str, classroom: str
) -> None:
    """Llena el formulario de registro y lo envía.

    :param page: Página abierta en el producto
    :type page: Page
    :param name: Nombre del alumno
    :type name: str
    :param grade: Grado, tal como lo escribiría una persona
    :type grade: str
    :param classroom: Número de salón
    :type classroom: str
    """
    page.get_by_test_id("name").fill(name)
    page.get_by_test_id("subject").fill("Ciencias")
    page.get_by_test_id("grade").fill(grade)
    page.get_by_test_id("classroom").fill(classroom)
    page.get_by_test_id("save").click()


def ask(page: Page, question: str) -> None:
    """Escribe una pregunta al asistente y la envía.

    :param page: Página abierta en el producto
    :type page: Page
    :param question: Texto de la pregunta
    :type question: str
    """
    page.get_by_test_id("question").fill(question)
    page.get_by_test_id("send").click()


def test_registered_student_appears_in_the_list(page: Page) -> None:
    """Registrar un alumno con el formulario lo muestra en la lista."""
    open_with_valid_key(page)
    name = unique_name("Ana Registro")

    register_student(page, name, grade="4", classroom="921")

    students = page.get_by_test_id("students")
    expect(students).to_contain_text(name)
    expect(page.get_by_test_id("form-error")).to_be_empty()


def test_invalid_grade_shows_an_error_in_spanish(page: Page) -> None:
    """Un grado fuera de rango muestra un error en español y no registra."""
    open_with_valid_key(page)
    name = unique_name("Grado Invalido")

    register_student(page, name, grade="13", classroom="922")

    form_error = page.get_by_test_id("form-error")
    expect(form_error).to_have_text(SPANISH_ERROR)
    expect(form_error).not_to_have_text(ENGLISH_ERROR)
    expect(form_error).not_to_contain_text(INVALID_KEY_MESSAGE)
    expect(page.get_by_test_id("students")).not_to_contain_text(name)


def test_classroom_filter_shows_only_that_classroom(page: Page) -> None:
    """Filtrar por salón deja en la lista solo a los alumnos de ese salón."""
    open_with_valid_key(page)
    inside = unique_name("Dentro Filtro")
    outside = unique_name("Fuera Filtro")
    students = page.get_by_test_id("students")
    register_student(page, inside, grade="2", classroom="931")
    expect(students).to_contain_text(inside)
    register_student(page, outside, grade="2", classroom="932")
    expect(students).to_contain_text(outside)

    page.get_by_test_id("classroom-filter").fill("931")

    expect(students).not_to_contain_text(outside)
    expect(students).to_contain_text(inside)
    classroom_cells = students.locator("tr td:nth-child(5)")
    expect(classroom_cells).to_have_text(["931"])


def test_answers_show_request_id_and_keep_the_conversation(page: Page) -> None:
    """Cada respuesta muestra su request_id y la conversación queda en pantalla."""
    open_with_valid_key(page)
    first_question = "¿Quiénes están en el salón 101?"
    second_question = "¿Qué materia lleva Valeria Torres?"
    messages = page.get_by_test_id("message")
    answer_request_ids = page.get_by_test_id("answer").get_by_test_id(
        "request-id"
    )

    ask(page, first_question)

    expect(messages).to_have_count(2)
    expect(messages.first).to_contain_text(first_question)
    expect(messages.last).not_to_be_empty()
    expect(answer_request_ids).to_have_text([REQUEST_ID])
    expect(page.get_by_test_id("ask-error")).to_be_empty()

    ask(page, second_question)

    expect(messages).to_have_count(4)
    expect(messages.nth(0)).to_contain_text(first_question)
    expect(messages.nth(2)).to_contain_text(second_question)
    expect(answer_request_ids).to_have_text([REQUEST_ID, REQUEST_ID])


def test_empty_question_shows_an_error_in_spanish(page: Page) -> None:
    """Enviar una pregunta vacía muestra un error en español."""
    open_with_valid_key(page)

    ask(page, "")

    ask_error = page.get_by_test_id("ask-error")
    expect(ask_error).to_have_text(SPANISH_ERROR)
    expect(ask_error).not_to_have_text(ENGLISH_ERROR)
    expect(ask_error).not_to_contain_text(INVALID_KEY_MESSAGE)
    expect(page.get_by_test_id("message")).to_have_count(0)


def test_wrong_api_key_shows_invalid_key_message(page: Page) -> None:
    """Con una clave equivocada la página muestra «Clave inválida»."""
    page.goto("/")
    api_key = page.get_by_test_id("api-key")
    expect(api_key).to_have_attribute("type", "password")
    enter_api_key(page, WRONG_API_KEY)

    ask(page, "¿Quiénes están en el salón 101?")

    expect(page.get_by_test_id("ask-error")).to_contain_text(INVALID_KEY_MESSAGE)
    expect(page.get_by_test_id("message")).to_have_count(0)
