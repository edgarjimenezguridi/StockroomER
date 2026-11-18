/* StockroomER 23J: búsquedas remotas accesibles para escáner y teclado.
 * Nunca envía formularios ni modifica existencias. El servidor valida el POST.
 */
(function () {
  "use strict";
  const script = document.currentScript || document.querySelector('script[src*="busqueda_escaneo.js"]');
  const endpoint = script && script.dataset.apiUrl;
  if (!endpoint) return;

  function iniciar(select) {
    if (!select.dataset.srLookupType || select.dataset.srScanReady) return;
    select.dataset.srScanReady = "1";

    const container = document.createElement("div");
    container.className = "sr-scan-lookup";
    const label = document.createElement("label");
    const input = document.createElement("input");
    const status = document.createElement("small");
    const toolbar = document.createElement("div");
    const clearButton = document.createElement("button");
    const key = select.id || select.name || "buscar";

    label.textContent = select.dataset.srScanLabel || "Buscar o escanear";
    input.id = `sr-scan-${key}`;
    label.htmlFor = input.id;
    input.type = "search";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.maxLength = 80;
    input.placeholder = "Escribe el nombre, número o escanea el código";
    clearButton.type = "button";
    clearButton.className = "sr-scan-clear";
    clearButton.textContent = "Limpiar selección";
    clearButton.title = "Borra la selección y permite buscar otra vez";
    status.className = "sr-scan-hint";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.textContent = "Busca un registro y selecciónalo; escanear no registra movimientos.";
    toolbar.className = "sr-scan-toolbar";
    toolbar.append(input, clearButton);
    container.append(label, toolbar, status);
    select.before(container);
    select.setAttribute("aria-label", "Selecciona el resultado correcto");

    let requestId = 0;
    let timer = null;
    let controller = null;
    let searching = false;

    function setStatus(message, kind) {
      status.textContent = message;
      status.dataset.state = kind || "info";
      container.dataset.state = kind || "info";
    }
    function cancel() {
      ++requestId; // invalida también respuestas anteriores que ya iban en camino
      window.clearTimeout(timer);
      if (controller) controller.abort();
      controller = null;
      searching = false;
      input.removeAttribute("aria-busy");
    }
    function resetOptions() {
      select.replaceChildren(new Option("Selecciona un resultado", ""));
      select.value = "";
      select.dispatchEvent(new Event("change", {bubbles: true}));
    }
    function clear() {
      cancel();
      input.value = "";
      resetOptions();
      setStatus("Selección borrada. Escribe o escanea otro código.", "info");
      input.focus();
    }
    clearButton.addEventListener("click", clear);

    function show(items) {
      const previous = select.value;
      select.replaceChildren(new Option("Selecciona un resultado", ""));
      items.forEach(item => {
        if (!item || item.id === undefined || typeof item.text !== "string") return;
        select.add(new Option(item.text, String(item.id)));
      });
      const keep = Array.from(select.options).some(o => o.value && o.value === previous);
      select.value = keep ? previous : "";
      if (!items.length) {
        setStatus("Sin coincidencias. Verifica el código o intenta con el nombre.", "empty");
      } else {
        setStatus(`${items.length} resultado(s). Elige el registro correcto.`, "success");
      }
    }

    async function search() {
      const q = input.value.trim().slice(0, 80);
      cancel();
      const ticket = requestId;
      if (!q) {
        // Al limpiar el texto no se borra una opción seleccionada; el botón sí la borra.
        setStatus(select.value ? "Registro seleccionado. Puedes limpiar la selección para cambiarlo." :
          "Escribe o escanea para buscar (hasta 20 resultados).", "info");
        return;
      }
      const currentController = new AbortController();
      controller = currentController;
      searching = true;
      input.setAttribute("aria-busy", "true");
      setStatus("Buscando coincidencias…", "loading");
      try {
        const url = new URL(endpoint, window.location.href);
        url.searchParams.set("tipo", select.dataset.srLookupType);
        url.searchParams.set("q", q);
        const response = await fetch(url.toString(), {
          method: "GET", credentials: "same-origin", cache: "no-store",
          redirect: "manual", signal: currentController.signal,
          headers: {"Accept": "application/json"}
        });
        if (!response.ok || response.redirected || response.type === "opaqueredirect" ||
            !(response.headers.get("content-type") || "").includes("application/json")) {
          throw new Error("Consulta no autorizada o conexión interrumpida");
        }
        const data = await response.json();
        if (ticket !== requestId || input.value.trim().slice(0, 80) !== q || !Array.isArray(data.results)) return;
        show(data.results);
        // Solo selecciona automáticamente códigos exactos; nunca registra el formulario.
        // No selecciona automáticamente entradas históricas: pueden tener varias coincidencias.
        if (select.dataset.srLookupType !== "entradas_correccion") {
          const exact = data.results.filter(item =>
            String(item.text || "").split(" — ")[0].trim().toLocaleLowerCase("es-MX") === q.toLocaleLowerCase("es-MX"));
          if (exact.length === 1) {
            select.value = String(exact[0].id);
            select.dispatchEvent(new Event("change", {bubbles: true}));
            setStatus("Código exacto localizado. Verifica el registro antes de confirmar.", "success");
          }
        }
      } catch (error) {
        if (error.name !== "AbortError" && ticket === requestId) {
          setStatus("No se pudo buscar. Revisa la conexión o la sesión e intenta otra vez.", "error");
        }
      } finally {
        if (ticket === requestId) {
          searching = false;
          controller = null;
          input.removeAttribute("aria-busy");
        }
      }
    }

    input.addEventListener("input", () => {
      // Invalidar la respuesta anterior inmediatamente, sin esperar al debounce.
      cancel();
      if (!input.value.trim()) {
        setStatus(select.value ? "Selección conservada; usa Limpiar selección para cambiarla." :
          "Escribe o escanea para buscar.", "info");
        return;
      }
      timer = window.setTimeout(search, 250);
    });
    input.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault(); // El Enter del lector nunca envía el formulario.
        window.clearTimeout(timer);
        search();
      }
    });
    select.addEventListener("change", () => {
      if (select.value && !searching) setStatus("Registro seleccionado. Revisa los datos antes de confirmar.", "success");
    });
    // En un POST inválido Django puede devolver la opción ya elegida.
    if (select.value) setStatus("Registro seleccionado. Puedes cambiarlo con Limpiar selección.", "success");
  }
  function start() {
    document.querySelectorAll("select[data-sr-scan][data-sr-lookup-type]").forEach(iniciar);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
