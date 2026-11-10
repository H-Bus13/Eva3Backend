(() => {
  const visor = document.getElementById("visor-firma");
  if (!visor || !window.bootstrap?.Modal) return;
  const imagen = document.getElementById("imagen-visor-firma");
  const estado = document.getElementById("estado-visor-firma");
  const modal = bootstrap.Modal.getOrCreateInstance(visor, {backdrop: true, keyboard: true});
  let origen = null;

  document.addEventListener("click", (evento) => {
    const enlace = evento.target.closest("a[data-firma-preview]");
    if (!enlace || evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey || evento.button !== 0) return;
    evento.preventDefault();
    origen = enlace;
    imagen.hidden = true;
    estado.hidden = false;
    estado.textContent = "Cargando firma…";
    // Se usa la misma ruta privada, con sus permisos y cookies de sesión.
    // La firma no se copia a una ruta pública ni a almacenamiento local.
    imagen.onload = () => {
      imagen.hidden = false;
      estado.hidden = true;
    };
    imagen.onerror = () => {
      imagen.hidden = true;
      estado.hidden = false;
      estado.textContent = "No se pudo cargar la firma. Actualiza la página o vuelve a ingresar.";
    };
    modal.show();
    imagen.src = enlace.href;
  });

  visor.addEventListener("hidden.bs.modal", () => {
    // Se retira la imagen al cerrar y se devuelve el foco al enlace usado.
    imagen.onload = null;
    imagen.onerror = null;
    imagen.removeAttribute("src");
    imagen.hidden = true;
    origen?.focus({preventScroll: true});
    origen = null;
  });
})();
