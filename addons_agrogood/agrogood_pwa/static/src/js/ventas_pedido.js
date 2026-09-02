/* Ventas: cambiar una orden ya tomada.
 *
 * El cliente llama a media manana para agregar dos kilos. Toda la pantalla
 * esta hecha para resolver eso sin colgar el telefono: las lineas ya estan
 * escritas en la pagina, se tocan los mas y los menos, y se guarda.
 *
 * Se manda el pedido ENTERO al guardar, no una lista de cambios. Con dos
 * personas editando el mismo pedido desde dos telefonos, una lista de cambios
 * se aplica sobre un pedido que ya no es el que se vio y el resultado no es
 * ninguno de los dos. Mandandolo entero gana el ultimo que guarda, que es un
 * resultado que al menos se puede explicar por telefono.
 */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const contenedor = $("lineas");
    if (!contenedor) { return; }

    const PEDIDO = parseInt(contenedor.dataset.pedido, 10);
    const EDITABLE = contenedor.dataset.editable === "1";

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

    async function conBloqueo(boton, fn) {
        if (boton.disabled) { return; }
        const texto = boton.textContent;
        boton.disabled = true;
        boton.textContent = "Un momento...";
        try {
            await fn();
        } catch (e) {
            avisar(e.message || "No se pudo guardar.", true);
        } finally {
            boton.disabled = false;
            boton.textContent = texto;
        }
    }

    function lineasActuales() {
        return Array.from(contenedor.querySelectorAll(".ag-line")).map((el) => ({
            id: parseInt(el.dataset.producto, 10),
            qty: parseFloat(el.querySelector(".ag-qty").value) || 0,
        }));
    }

    // --- los mas y los menos -------------------------------------------
    contenedor.addEventListener("click", (ev) => {
        const boton = ev.target.closest("[data-paso]");
        if (!boton || !EDITABLE) { return; }
        const campo = boton.closest(".ag-line").querySelector(".ag-qty");
        const paso = parseFloat(boton.dataset.paso);
        // Nunca por debajo de cero: cero ya significa "quitar esta linea", y
        // un negativo no significa nada que se pueda vender.
        const nuevo = Math.max(0, (parseFloat(campo.value) || 0) + paso);
        campo.value = Number(nuevo.toFixed(2));
        marcarSiSeVa(campo);
    });

    contenedor.addEventListener("input", (ev) => {
        if (ev.target.classList.contains("ag-qty")) { marcarSiSeVa(ev.target); }
    });

    function marcarSiSeVa(campo) {
        // Que se vea antes de guardar que esa linea va a desaparecer. Sin la
        // marca, un cero por descuido borra un producto y nadie lo nota hasta
        // que Bodega no lo prepara.
        const linea = campo.closest(".ag-line");
        const cero = (parseFloat(campo.value) || 0) <= 0;
        linea.classList.toggle("ag-line-sin-precio", cero);
    }

    // --- agregar productos ---------------------------------------------
    const buscador = $("q-producto");
    const lista = $("lista-productos");
    let temporizador = null;

    if (buscador) {
        buscador.addEventListener("input", () => {
            clearTimeout(temporizador);
            temporizador = setTimeout(buscar, 250);
        });
    }

    async function buscar() {
        const q = buscador.value.trim();
        if (q.length < 2) { lista.innerHTML = ""; return; }
        const productos = await rpc("/agrogood/api/ventas/productos", {q: q});
        lista.innerHTML = "";
        productos.forEach((p) => {
            if (contenedor.querySelector('[data-producto="' + p.id + '"]')) { return; }
            const b = document.createElement("button");
            b.type = "button";
            b.className = "ag-card";
            b.innerHTML = '<div class="ag-card-main">'
                + '<span class="ag-card-title"></span>'
                + '<span class="ag-card-sub"></span></div>';
            b.querySelector(".ag-card-title").textContent = p.nombre;
            b.querySelector(".ag-card-sub").textContent = p.uom || "";
            b.addEventListener("click", () => agregar(p));
            lista.appendChild(b);
        });
    }

    function agregar(p) {
        const el = document.createElement("div");
        el.className = "ag-line";
        el.dataset.producto = p.id;
        el.innerHTML = '<div class="ag-line-head">'
            + '<span class="ag-line-name"></span>'
            + '<span class="ag-uom"></span></div>'
            + '<div class="ag-qty-row">'
            + '<button type="button" class="ag-btn-qty" data-paso="-1">−</button>'
            + '<input type="number" class="ag-qty" step="0.1" min="0" value="1"/>'
            + '<button type="button" class="ag-btn-qty" data-paso="1">+</button></div>';
        el.querySelector(".ag-line-name").textContent = p.nombre;
        el.querySelector(".ag-uom").textContent = p.uom || "";
        contenedor.appendChild(el);
        lista.innerHTML = "";
        buscador.value = "";
        el.querySelector(".ag-qty").focus();
    }

    // --- guardar y anular ----------------------------------------------
    const guardar = $("btn-guardar");
    if (guardar) {
        guardar.addEventListener("click", () => conBloqueo(guardar, async () => {
            const r = await rpc("/agrogood/api/ventas/modificar",
                                {order_id: PEDIDO, lineas: lineasActuales()});
            avisar(r.mensaje, !r.ok);
            if (r.ok) {
                // Se recarga en lugar de repintar a mano: despues de cambiar
                // las lineas cambian tambien los faltantes y la etapa, y
                // repintarlos por separado es donde la pantalla empieza a
                // mentir.
                setTimeout(() => window.location.reload(), 900);
            }
        }));
    }

    const anular = $("btn-anular");
    if (anular) {
        anular.addEventListener("click", () => conBloqueo(anular, async () => {
            const motivo = ($("motivo-anular").value || "").trim();
            if (!motivo) {
                avisar("Anota por que se anula.", true);
                return;
            }
            if (!window.confirm("Anular esta orden? No se puede deshacer desde aqui.")) {
                return;
            }
            const r = await rpc("/agrogood/api/ventas/anular",
                                {order_id: PEDIDO, motivo: motivo});
            avisar(r.mensaje, !r.ok);
            if (r.ok) {
                setTimeout(() => { window.location.href = "/agrogood/ventas"; }, 900);
            }
        }));
    }
})();
