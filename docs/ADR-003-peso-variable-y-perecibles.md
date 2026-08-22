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
