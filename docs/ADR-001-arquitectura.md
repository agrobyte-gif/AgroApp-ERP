# ADR-001 - Decisiones de arquitectura de la plataforma Agrogood

Fecha: 2026-08-21
Estado: aceptado

## Contexto

La auditoria del 21-08-2026 establecio que no existia proyecto previo: la carpeta
contenia unicamente el codigo fuente de Odoo 19.0 Community sin ejecutar, sin
personalizaciones, sin base de datos y sin dependencias instaladas.

## Decisiones

### D1 - Base sobre Odoo 18.0 Community, no 19.0

Odoo 19.0 se libero demasiado recientemente para que el ecosistema OCA y los
proveedores chilenos de facturacion electronica lo soporten. Como no habia nada
construido, el cambio de version tuvo coste cero.

Consecuencia: el arbol `odoo-19.0` original queda obsoleto y se reemplaza por
`odoo-18.0`.

### D2 - El nucleo de Odoo no se modifica nunca

Toda extension se hace por herencia desde modulos `agrogood_*` en un directorio
`addons_agrogood/` versionado por separado. El nucleo queda fuera de Git y es
reemplazable por una version nueva sin perder trabajo propio.

### D3 - El codigo sale de OneDrive

OneDrive sincroniza y bloquea archivos de forma continua. Sobre un arbol de miles
de archivos Python produce bloqueos de escritura, `.pyc` corruptos y conflictos de
sincronizacion. El proyecto vive en `C:\dev\agrogood`.

### D4 - Se factura sobre lo entregado, no sobre lo pedido

Cuando el Picker sustituye, cancela o no encuentra un producto, la fuente de
verdad es el picking. Toda diferencia ajusta la orden de venta antes de facturar y
queda registrada con motivo y responsable.

### D5 - Los precios se versionan, nunca se sobrescriben

`product.pricelist.item` ya soporta `date_start` y `date_end`. Cada carga semanal
crea items nuevos y cierra los anteriores. Los pedidos historicos conservan su
precio porque `sale.order.line` almacena el precio unitario como dato propio.

### D6 - Pickers y Conductores no acceden al backend

Se implementan como usuarios de tipo portal con record rules que limitan por
asignacion. La restriccion vive en la regla de registro, no en la ocultacion de
menus: ocultar un menu no impide una peticion construida a mano.

### D7 - La emision de DTE se hace en el portal MIPYME del SII

Odoo registra el documento emitido, no lo emite. Ver ADR-002.

## Pendiente de decidir

Nada bloqueante. La operativa actual de Agrogood (volumenes, sistema de origen e
historial a migrar) sigue sin documentarse y condiciona el alcance de la fase 1.
