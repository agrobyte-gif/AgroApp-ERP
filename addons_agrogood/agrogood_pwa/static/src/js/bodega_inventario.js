/* Bodega: contar un producto y dejar el sistema en lo contado.
 *
 * La diferencia se muestra ANTES de guardar. Un ajuste es dinero que aparece o
 * desaparece del balance sin que nadie haya comprado ni vendido nada, y ver
 * "faltan 40 kg" antes de tocar el boton es lo que hace que alguien vuelva a
 * contar en vez de confirmar un dedazo.
 */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    if (!$("q-producto") || !$("btn-ajustar")) { return; }

    let actual = null;   // lo que devolvio el servidor del producto elegido

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

    // --- buscar ---------------------------------------------------------
    let temporizador = null;
    $("q-producto").addEventListener("input", () => {
        clearTimeout(temporizador);
        temporizador = setTimeout(buscar, 250);
    });

    async function buscar() {
        const q = $("q-producto").value.trim();
        const lista = $("lista-productos");
        if (q.length < 2) { lista.innerHTML = ""; return; }
        const productos = await rpc("/agrogood/api/bodega/productos", {q: q});
        lista.innerHTML = "";
        productos.forEach((p) => {
            const b = document.createElement("button");
            b.type = "button";
            b.className = "ag-card";
            b.innerHTML = '<div class="ag-card-main">'
                + '<span class="ag-card-title"></span>'
                + '<span class="ag-card-sub"></span></div>';
            b.querySelector(".ag-card-title").textContent = p.nombre;
            b.querySelector(".ag-card-sub").textContent =
                (p.codigo ? p.codigo + " · " : "") + (p.uom || "");
            b.addEventListener("click", () => elegir(p.id));
            lista.appendChild(b);
        });
    }

    async function elegir(id) {
        actual = await rpc("/agrogood/api/bodega/existencias", {product_id: id});
        $("p-nombre").textContent = actual.nombre;
        $("p-actual").textContent =
            "El sistema dice " + actual.existencias + " " + actual.uom;

        const zonaLotes = $("p-lotes");
        const selector = $("p-lote");
        selector.innerHTML = "";
        if (actual.por_lote) {
            zonaLotes.classList.remove("ag-oculto");
            actual.lotes.forEach((l) => {
                const o = document.createElement("option");
                o.value = l.id;
                o.textContent = l.nombre + " · " + l.cantidad + " " + actual.uom
                    + (l.vence ? " · vence " + l.vence : "");
                selector.appendChild(o);
            });
            if (!actual.lotes.length) {
                const o = document.createElement("option");
                o.value = "";
                o.textContent = "Sin lotes con existencias";
                selector.appendChild(o);
            }
        } else {
            zonaLotes.classList.add("ag-oculto");
        }

        $("p-contado").value = "";
        $("p-motivo").value = "";
        $("p-diferencia").textContent = "";
        $("lista-productos").innerHTML = "";
        $("q-producto").value = "";
        $("et-contar").classList.remove("ag-oculto");
        $("p-contado").focus();
    }

    // --- la diferencia, antes de guardar --------------------------------
    function esperado() {
        if (!actual) { return 0; }
        if (!actual.por_lote) { return actual.existencias; }
        const lote = actual.lotes.find(
            (l) => String(l.id) === $("p-lote").value);
        return lote ? lote.cantidad : 0;
    }

    function pintarDiferencia() {
        const contado = parseFloat($("p-contado").value);
        const zona = $("p-diferencia");
        if (isNaN(contado)) { zona.textContent = ""; return; }
        const dif = Number((contado - esperado()).toFixed(2));
        if (dif === 0) {
            zona.textContent = "Cuadra exacto.";
            zona.classList.remove("ag-warn");
        } else {
            zona.textContent = (dif > 0 ? "Sobran " : "Faltan ")
                + Math.abs(dif) + " " + actual.uom + " respecto de lo que dice"
                + " el sistema.";
            zona.classList.add("ag-warn");
        }
    }

    $("p-contado").addEventListener("input", pintarDiferencia);
    $("p-lote").addEventListener("change", pintarDiferencia);

    // --- guardar --------------------------------------------------------
    $("btn-ajustar").addEventListener("click", async () => {
        const boton = $("btn-ajustar");
        if (boton.disabled || !actual) { return; }
        const contado = parseFloat($("p-contado").value);
        if (isNaN(contado)) {
            return avisar("Escribe cuanto hay de verdad.", true);
        }
        const motivo = ($("p-motivo").value || "").trim();
        if (!motivo) {
            return avisar("Anota por que cuadra distinto.", true);
        }
        const dif = Number((contado - esperado()).toFixed(2));
        if (dif !== 0 && !window.confirm(
                (dif > 0 ? "Sobran " : "Faltan ") + Math.abs(dif) + " "
                + actual.uom + ". Dejarlo en " + contado + "?")) {
            return;
        }
        const texto = boton.textContent;
        boton.disabled = true;
        boton.textContent = "Un momento...";
        try {
            const r = await rpc("/agrogood/api/bodega/ajustar", {
                product_id: actual.id,
                contado: contado,
                motivo: motivo,
                lot_id: actual.por_lote ? ($("p-lote").value || null) : null,
            });
            avisar(r.mensaje, !r.ok);
            if (r.ok) { setTimeout(() => window.location.reload(), 1200); }
        } catch (e) {
            avisar(e.message || "No se pudo ajustar.", true);
        } finally {
            boton.disabled = false;
            boton.textContent = texto;
        }
    });

    $("btn-otro").addEventListener("click", () => {
        $("et-contar").classList.add("ag-oculto");
        actual = null;
        $("q-producto").focus();
    });
})();
