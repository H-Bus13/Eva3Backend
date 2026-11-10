(() => {
  const canvas = document.getElementById("firma");
  const form = document.getElementById("form-firma");
  if (!canvas || !form) return;
  const ctx = canvas.getContext("2d");
  const error = document.getElementById("error-firma");
  const guardar = document.getElementById("guardar-firma");
  let dibujando = false;
  let puntero = null;
  let hayTrazo = false;

  function limpiar() {
    ctx.fillStyle = "white";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#172c40";
    ctx.lineWidth = 4;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    hayTrazo = false;
    error.textContent = "";
  }
  // La imagen mantiene sus dimensiones aunque el espacio visible se reduzca
  // en un teléfono. Se convierten las coordenadas a la resolución del canvas.
  function punto(evento) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: (evento.clientX - rect.left) * canvas.width / rect.width,
      y: (evento.clientY - rect.top) * canvas.height / rect.height,
    };
  }
  canvas.addEventListener("pointerdown", (evento) => {
    if (dibujando || (evento.pointerType === "mouse" && evento.button !== 0)) return;
    evento.preventDefault();
    puntero = evento.pointerId;
    canvas.setPointerCapture(puntero);
    dibujando = true;
    const p = punto(evento);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
  });
  canvas.addEventListener("pointermove", (evento) => {
    if (!dibujando || evento.pointerId !== puntero) return;
    const p = punto(evento);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    hayTrazo = true;
  });
  const terminar = (evento) => {
    if (evento.pointerId === puntero) {
      dibujando = false;
      puntero = null;
    }
  };
  canvas.addEventListener("pointerup", terminar);
  canvas.addEventListener("pointercancel", terminar);
  canvas.addEventListener("lostpointercapture", terminar);
  document.getElementById("limpiar-firma").addEventListener("click", limpiar);

  form.addEventListener("submit", (evento) => {
    evento.preventDefault();
    if (!hayTrazo) {
      error.textContent = "Dibuja tu firma antes de guardarla.";
      return;
    }
    guardar.disabled = true;
    // Se adjunta un PNG a un formulario normal. El servidor vuelve a validar
    // el archivo y la aceptación; esta revisión del navegador es solo una ayuda.
    canvas.toBlob((blob) => {
      if (!blob) {
        error.textContent = "No se pudo preparar la firma. Inténtalo otra vez.";
        guardar.disabled = false;
        return;
      }
      try {
        const archivos = new DataTransfer();
        archivos.items.add(new File([blob], "firma.png", { type: "image/png" }));
        document.getElementById("archivo-firma").files = archivos.files;
        HTMLFormElement.prototype.submit.call(form);
      } catch {
        error.textContent = "El navegador no pudo adjuntar la firma. Prueba con una versión actualizada.";
        guardar.disabled = false;
      }
    }, "image/png");
  });
  limpiar();
})();
