/* Bodega: recibir una compra y registrar mermas.
 *
 * Las dos pantallas comparten archivo porque comparten la mitad del codigo y
 * son el mismo trabajo: anotar lo que de verdad hay, no lo que deberia haber.
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

    /* Un boton que se puede pulsar dos veces mientras el servidor responde
       registra la recepcion dos veces. Se bloquea mientras dura. */
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
       Recibir una compra
       --------------------------------------------------------------- */

    function initRecepcion() {
        const boton = document.querySelector("[data-action='recibir']");
        if (!boton) { return; }

        boton.addEventListener("click", () => conBloqueo(boton, async () => {
            const lineas = [];
            let faltaLote = null;
            document.querySelectorAll(".ag-line[data-move]").forEach((fila) => {
                const qty = parseFloat(fila.querySelector(".ag-recibido").value) || 0;
                const campoLote = fila.querySelector(".ag-lote");
                const lote = campoLote ? campoLote.value.trim() : "";
                const campoVence = fila.querySelector(".ag-vence");
                if (fila.dataset.lote === "1" && qty > 0 && !lote && !faltaLote) {
                    faltaLote = fila.querySelector(".ag-line-name").textContent;
                }
                lineas.push({
                    move_id: +fila.dataset.move,
                    qty: qty,
                    lote: lote,
                    vence: campoVence ? campoVence.value : null,
                });
            });

            /* Se avisa aqui y no se manda al servidor para que lo rechace: el
               mensaje llega antes y dice cual falta, con la pantalla delante. */
            if (faltaLote) {
                return avisar("Falta el numero de lote de " + faltaLote, true);
            }
            if (!lineas.some((l) => l.qty > 0)) {
                return avisar("No has anotado ninguna cantidad recibida.", true);
            }

            const r = await rpc("/agrogood/api/bodega/recibir", {
                picking_id: +boton.dataset.picking,
                lineas: lineas,
            });
            if (!r.ok) { return avisar(r.mensaje, true); }
            avisar(r.mensaje);
            setTimeout(() => { location.href = "/agrogood/bodega"; }, 1200);
        }));
    }

    /* ---------------------------------------------------------------
       Registrar una merma
       --------------------------------------------------------------- */

    function initMerma() {
        const campo = $("q-merma");
        if (!campo) { return; }
        let elegido = null;
        let temporizador = null;

        async function buscar() {
            const productos = await rpc("/agrogood/api/bodega/productos",
                                        {q: campo.value.trim()});
            const lista = $("lista-merma");
            lista.innerHTML = "";
            if (!productos.length) {
                lista.innerHTML = '<p class="ag-muted ag-pad">Ningun producto con ese nombre.</p>';
                return;
            }
            productos.forEach((p) => {
                const el = document.createElement("button");
                el.type = "button";
                el.className = "ag-card";
                el.innerHTML = '<div class="ag-card-main">' +
                    '<span class="ag-card-title"></span>' +
                    '<span class="ag-card-sub"></span></div>' +
                    '<span class="ag-chip"></span>';
                el.querySelector(".ag-card-title").textContent = p.nombre;
                el.querySelector(".ag-card-sub").textContent =
                    (p.codigo ? p.codigo + " · " : "") + "hay " + p.stock + " " + p.uom;
                el.querySelector(".ag-chip").textContent = p.uom;
                el.addEventListener("click", async () => {
                    elegido = p;
                    $("lista-merma").innerHTML = "";
                    campo.classList.add("ag-oculto");
                    $("merma-form").classList.remove("ag-oculto");
                    $("merma-producto").textContent = p.nombre;
                    $("merma-stock").textContent = "hay " + p.stock + " " + p.uom;
                    $("merma-uom").textContent = p.uom;

                    /* Con caducidad hay que decir de que lote. Se cargan aqui,
                       al elegir el producto, y no al enviar: si no queda
                       ninguno con existencias conviene saberlo antes de
                       teclear la cantidad. */
                    const caja = $("merma-lote-caja");
                    const sel = $("merma-lote");
                    sel.innerHTML = '<option value="">De que lote</option>';
                    if (p.lleva_lote) {
                        caja.classList.remove("ag-oculto");
                        const lotes = await rpc("/agrogood/api/bodega/lotes",
                                                {product_id: p.id});
                        lotes.forEach((l) => {
                            const o = document.createElement("option");
                            o.value = l.id;
                            o.textContent = l.nombre + " · " + l.cantidad + " " + p.uom +
                                (l.vence ? " · vence " + l.vence : "");
                            sel.appendChild(o);
                        });
                        if (!lotes.length) {
                            avisar("Este producto no tiene lotes con existencias.", true);
                        }
                    } else {
                        caja.classList.add("ag-oculto");
                    }
                    $("merma-qty").focus();
                });
                lista.appendChild(el);
            });
        }

        campo.addEventListener("input", () => {
            clearTimeout(temporizador);
            temporizador = setTimeout(buscar, 250);
        });
        buscar();

        /* Dos de los ocho motivos -llego mal del proveedor, danado en
           transporte- son reclamables, y entonces hace falta decir a quien.
           El selector solo aparece en esos casos. */
        const RECLAMABLES = ["supplier", "damaged_transport"];
        let responsablesCargados = false;
        $("merma-motivo").addEventListener("change", async () => {
            const caja = $("merma-responsable-caja");
            if (RECLAMABLES.indexOf($("merma-motivo").value) === -1) {
                caja.classList.add("ag-oculto");
                $("merma-responsable").value = "";
                return;
            }
            caja.classList.remove("ag-oculto");
            if (responsablesCargados) { return; }
            const gente = await rpc("/agrogood/api/bodega/responsables", {q: ""});
            const sel = $("merma-responsable");
            gente.forEach((g) => {
                const o = document.createElement("option");
                o.value = g.id;
                o.textContent = g.nombre;
                sel.appendChild(o);
            });
            responsablesCargados = true;
            if (!gente.length) {
                avisar("No hay proveedores dados de alta para reclamarles.", true);
            }
        });

        const boton = document.querySelector("[data-action='merma']");
        boton.addEventListener("click", () => conBloqueo(boton, async () => {
            const qty = parseFloat($("merma-qty").value) || 0;
            const motivo = $("merma-motivo").value;
            if (!elegido) { return avisar("Elige un producto.", true); }
            if (qty <= 0) { return avisar("Escribe cuanto se perdio.", true); }
            if (!motivo) { return avisar("Elige por que se perdio.", true); }
            const lote = $("merma-lote").value;
            if (elegido.lleva_lote && !lote) {
                return avisar("Este producto lleva caducidad: di de que lote.", true);
            }
            const responsable = $("merma-responsable").value;
            if (RECLAMABLES.indexOf(motivo) !== -1 && !responsable) {
                return avisar("Esta merma se puede reclamar: di a quien.", true);
            }
            const r = await rpc("/agrogood/api/bodega/merma", {
                product_id: elegido.id, qty: qty, reason: motivo,
                note: $("merma-nota").value.trim(),
                partner_id: responsable ? +responsable : null,
                lot_id: lote ? +lote : null,
            });
            if (!r.ok) { return avisar(r.mensaje, true); }
            avisar(r.mensaje);
            setTimeout(() => { location.href = "/agrogood/bodega"; }, 1200);
        }));
    }

    document.addEventListener("DOMContentLoaded", function () {
        initRecepcion();
        initMerma();
    });
})();
