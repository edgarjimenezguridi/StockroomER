/* StockroomER: selector de artículos, entradas y trabajadores por código/nombre.
 * Escanear nunca envía un formulario ni modifica inventario.
 */
(function () {
  "use strict";
  function normalizar(valor) {
    return String(valor || "").toLocaleLowerCase("es-MX").normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "").trim();
  }
  function iniciar(select) {
    if (!select || select.dataset.srScanReady) return;
    select.dataset.srScanReady = "1";
    const contenedor = document.createElement("div");
    contenedor.className = "sr-scan-lookup";
    const etiqueta = document.createElement("label");
    etiqueta.textContent = select.dataset.srScanLabel || "Buscar o escanear código";
    const campo = document.createElement("input");
    campo.type = "search";
    campo.autocomplete = "off";
    campo.placeholder = "Escanea el código o escribe nombre / número";
    campo.setAttribute("aria-label", etiqueta.textContent);
    const aviso = document.createElement("small");
    aviso.className = "sr-scan-hint";
    aviso.textContent = "Escanear solo busca. Confirma la operación manualmente.";
    contenedor.append(etiqueta, campo, aviso);
    select.parentNode.insertBefore(contenedor, select);
    const opciones = Array.from(select.options).map(o => ({value:o.value, label:o.textContent}));
    function filtrar() {
      const busqueda = normalizar(campo.value);
      const elegido = select.value;
      const coincidencias = opciones.filter(o => !busqueda || normalizar(o.label).includes(busqueda) || !o.value);
      select.replaceChildren();
      for (const item of coincidencias) {
        const opcion = new Option(item.label, item.value);
        select.add(opcion);
      }
      if (coincidencias.some(o=>o.value===elegido)) select.value=elegido;
      else select.value="";
      const validas = coincidencias.filter(o=>o.value);
      aviso.textContent = !busqueda ? "Escanea para localizar. Confirma la operación manualmente."
        : validas.length===0 ? "Sin coincidencias; verifica el código." 
        : validas.length===1 ? "1 coincidencia. Verifica el artículo antes de continuar."
        : validas.length+" coincidencias; selecciona la correcta.";
      // No se autoselecciona una entrada: un artículo puede tener muchas entradas históricas.
    }
    campo.addEventListener("input", filtrar);
    campo.addEventListener("keydown", e => {
      if (e.key === "Enter") {
        e.preventDefault();
        filtrar();
        select.focus();
      }
    });
  }
  function arrancar() {
    document.querySelectorAll('select[data-sr-scan]').forEach(iniciar);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", arrancar);
  else arrancar();
})();
