"""Repositorio de alumnos: único dueño del archivo JSON."""

import json
import os
import tempfile
import threading
import unicodedata
from pathlib import Path

ID_PREFIX = "STU-"
ID_DIGITS = 4


def normalize(text):
    """Normaliza un texto para comparar sin mayúsculas ni tildes.

    :param text: Texto original
    :type text: str
    :return: Texto en minúsculas (casefold) y sin marcas diacríticas
    :rtype: str
    """
    decomposed = unicodedata.normalize("NFKD", str(text).casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def format_id(number):
    """Arma un id de alumno con cuatro dígitos.

    :param number: Número consecutivo
    :type number: int
    :return: Id con forma ``STU-0001``
    :rtype: str
    """
    return f"{ID_PREFIX}{number:0{ID_DIGITS}d}"


def _id_number(student_id):
    """Extrae el número de un id de alumno.

    :param student_id: Id con forma ``STU-0001``
    :type student_id: str
    :return: Número del id, o 0 si no tiene la forma esperada
    :rtype: int
    """
    text = str(student_id)
    if not text.startswith(ID_PREFIX):
        return 0
    digits = text[len(ID_PREFIX):]
    return int(digits) if digits.isdigit() else 0


class StudentRepository:
    """Lee y escribe los alumnos en un archivo JSON, sin guardar estado.

    Lee el archivo en cada llamada y escribe de forma atómica (archivo temporal
    en la misma carpeta y ``os.replace``). Un candado evita ids repetidos.

    :param path: Ruta del archivo JSON de alumnos
    :type path: str or pathlib.Path
    """

    def __init__(self, path):
        self._path = Path(path)
        self._lock = threading.Lock()

    @property
    def path(self):
        """Ruta del archivo de alumnos.

        :return: Ruta del archivo
        :rtype: pathlib.Path
        """
        return self._path

    def _read(self):
        """Lee todos los alumnos del archivo.

        :return: Alumnos guardados; lista vacía si el archivo no existe
        :rtype: list[dict]
        """
        try:
            with self._path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return []
        return list(data) if isinstance(data, list) else []

    def _write(self, students):
        """Escribe los alumnos de forma atómica.

        :param students: Alumnos a guardar
        :type students: list[dict]
        :raises OSError: Si la escritura falla; el archivo original queda intacto
        """
        folder = self._path.parent
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.", suffix=".tmp", dir=folder
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(students, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self._path)
        except BaseException:
            if os.path.exists(temp_name):
                os.remove(temp_name)
            raise

    def list_all(self):
        """Devuelve todos los alumnos en orden de id.

        :return: Alumnos ordenados por id
        :rtype: list[dict]
        """
        return sorted(self._read(), key=lambda student: _id_number(student["id"]))

    def get(self, student_id):
        """Busca un alumno por id.

        :param student_id: Id del alumno, por ejemplo ``STU-0003``
        :type student_id: str
        :return: El alumno, o ``None`` si no existe
        :rtype: dict or None
        """
        wanted = str(student_id).strip().upper()
        for student in self._read():
            if str(student.get("id", "")).upper() == wanted:
                return student
        return None

    def find_by_classroom(self, classroom):
        """Devuelve los alumnos de un salón.

        :param classroom: Número de salón
        :type classroom: int
        :return: Alumnos del salón, en orden de id
        :rtype: list[dict]
        """
        return [s for s in self.list_all() if s.get("classroom") == classroom]

    def find_by_subject(self, subject):
        """Devuelve los alumnos de una materia, sin distinguir mayúsculas ni tildes.

        :param subject: Nombre de la materia
        :type subject: str
        :return: Alumnos de la materia, en orden de id
        :rtype: list[dict]
        """
        wanted = normalize(subject).strip()
        return [
            s for s in self.list_all() if normalize(s.get("subject", "")) == wanted
        ]

    def subjects(self):
        """Devuelve las materias distintas que existen en los datos.

        :return: Materias tal como están guardadas, sin repetir
        :rtype: list[str]
        """
        seen = {}
        for student in self.list_all():
            subject = student.get("subject", "")
            seen.setdefault(normalize(subject), subject)
        return list(seen.values())

    def add(self, data):
        """Registra un alumno nuevo con el id siguiente al mayor.

        Crea el archivo si no existe.

        :param data: Campos ``name``, ``subject``, ``grade`` y ``classroom``
        :type data: dict
        :return: El alumno guardado, con su ``id``
        :rtype: dict
        :raises OSError: Si no se puede escribir el archivo
        """
        with self._lock:
            students = self._read()
            highest = max((_id_number(s.get("id", "")) for s in students), default=0)
            student = {
                "id": format_id(highest + 1),
                "name": str(data["name"]).strip(),
                "subject": str(data["subject"]).strip(),
                "grade": data["grade"],
                "classroom": data["classroom"],
            }
            students.append(student)
            self._write(students)
            return student
