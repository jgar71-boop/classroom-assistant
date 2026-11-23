"""Reglas de compliance que se revisan solas al arrancar en producción (fase 4).

Con ``ENVIRONMENT=production`` el producto se niega a arrancar si alguna regla
falla. El error nombra cada regla, nunca un valor secreto.
"""

PRODUCTION = "production"
FAKE_PROVIDER = "fake"
MIN_KEY_LENGTH = 16


def production_violations(settings):
    """Reglas de producción que la configuración no cumple.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :return: Una descripción por regla que falla, sin valores secretos
    :rtype: list[str]
    """
    violations = []
    if settings.model_provider == FAKE_PROVIDER:
        violations.append("MODEL_PROVIDER must not be fake in production")
    api_keys = settings.security.api_keys
    if len(api_keys) == 0:
        violations.append("API_KEYS must not be empty in production")
    for number, length in enumerate(api_keys.key_lengths(), start=1):
        if length < MIN_KEY_LENGTH:
            violations.append(
                f"API_KEYS entry {number} is too short (length {length}, "
                f"minimum {MIN_KEY_LENGTH})"
            )
    # Se mira LANGSMITH_TRACING y no solo la clave: la clave se puede agregar
    # después en Render y encender trazas sin ocultar entradas ni salidas.
    if settings.langsmith_tracing and not (
        settings.hide_inputs and settings.hide_outputs
    ):
        violations.append(
            "HIDE_INPUTS and HIDE_OUTPUTS must be true when tracing in production"
        )
    return violations


def check_production(settings):
    """Impide arrancar en producción si alguna regla de compliance falla.

    En ``development`` no se aplica ninguna regla.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :raises ValueError: Con todas las reglas que fallan en un solo mensaje
    """
    if settings.security.environment != PRODUCTION:
        return
    violations = production_violations(settings)
    if violations:
        raise ValueError(
            "production compliance failed: " + "; ".join(violations)
        )
