"""Revoca sesiones de trabajador cuando cambia su NIP o se desactiva su cuenta.

No guarda el NIP ni su hash de contraseña en la sesión. La marca HMAC
cambia cada vez que cambia pin_hash (también cuando se restablece el NIP).
"""
from django.shortcuts import redirect
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import EmployeeCredential

SESSION_KEY = "worker_pin_version"


def pin_session_version(pin_hash):
    if not pin_hash:
        return ""
    return salted_hmac(
        "stockroom.worker-session-pin-version.v1", pin_hash, algorithm="sha256"
    ).hexdigest()


class WorkerPinSessionMiddleware:
    """Valida cada sesión identificada como trabajador antes de procesar la vista.

    Se coloca después de SessionMiddleware; funciona con el backend de sesiones
    configurado en Django y no exige un cambio en la base de datos.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        employee_id = request.session.get("worker_employee_id")
        credential_id = request.session.get("worker_credential_id")

        # No se ejecuta para sesiones administrativas ni identificación inicial.
        if employee_id is None and credential_id is None:
            return self.get_response(request)

        # La pantalla de acceso siempre debe permitir iniciar desde cero.
        # acceso_empleado ya limpia los identificadores de sesión anteriores.
        if request.path.rstrip("/") == "/trabajadores/acceso":
            return self.get_response(request)

        credential = None
        if employee_id and credential_id:
            credential = EmployeeCredential.objects.filter(
                pk=credential_id,
                employee_id=employee_id,
                is_active=True,
                employee__is_active=True,
            ).only("pin_hash").first()

        expected = pin_session_version(credential.pin_hash) if credential else ""
        supplied = request.session.get(SESSION_KEY, "")

        if not expected or not supplied or not constant_time_compare(expected, supplied):
            request.session.flush()
            if request.path.startswith("/trabajadores/"):
                return redirect("acceso_empleado")

        return self.get_response(request)
