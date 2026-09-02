# ADR-006 - La cobranza se lleva sobre la orden de compra

Fecha: 2026-09-01
Estado: aceptado
Decide: contra que documento se cobra, si la factura no vive en Odoo

## Contexto

Por ADR-002, Agrogood emite sus documentos tributarios en el portal MIPYME del
SII. Odoo no factura. Se comprobo en la base: **cero facturas de venta**.

El modulo de conciliacion, tal como se construyo primero, cruzaba el abono
contra las facturas abiertas del cliente. Sobre una base sin facturas eso no
responde nada: identificaba quien pago y a continuacion decia que no debia
nada. La mitad util del modulo estaba apagada.

## Decision

**El documento de cobro es la orden de compra** -que es como Agrogood llama a
su pedido de venta-. Es el documento que si existe en el sistema, el que
registra que se entrego y por cuanto, y el que el cliente reconoce.

**Se debe lo entregado, no lo pedido.** Es la misma regla de ADR-003 que aplica
la facturacion: 20 kg pedidos y 19,4 entregados son 19,4 cobrados. Cobrar lo
pedido convertiria cada diferencia de peso en una discusion, y en este rubro la
diferencia de peso es la norma, no la excepcion.

El importe cobrable de una linea es su total con IVA en proporcion a lo
entregado. Se calcula asi, y no volviendo a aplicar precios e impuestos, para
que un descuento de linea o un impuesto distinto no haya que replicarlos aqui
y acaben discrepando.

### Como se imputa

Una tabla aparte, `agrogood.payment.allocation`, guarda que parte de que abono
paga que orden. Hace falta porque la relacion es de muchos a muchos y con
importe: un cliente junta cuatro entregas en una transferencia, y otro paga una
entrega grande en dos veces. Guardar el pago en la orden -o la orden en el
pago- cubre solo el caso facil, y el caso facil no es el que da problemas.

El reparto automatico va **de la deuda mas antigua a la mas nueva**. No es una
preferencia: es lo que evita que una deuda vieja se quede atras mientras se van
pagando las nuevas. Y lo que sobra **se ve sobrar**: un abono que no calza suele
ser un anticipo o el cobro de algo que aun no esta en el sistema, y forzarlo a
cuadrar seria inventar la deuda que falta.

Dos comprobaciones en base de datos impiden que el saldo mienta: no se puede
repartir mas de lo que trae el abono, ni dejar una orden pagada de mas.

## Lo que se descarto

* **Crear facturas en Odoo solo para poder cobrar contra ellas.** Serian
  facturas que no existen para el SII: dos numeraciones, y la de Odoo sin valor
  legal. El dia que alguien confunda una con otra, el problema es tributario.
* **Esperar al modulo de DTE (ADR-002).** La cobranza es un problema de hoy y
  el registro de folios es un proyecto aparte. Cuando exista, la orden ya tiene
  donde anotar el folio y no habra que rehacer nada.

## Consecuencias

* El folio del SII se anota a mano en la orden -campo `agrogood_sii_folio`-.
  Es doble digitacion, la misma que ADR-002 ya acepto. Se anota porque es como
  el cliente se refiere a la deuda cuando se le llama: *"te pague la 1234"*.
  Sin el numero, cobranza y cliente hablan de documentos distintos.
* El saldo de un cliente es lo entregado y no pagado, y vive como campo suyo,
  igual que las metricas de reactivacion.
* **La cuenta corriente empieza vacia.** Refleja lo que pasa por el sistema, de
  modo que solo dice la verdad desde el dia en que las ordenes se toman aqui.
  Las entregas anteriores a la puesta en marcha no estan y no se pueden cobrar
  desde esta pantalla.
* Los plazos de pago se guardan como dias en la ficha del cliente
  (`agrogood_credit_days`) y no como condiciones de pago contables. Cero es
  contado. Se eligio lo simple porque lo que hace falta es saber a quien llamar
  hoy, no construir un calendario de vencimientos.
