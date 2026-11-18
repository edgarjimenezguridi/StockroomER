/* Fase 23O: solo marca casillas; no envía formularios ni modifica inventario. */
(() => {
  "use strict";
  const raiz = document.querySelector("[data-escaneo-preparacion]");
  if (!raiz) return;
  const campo = document.getElementById("codigo-pieza-preparacion");
  const estado = document.getElementById("estado-escaneo-preparacion");
  const contador = document.getElementById("contador-preparacion");
  const cantidad = document.querySelector(".formulario-preparacion input[name='quantity']");
  const lista = document.getElementById("piezas-preparacion");
  if (!campo || !estado || !contador || !lista) return;
  const casillas = () => Array.from(lista.querySelectorAll("input[type='checkbox'][name='tools']"));
  const normalizar = value => String(value || "").trim().toUpperCase();
  const codigoDe = checkbox => {
    const label = lista.querySelector(`label[for="${CSS.escape(checkbox.id)}"]`);
    const texto = label ? label.textContent : (checkbox.parentElement?.textContent || "");
    return normalizar(texto).split(/\s+-\s+/)[0].trim();
  };
  const actualizar = () => {
    const seleccionadas = casillas().filter(c => c.checked).length;
    const solicitadas = cantidad ? Number(cantidad.value || 0) : 0;
    contador.textContent = `Piezas seleccionadas: ${seleccionadas} · Cantidad a preparar: ${solicitadas}`;
  };
  const marcar = () => {
    const codigo = normalizar(campo.value);
    campo.value = "";
    if (!codigo) return;
    const coincidencias = casillas().filter(c => codigoDe(c) === codigo);
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
  lista.addEventListener("change", actualizar);
  if (cantidad) cantidad.addEventListener("input", actualizar);
  actualizar();
})();
