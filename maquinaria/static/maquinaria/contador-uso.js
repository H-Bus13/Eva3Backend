(() => {
  const panel = document.getElementById("contador-uso");
  const inicial = document.getElementById("estado-uso-inicial");
  if (!panel || !inicial) return;
  let estado = JSON.parse(inicial.textContent);
  let sincronizadoEn = performance.now();
  let conectado = true;
  let consultando = false;
  const error = document.getElementById("error-contador");
  const inicio = document.getElementById("iniciar-uso");
  const pausa = document.getElementById("pausar-uso");
  const formato = (valor) => {
    const segundos = Math.max(0, Math.floor(valor));
    const horas = Math.floor(segundos / 3600);
    return [horas, Math.floor(segundos / 60) % 60, segundos % 60]
      .map((n) => String(n).padStart(2, "0")).join(":");
  };
  function dibujar() {
    // Esta animación no escribe horas. performance.now evita depender de
    // cambios del reloj del equipo; el servidor confirma todos los valores.
    const incremento = conectado && estado.sesion_activa ? (performance.now() - sincronizadoEn) / 1000 : 0;
    document.getElementById("tiempo-sesion").textContent = formato(estado.segundos_sesion + incremento);
    document.getElementById("tiempo-arriendo").textContent = formato(estado.segundos_arriendo + incremento);
    document.getElementById("tiempo-total").textContent = formato(estado.segundos_totales + incremento);
    document.getElementById("estado-contador").textContent = conectado
      ? (estado.sesion_activa ? "Sesión en marcha" : "Sin sesión en marcha")
      : "Sin conexión confirmada. Los tiempos volverán a sincronizarse al recuperar acceso.";
    inicio.hidden = !conectado || !estado.puede_iniciar;
    pausa.hidden = !estado.puede_pausar;
    document.getElementById("aviso-mantencion").hidden = !estado.revision_pendiente;
  }
  async function sincronizar() {
    if (consultando) return;
    consultando = true;
    try {
      const respuesta = await fetch(panel.dataset.estadoUrl, {
        method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error",
        headers: { "X-CSRFToken": panel.querySelector('[name="csrfmiddlewaretoken"]').value },
      });
      if (!respuesta.ok) throw new Error("No se pudo actualizar el contador. Revisa tu conexión o vuelve a ingresar.");
      estado = await respuesta.json();
      sincronizadoEn = performance.now();
      conectado = true;
      error.textContent = "";
    } catch (fallo) {
      // Conserva la última estimación visible al perder conexión, para que
      // el número no retroceda al valor de la consulta anterior.
      if (conectado && estado.sesion_activa) {
        const transcurrido = (performance.now() - sincronizadoEn) / 1000;
        estado.segundos_sesion += transcurrido;
        estado.segundos_arriendo += transcurrido;
        estado.segundos_totales += transcurrido;
        sincronizadoEn = performance.now();
      }
      conectado = false;
      error.textContent = "No se pudo confirmar el tiempo con el servidor. El trabajo no se detiene al perder conexión.";
    } finally {
      consultando = false;
      dibujar();
    }
  }
  // Los botones envían formularios con CSRF. Solo se deshabilita el botón
  // pulsado para evitar dobles clics; el servidor protege también el guardado.
  [inicio, pausa].forEach((form) => form.addEventListener("submit", () => {
    form.querySelector("button").disabled = true;
  }));
  dibujar();
  sincronizar();
  setInterval(dibujar, 1000);
  setInterval(sincronizar, 15000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) sincronizar(); });
  window.addEventListener("online", sincronizar);
})();

