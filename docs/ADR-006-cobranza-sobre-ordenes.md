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

---

## Añadido (2026-09-01): el plazo se congela, y la cobranza en el telefono

### El plazo pactado vale el del dia de la venta

Al principio el vencimiento se calculaba leyendo los dias de plazo de la ficha
del cliente. Una prueba lo destapo: **ampliarle el plazo a un cliente moroso
descontaba de golpe todas sus entregas vencidas** y lo sacaba de la lista de
cobranza sin haber pagado nada. Un numero en una ficha borraba la deuda de la
pantalla.

Ahora el plazo se copia a la orden al elegir el cliente y se queda ahi. Cambiar
la ficha afecta a lo que se venda desde entonces, no a lo ya entregado. Vale lo
que se pacto ese dia.

### Cobrar es una conversacion

La pantalla de Cobranza en el telefono existe porque cobrar no se hace sentado:
se hace con el telefono en la mano, mirando cuanto debe el cliente y desde
cuando. Lo unico que hace falta anotar despues de colgar es que dijo.

El orden de la lista es el orden en que hay que llamar:

1. **Los que ya prometieron y llego el dia.** Es la lista mas corta y la que
   mas rinde: ya hubo conversacion, y volver a llamar el dia que dijeron es lo
   que separa una promesa de una excusa.
2. **Los vencidos**, del que mas debe al que menos.
3. **Los que deben y aun no vencen**, para consultarlos, no para llamarlos.

Se ordena por lo VENCIDO y no por el saldo total: un cliente que debe mucho y
no ha vencido nada esta al dia, y ordenar por saldo lo pondria arriba, que es
justo a quien no hay que llamar.

La promesa se guarda en dos sitios a proposito. El campo responde *cuando dijo
que pagaba*; la conversacion del cliente responde *cuantas veces lo ha dicho
ya*, que es la pregunta que decide si se le sigue llamando o se le corta el
credito. Solo con el campo, cada promesa borra la anterior y el que promete
todos los viernes parece igual de fiable que el que cumple.

**Imputar abonos no esta en el telefono.** Eso se hace sentado y con la cartola
delante; meterlo aqui seria llenar de riesgo una pantalla que se usa de pie.

### Efecto secundario a vigilar

Ventas gana una pantalla, de modo que quien solo tenia Ventas pasa de entrar
directo a elegir entre dos. Es un toque mas cada dia. Se acepto porque cobrar y
vender son trabajos distintos y la persona que llama al cliente es la misma que
le vende; si en la practica Ventas no cobra, la pantalla deberia quedar solo
para Direccion.

---

## Añadido (2026-09-01): el saldo de apertura

La cuenta corriente solo sabe de lo que pasa por Agroapp, de modo que el dia
del arranque diria que nadie debe nada y la cobranza habria que llevarla por
fuera durante meses. El **saldo de apertura** es lo que cada cliente ya debia
ese dia, de entregas anteriores al sistema.

Se descartaron dos alternativas:

* **Cargar el historico de entregas.** Da el detalle completo, pero son miles
  de filas que dependen de lo limpio que este lo que hay en planilla, y si
  entran sucias el sistema arranca con numeros que nadie cree. Para cobrar hace
  falta saber cuanto debe, no que llevo en marzo.
* **No cargar nada.** Cero trabajo, pero durante meses conviven dos formas de
  saber cuanto debe un cliente, y la que esta en la pantalla es la incompleta.

### Por que NO es una orden de compra

La tentacion era crear una orden falsa por cliente y reutilizar toda la
maquinaria de imputacion. Se probo mentalmente y se descarto: esa orden se
colaria en las **ventas del dia**, en el **ticket medio**, en los **productos
mas vendidos**, en los **paneles** y en las **alertas** -diez sitios que leen
`sale.order` como si fuera una venta-, y cada informe nuevo tendria que
acordarse de excluirla. Es el tipo de decision que funciona el primer mes y
corrompe las cifras el sexto.

El saldo vive como un importe del cliente, que no se cuela en ningun sitio. Lo
unico que hubo que ampliar es la imputacion: una linea apunta a una orden **o**
al saldo de apertura de un cliente, y una comprobacion exige que sea a una sola
de las dos.

### Como se cobra

El saldo de apertura es, por definicion, **la deuda mas antigua que existe** y
esta vencida desde la fecha de corte. Por eso un abono lo salda primero y solo
despues reparte lo que sobre entre las ordenes. Dejarlo para el final lo
volveria incobrable en la practica: siempre habria una entrega mas reciente por
delante.

### Como se carga

`tools/exportar_saldos.py` saca la cartera a `C:/dev/Saldos por completar.xlsx`
-una fila por cliente, una sola columna que rellenar, y viene en cero porque un
saldo no se puede proponer: hay que mirarlo-. `tools/importar_saldos.py` la
lee, informa por defecto y escribe con `AGROGOOD_SALDOS=escribir`.

Volver a cargar la planilla **reemplaza** el saldo, no lo suma: corregir una
cifra mal puesta es editar la celda y volver a cargar, sin tener que acordarse
de cuantas veces se cargo antes. Y antes de escribir se listan los diez que mas
deben con su porcentaje, porque el error tipico es un cero de mas y ahi se ve.
