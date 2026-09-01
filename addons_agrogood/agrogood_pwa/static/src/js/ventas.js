/* Tomar un pedido.
 *
 * Tres etapas en una sola pagina: cliente, productos, confirmar. El pedido
 * vive en memoria hasta que se pulsa Confirmar; solo entonces se crea en el
 * servidor. Asi no quedan borradores a medias cuando alguien se arrepiente o
 * se corta la llamada, que en el formulario estandar es lo que pasa.
 */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const estado = {
        cliente: null,
        lineas: new Map(),      // product_id -> {producto, qty}
        productos: [],
    };

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

    /* El aviso se muestra donde el usuario esta mirando, no en una alerta del
       navegador: las alertas se cierran por reflejo sin leerlas. */
    function avisar(texto, clase) {
        const t = $("ag-toast");
        if (!t) { return; }
        t.textContent = texto;
        t.className = "ag-toast ag-show " + (clase || "");
        setTimeout(() => { t.className = "ag-toast"; }, 4000);
    }

    const money = (n) => Math.round(n).toLocaleString("es-CL");

    /* ---------------------------------------------------------------
       Etapa 1: el cliente
       --------------------------------------------------------------- */

    let temporizador = null;
    function alTeclear(campo, accion) {
        campo.addEventListener("input", () => {
            clearTimeout(temporizador);
            // Se espera a que deje de teclear. Sin esto se lanza una busqueda
            // por letra y las respuestas llegan desordenadas: se ve la lista
            // de "TOM" despues de la de "TOMATE".
            temporizador = setTimeout(accion, 250);
        });
    }

    async function buscarClientes() {
        const q = $("q-cliente").value.trim();
        const lista = $("lista-clientes");
        const socios = await rpc("/agrogood/api/ventas/clientes", {q: q});
        lista.innerHTML = "";
        if (!socios.length) {
            lista.innerHTML = '<p class="ag-muted ag-pad">Ningun cliente con ese nombre.</p>';
            return;
        }
        socios.forEach((s) => {
            const el = document.createElement("button");
            el.type = "button";
            el.className = "ag-card";
            el.innerHTML =
                '<div class="ag-card-main">' +
                '<span class="ag-card-title"></span>' +
                '<span class="ag-card-sub"></span>' +
                "</div>" +
                '<span class="ag-chip"></span>';
            el.querySelector(".ag-card-title").textContent = s.nombre;
            el.querySelector(".ag-card-sub").textContent =
                s.linea + (s.direccion ? " · " + s.direccion : "");
            const chip = el.querySelector(".ag-chip");
            if (s.bloqueado) {
                chip.className = "ag-chip ag-chip-warn";
                chip.textContent = "Sin facturar";
            } else {
                chip.textContent = s.linea;
            }
            el.addEventListener("click", () => elegirCliente(s));
            lista.appendChild(el);
        });
    }

    async function elegirCliente(s) {
        estado.cliente = s;
        $("et-cliente").classList.add("ag-oculto");
        $("et-productos").classList.remove("ag-oculto");
        $("pie").classList.remove("ag-oculto");

        const cab = $("cabecera-cliente");
        cab.innerHTML = "";
        const nombre = document.createElement("div");
        nombre.className = "ag-client";
        nombre.textContent = s.nombre;
        cab.appendChild(nombre);
        const sub = document.createElement("div");
        sub.className = "ag-muted";
        sub.textContent = "Precios de " + s.linea;
        cab.appendChild(sub);
        if (s.bloqueado) {
            // Se dice ahora, no al confirmar. Enterarse de que no se le puede
            // facturar cuando el pedido ya esta tomado no sirve de nada.
            const w = document.createElement("div");
            w.className = "ag-warn";
            w.textContent = "Se le puede vender y repartir, pero no facturar: " +
                (s.motivo || "le faltan datos de facturacion");
            cab.appendChild(w);
        }
        await buscarProductos();
        $("q-producto").focus();
    }

    /* ---------------------------------------------------------------
       Etapa 2: los productos
       --------------------------------------------------------------- */

    async function buscarProductos() {
        const q = $("q-producto").value.trim();
        estado.productos = await rpc("/agrogood/api/ventas/productos", {
            partner_id: estado.cliente.id, q: q,
        });
        pintarProductos();
    }

    function pintarProductos() {
        const lista = $("lista-productos");
        lista.innerHTML = "";
        if (!estado.productos.length) {
            lista.innerHTML = '<p class="ag-muted ag-pad">Ningun producto con ese nombre.</p>';
            return;
        }
        estado.productos.forEach((p) => {
            const puesto = estado.lineas.get(p.id);
            const fila = document.createElement("div");
            fila.className = "ag-line" + (puesto ? " ag-line-puesta" : "");

            const cab = document.createElement("div");
            cab.className = "ag-line-head";
            const nom = document.createElement("span");
            nom.className = "ag-line-name";
            nom.textContent = p.nombre;
            cab.appendChild(nom);
            const precio = document.createElement("span");
            precio.className = "ag-precio";
            precio.textContent = money(p.precio) + " / " + p.uom;
            cab.appendChild(precio);
            fila.appendChild(cab);

            const sub = document.createElement("div");
            sub.className = "ag-muted";
            let texto = p.codigo ? p.codigo + " · " : "";
            texto += p.stock > 0 ? "hay " + p.stock + " " + p.uom : "sin stock";
            if (p.variable) { texto += " · peso variable"; }
            sub.textContent = texto;
            fila.appendChild(sub);

            /* Sin precio en la tarifa del cliente el producto saldria a cero.
               Se apaga la fila entera en vez de dejar pulsar y avisar despues:
               un boton que no hace nada se pulsa tres veces antes de leer. */
            if (p.sin_precio) {
                fila.classList.add("ag-line-sin-precio");
                precio.textContent = "sin precio";
                const aviso = document.createElement("div");
                aviso.className = "ag-warn";
                aviso.textContent = "No tiene precio en la tarifa de este " +
                    "cliente. Ventas debe ponerselo antes de venderlo.";
                fila.appendChild(aviso);
                lista.appendChild(fila);
                return;
            }

            const control = document.createElement("div");
            control.className = "ag-qty-row";
            const menos = document.createElement("button");
            menos.type = "button";
            menos.className = "ag-btn ag-btn-ghost ag-btn-qty";
            menos.textContent = "−";
            const campo = document.createElement("input");
            campo.type = "number";
            campo.className = "ag-qty";
            campo.min = "0";
            campo.step = "0.1";
            campo.inputMode = "decimal";
            campo.value = puesto ? puesto.qty : "";
            campo.placeholder = "0";
            const mas = document.createElement("button");
            mas.type = "button";
            mas.className = "ag-btn ag-btn-ghost ag-btn-qty";
            mas.textContent = "+";

            const fijar = (v) => {
                const n = Math.max(0, Math.round(v * 10) / 10);
                campo.value = n ? n : "";
                if (n > 0) {
                    estado.lineas.set(p.id, {producto: p, qty: n});
                    fila.classList.add("ag-line-puesta");
                } else {
                    estado.lineas.delete(p.id);
                    fila.classList.remove("ag-line-puesta");
                }
                pintarPie();
            };
            menos.addEventListener("click", () => fijar((parseFloat(campo.value) || 0) - 1));
            mas.addEventListener("click", () => fijar((parseFloat(campo.value) || 0) + 1));
            campo.addEventListener("change", () => fijar(parseFloat(campo.value) || 0));

            control.appendChild(menos);
            control.appendChild(campo);
            control.appendChild(mas);
            const uom = document.createElement("span");
            uom.className = "ag-uom";
            uom.textContent = p.uom;
            control.appendChild(uom);
            fila.appendChild(control);

            lista.appendChild(fila);
        });
    }

    function pintarPie() {
        let total = 0;
        estado.lineas.forEach((l) => { total += l.producto.precio * l.qty; });
        $("pie-lineas").textContent = estado.lineas.size === 1
            ? "1 linea" : estado.lineas.size + " lineas";
        $("pie-total").textContent = money(total);
        $("btn-confirmar").disabled = estado.lineas.size === 0;
    }

    async function repetirUltimo() {
        const r = await rpc("/agrogood/api/ventas/ultimo",
                            {partner_id: estado.cliente.id});
        if (!r.ok) { avisar(r.mensaje); return; }
        // Se piden los productos de aquel pedido para tener su precio DE HOY.
        // Copiar el precio anterior seria copiar la tarifa de la semana pasada.
        const ids = r.lineas.map((l) => l.id);
        const todos = await rpc("/agrogood/api/ventas/productos",
                                {partner_id: estado.cliente.id, q: ""});
        const porId = new Map(todos.map((p) => [p.id, p]));
        let puestas = 0;
        r.lineas.forEach((l) => {
            const p = porId.get(l.id);
            if (p) { estado.lineas.set(p.id, {producto: p, qty: l.qty}); puestas++; }
        });
        estado.productos = todos.filter((p) => ids.includes(p.id));
        pintarProductos();
        pintarPie();
        avisar("Copiado de " + r.referencia + ": " + puestas + " lineas. " +
               "Los precios son los de hoy.");
    }

    /* ---------------------------------------------------------------
       Etapa 3: confirmar
       --------------------------------------------------------------- */

    async function confirmar() {
        const boton = $("btn-confirmar");
        boton.disabled = true;
        boton.textContent = "Confirmando...";
        try {
            const lineas = [];
            estado.lineas.forEach((l, id) => lineas.push({id: id, qty: l.qty}));
            const r = await rpc("/agrogood/api/ventas/crear", {
                partner_id: estado.cliente.id, lineas: lineas,
            });
            if (!r.ok) { avisar(r.mensaje); return; }
            $("et-productos").classList.add("ag-oculto");
            $("pie").classList.add("ag-oculto");
            $("et-hecho").classList.remove("ag-oculto");
            let texto = r.nombre + " confirmado. " + money(r.total) + " sin IVA.";
            if (r.faltantes) {
                texto += " Faltan " + r.faltantes +
                    (r.faltantes === 1 ? " producto" : " productos") +
                    ": Compras ya tiene el aviso.";
            }
            $("hecho-texto").textContent = texto;
        } catch (e) {
            avisar(e.message || "No se pudo confirmar el pedido.");
        } finally {
            boton.disabled = false;
            boton.textContent = "Confirmar";
        }
    }

    /* --------------------------------------------------------------- */

    document.addEventListener("DOMContentLoaded", function () {
        if (!$("q-cliente")) { return; }
        alTeclear($("q-cliente"), buscarClientes);
        alTeclear($("q-producto"), buscarProductos);
        $("btn-repetir").addEventListener("click", repetirUltimo);
        $("btn-confirmar").addEventListener("click", confirmar);
        buscarClientes();
    });
})();
