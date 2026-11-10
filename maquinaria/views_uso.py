from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .servicios_uso import estado_uso, iniciar_trabajo, pausar_trabajo
from .consultas_arriendos import consulta_arriendos


@login_required
@never_cache
@require_POST
def sincronizar_uso(request, pk):
    get_object_or_404(consulta_arriendos(request.user), pk=pk)
    try:
        datos = estado_uso(arriendo_id=pk, usuario=request.user, sincronizar=True)
    except ValidationError as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=400)
    return JsonResponse(datos)


@login_required
@require_POST
def operar_uso(request, pk, accion):
    from django.http import Http404
    get_object_or_404(consulta_arriendos(request.user), pk=pk)
    opciones = {"iniciar": iniciar_trabajo, "pausar": pausar_trabajo}
    if accion not in opciones:
        raise Http404
    try:
        opciones[accion](arriendo_id=pk, usuario=request.user)
    except ValidationError as error:
        for mensaje in error.messages:
            messages.error(request, mensaje)
    else:
        messages.success(request, "Trabajo iniciado." if accion == "iniciar" else "Sesión de trabajo detenida y horas guardadas.")
    return redirect("detalle_arriendo", pk=pk)

