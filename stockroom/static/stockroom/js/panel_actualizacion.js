
/* StockroomER Fase 23B: actualización visual sin recargar formularios. */
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

        const activo = document.activeElement;

        if (
            activo &&
            activo.matches(
                "input, select, textarea, button, [contenteditable]"
            )
        ) return;

        consultando = true;

        try {
            const respuesta = await fetch(
                window.location.pathname + window.location.search,
                {
                    method: "GET",
                    credentials: "same-origin",
                    cache: "no-store",
                    redirect: "manual",
                    headers: {
                        "X-Requested-With": "XMLHttpRequest"
                    }
                }
            );

            if (
                !respuesta.ok ||
                respuesta.type === "opaqueredirect" ||
                respuesta.redirected ||
                !(respuesta.headers.get("content-type") || "")
                    .includes("text/html")
            ) return;

            const pagina = new DOMParser().parseFromString(
                await respuesta.text(),
                "text/html"
            );

            if (!pagina.querySelector(SELECTOR)) return;

            document.querySelectorAll(SELECTOR).forEach(function (actual) {
                const identificador = actual.getAttribute("data-sr-live");
                if (!identificador) return;

                const nuevo = Array.from(
                    pagina.querySelectorAll(SELECTOR)
                ).find(
                    elemento =>
                        elemento.getAttribute("data-sr-live") === identificador
                );

                if (
                    !nuevo ||
                    actual.contains(document.activeElement) ||
                    actual.matches(":hover")
                ) return;

                if (actual.innerHTML === nuevo.innerHTML) return;

                conservarDetalles(actual, nuevo);

                actual.replaceChildren(
                    ...Array.from(nuevo.childNodes)
                );
            });

            document.dispatchEvent(
                new CustomEvent("stockroom:panel-actualizado")
            );

        } catch (error) {
            console.warn(
                "StockroomER: actualización temporalmente no disponible.",
                error
            );
        } finally {
            consultando = false;
        }
    }

    const reloj = window.setInterval(actualizar, INTERVALO);

    document.addEventListener("visibilitychange", function () {
        if (!document.hidden) actualizar();
    });

    window.addEventListener("pagehide", function () {
        window.clearInterval(reloj);
    });
})();
