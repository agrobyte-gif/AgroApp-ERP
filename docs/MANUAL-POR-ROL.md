# Agroapp: una hoja por persona

Una página por rol. Están pensadas para imprimirse y pegarse donde se trabaja,
no para leerse enteras.

**Entrar es siempre igual:** abrir en el teléfono

```
http://AGROGOOD.local:8069/agrogood/app
```

y entrar con el correo y la clave de cada uno. Conviene guardarlo en la
pantalla de inicio la primera vez: después se abre como cualquier aplicación.

Quien tiene un solo trabajo entra directo a su pantalla. Quien tiene varios
—Felipe, Victor— elige primero.

---
---

# VENTAS

*Sebastián, Yere*

## Lo que ves al abrir

Cuántas órdenes entraron hoy y cuánto suman. Debajo, **a quién llamar hoy**:
clientes que compraban este mismo día de la semana y todavía no han pedido. Es
la lista más corta y la que más vende.

Y las órdenes del día. Las que tocan un cliente todavía se pueden cambiar.

## Lo que haces

**Tomar una orden.** Buscar el cliente, buscar productos, confirmar. El botón
*Repetir su última orden* trae lo de la vez pasada, que en la mayoría de los
clientes es casi lo mismo.

**Cambiar una orden.** Se toca la orden en la lista del día. Los más y los
menos cambian cantidades; **poner cero quita el producto**. Guardar al final.

**Dar de alta un cliente.** Nombre y línea comercial son obligatorios: de la
línea sale su lista de precios. El RUT se puede dejar para después.

## Cuando algo sale mal

| Dice | Qué pasa |
|---|---|
| «no tienen precio en la tarifa» | Ese producto saldría a cero. Avisa a Victor antes de venderlo. |
| «ya no se puede cambiar» | Alguien ya lo está preparando. Habla con Felipe. |
| «no se le podrá facturar» | Al cliente le falta el RUT. Se le vende y se le reparte igual. |
| «ese RUT no cuadra» | Está mal escrito. Pregúntaselo ahora, que lo tienes al teléfono. |

**Anular pide el motivo.** No es burocracia: sin él, el cliente aparece después
como si hubiera dejado de comprar y el sistema te lo pone en la lista de
llamadas.

---
---

# COMPRAS

*Johan*

## Lo que ves al abrir

La pizarra, con **lo urgente arriba y separado**. Lo que se necesita hoy va
primero aunque se haya pedido esta mañana.

Todo lo que aparece ahí lo puso el sistema solo: cuando Ventas toma un pedido y
no hay stock, la solicitud llega sin que nadie te avise.

## Lo que haces

**Anotar mientras preguntas.** Proveedor y precio se guardan por separado del
estado, porque se consiguen en momentos distintos: primero preguntas el precio,
después decides si compras.

**Mover el estado:** buscando, cotizando, no encontrado, rechazar.

**Generar las órdenes.** El botón de arriba las hace todas de una vez y
**agrupa por proveedor**: tres productos al mismo son una orden con tres
líneas, no tres órdenes.

## Cuando algo sale mal

Si un producto no aparece en ningún proveedor, márcalo **No encontrado**. Eso
avisa a Ventas, que puede ofrecerle otra cosa al cliente. Dejarlo callado en la
pizarra es lo que hace que un pedido llegue incompleto sin que nadie lo supiera.

---
---

# BODEGA

*Matías, Felipe*

## Lo que ves al abrir

Las recepciones que están por llegar, las preparaciones en curso, y **lo que
está por vencer**.

## Lo que haces

**Recibir mercadería.** Producto por producto, con la cantidad real. En lo que
lleva lote, hay que poner el lote y la fecha de vencimiento: es lo que después
permite sacar primero lo que antes vence.

> Recibir **menos** de lo pedido es normal y no genera nada raro. Recibir
> **más** de lo que dice el papel sí avisa: suele ser un error de conteo.

**Registrar mermas.** Qué se perdió, cuánto y por qué. Si la culpa es del
proveedor o del transporte, hay que decir de quién: eso es lo que después
permite reclamarlo.

**Ajustar inventario.** Se cuenta un producto y se deja el sistema en lo
contado. Antes de guardar te dice cuánto sobra o falta: **si el número te
sorprende, vuelve a contar**. Pide el motivo siempre.

## Cuando algo sale mal

| Dice | Qué pasa |
|---|---|
| «se lleva por lotes» | Hay que decir de qué lote es el conteo. |
| «no se puede contar en negativo» | Cero es lo mínimo. |
| pide el motivo | Un ajuste mueve plata. Sin explicación, a fin de mes nadie sabe si fue merma o error. |

---
---

# LOGÍSTICA

*Felipe*

## Lo que ves al abrir

Cuatro listas, en el orden en que se trabaja el día:

1. **Sin Picker** — pedidos esperando a que alguien los prepare.
2. **Preparando** — en curso ahora mismo.
3. **Listos** — preparados y esperando ruta.
4. **Rutas** — las de hoy.

