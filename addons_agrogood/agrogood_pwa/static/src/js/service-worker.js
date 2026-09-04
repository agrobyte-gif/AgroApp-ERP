/* Service worker de Agrogood movil.
 *
 * Cachea SOLO los recursos estaticos: CSS, JS y manifiesto. Los datos NUNCA se
 * cachean, y es deliberado. Un Picker que ve una lista de pedidos guardada de
 * hace una hora prepara lo que no toca, y un conductor que ve una parada ya
 * entregada la entrega dos veces. En este flujo, un dato viejo hace mas dano
 * que una pantalla que avisa de que no hay conexion.
 *
 * El trabajo verdaderamente offline -preparar sin cobertura y sincronizar
 * despues- exige una cola de operaciones con resolucion de conflictos. Es un
 * desarrollo aparte y solo merece la pena si la bodega tiene zonas sin senal.
 */

const CACHE = "agrogood-estaticos-v2";
const ESTATICOS = [
    "/agrogood_pwa/static/src/css/pwa.css",
    "/agrogood_pwa/static/src/js/pwa.js",
    "/agrogood_pwa/static/manifest.webmanifest",
];

// La pagina que se muestra al intentar abrir una pantalla sin senal. No trae
// datos -eso seria mentir con informacion vieja-: dice la verdad y ofrece
// reintentar. Reemplaza al dinosaurio del navegador, que no explica nada.
const SIN_CONEXION = `<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Sin conexion</title>
<style>
  body{margin:0;font:16px system-ui,sans-serif;background:#F4F6F3;color:#1B2A22;
       display:flex;min-height:100vh;align-items:center;justify-content:center}
  .caja{text-align:center;padding:32px;max-width:340px}
  h1{font-size:20px;margin:0 0 8px}
  p{color:#46564D;line-height:1.5}
  button{margin-top:20px;background:#15653B;color:#fff;border:0;border-radius:12px;
         padding:14px 24px;font-size:16px;font-weight:600;width:100%}
</style></head>
<body><div class="caja">
  <h1>Sin conexion</h1>
  <p>No hay senal para abrir esta pantalla. Nada se perdio: cuando vuelva la
     conexion, reintenta.</p>
  <button onclick="location.reload()">Reintentar</button>
</div></body></html>`;

function respuestaSinConexion() {
    return new Response(SIN_CONEXION,
        { headers: { "Content-Type": "text/html; charset=utf-8" } });
}

self.addEventListener("install", (e) => {
    e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ESTATICOS)));
    self.skipWaiting();
});

self.addEventListener("activate", (e) => {
    e.waitUntil(
        caches.keys().then((claves) =>
            Promise.all(claves.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener("fetch", (e) => {
    const url = new URL(e.request.url);
    const esEstatico = url.pathname.startsWith("/agrogood_pwa/static/");

    // Abrir una pantalla sin senal: en vez del dinosaurio, la pagina honesta de
    // sin conexion. Solo cuando la red falla de verdad -si contesta, aunque sea
    // un error de Odoo, ese error se muestra, que es informacion util-.
    if (e.request.mode === "navigate") {
        e.respondWith(fetch(e.request).catch(() => respuestaSinConexion()));
        return;
    }

    if (e.request.method !== "GET" || !esEstatico) {
        return; // datos y acciones van siempre a la red
    }
    e.respondWith(
        caches.match(e.request).then((r) => r || fetch(e.request))
    );
});
