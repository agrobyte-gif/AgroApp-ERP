/* Mapa de seguimiento de rutas.
 *
 * Se refresca cada 30 segundos pidiendo solo lo nuevo. Recargar la pagina
 * entera perderia el encuadre que el jefe de logistica haya elegido, y eso
 * hace que se deje de mirar.
 */
(function () {
    "use strict";
    const caja = document.getElementById("mapa");

    /* Un recuadro gris sin explicacion es el peor mensaje de error posible:
       no se distingue de una pagina rota, y quien lo ve no puede hacer nada.
       Este aviso dice que pasa y que comprobar. */
    function avisar(texto) {
        let el = document.getElementById("mp-aviso");
        if (!el) {
            el = document.createElement("div");
            el.id = "mp-aviso";
            el.className = "mp-aviso";
            caja.appendChild(el);
        }
        el.textContent = texto;
        el.style.display = texto ? "block" : "none";
    }

    if (typeof L === "undefined") {
        avisar("No se pudo cargar la libreria del mapa. Recarga la pagina; " +
               "si sigue igual, avisa al Administrador Tecnico.");
        return;
    }

    const datos = JSON.parse(document.getElementById("mp-datos").textContent || "{}");
    const mapa = L.map("mapa");

    const mosaicos = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap',
    });

    /* Las imagenes del mapa son lo unico de esta pagina que viene de fuera:
       Leaflet lo servimos nosotros, pero los mosaicos son de OpenStreetMap.
       Si el equipo no tiene salida a internet -o la red del almacen la
       filtra-, Leaflet se queda en silencio y deja el recuadro vacio. */
    let hayMosaicos = false;
    mosaicos.on("tileload", function () {
        hayMosaicos = true;
        const el = document.getElementById("mp-aviso");
        if (el && el.dataset.motivo === "red") avisar("");
    });
    mosaicos.on("tileerror", function () {
        if (hayMosaicos) return;               // un mosaico suelto no es un fallo
        const el = document.getElementById("mp-aviso");
        avisar("No se pueden cargar las imagenes del mapa. Este equipo necesita " +
               "salida a internet para verlas. Las rutas y las entregas siguen " +
               "funcionando igual.");
        (el || document.getElementById("mp-aviso")).dataset.motivo = "red";
    });
    mosaicos.addTo(mapa);

    /* Leaflet mide el recuadro al arrancar. Si en ese instante el navegador
       todavia no ha terminado de repartir el espacio -pasa con contenedores
       flexibles, que es justo lo que usa esta pagina-, lo mide como cero, no
       pide ningun mosaico y deja el hueco en blanco para siempre: nada vuelve
       a mirarlo. Recalcularlo cuando la pagina termina de cargar, y en cada
       cambio de tamano, cuesta nada y evita ese blanco. */
    function remedir() {
        if (mapa) mapa.invalidateSize();
    }
    window.addEventListener("load", remedir);
    window.addEventListener("resize", remedir);
    window.addEventListener("orientationchange", remedir);
    setTimeout(remedir, 300);

    // Iconos propios: no usamos los de Leaflet porque sus rutas de imagen
    // asumen una estructura de carpetas que aqui no existe.
    const icono = (color, texto) => L.divIcon({
        className: "",
        html: `<div style="background:${color};color:#fff;width:26px;height:26px;
               border-radius:50%;display:flex;align-items:center;justify-content:center;
               font:700 12px system-ui;border:2px solid #fff;
               box-shadow:0 1px 4px rgba(0,0,0,.4)">${texto}</div>`,
        iconSize: [26, 26], iconAnchor: [13, 13],
    });

    const capas = {};
    let primerAjuste = true;

    function pintar(rutas) {
        const limites = [];
        rutas.forEach((r) => {
            if (capas[r.id]) mapa.removeLayer(capas[r.id]);
            const grupo = L.layerGroup();

            // El recorrido del camion
            if (r.rastro && r.rastro.length > 1) {
                L.polyline(r.rastro, {color: r.color, weight: 4, opacity: .75}).addTo(grupo);
                r.rastro.forEach((p) => limites.push(p));
            }
            // Donde esta ahora
            if (r.posicion) {
                L.marker(r.posicion, {icon: icono(r.color, "▲")})
                    .bindPopup(`<b>${r.nombre}</b><br>${r.conductor}<br>` +
                               `${r.ultima ? "Ultima senal: " + r.ultima : "sin senal"}` +
                               `${r.bateria ? "<br>Bateria: " + r.bateria + "%" : ""}`)
                    .addTo(grupo);
                limites.push(r.posicion);
            }
            // Las paradas, numeradas en su orden de entrega
            (r.paradas_geo || []).forEach((p, i) => {
                const col = p.estado === "delivered" ? "#1C874F"
                          : (p.estado === "not_delivered" || p.estado === "rescheduled")
                          ? "#9E3226" : "#78877F";
                L.marker([p.lat, p.lng], {icon: icono(col, String(i + 1))})
                    .bindPopup(`<b>${p.cliente}</b><br>${p.direccion || ""}<br>${p.estado_txt}`)
                    .addTo(grupo);
                limites.push([p.lat, p.lng]);
            });
            grupo.addTo(mapa);
            capas[r.id] = grupo;
        });

        // Solo se encuadra la primera vez: despues manda el usuario.
        if (primerAjuste && limites.length) {
            mapa.fitBounds(limites, {padding: [40, 40]});
            primerAjuste = false;
        } else if (primerAjuste) {
            mapa.setView([-36.827, -73.05], 12);  // Gran Concepcion
            primerAjuste = false;
        }
    }

    pintar(datos.rutas || []);

    // Marca el recuadro cuando no hay nada que pintar, para que el CSS pueda
    // decirlo encima del mapa. Un mapa vacio sin explicacion parece averiado.
    function marcarVacio(rutas) {
        document.getElementById("mapa").dataset.vacio = rutas.length ? "0" : "1";
    }
    marcarVacio(datos.rutas || []);

    document.querySelectorAll(".mp-ruta").forEach((el) => {
        el.addEventListener("click", () => {
            const r = (datos.rutas || []).find((x) => String(x.id) === el.dataset.ruta);
            if (r && r.posicion) mapa.setView(r.posicion, 15);
        });
    });

    async function refrescar() {
        try {
            const res = await fetch("/agrogood/api/tracking/rutas", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({jsonrpc: "2.0", method: "call", params: {}}),
            });
            const d = await res.json();
            if (d.result && d.result.rutas) {
                pintar(d.result.rutas);
                marcarVacio(d.result.rutas);
            }
        } catch (e) { /* sin conexion: se mantiene lo ultimo pintado */ }
    }
    setInterval(refrescar, 30000);
})();