## Lo que haces

**Repartir el trabajo.** Se seleccionan varios pedidos y se asignan de una vez.
Antes de decidir se ve **cuántas preparaciones abiertas tiene cada Picker**, que
es lo que evita cargarle todo al mismo.

**Armar rutas.** Se eligen las entregas listas, el conductor y el vehículo. El
sistema avisa si el peso pasa la capacidad del camión.

## Cuando algo sale mal

**Una entrega reprogramada vuelve sola a tu lista** el día para el que se
reprogramó. No hay que ir a buscarla.

Si un conductor marca un fallo en la revisión del vehículo, te llega el aviso.
La ruta **no arranca** sin revisión: es a propósito.

---
---

# PREPARACIÓN

*El Picker*

## Lo que ves al abrir

Tus preparaciones, y nada más. Lo de los demás no aparece.

## Lo que haces

Abrir la preparación y **empezar**. Después, producto por producto:

- **Confirmado** — está y es la cantidad.
- **Faltante** — no hay suficiente.
- **Sustituido** — se cambia por otro; hay que decir por cuál.
- **No encontrado** — no aparece en bodega.
- **Cancelado** — el pedido ya no lo lleva.

En lo que se vende por peso, se anota **el peso real**. No hay que cuadrarlo con
lo pedido: 19,4 kg de los 20 pedidos está bien y no genera nada pendiente.

Al terminar, **cerrar la preparación**. Eso es lo que la pasa a Logística.

## Cuando algo sale mal

Marcar algo como faltante o sustituido **obliga a explicarlo**. Es un segundo
ahí y ahorra la llamada de después, cuando el cliente pregunta por qué le llegó
otra cosa.

Si te equivocaste en una línea ya marcada, se puede volver a marcar antes de
cerrar. Después de cerrar, hay que avisar a Felipe.

---
---

# REPARTO

*El conductor*

## Antes de salir

**La revisión del vehículo.** Seis puntos: combustible, neumáticos, luces,
frenos, equipo de frío y carga asegurada.

Si algo está mal, se marca y **hay que decir qué pasa**. El aviso le llega a
Logística. Sin revisión la ruta no arranca.

## En la ruta

Tus paradas en orden. En cada una:

- **Llegué** — al bajarse.
- **Entregado** — con el nombre de quien recibe y, si se puede, una foto.
- **No pude entregar** — con el motivo.
- **Reprogramar** — con el motivo **y el día** para volver a intentarlo.

La ubicación se guarda sola cuando marcas algo. Sirve como respaldo tuyo: si
alguien dice que no llegaste, queda registrado que sí.

## Cuando algo sale mal

| Situación | Qué hacer |
|---|---|
| El cliente no está | *No pude entregar*, motivo «cliente no recibió». |
| Va a estar mañana | *Reprogramar*, y pones el día. |
| La dirección está mal | *No pude entregar*, motivo «dirección incorrecta». Se corrige en la ficha. |
| Se te fue la señal | Espera a tener señal. **No cierres la aplicación**: lo que marques sin señal no se guarda. |

---
---

# COBRANZA

*Victor, Ventas*

## Lo que ves al abrir

Lo que hay por cobrar y lo vencido. Debajo, tres listas **en el orden en que
hay que llamar**:

1. **Dijeron que pagaban** y llegó el día. La lista más corta y la que más
   rinde: ya hubo conversación.
2. **Vencidos**, del que más debe al que menos.
3. **Deben pero aún no vencen** — para consultarlos, no para llamarlos.

## Lo que haces

Abres el cliente y ves cuánto debe, desde cuándo y qué órdenes son. Los botones
de **Llamar** y **WhatsApp** están arriba, antes del detalle.

Al colgar, anotas **qué dijo**: la fecha en que queda de pagar y una nota. Eso
queda también en la ficha del cliente, así que la próxima vez sabes cuántas
veces lo ha prometido ya.

## Cuando algo sale mal

Si el cliente dice que ya pagó, pídele el día y el monto. Los abonos del banco
se cruzan en el escritorio, con la cartola delante: desde el teléfono no se
imputan, a propósito.

«Deuda anterior a Agroapp» es lo que ya debía cuando se empezó a usar el
sistema, de entregas que no están cargadas.

---
---

# DIRECCIÓN

*Victor*

## Lo que ves al abrir

Seis cifras y ni un botón. En el orden del dinero:

```
lo que entró        vendido hoy, y cuántas órdenes
lo prometido        por entregar, y cuánto vale
lo que falta cobrar pendiente y vencido
lo que se pierde    mermas del mes, y clientes sin poder facturar
```

Debajo, **los camiones que están en la calle ahora** con cuántas entregas
llevan hechas.

## Por qué seis y no veinte

Un tablero con veinte indicadores se mira una semana. Con seis se mira todos
los días, que es lo único que hace que sirva.

El detalle está en los paneles del escritorio, que es donde se analiza con
tiempo. Esta pantalla es para mirarla entre dos cosas.
