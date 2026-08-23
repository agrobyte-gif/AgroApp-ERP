/* Agroapp - envoltorio nativo Android.
 *
 * La app hace tres cosas y solo tres:
 *   1. Guarda el servidor y la sesion, para que el conductor no teclee una IP
 *      cada manana.
 *   2. Mantiene el rastreo de ubicacion vivo aunque el telefono deje la app en
 *      segundo plano. Esto es lo unico que una PWA no puede hacer, y es la
 *      razon por la que existe este envoltorio.
 *   3. Abre la interfaz web que ya funciona. No se reimplementa nada: la
 *      pantalla del conductor sigue siendo la misma, y una correccion en el
 *      servidor le llega sin pasar por la tienda de aplicaciones.
 */

const { Preferences } = Capacitor.Plugins;
const Fondo = Capacitor.Plugins.BackgroundGeolocation;

const S = {
    servidor: null,
    rutaId: null,
    vigilante: null,
    cola: [],
    enviados: 0,
};

const $ = (id) => document.getElementById(id);
const mostrar = (id) => {
    document.querySelectorAll(".pantalla").forEach((p) => p.classList.remove("activa"));
    $(id).classList.add("activa");
};
const error = (t) => { const e = $("err"); e.textContent = t; e.style.display = t ? "block" : "none"; };

async function guardar(k, v) { await Preferences.set({ key: k, value: String(v) }); }
async function leer(k) { return (await Preferences.get({ key: k })).value; }

/* -------------------------------------------------------------------
   Comunicacion con Odoo
   ------------------------------------------------------------------- */

async function rpc(ruta, params) {
    const r = await fetch(S.servidor + ruta, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: params || {} }),
    });
    const d = await r.json();
    if (d.error) throw new Error(d.error.data?.message || d.error.message);
    return d.result;
}

async function entrar(servidor, login, clave) {
    S.servidor = servidor.replace(/\/+$/, "");
    const r = await fetch(S.servidor + "/web/session/authenticate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
            jsonrpc: "2.0", method: "call",
            params: { db: null, login: login, password: clave },
        }),
    });
    const d = await r.json();
    if (d.error) throw new Error("Usuario o contrasena incorrectos");
    return d.result;
}

/* -------------------------------------------------------------------
   Rastreo en segundo plano
   ------------------------------------------------------------------- */

async function arrancarRastreo() {
    if (S.vigilante) return;
    S.vigilante = await Fondo.addWatcher({
        // Android exige mostrar este aviso permanente mientras se use la
        // ubicacion en segundo plano. No se puede ocultar, asi que al menos
        // dice la verdad: por que esta encendido y cuando se apaga.
        backgroundMessage: "Enviando tu ubicacion a Logistica durante la ruta",
        backgroundTitle: "Reparto en curso",
        requestPermissions: true,
        stale: false,
        distanceFilter: 40,
    }, function (posicion, err) {
        if (err) {
            // Si el conductor niega el permiso no se insiste: la app sigue
            // sirviendo para entregar, solo que sin mapa.
            if (err.code === "NOT_AUTHORIZED") pintarEstado(false, "Permiso de ubicacion denegado");
            return;
        }
        S.cola.push({
            latitude: posicion.latitude,
            longitude: posicion.longitude,
            accuracy: posicion.accuracy,
            speed: posicion.speed ? posicion.speed * 3.6 : 0,
            is_moving: !!posicion.speed,
            timestamp: new Date(posicion.time || Date.now()).toISOString().slice(0, 19).replace("T", " "),
        });
        if (S.cola.length >= 3) vaciarCola();
    });
    pintarEstado(true);
}

async function pararRastreo() {
    if (!S.vigilante) return;
    await vaciarCola();
    await Fondo.removeWatcher({ id: S.vigilante });
    S.vigilante = null;
    pintarEstado(false);
}

