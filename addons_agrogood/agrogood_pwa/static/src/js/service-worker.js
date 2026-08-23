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

const CACHE = "agrogood-estaticos-v1";
const ESTATICOS = [
    "/agrogood_pwa/static/src/css/pwa.css",
    "/agrogood_pwa/static/src/js/pwa.js",
    "/agrogood_pwa/static/manifest.webmanifest",
];

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
    if (e.request.method !== "GET" || !esEstatico) {
        return; // datos y acciones van siempre a la red
    }
    e.respondWith(
        caches.match(e.request).then((r) => r || fetch(e.request))
    );
});
