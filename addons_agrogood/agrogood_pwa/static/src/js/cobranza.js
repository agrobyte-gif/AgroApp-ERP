/* Cobranza: anotar lo que dijo el cliente al colgar.
 *
 * Una sola cosa hace esta pantalla, y es a proposito. Cobrar por telefono es
 * mirar cuanto debe y desde cuando -eso ya esta escrito en la pagina, sin
 * javascript de por medio- y anotar la respuesta. Imputar abonos y revisar la
 * cartola se hace sentado, en el escritorio.
 */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);

    async function rpc(ruta, params) {
        const r = await fetch(ruta, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            credentials: "same-origin",
            body: JSON.stringify({jsonrpc: "2.0", method: "call", params: params || {}}),
        });
        const d = await r.json();
        if (d.error) {
            throw new Error((d.error.data && d.error.data.message) || d.error.message);
        }
        return d.result;
    }

    function avisar(texto, esError) {
        const t = $("ag-toast");
        if (!t) { return; }
        t.textContent = texto;
        t.className = "ag-toast ag-show" + (esError ? " ag-error" : "");
        setTimeout(() => { t.className = "ag-toast"; }, 5000);
    }

    async function conBloqueo(boton, fn) {
        if (boton.disabled) { return; }
        const texto = boton.textContent;
        boton.disabled = true;
        boton.textContent = "Un momento...";
        try {
            await fn();
        } catch (e) {
            avisar(e.message || "No se pudo anotar.", true);
        } finally {
            boton.disabled = false;
            boton.textContent = texto;
        }
    }

    document.addEventListener("click", (ev) => {
        const boton = ev.target.closest("[data-action='promesa']");
        if (!boton) { return; }
        ev.preventDefault();
        conBloqueo(boton, async () => {
            const fecha = $("ag-promesa-fecha");
            const nota = $("ag-promesa-nota");
            const r = await rpc("/agrogood/api/cobranza/promesa", {
                partner_id: parseInt(boton.dataset.id, 10),
                fecha: (fecha && fecha.value) || null,
                nota: (nota && nota.value) || "",
            });
            avisar(r.mensaje, !r.ok);
        });
    });
})();
