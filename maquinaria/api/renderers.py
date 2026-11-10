from rest_framework.renderers import BaseRenderer, JSONRenderer


class PNGPrivadoRenderer(BaseRenderer):
    media_type = "image/png"
    format = "png"
    charset = None
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        # La imagen correcta se entrega como FileResponse, sin pasar por
        # este render. Los errores deben seguir siendo JSON, aun si el
        # cliente pidió image/png: no se convierten dicts en imágenes rotas.
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        respuesta = (renderer_context or {}).get("response")
        if respuesta is not None:
            respuesta["Content-Type"] = "application/json"
        return JSONRenderer().render(data, renderer_context=renderer_context)
