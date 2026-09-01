# ADR-005 - Conciliacion bancaria: cruzar los pagos con los clientes

Fecha: 2026-08-26
Estado: **aceptado; el modelo de identidades ya esta implementado**
Decide: como se sabe quien pago, sin revisar la cartola a mano

## Contexto

Agrogood cobra por transferencia. Hoy alguien abre la cartola del banco y va
buscando a mano que factura corresponde a cada abono. Con 153 clientes y varios
cientos de movimientos al mes, eso es media jornada y se equivoca.

El sistema anterior construido sobre IDURAR tenia un modelo `BankTransaction`
con un campo `originRut`, y esa fue la unica idea suya que valia la pena traer:
**cruzar por RUT**. El resto -caja chica, formas de pago- ya lo resuelve Odoo.

## Lo que dicen los datos

Se analizo una cartola real de Agrogood (marzo, tres cuentas, 14.362
movimientos). **No se importo ni un registro**: solo se midio.

| Cuenta | Movimientos | Trae RUT |
|---|---|---|
| Scotiabank | 9.088 | **Si**, en columna propia |
| Santander | 4.501 | 2%, suelto en la descripcion |
| Santander Agroretail | 473 | 1% |

Y del lado de Scotiabank, que es el que cruza:

* 407 RUT distintos validos.
* **48 son clientes nuestros**, de los 94 que hoy tienen RUT cargado.
* 359 pagan y **no estan en la cartera**: o son fichas que faltan, o
  transferencias que no son de venta.

De aqui salen dos conclusiones que cambian el diseno:

1. **Completar los RUT que faltan aumenta directamente lo que se concilia
   solo.** No es una tarea administrativa: es la palanca del modulo.
2. **Mas de la mitad del dinero entra por Santander, que no trae RUT.** Un
   modulo que solo cruce por RUT deja fuera la mitad.

## Decision

**Dos estrategias, una por banco, y la segunda aprende.**

### Scotiabank: por RUT

Columna `Rut Origen`, sin guion ni separador (`783444062` es `78344406-2`,
`77716841K` es `77716841-K`). Se normaliza, se valida el digito verificador y
se busca el cliente. Directo.

### Santander: por alias, aprendido una vez

La columna `CLIENTE` trae el nombre corto que Agrogood ya usa: *BAR CALLEJON*,
*HOP*, *LOCO JOE*, *PENCOPOLITAN*. No es el nombre fiscal, pero es estable.

La primera vez que una persona enlaza un alias con su cliente, **se guarda**. A
partir de ahi ese alias cruza solo.

Se descartaron las alternativas:

* **Solo Scotiabank.** Funciona ya y sin trabajo manual, pero deja sin
  conciliar mas de la mitad de los cobros, que es el problema que se venia a
  resolver.
* **Cruzar por monto y fecha.** No necesita aprender nada, pero con muchos
  pagos parecidos acierta poco, y equivocarse aqui no es un dato mal puesto:
  es dar por pagada la factura de otro cliente.

El alias es el unico camino que **mejora con el uso**. El primer mes hay
trabajo manual; a partir del segundo, cada vez menos. Los otros dos se quedan
donde empiezan.

## Consecuencias

* Hace falta un modelo para el alias -cliente, texto, banco- y una pantalla
  para enlazarlo cuando aparece uno nuevo.
* Los movimientos se cargan subiendo el archivo que exporta el banco. La
  cartola vive **fuera del repositorio**, como las planillas de clientes: son
  datos reales de terceros con RUT, montos y numeros de cuenta.
* Los 359 RUT que pagan y no estan en la cartera conviene mirarlos una vez: es
  probable que haya clientes reales sin ficha.
* Ojo con el formato: la hoja de Scotiabank tiene 790 filas con las columnas
  corridas -otro bloque dentro de la misma hoja-. El lector tiene que
  saltarselas en lugar de interpretarlas mal.


---

## Correccion (2026-08-26): no se cruza contra el RUT de la ficha

Al revisar el analisis con Agrogood aparecio lo que faltaba: **un cliente no
paga siempre desde el mismo RUT**. Transfiere desde la sociedad operativa,
desde otra relacionada, o desde el RUT personal del dueno. Ninguno tiene por
que ser el que figura en su ficha.

Se volvio a medir sobre la misma cartola, cruzando por NOMBRE los 359
pagadores desconocidos:

| | |
|---|---|
| Pagadores distintos en Scotiabank | 407 |
| Cruzan por el RUT de su ficha | 48 |
| Mismo negocio con otro RUT (por nombre) | 5 |
| No se parecen a ningun cliente | 354 |

Y de esos cinco, tres son **clientes que no tienen RUT en su ficha**: la
cartola se lo esta dando. Los otros dos -`RESTAURANT PAC` contra `RESTAURANT
KEKA`, `RESTAURANTES BU` contra `RESTAURANT GABY`- se parecen un 80% y no
tienen nada que ver. Ese es exactamente el motivo por el que **no se adivina
por parecido de nombre**: dar por pagada la factura de otro cliente no es un
dato mal puesto, es un cobro que se deja de perseguir.

### El modelo

`agrogood.payer` guarda **como aparece un cliente en el banco**: un cliente
tiene tantas identidades como haga falta, de dos tipos.

| Tipo | De donde sale |
|---|---|
| `rut` | Columna `Rut Origen` de Scotiabank, normalizada y validada |
| `alias` | Columna `CLIENTE` de Santander: *BAR CALLEJON*, *HOP*, *LOCO JOE* |

Se aprende UNA vez, al enlazar un pago a mano, y a partir de ahi cruza solo. El
RUT de la ficha sigue funcionando sin configurar nada: es el caso mas comun al
empezar y no tiene sentido obligar a registrarlo dos veces.

Una identidad no puede apuntar a dos clientes -restriccion en base de datos-,
porque eso repartiria los cobros al azar entre ambos.

Las identidades se ven y se editan en la propia ficha del cliente, pestana
**Como paga**. Un cliente que paga raro se explica en su ficha, no en otra
pantalla que hay que saber que existe.
