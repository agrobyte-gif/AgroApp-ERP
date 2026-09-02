/* Caja chica: anotar un gasto de pie, con la boleta en la mano.
 *
 * El campo "por que no hay boleta" solo aparece cuando de verdad no hay foto.
 * Mostrarlo siempre lo convertiria en el camino corto -es mas rapido escribir
 * "no dieron" que sacar la foto- y a fin de mes no habria ni una boleta.
 */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const boton = $("btn-gasto");
    if (!boton) { return; }

    let boleta = null;

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
        setTimeout(() => { t.className = "ag-toast"; }, 6000);
    }

    function leerArchivo(f) {
        return new Promise((ok, mal) => {
            const lector = new FileReader();
            lector.onload = () => ok(lector.result.split(",")[1]);
            lector.onerror = mal;
            lector.readAsDataURL(f);
        });
    }

    const entrada = $("c-boleta");
    entrada.addEventListener("change", async () => {
        const f = entrada.files[0];
        if (!f) { return; }
        try {
            boleta = await leerArchivo(f);
            $("c-boleta-nombre").textContent = "Boleta lista: " + f.name;
            // Con foto, la excusa sobra y se esconde.
            $("c-sin-boleta").classList.add("ag-oculto");
            $("c-motivo").value = "";
        } catch (e) {
            avisar("No se pudo leer la foto. Intenta de nuevo.", true);
        }
    });

    boton.addEventListener("click", async () => {
        if (boton.disabled) { return; }
        const monto = parseFloat($("c-monto").value);
        if (isNaN(monto) || monto <= 0) {
            return avisar("Escribe cuanto se gasto.", true);
        }
        if (!$("c-categoria").value) {
            return avisar("Elige en que se gasto.", true);
        }
        // Sin foto se pide el motivo, y solo entonces aparece el campo.
        if (!boleta && !($("c-motivo").value || "").trim()) {
            $("c-sin-boleta").classList.remove("ag-oculto");
            $("c-motivo").focus();
            return avisar("Saca la foto de la boleta, o escribe por que no hay.",
                          true);
        }
        const texto = boton.textContent;
        boton.disabled = true;
        boton.textContent = "Un momento...";
        try {
            const r = await rpc("/agrogood/api/caja/gasto", {
                amount: monto,
                category: $("c-categoria").value,
                note: $("c-detalle").value,
                receipt: boleta,
                no_receipt_reason: $("c-motivo").value,
            });
            if (!r.ok) {
                avisar(r.mensaje, true);
                return;
            }
            $("hecho-texto").textContent = r.mensaje;
            $("et-form").classList.add("ag-oculto");
            $("et-hecho").classList.remove("ag-oculto");
        } catch (e) {
            avisar(e.message || "No se pudo anotar el gasto.", true);
        } finally {
            boton.disabled = false;
            boton.textContent = texto;
        }
    });
})();