/* La cola es lo que hace util el rastreo en un camion: entre bodegas y calles
   estrechas se pierde cobertura constantemente. Las posiciones se acumulan y
   se envian juntas al recuperar red; si el envio falla, se vuelven a poner en
   la cola en vez de descartarse. */
async function vaciarCola() {
    if (!S.cola.length || !S.rutaId) return;
    const lote = S.cola.splice(0, S.cola.length);
    try {
        const r = await rpc("/agrogood/api/driver/positions",
                            { route_id: S.rutaId, positions: lote });
        if (r && r.detener) { await pararRastreo(); S.rutaId = null; }
        S.enviados += (r && r.guardadas) || 0;
        $("e-envios").textContent = `${S.enviados} posiciones enviadas en esta ruta`;
    } catch (e) {
        S.cola = lote.concat(S.cola);
    }
}

function pintarEstado(activo, texto) {
    const p = $("e-pastilla");
    p.className = "pastilla " + (activo ? "on" : "off");
    p.querySelector(".punto").className = "punto" + (activo ? " late" : "");
    $("e-txt").textContent = texto || (activo ? "Enviando ubicacion" : "Ubicacion en reposo");
}

/* -------------------------------------------------------------------
   Ciclo: mira si hay ruta en curso y enciende o apaga en consecuencia
   ------------------------------------------------------------------- */

async function revisarRuta() {
    try {
        const r = await rpc("/agrogood/api/driver/my_route", {});
        if (r && r.ruta) {
            S.rutaId = r.ruta.id;
            $("e-ruta").textContent = r.ruta.nombre;
            $("e-detalle").textContent =
                `${r.ruta.pendientes} de ${r.ruta.paradas} entregas pendientes`;
            if (await leer("acepta_ubicacion") === "1") await arrancarRastreo();
        } else {
            S.rutaId = null;
            $("e-ruta").textContent = "Sin ruta activa";
            $("e-detalle").textContent =
                "Cuando Logistica te asigne una ruta y la inicies, aparecera aqui.";
            await pararRastreo();
        }
    } catch (e) { /* sin red: se reintenta en el siguiente ciclo */ }
    await vaciarCola();
}

/* -------------------------------------------------------------------
   Arranque
   ------------------------------------------------------------------- */

document.addEventListener("DOMContentLoaded", async () => {
    const srv = await leer("servidor");
    const usr = await leer("usuario");
    if (srv) $("servidor").value = srv;
    if (usr) $("usuario").value = usr;

    $("btn-entrar").addEventListener("click", async () => {
        error("");
        const s = $("servidor").value.trim(), u = $("usuario").value.trim(), c = $("clave").value;
        if (!s || !u || !c) return error("Completa los tres campos.");
        $("btn-entrar").disabled = true;
        $("btn-entrar").textContent = "Entrando...";
        try {
            await entrar(s, u, c);
            await guardar("servidor", S.servidor);
            await guardar("usuario", u);
            mostrar(await leer("acepta_ubicacion") === "1" ? "p-estado" : "p-aviso");
            if (await leer("acepta_ubicacion") === "1") iniciarCiclo();
        } catch (e) {
            error(e.message || "No se pudo conectar. Revisa la direccion del servidor.");
        } finally {
            $("btn-entrar").disabled = false;
            $("btn-entrar").textContent = "Entrar";
        }
    });

    $("btn-acepto").addEventListener("click", async () => {
        await guardar("acepta_ubicacion", "1");
        mostrar("p-estado"); iniciarCiclo();
    });
    $("btn-rechazo").addEventListener("click", async () => {
        await guardar("acepta_ubicacion", "0");
        mostrar("p-estado"); iniciarCiclo();
    });
    $("btn-abrir").addEventListener("click", () => {
        window.location.href = S.servidor + "/agrogood/driver";
    });
    $("btn-salir").addEventListener("click", async () => {
        await pararRastreo();
        await Preferences.remove({ key: "acepta_ubicacion" });
        mostrar("p-acceso");
    });
});

function iniciarCiclo() {
    revisarRuta();
    setInterval(revisarRuta, 60000);
}
