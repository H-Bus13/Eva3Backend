// Se comprueba cada formulario por separado para enfocar el motivo
// correspondiente. Aprobar no requiere completar las observaciones.
document.querySelectorAll(".form-revision").forEach((formulario) => {
  formulario.addEventListener("submit", (evento) => {
    const accion = evento.submitter?.value;
    const motivo = formulario.querySelector('[name="motivo"]');

    if (accion === "rechazar" && !motivo.value.trim()) {
      evento.preventDefault();
      alert("Debes indicar el motivo del rechazo.");
      motivo.focus();
    }
  });
});
