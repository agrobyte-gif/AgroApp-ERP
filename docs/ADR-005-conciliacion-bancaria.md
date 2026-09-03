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

---

## Correccion (2026-09-01): Santander si publica el RUT, y el modulo ya existe

Al construir el lector aparecio que la medicion anterior estaba mal. Se dijo
que Santander traia el RUT en el 2% de los movimientos. **Lo trae en el 95%.**

Lo pone al principio de la descripcion, relleno de ceros hasta once digitos:

```
00763341712 Pago factura     ->  76.334.171-2
77.811.898-K Transf. C       ->  77.811.898-K
```

La medicion anterior buscaba el RUT escrito con puntos y guion, que es como lo
escribe una persona. Santander lo escribe como lo escribe una maquina. Buscar
el formato bonito y concluir que el dato no existe es un error facil de
cometer y caro: sobre esa conclusion se habia decidido que **la mitad del
dinero solo se podia cruzar por alias aprendido**, y no era verdad.

**El cruce es por RUT en los tres bancos.** El alias pasa de ser la estrategia
principal de Santander a ser lo que resuelve el 5% que no lleva RUT, y lo que
desempata cuando un RUT no basta.

### Un RUT no siempre es un solo cliente

Cruzando por nombre los pagadores de la misma cartola:

| | |
|---|---|
| RUT de pagador distintos | 523 |
| Pagaron facturas de **mas de un negocio** | 108 |
| De esos, sin un nombre que domine | 81 |

Es la sociedad que paga por dos locales, o el dueno que paga por el suyo y por
el de un socio. Se consideraron dos salidas:

* **Marcar dudoso todo RUT que se repita.** Correcto y automatico, pero dejaba
  el 47% de los abonos esperando a una persona. Tanto trabajo manual como no
  tener el modulo.
* **Aprenderlo.** Un RUT se marca compartido cuando *se demuestra* que lo es:
  cuando alguien lo enlaza a un segundo cliente. Desde entonces deja de asignar
  solo. Se eligio esta.

La identidad compartida no cambia de dueno ni se duplica -eso repartiria los
cobros al azar-. Y si el abono trae ademas el nombre corto, el nombre desempata
y el abono se resuelve igual: una senal compartida no anula a la otra.

### Lo que da hoy, sin configurar nada

Ensayo con la cartola de un mes, partiendo de cero identidades aprendidas y con
rollback -no se importo nada-:

| | Abonos | |
|---|---|---|
| Leidos del archivo | 13.167 | |
| Cargos y traspasos, descartados | 1.642 | no los paga ningun cliente |
| **Identificados solos** | **4.326** | 33%, solo con el RUT que ya esta en la ficha |
| Pendientes | 8.841 | |

Y lo que importa: esos 8.841 abonos vienen de **593 pagadores distintos**, y
los **20 de mas monto concentran el 76% del dinero pendiente**. El trabajo
manual del primer mes no son 8.841 decisiones: son 593 como mucho, y veinte
resuelven tres cuartas partes.

Sigue en pie la conclusion del analisis original: **completar los RUT que
faltan en las fichas es la palanca del modulo**, porque es lo unico que
identifica sin que nadie enlace nada.

### Lo que el modulo NO hace

No asienta ningun pago. Dice de quien es el abono y que facturas tiene abiertas
ese cliente -y marca la que calza exactamente con el importe-, pero conciliar
sigue siendo una decision de una persona con la factura delante. Dar por
cobrada la factura equivocada no se descubre al dia siguiente: se descubre
semanas despues, reclamando una deuda que ya estaba pagada.

---

## Enmienda 3 - 3 de septiembre de 2026: se midio sobre la cartola ya cargada

Las cifras de arriba salieron de un ensayo con rollback. Con los 13.167
movimientos ya en la base, se volvio a medir **en plata** y no en cantidad de
abonos, que es lo que decide donde vale la pena trabajar. Cambia el cuadro.

### Reconociamos el 17% del dinero, no el 33% de los abonos

| | Abonos | Plata |
|---|---|---|
| Reconocidos | 4.326 | 731.292.968 |
| Sin nombre | 8.841 | 3.501.964.726 |

Contar abonos hacia parecer el problema mas chico de lo que era: los que se
reconocian solos eran los pequenos. **El cruce no falla -funciona-: lo que
falta son los datos.**

### Los pendientes son dos problemas distintos, no uno

Al separarlos aparecio que se habian estado tratando igual dos cosas que
cuestan trabajos muy distintos:

| | Abonos | Plata | Claves distintas | Cuantas cubren el grueso |
|---|---|---|---|---|
| Traen RUT | 7.885 | 1.500.119.292 | 454 RUT | 30 son el 71% |
| Solo nombre del banco | 956 | 2.001.845.434 | 139 nombres | **10 son el 94%** |

El segundo grupo es **mas plata con menos filas**, y se habia quedado detras
del primero porque son menos abonos. Ordenar por cantidad de movimientos en
vez de por monto habria mandado el trabajo al lado equivocado.

Por eso `exportar_pagadores.py` saca **dos hojas**, la de nombres primero, las
dos ordenadas por monto y con el porcentaje acumulado al lado: para poder
parar donde deje de rendir en vez de tener que llegar al final.

### Los traspasos entre cuentas propias no son cobros pendientes

403 movimientos por 169 millones venian del RUT `77135321-5`, que es de
Agrogood. Esa plata no la va a reclamar ningun cliente, de modo que estaba
condenada a quedarse en "sin identificar" para siempre, inflando el trabajo
pendiente y desinflando el porcentaje de reconocimiento.

Ahora `_cruzar()` los descarta con el motivo a la vista, leyendo la lista del
parametro `agrogood_bank.ruts_propios` -editable desde Ajustes, porque una
empresa abre cuentas y constituye sociedades- mas el RUT de la ficha de la
compania.

**Se esperaba mas de este cambio del que dio: movio el reconocimiento del 17%
al 18%.** La hipotesis de que buena parte de lo no identificado fuera plata
propia moviendose era comoda y era falsa. Se deja escrito para no volver a
proponerla.

### El grueso no es un problema de programacion

Con las 22 identidades que se pueden proponer solas -nombres del banco que
coinciden exactamente con un cliente que ya existe- el reconocimiento pasa
**del 18% al 45%** sin que nadie escriba nada.

Lo demas no lo arregla el codigo. De los 97 nombres que la planilla de RUT ya
tenia, **solo 2 coinciden con un cliente de Odoo**: hay 157 clientes en la
base contra 454 RUT y 139 nombres que transfieren plata todos los meses.
AMADOR, ANDES SUSHI, BIG CUT, BRONTO FOOD pagan millones y no existen como
ficha.

**Completar la lista de clientes es la palanca**, y sigue siendo la misma
conclusion del analisis original, ahora con el numero al lado.

### Lo que se decidio NO hacer

**No crear clientes desde la importacion.** `importar_pagadores.py` informa los
nombres que no existen y no los crea. Crearlos ahi llenaria la lista de
variantes tipograficas del mismo negocio, y cada variante parte su cuenta
corriente en dos: la deuda queda repartida entre dos fichas y ninguna de las
dos dice lo que el cliente debe.

**No proponer por parecido, solo por igualdad exacta.** En esta misma cartola
`RESTAURANT PAC LIMITADA` se parece un 83% a `RESTAURANT KEKA`. Dar por pagada
la factura de otro cliente no es un dato mal puesto: es un cobro que se deja
de perseguir, y se descubre semanas despues reclamando una deuda saldada.
