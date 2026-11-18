/* StockroomER Fase 23K.1: actualización supervisada, solo lectura, para paneles. */
(function () {
    "use strict";
    const INTERVALO = 10000;
    const TIMEOUT = 8000;
    const SELECTOR = "[data-sr-live]";
    let consultando = false;
    let cerrado = false;

    function crearIndicador() {
        const regiones = document.querySelectorAll(SELECTOR);
        if (!regiones.length || document.getElementById("sr-estado-actualizacion")) return null;
        const contenedor = document.createElement("div");
        contenedor.id = "sr-estado-actualizacion";
        contenedor.style.cssText = "display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:8px 0 16px;font-size:.86rem;color:inherit;opacity:.85";
        const estado = document.createElement("span");
        estado.id = "sr-estado-texto";
        estado.setAttribute("role", "status");
        estado.setAttribute("aria-live", "polite");
        estado.textContent = "Actualización automática cada 10 s";
        contenedor.appendChild(estado);
        const espacio = document.querySelector("[data-sr-update-host]");
        if (espacio) {
            espacio.appendChild(contenedor);
        } else {
            regiones[0].parentNode.insertBefore(contenedor, regiones[0]);
        }
        return estado;
    }

    function informar(mensaje) {
        const estado = document.getElementById("sr-estado-texto");
        if (estado) estado.textContent = mensaje;
    }

    function conservarDetalles(actual, nuevo) {
        const abiertos = new Set();
        actual.querySelectorAll("details[open]").forEach(function (detalle) {
            const resumen = detalle.querySelector("summary");
            if (resumen) abiertos.add(resumen.textContent.trim());
        });
        nuevo.querySelectorAll("details").forEach(function (detalle) {
            const resumen = detalle.querySelector("summary");
            if (resumen && abiertos.has(resumen.textContent.trim())) detalle.open = true;
        });
    }

    function tieneCambiosPendientes(actual) {
        const activo = document.activeElement;
        const editando = activo && actual.contains(activo) &&
            activo.matches("input, select, textarea, [contenteditable]");
        if (editando) return true;
        const formularios = actual.querySelectorAll("form");
        return Array.from(formularios).some(form =>
            Array.from(form.elements).some(campo =>
                campo.matches("input:not([type=hidden]), textarea, select") &&
                ((campo.matches("input[type=checkbox], input[type=radio]") &&
                  campo.checked !== campo.defaultChecked) ||
                 (!campo.matches("input[type=checkbox], input[type=radio]") &&
                  campo.value !== campo.defaultValue && campo.defaultValue !== undefined))
            )
        );
    }

    async function actualizar() {
        if (document.hidden || consultando || cerrado) return;
        consultando = true;
        const controlador = new AbortController();
        const limite = window.setTimeout(function () { controlador.abort(); }, TIMEOUT);
        try {
            const respuesta = await fetch(window.location.pathname + window.location.search, {
                method: "GET", credentials: "same-origin", cache: "no-store", redirect: "manual",
                signal: controlador.signal,
                headers: {"X-Requested-With": "XMLHttpRequest"}
            });
            // No sustituir datos con una página de inicio de sesión o con un error HTTP.
            if (!respuesta.ok || respuesta.type === "opaqueredirect" || respuesta.redirected ||
                !(respuesta.headers.get("content-type") || "").includes("text/html")) {
                informar("No se pudo actualizar · comprueba la sesión o conexión");
                return;
            }
            const pagina = new DOMParser().parseFromString(await respuesta.text(), "text/html");
            const regionesNuevas = Array.from(pagina.querySelectorAll(SELECTOR));
            if (!regionesNuevas.length) {
                informar("Actualización no disponible · recarga la página para comprobar la sesión");
                return;
            }
            if (cerrado) return;
            let cambios = 0;
            let protegidas = 0;
            document.querySelectorAll(SELECTOR).forEach(function (actual) {
                const identificador = actual.getAttribute("data-sr-live");
                if (!identificador) return;
                const nuevo = regionesNuevas.find(elemento =>
                    elemento.getAttribute("data-sr-live") === identificador
                );
                if (!nuevo || actual.innerHTML === nuevo.innerHTML) return;
                if (tieneCambiosPendientes(actual)) { protegidas += 1; return; }
                conservarDetalles(actual, nuevo);
                // Solo sustituir regiones de consulta, nunca el resto del formulario.
                actual.replaceChildren(...Array.from(nuevo.childNodes));
                cambios += 1;
            });
            if (cerrado) return;
            const hora = new Date().toLocaleTimeString("es-MX", {hour: "2-digit", minute: "2-digit", second: "2-digit"});
            informar("Actualizado " + hora + (cambios ? " · cambios recibidos" : " · sin cambios") +
                (protegidas ? " · edición protegida" : ""));
            document.dispatchEvent(new CustomEvent("stockroom:panel-actualizado", {
                detail: {cambios: cambios, protegidas: protegidas}
            }));
        } catch (error) {
            if (!cerrado) {
                informar("Sin conexión · se conservaron los datos visibles");
                console.warn("StockroomER: actualización temporalmente no disponible.", error);
            }
        } finally {
            window.clearTimeout(limite);
            consultando = false;
        }
    }

    if (!document.querySelector(SELECTOR)) return;
    crearIndicador();
    // Ejecutar una primera comprobación sin esperar diez segundos.
    actualizar();
    const reloj = window.setInterval(actualizar, INTERVALO);
    document.addEventListener("visibilitychange", function () {
        if (!document.hidden) actualizar();
    });
    window.addEventListener("pagehide", function () {
        cerrado = true;
        window.clearInterval(reloj);
    });
})();
