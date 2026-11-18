/* StockroomER Fase 23B: actualización visual de consultas, sin recargar formularios. */
(function () {
    "use strict";
    const INTERVALO = 10000;
    const SELECTOR = "[data-sr-live]";
    let consultando = false;

    function conservarDetalles(actual, nuevo) {
        const abiertos = new Set();
        actual.querySelectorAll("details[open]").forEach(function (detalle) {
            const resumen = detalle.querySelector("summary");
            if (resumen) abiertos.add(resumen.textContent.trim());
        });
        nuevo.querySelectorAll("details").forEach(function (detalle) {
            const resumen = detalle.querySelector("summary");
            if (resumen && abiertos.has(resumen.textContent.trim())) {
                detalle.open = true;
            }
        });
    }

    async function actualizar() {
        if (document.hidden || consultando) return;
        consultando = true;
        try {
            const respuesta = await fetch(window.location.pathname + window.location.search, {
                method: "GET", credentials: "same-origin", cache: "no-store", redirect: "manual",
                headers: {"X-Requested-With": "XMLHttpRequest"}
            });
            if (!respuesta.ok || respuesta.type === "opaqueredirect" || respuesta.redirected ||
                !(respuesta.headers.get("content-type") || "").includes("text/html")) return;
            const pagina = new DOMParser().parseFromString(await respuesta.text(), "text/html");
            if (!pagina.querySelector(SELECTOR)) return;
            document.querySelectorAll(SELECTOR).forEach(function (actual) {
                const identificador = actual.getAttribute("data-sr-live");
                if (!identificador) return;
                const nuevo = Array.from(pagina.querySelectorAll(SELECTOR)).find(
                    elemento => elemento.getAttribute("data-sr-live") === identificador
                );
                if (!nuevo) return;
                // Un botón pulsado puede conservar el foco durante minutos.
                // Solo protegemos campos que estén siendo editados DENTRO de esta región.
                const activo = document.activeElement;
                const editando = activo && actual.contains(activo) &&
                    activo.matches("input, select, textarea, [contenteditable]");
                if (editando) return;
                // No reemplazar una región que contenga formularios con cambios pendientes.
                const formularios = actual.querySelectorAll("form");
                if (Array.from(formularios).some(form =>
                    Array.from(form.elements).some(campo =>
                        campo.matches("input:not([type=hidden]), textarea, select") &&
                        ((campo.matches("input[type=checkbox], input[type=radio]") && campo.checked !== campo.defaultChecked) ||
                        (!campo.matches("input[type=checkbox], input[type=radio]") &&
                         campo.value !== campo.defaultValue && campo.defaultValue !== undefined))
                    )
                )) return;
                if (actual.innerHTML === nuevo.innerHTML) return;
                conservarDetalles(actual, nuevo);
                // Solo sustituir las regiones explícitamente marcadas como actualizables.
                actual.replaceChildren(...Array.from(nuevo.childNodes));
            });
            document.dispatchEvent(new CustomEvent("stockroom:panel-actualizado"));
        } catch (error) {
            // La pérdida temporal de red nunca debe ocultar los datos actuales.
            console.warn("StockroomER: actualización temporalmente no disponible.", error);
        } finally {
            consultando = false;
        }
    }

    const reloj = window.setInterval(actualizar, INTERVALO);
    document.addEventListener("visibilitychange", function () {
        if (!document.hidden) actualizar();
    });
    window.addEventListener("pagehide", function () { window.clearInterval(reloj); });
})();
