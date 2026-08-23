/* Mapa de seguimiento de rutas.
 *
 * Se refresca cada 30 segundos pidiendo solo lo nuevo. Recargar la pagina
 * entera perderia el encuadre que el jefe de logistica haya elegido, y eso
 * hace que se deje de mirar.
 */
(function () {
    "use strict";
    const datos = JSON.parse(document.getElementById("mp-datos").textContent || "{}");
    const mapa = L.map("mapa");
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap',
    }).addTo(mapa);

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
            if (d.result && d.result.rutas) pintar(d.result.rutas);
        } catch (e) { /* sin conexion: se mantiene lo ultimo pintado */ }
    }
    setInterval(refrescar, 30000);
})();
