/* Agrogood movil.
   JavaScript deliberadamente minimo: sin framework, sin bundle. Todo lo que
   hace es llamar a los endpoints JSON de Odoo y refrescar lo justo. */

(function () {
    "use strict";

    // ---------------------------------------------------------------
    // Llamada al servidor (formato JSON-RPC de Odoo)
    // ---------------------------------------------------------------
    async function llamar(ruta, params) {
        let res;
        try {
            res = await fetch(ruta, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: params || {} }),
            });
        } catch (e) {
            // fetch solo revienta asi cuando no hubo red: el servidor no llego
            // a contestar. Es distinto de un error del servidor -ahi si hay
            // respuesta- y el mensaje tiene que decir que reintente, no que
            // algo salio mal, porque no salio mal: no salio.
            estadoConexion();
            throw new Error("Sin conexion. Lo que anotaste no se guardo; "
                + "reintenta cuando vuelva la senal.");
        }
        const data = await res.json();
        if (data.error) {
            const d = data.error.data || {};
            throw new Error(d.message || data.error.message || "Error del servidor");
        }
        return data.result;
    }

    // Enciende o apaga la barra de sin conexion segun el estado del telefono.
    function estadoConexion() {
        const barra = document.getElementById("ag-offline");
        if (barra) { barra.hidden = navigator.onLine; }
    }

    function aviso(texto, esError) {
        const el = document.getElementById("ag-toast");
        if (!el) return;
        el.textContent = texto;
        el.classList.toggle("ag-error", !!esError);
        el.classList.add("ag-show");
        clearTimeout(el._t);
        el._t = setTimeout(() => el.classList.remove("ag-show"), 3200);
    }

    // Evita el doble toque accidental, que en una pantalla de bodega es
    // constante: se bloquea el boton mientras la peticion esta en vuelo.
    async function conBloqueo(boton, fn) {
        if (boton.disabled) return;
        boton.disabled = true;
        try {
            await fn();
        } catch (e) {
            aviso(e.message || String(e), true);
        } finally {
            boton.disabled = false;
        }
    }

    const leerArchivo = (file) => new Promise((ok, err) => {
        const r = new FileReader();
        r.onload = () => ok(String(r.result).split(",")[1]);
        r.onerror = err;
        r.readAsDataURL(file);
    });

    // La ubicacion es evidencia, no un requisito: si el navegador la niega o
    // tarda, la entrega se registra igual. Bloquear una entrega por el GPS
    // seria dejar tirado al conductor en un subterraneo.
    const ubicacion = () => new Promise((ok) => {
        if (!navigator.geolocation) return ok({});
        navigator.geolocation.getCurrentPosition(
            (p) => ok({ latitude: p.coords.latitude, longitude: p.coords.longitude }),
            () => ok({}),
            { timeout: 4000, maximumAge: 60000 }
        );
    });

    // ---------------------------------------------------------------
    // Picker
    // ---------------------------------------------------------------
    function initPicker() {
        document.querySelectorAll("[data-action='start']").forEach((b) => {
            b.addEventListener("click", () => conBloqueo(b, async () => {
                const r = await llamar("/agrogood/api/picker/start",
                                       { session_id: +b.dataset.session });
                if (!r.ok) return aviso(r.mensaje, true);
                location.reload();
            }));
        });

        const cont = document.querySelector(".ag-lines");
        if (!cont) return;
        const sessionId = +cont.dataset.session;

        cont.querySelectorAll(".ag-line").forEach((linea) => {
            const input = linea.querySelector(".ag-qty");
            const avisoEl = linea.querySelector(".ag-warn");
            const pedido = parseFloat(linea.dataset.ordered || "0");
            const tolerancia = parseFloat(linea.dataset.tolerance || "0");
            const esVariable = linea.dataset.variable === "1";

            function revisarDesviacion() {
                if (!esVariable || !tolerancia || !pedido || !avisoEl) return;
                const v = parseFloat(input.value || "0");
                const desv = ((v - pedido) / pedido) * 100;
                const fuera = Math.abs(desv) > tolerancia;
                input.classList.toggle("ag-out", fuera);
                avisoEl.hidden = !fuera;
                if (fuera) {
                    avisoEl.textContent =
                        `Se pidieron ${pedido} y pusiste ${v} (${desv > 0 ? "+" : ""}` +
                        `${desv.toFixed(0)}%). Revisa la coma o explica la incidencia.`;
                }
            }

            if (input) {
                input.addEventListener("input", revisarDesviacion);
                revisarDesviacion();
            }

            linea.querySelectorAll(".ag-step").forEach((b) => {
                b.addEventListener("click", () => {
                    const paso = parseFloat(b.dataset.step);
                    input.value = Math.max(0, (parseFloat(input.value || "0") + paso))
                        .toFixed(2).replace(/\.00$/, "");
                    revisarDesviacion();
                });
            });

            linea.querySelectorAll("[data-status]").forEach((b) => {
                b.addEventListener("click", () => conBloqueo(b, async () => {
                    const nota = linea.querySelector(".ag-note");
                    const r = await llamar("/agrogood/api/picker/line", {
                        session_id: sessionId,
                        move_id: +linea.dataset.move,
                        status: b.dataset.status,
                        quantity: input ? parseFloat(input.value || "0") : undefined,
                        note: nota ? nota.value : undefined,
                    });
                    if (!r.ok) return aviso(r.mensaje, true);
                    const et = linea.querySelector(".ag-line-status");
                    et.dataset.status = r.estado;
                    et.textContent = b.textContent.trim();
                    linea.dataset.done = "1";
                    aviso("Guardado");
                }));
            });
        });

        document.querySelectorAll("[data-action='finish']").forEach((b) => {
            b.addEventListener("click", () => conBloqueo(b, async () => {
                const r = await llamar("/agrogood/api/picker/finish",
                                       { session_id: +b.dataset.session });
                if (!r.ok) return aviso(r.mensaje, true);
                location.href = "/agrogood/picker";
            }));
        });
    }

    // ---------------------------------------------------------------
    // Conductor
    // ---------------------------------------------------------------
    function initDriver() {
        document.querySelectorAll("[data-action='route_start'], [data-action='route_finish']")
            .forEach((b) => {
                b.addEventListener("click", () => conBloqueo(b, async () => {
                    const ruta = b.dataset.action === "route_start"
                        ? "/agrogood/api/driver/route_start"
                        : "/agrogood/api/driver/route_finish";
                    const r = await llamar(ruta, { route_id: +b.dataset.route });
                    if (!r.ok) return aviso(r.mensaje, true);
                    location.reload();
                }));
            });

        /* Revision del vehiculo antes de salir. Todas las casillas nacen
           marcadas: lo normal es que el camion este bien, y obligar a marcar
           seis veces lo que casi siempre se cumple convierte la revision en un
           tramite. Aqui se DESMARCA lo que falla. */
        const btnRevision = document.querySelector("[data-action='revision']");
        if (btnRevision) {
            btnRevision.addEventListener("click", () => conBloqueo(btnRevision, async () => {
                const marcados = Array.from(
                    document.querySelectorAll(".ag-check-input:checked")
                ).map((c) => c.value);
                const nota = (document.getElementById("ag-revision-nota").value || "").trim();
                const km = document.getElementById("ag-odometro").value;
                const total = document.querySelectorAll(".ag-check-input").length;
                if (marcados.length < total && !nota) {
                    return aviso("Desmarcaste algo: cuenta que encontraste.", true);
                }
                const r = await llamar("/agrogood/api/driver/revision", {
                    route_id: +btnRevision.dataset.route,
                    marcados: marcados,
                    note: nota,
                    odometer: km ? parseFloat(km) : null,
                });
                if (!r.ok) return aviso(r.mensaje, true);
                aviso(r.mensaje, r.estado === "warning");
                setTimeout(() => {
                    location.href = "/agrogood/driver/route/" + btnRevision.dataset.route;
                }, 1200);
            }));
        }

        const zona = document.querySelector(".ag-stop-actions");
        if (!zona) return;
        const stopId = +zona.dataset.stop;

        const inputFoto = document.getElementById("ag-photo");
        if (inputFoto) {
            inputFoto.addEventListener("change", () => {
                const n = document.getElementById("ag-photo-name");
                if (n) n.textContent = inputFoto.files[0]
                    ? "Foto lista: " + inputFoto.files[0].name : "";
            });
        }

        zona.querySelectorAll("[data-action]").forEach((b) => {
            b.addEventListener("click", () => conBloqueo(b, async () => {
                const accion = b.dataset.action;
                const params = { stop_id: stopId, accion: accion };

                if (accion === "delivered") {
                    const rec = document.getElementById("ag-received");
                    if (rec && rec.value) params.received_by = rec.value;
                    if (inputFoto && inputFoto.files[0]) {
                        params.photo = await leerArchivo(inputFoto.files[0]);
                    }
                }
                if (accion === "not_delivered" || accion === "rescheduled") {
                    const motivo = document.getElementById("ag-reason");
                    if (!motivo || !motivo.value) {
                        return aviso("Elige primero el motivo.", true);
                    }
                    params.reason = motivo.value;
                    const nota = document.getElementById("ag-stopnote");
                    if (nota && nota.value) params.note = nota.value;
                }
                if (accion === "rescheduled") {
                    // La fecha se pide aqui y el servidor la vuelve a exigir.
                    // Avisar en el telefono ahorra el viaje de ida y vuelta,
                    // que en la calle y con mala senal no es gratis.
                    const dia = document.getElementById("ag-reprograma");
                    if (!dia || !dia.value) {
                        return aviso("Di para que dia se reprograma.", true);
                    }
                    params.fecha = dia.value;
                }
                if (accion !== "arrived") {
                    Object.assign(params, await ubicacion());
                }
                const r = await llamar("/agrogood/api/driver/stop", params);
                if (!r.ok) return aviso(r.mensaje, true);
                location.reload();
            }));
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        initPicker();
        initDriver();
        // La barra de sin conexion se pinta al cargar y cada vez que el
        // telefono gana o pierde la senal.
        estadoConexion();
        window.addEventListener("online", estadoConexion);
        window.addEventListener("offline", estadoConexion);
        if ("serviceWorker" in navigator) {
            navigator.serviceWorker
                .register("/agrogood_pwa/static/src/js/service-worker.js")
                .catch(() => { /* sin service worker la app funciona igual */ });
        }
    });
})();
