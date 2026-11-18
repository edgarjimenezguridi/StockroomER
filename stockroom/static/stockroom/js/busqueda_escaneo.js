/* StockroomER 23I: búsqueda remota para selects ModelChoiceField.
 * Escanear o buscar solo selecciona una opción: NO envía formularios.
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
    label.textContent = select.dataset.srScanLabel || "Buscar o escanear";
    const input = document.createElement("input");
    input.type = "search";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = "Escribe nombre, número o escanea el código";
    input.setAttribute("aria-label", label.textContent);
    const hint = document.createElement("small");
    hint.className = "sr-scan-hint";
    hint.setAttribute("role", "status");
    hint.textContent = "Busca y después selecciona el resultado. Escanear no registra movimientos.";
    container.append(label, input, hint);
    select.before(container);
    select.setAttribute("aria-label", "Selecciona un resultado de búsqueda");

    // Un valor ya elegido se conserva en POST con errores de validación.
    let requestId = 0;
    let timer = null;
    let controller = null;
    function mostrar(items) {
      const anterior = select.value;
      select.replaceChildren(new Option("Selecciona un resultado", ""));
      items.forEach(item => {
        const opt = new Option(item.text, String(item.id));
        select.add(opt);
      });
      if (items.some(item => String(item.id) === anterior)) select.value = anterior;
      else select.value = "";
      hint.textContent = !items.length ? "Sin coincidencias. Verifica el código o nombre."
        : `${items.length} resultado(s). Selecciona el registro correcto para continuar.`;
    }
    async function buscar() {
      const q = input.value.trim().slice(0, 80);
      const ticket = ++requestId;
      if (controller) controller.abort();
      if (!q) {
        // Evitar perder un valor ya elegido al limpiar la búsqueda.
        const elegido = select.selectedOptions[0];
        if (!select.value || !elegido) mostrar([]);
        hint.textContent = "Escanea o escribe para buscar (hasta 20 coincidencias).";
        return;
      }
      controller = new AbortController();
      hint.textContent = "Buscando…";
      try {
        const url = new URL(endpoint, window.location.href);
        url.searchParams.set("tipo", select.dataset.srLookupType);
        url.searchParams.set("q", q);
        const response = await fetch(url.toString(), {
          method: "GET", credentials: "same-origin", cache: "no-store",
          redirect: "manual", signal: controller.signal,
          headers: {"Accept": "application/json"}
        });
        if (!response.ok || response.redirected || response.type === "opaqueredirect" ||
            !(response.headers.get("content-type") || "").includes("application/json")) {
          throw new Error("Consulta no autorizada o conexión interrumpida");
        }
        const data = await response.json();
        if (ticket !== requestId || !Array.isArray(data.results)) return;
        mostrar(data.results);
        // Un lector suele enviar Enter. Selección automática solo si
        // existe UNA coincidencia cuyo código coincida exactamente.
        const coincidenciaExacta = data.results.filter(item =>
          String(item.text).split(" — ")[0].trim().toLowerCase() === q.toLowerCase());
        if (coincidenciaExacta.length === 1) {
          select.value = String(coincidenciaExacta[0].id);
          select.dispatchEvent(new Event("change", {bubbles: true}));
          hint.textContent = "Código localizado. Verifica el registro y confirma manualmente.";
        }
      } catch (error) {
        if (error.name !== "AbortError" && ticket === requestId) {
          hint.textContent = "No se pudo consultar. Revisa tu conexión y vuelve a intentar.";
        }
      }
    }
    input.addEventListener("input", () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(buscar, 250);
    });
    input.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        window.clearTimeout(timer);
        buscar();
      }
    });
    select.addEventListener("change", () => {
      if (select.value) hint.textContent = "Registro seleccionado. Revisa los datos antes de confirmar.";
    });
  }
  function arrancar() {
    document.querySelectorAll("select[data-sr-scan][data-sr-lookup-type]").forEach(iniciar);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", arrancar);
  else arrancar();
})();
