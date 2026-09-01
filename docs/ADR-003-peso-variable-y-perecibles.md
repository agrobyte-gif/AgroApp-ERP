# ADR-003 - Peso variable, perecibilidad y base de facturacion

Fecha: 2026-08-21
Estado: aceptado
Decide: H4, H6 y H9 del informe de auditoria

## Contexto

Tres problemas del rubro hortofruticola que deben resolverse antes de cargar
datos maestros, porque cambiarlos despues obliga a migrar movimientos de
inventario ya registrados.

Se reviso el codigo de Odoo 18 antes de disenar nada. El resultado cambio la
propuesta inicial: dos de los tres se resuelven sin escribir codigo.

## H6 - Perecibilidad: resuelto por configuracion

`product_expiry` esta en el arbol estandar y aporta sobre `stock.lot`:
`expiration_date`, `use_date` (consumo preferente), `removal_date` y
`alert_date`. La estrategia de salida FEFO ya esta implementada en
`product_expiry/models/stock_quant.py`.

**Decision:** activar `product_expiry`, marcar `use_expiration_date` en las
categorias perecibles y fijar FEFO como estrategia de remocion en las
ubicaciones de bodega.

**Codigo propio necesario: ninguno.** Solo configuracion y, mas adelante, una
alerta programada sobre `alert_date`.

## H9 - Base de facturacion: resuelto por configuracion

`sale.order.line._compute_qty_delivered` (en `sale_stock`) calcula la cantidad
entregada a partir de `move.quantity` de los movimientos en estado `done`,
convertida a la unidad de la linea de venta. Si el producto tiene
`invoice_policy = 'delivery'`, Odoo factura exactamente esa cantidad.

**Decision:** todos los productos de Agrogood usan
`invoice_policy = 'delivery'`.

Esto convierte "se factura lo entregado, no lo pedido" en **comportamiento
nativo**. Lo que el Picker registre en el picking es lo que se factura, sin
codigo intermedio y sin riesgo de divergencia.

**Codigo propio necesario: ninguno.**

## H4 - Peso variable: se evita, no se construye

Odoo 18 Community no tiene catchweight. `stock_delivery` anade un `weight` sobre
`stock.move`, pero es **peso teorico** (peso del producto por cantidad), no peso
capturado. No sirve para facturar.

Se evaluo construir un sistema de catchweight propio: dos cantidades por linea,
una para stock y otra para facturar. Se descarta. Duplica el concepto de
cantidad en todo el flujo, rompe los informes estandar y es exactamente el tipo
de reimplementacion que este proyecto quiere evitar.

**Decision: la unidad de medida es aquella en la que se factura.**

Para un producto de peso variable, la unidad de venta, de stock y de
facturacion es el **kilogramo**. La caja no es unidad de medida: es un formato
de presentacion, informativo, que ayuda a preparar el pedido pero no interviene
en el calculo.

Flujo resultante:

1. El cliente pide 20 kg de tomate. La linea de venta son 20 kg.
2. El Picker prepara dos cajas y registra en la PWA el peso real: 19,4 kg.
3. `move.quantity` queda en 19,4 kg y el stock se descuenta por 19,4 kg.
4. `qty_delivered` pasa a 19,4 kg y se factura 19,4 kg.

Nada de esto requiere modelo nuevo.

**Codigo propio necesario, y solo esto:**

* La PWA debe permitir al Picker capturar el peso real de forma comoda
  (`agrogood_picking_ops`).
* Una validacion de tolerancia que avise cuando el peso capturado se aparte del
  pedido mas de un porcentaje configurable. Protege contra el error de tecleo,
  que en kilos es caro.
* El formato de presentacion (caja, malla, bandeja) como dato informativo del
  producto, para que el Picker sepa cuantos bultos armar.

## Consecuencia para la fase 1

Los datos maestros deben cargarse con esta clasificacion resuelta desde el
principio: cada producto declara si es de peso fijo o variable, y los de peso
variable se dan de alta en kilogramos. Cargar primero y reclasificar despues
implica migrar movimientos ya registrados.

## Addendum (2026-08-23) - el backorder en peso variable

Detectado probando el flujo completo contra la base real.

Cuando el Picker prepara 19,4 kg de los 20 pedidos, Odoo ofrece crear un
**backorder** por los 0,6 kg restantes. En peso variable eso es un error
conceptual: la diferencia no es una entrega pendiente, es lo que peso el bulto.
Aceptarlo dejaria un albaran fantasma abierto por cada linea de peso variable,
y en pocos dias el listado de entregas pendientes seria inservible.

**Regla:** al validar un albaran cuyas lineas son de peso variable, se cierra
sin backorder. La cantidad entregada es la definitiva por definicion.

Se implementa en `agrogood_picking_ops` (fase 6), que es donde vive la
validacion desde la PWA. Hasta entonces, quien valide a mano debe elegir
"No crear pedido en espera".

Verificado en la prueba de punta a punta: cerrando sin backorder, el pedido
queda en 'Entregado' con un solo albaran y la factura sale por 19,4 kg.


---

## Correccion (2026-08-26): la regla es SOLO para las salidas

La supresion del pedido en espera se implemento para cualquier albaran cuyas
lineas cortas fueran todas de peso variable, sin mirar si entraba o salia
mercaderia. Se estaba aplicando tambien a las RECEPCIONES DE COMPRA.

El efecto: se compraban 20 kg, llegaban 18, y el sistema cerraba la compra como
completa. Los 2 kg que faltaban desaparecian sin que nadie los reclamara, y se
pagaba la factura entera.

El razonamiento original -"esos 0,6 kg no son una entrega pendiente, son lo que
peso la caja"- vale cuando **Agrogood prepara** el pedido. En una compra, lo que
falta es mercaderia **pagada y no recibida**. La diferencia entre las dos
situaciones no es la cantidad: es de quien es la perdida.

### La regla definitiva

No es "salidas si, entradas no": es que cada lado tiene su criterio.

| | Falta mercaderia | De quien es la perdida |
|---|---|---|
| **Entrega** | Es el peso de la caja | De nadie: se factura lo entregado |
| **Compra, dentro de tolerancia** | Es el peso del envase | De nadie: se paga lo que llego |
| **Compra, fuera de tolerancia** | Entrega corta | Del proveedor: hay que reclamar |

La tolerancia es la del producto -10% por defecto-, la MISMA que el Picker
tiene en la balanza. Dos reglas distintas segun la punta del almacen en la que
uno este serian imposibles de recordar.

### El control de peso tampoco valia para las entradas

`_agrogood_check_weight_tolerance()` se ejecutaba en cualquier albaran y
BLOQUEABA recibir 15 de 20, pidiendole ademas a Bodega que marcara la linea
como "faltante o sustituida" -conceptos del Picker que no existen al recibir-.

Al recibir, quedarse corto es normal y se persigue con el pedido en espera. Lo
sospechoso es lo contrario: registrar MAS de lo comprado, que casi siempre es
un cero de mas e infla el stock y el costo promedio. El control queda asi: en
salidas vigila las dos direcciones; en entradas, solo el exceso.

Todo cubierto por `tools/prueba_bodega.py`.
