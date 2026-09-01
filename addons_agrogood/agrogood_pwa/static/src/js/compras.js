/* Compras: la pizarra de Johan en el telefono.
 *
 * Tres cosas y nada mas: anotar proveedor y precio, mover el estado, y generar
 * la orden al proveedor. Es lo que se hace de pie en la feria; el resto de la
 * gestion sigue en el escritorio, donde hay sitio para pensarla.
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

    /* ---------------------------------------------------------------
       Proveedores: se cargan al abrir la solicitud
       --------------------------------------------------------------- */

    async function cargarProveedores() {
        const sel = $("proveedor");
        if (!sel) { return; }
        const yaPuesto = sel.value;
        const gente = await rpc("/agrogood/api/compras/proveedores", {q: ""});
        gente.forEach((p) => {
            /* El proveedor ya anotado viene puesto desde el servidor: si se
               vuelve a anadir, aparece dos veces en la lista. */
            if (sel.querySelector('option[value="' + p.id + '"]')) { return; }
            const o = document.createElement("option");
            o.value = p.id;
            o.textContent = p.nombre;
            sel.appendChild(o);
        });
        if (yaPuesto) { sel.value = yaPuesto; }
        if (!gente.length) {
            avisar("No hay proveedores dados de alta.", true);
        }
    }

    /* ---------------------------------------------------------------
       Acciones
       --------------------------------------------------------------- */

    function initSolicitud() {
        const anotar = document.querySelector("[data-action='anotar']");
        if (anotar) {
            anotar.addEventListener("click", () => conBloqueo(anotar, async () => {
                const proveedor = $("proveedor").value;
                const precio = $("precio").value;
                if (!proveedor && !precio) {
                    return avisar("Anota al menos el proveedor o el precio.", true);
                }
                const r = await rpc("/agrogood/api/compras/anotar", {
                    request_id: +anotar.dataset.sol,
                    supplier_id: proveedor ? +proveedor : null,
                    price: precio === "" ? null : parseFloat(precio),
                    note: $("nota").value.trim(),
                });
                if (!r.ok) { return avisar(r.mensaje, true); }
                avisar(r.mensaje);
                /* Se recarga porque el boton de generar la orden solo aparece
                   cuando hay proveedor: sin recargar habria que explicarle a
                   Johan que vuelva atras y entre otra vez. */
                setTimeout(() => { location.reload(); }, 900);
            }));
        }

        document.querySelectorAll("[data-action='estado']").forEach((b) => {
            b.addEventListener("click", () => conBloqueo(b, async () => {
                const r = await rpc("/agrogood/api/compras/estado", {
                    request_id: +b.dataset.sol, accion: b.dataset.accion,
                });
                if (!r.ok) { return avisar(r.mensaje, true); }
                avisar(r.mensaje);
                setTimeout(() => { location.reload(); }, 900);
            }));
        });
    }

    function initOrden() {
        document.querySelectorAll("[data-action='orden-todas']").forEach((b) => {
            b.addEventListener("click", () => conBloqueo(b, async () => {
                const ids = (b.dataset.ids || "").split(",")
                    .filter(Boolean).map(Number);
                if (!ids.length) { return avisar("No hay solicitudes listas.", true); }
                const r = await rpc("/agrogood/api/compras/orden", {request_ids: ids});
                if (!r.ok) { return avisar(r.mensaje, true); }
                avisar(r.mensaje);
                setTimeout(() => { location.href = "/agrogood/compras"; }, 1800);
            }));
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        cargarProveedores();
        initSolicitud();
        initOrden();
    });
})();
