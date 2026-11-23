# 0001. API sin estado con un repositorio de archivo JSON atómico

Estado: propuesto

## Contexto

La especificación pide que la API no guarde nada en memoria entre peticiones y que los alumnos vivan en
`STUDENTS_PATH`. Dos altas simultáneas no deben recibir el mismo `id` y un corte a mitad de escritura no debe
dejar el archivo roto.

## Decisión

- `StudentRepository` es el único que toca el archivo: lo lee completo en cada operación y no cachea nada.
- Escribe a un temporal en la misma carpeta y lo publica con `os.replace`; si falla, borra el temporal.
- El cálculo del siguiente `id` (mayor existente + 1, formato `STU-NNNN`) y la escritura ocurren dentro de
  un mismo `threading.Lock` de la instancia.
- El historial de chat lo guarda y lo envía el navegador; la API no lo conserva.
- El servidor corre con un solo proceso worker.

## Consecuencias

- Cualquier proceso ve los cambios hechos al archivo en la siguiente petición; reiniciar no pierde datos.
- Leer el archivo entero en cada operación es aceptable para el tamaño de una escuela, no para miles de
  registros.
- El candado no protege entre procesos: con varios workers habría que cambiar a un candado de archivo o a una
  base de datos (nuevo ADR).
