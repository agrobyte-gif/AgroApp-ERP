/* Logistica: repartir el trabajo y armar rutas.
 *
 * Las dos pantallas son lo mismo -marcar pedidos y elegir a quien- asi que
 * comparten archivo y el mismo recolector de casillas.
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
            avisar(e.message || "No se pudo completar.", true);
        } finally {
            boton.disabled = false;
            boton.textContent = texto;
        }
    }

    const marcados = () => Array.from(
        document.querySelectorAll(".ag-alb:checked")).map((c) => +c.value);

    /* ---------------------------------------------------------------
       Repartir el trabajo
       --------------------------------------------------------------- */

    function initAsignar() {
        const boton = document.querySelector("[data-action='asignar']");
        if (!boton) { return; }
        boton.addEventListener("click", () => conBloqueo(boton, async () => {
            const albaranes = marcados();
            const picker = $("picker").value;
            if (!albaranes.length) { return avisar("No has marcado ningun pedido.", true); }
            if (!picker) { return avisar("Elige quien lo prepara.", true); }
            const r = await rpc("/agrogood/api/logistica/asignar", {
                picking_ids: albaranes, picker_id: +picker,
            });
            if (!r.ok) { return avisar(r.mensaje, true); }
            avisar(r.mensaje);
            setTimeout(() => { location.href = "/agrogood/logistica"; }, 1200);
        }));
    }

    /* ---------------------------------------------------------------
       Armar la ruta
       --------------------------------------------------------------- */

    function initRuta() {
        const boton = document.querySelector("[data-action='ruta']");
        if (!boton) { return; }
        boton.addEventListener("click", () => conBloqueo(boton, async () => {
            const albaranes = marcados();
            const conductor = $("conductor").value;
            const vehiculo = $("vehiculo").value;
            if (!albaranes.length) { return avisar("La ruta no lleva ninguna entrega.", true); }
            if (!conductor) { return avisar("Elige quien la lleva.", true); }
            if (!vehiculo) { return avisar("Elige el camion.", true); }
            const r = await rpc("/agrogood/api/logistica/ruta", {
                picking_ids: albaranes,
                driver_id: +conductor,
                vehicle_id: +vehiculo,
                fecha: $("fecha-ruta").value || null,
            });
            if (!r.ok) { return avisar(r.mensaje, true); }
            /* La sobrecarga se avisa AQUI, con la ruta recien armada y Felipe
               delante, no cuando el camion ya esta cargado. */
            if (r.sobrecargada) {
                avisar(r.mensaje + " OJO: pasa de la capacidad del camion (" +
                       r.ocupacion + "%).", true);
            } else {
                avisar(r.mensaje + " Ocupa el " + r.ocupacion + "% del camion.");
            }
            setTimeout(() => { location.href = "/agrogood/logistica"; },
                       r.sobrecargada ? 4000 : 1500);
        }));
    }

    document.addEventListener("DOMContentLoaded", function () {
        initAsignar();
        initRuta();
    });
})();
