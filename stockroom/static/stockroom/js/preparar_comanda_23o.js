/* Fase 23O: solo marca casillas; no envía formularios ni modifica inventario. */
(() => {
  "use strict";
  const raiz = document.querySelector("[data-escaneo-preparacion]");
  if (!raiz) return;
  const campo = document.getElementById("codigo-pieza-preparacion");
  const estado = document.getElementById("estado-escaneo-preparacion");
  const contador = document.getElementById("contador-preparacion");
  const coincidencia = document.getElementById("coincidencia-preparacion");
  const limpiar = document.getElementById("limpiar-seleccion-preparacion");
  const cantidad = document.querySelector(".formulario-preparacion input[name='quantity']");
  const lista = document.getElementById("piezas-preparacion");
  const formulario = raiz.closest("form");
  const guardar = formulario && formulario.querySelector('button[type="submit"]');
  if (!campo || !estado || !contador || !lista) return;
  const casillas = () => Array.from(lista.querySelectorAll("input[type='checkbox'][name='tools']"));
  const normalizar = value => String(value || "").trim().toUpperCase();
  // Las claves son los IDs de piezas que el formulario acepta; los valores,
  // los códigos de barra reales. No interpretar el texto mostrado en pantalla.
  let codigosPiezas = {};
  try {
    const mapa = document.getElementById("codigos-piezas-preparacion");
    if (mapa) codigosPiezas = JSON.parse(mapa.textContent);
  } catch (_) {
    estado.dataset.estado = "error";
    estado.textContent = "No se pudieron cargar los códigos de piezas. Recarga la página.";
  }
  const codigoDe = checkbox => normalizar(codigosPiezas[String(checkbox.value)]);
  const actualizar = () => {
    const seleccionadas = casillas().filter(c => c.checked).length;
    const solicitadas = cantidad ? Number(cantidad.value || 0) : 0;
    contador.textContent = `Piezas seleccionadas: ${seleccionadas} · Cantidad a preparar: ${solicitadas}`;
    if (coincidencia) {
      // Preparar cero piezas es válido cuando no hay material disponible.
      const coincide = seleccionadas === solicitadas && Number.isInteger(solicitadas) && solicitadas >= 0;
      coincidencia.dataset.estado = coincide ? "ok" : "error";
      coincidencia.textContent = coincide
        ? (solicitadas === 0
          ? "Prepararás 0 piezas. No se seleccionó ninguna herramienta."
          : "Cantidad y piezas seleccionadas coinciden. Revisa antes de guardar.")
        : "La cantidad a preparar debe coincidir con las piezas seleccionadas antes de guardar.";
    }
  };
  const marcar = () => {
    const codigo = normalizar(campo.value);
    campo.value = "";
    if (!codigo) return;
    const coincidencias = casillas().filter(c => codigoDe(c) && codigoDe(c) === codigo);
    if (coincidencias.length !== 1) {
      estado.dataset.estado = "error";
      estado.textContent = "No se encontró una pieza disponible con ese código para este artículo.";
      campo.focus();
      return;
    }
    const casilla = coincidencias[0];
    if (casilla.checked) {
      estado.dataset.estado = "error";
      estado.textContent = `La pieza ${codigo} ya está seleccionada.`;
    } else {
      casilla.checked = true;
      casilla.dispatchEvent(new Event("change", { bubbles: true }));
      estado.dataset.estado = "ok";
      estado.textContent = `Pieza ${codigo} seleccionada. Revisa la cantidad antes de guardar.`;
    }
    campo.focus();
  };
  campo.addEventListener("keydown", event => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    marcar();
  });
  if (limpiar) {
    limpiar.addEventListener("click", () => {
      casillas().filter(c => c.checked).forEach(c => {
        c.checked = false;
        c.dispatchEvent(new Event("change", { bubbles: true }));
      });
      campo.value = "";
      estado.dataset.estado = "ok";
      estado.textContent = "Selección limpia. Escanea la siguiente pieza.";
      actualizar();
      campo.focus();
    });
  }
  // Este control es preventivo; el servidor vuelve a validar cantidades, piezas y disponibilidad.
  if (formulario) {
    formulario.addEventListener("submit", event => {
      const seleccionadas = casillas().filter(c => c.checked).length;
      const solicitadas = cantidad ? Number(cantidad.value) : NaN;
      const valido = Number.isInteger(solicitadas) && solicitadas >= 0 &&
        cantidad.value.trim() !== "" && seleccionadas === solicitadas;
      if (!valido) {
        event.preventDefault();
        estado.dataset.estado = "error";
        estado.textContent = "Revisa la cantidad: debe ser igual al número de piezas seleccionadas.";
        actualizar();
        if (cantidad) cantidad.focus();
        return;
      }
      if (guardar) {
        // No se modifica el valor de ningún campo enviado ni se llama a submit().
        guardar.disabled = true;
        guardar.textContent = "Guardando preparación…";
      }
    });
    window.addEventListener("pageshow", () => {
      if (guardar) {
        guardar.disabled = false;
        guardar.textContent = "Guardar preparación";
      }
    });
  }
  lista.addEventListener("change", actualizar);
  if (cantidad) cantidad.addEventListener("input", actualizar);
  actualizar();
  // Solo toma el foco si el usuario no está editando otro campo.
  if (document.activeElement === document.body) campo.focus({ preventScroll: true });
})();
