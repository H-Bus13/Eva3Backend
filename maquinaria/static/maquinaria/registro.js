(() => {
  // Los errores vienen de Django, incluidos los envíos sin JavaScript.
  // El resumen recibe el foco para que el motivo sea visible y accesible.
  document.querySelector("[data-resumen-errores]")?.focus();
})();
