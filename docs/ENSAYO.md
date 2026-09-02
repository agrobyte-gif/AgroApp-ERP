# El ensayo: un día completo con el equipo

Todo lo que hay en Agroapp lo probé yo. Eso deja fuera el fallo que más
importa, porque **lo que rompe una aplicación de bodega no es el código: es que
el Picker no entienda un botón**. Ese fallo no aparece en ninguna prueba
automática y solo se ve mirando a alguien usarla.

Este documento es el guion de ese día. Dura una jornada, se hace una sola vez,
y de él sale la lista de lo que hay que arreglar antes de que la empresa
dependa del sistema.

---

## La regla del ensayo

**Nadie explica nada por adelantado, y nadie ayuda.**

Es la parte difícil y es la única que hace que el ensayo sirva. Si Victor se
pone al lado del Picker y le dice "ahí, ese botón", el ensayo demuestra que
Victor sabe usar la aplicación, que ya lo sabíamos.

Cuando alguien se atasca:

1. Se le deja atascado unos segundos y **se anota**.
2. Si no sale solo, se le pregunta: *«¿qué estabas buscando?»*. Esa frase es el
   dato; el botón que faltaba se deduce después.
3. Recién entonces se le muestra.

Un atasco no es un fracaso del ensayo. Es exactamente lo que se vino a buscar.

---

## Antes del día

### 1. Las cuentas, y sus claves

El equipo completo ya está creado. Falta **ponerle la clave a cada uno**, una
por una, desde `Ajustes > Usuarios > (el usuario) > Acción > Cambiar
contraseña`. Las pone una persona y no un script: una clave escrita en un
archivo del repositorio deja de ser una clave.

| Quién | Correo | Hace |
|---|---|---|
| Felipe Collio | `felipe.collio@agrogood.cl` | prepara |
| Orianna Pumar | `orianna.pumar@agrogood.cl` | prepara |
| Fernando Figueroa | `fernando.figueroa@agrogood.cl` | prepara |
| Thomas Schuster | `thomas.schuster@agrogood.cl` | prepara y reparte |
| Earvin Juárez | `earvin.juarez@agrogood.cl` | prepara y reparte |
| Luis Yáñez | `luis.yanez@agrogood.cl` | prepara y reparte |
| Felipe Fuentes | `felipe.fuentes@agrogood.cl` | prepara y reparte |

Los cuatro que preparan **y** reparten entran a una pantalla que les pregunta
cuál de los dos trabajos van a hacer. Conviene avisárselo: es el único punto
del día donde alguien puede quedarse mirando sin saber qué tocar.

Y el resto: Sebastián Lara y Yerendi Zambrano en Ventas, Johan Molina en
Compras, Felipe Labraña en Logística y Bodega, Matías Lobasso en Bodega.

> Hay **dos Felipes** en el equipo, y un tercero —Felipe Labraña— en Logística.
> Por eso los correos nuevos llevan nombre y apellido. Vale la pena decirlo en
> voz alta el día del ensayo.

### 1b. Las cuentas de demostración

`Picker Demo` y `Conductor Demo` fueron mías para probar. **No participan en el
ensayo**: parte de lo que se comprueba es que cada uno entre con lo suyo. Y
tienen permisos de más —pueden administrar empleados, proyectos y vacaciones—,
así que conviene limpiarlas antes (ver más abajo).

### 2. Los teléfonos

Cada uno con **su** teléfono, no con uno prestado. La aplicación se abre en el
navegador, sin instalar nada:

```
http://AGROGOOD.local:8069/agrogood/app
```

Conviene que cada uno lo deje guardado en la pantalla de inicio la noche
anterior. Si alguien llega el día del ensayo peleándose con la dirección, se
pierde la primera hora en algo que no es lo que se quería probar.

El conductor además necesita el APK, que es la misma aplicación con permiso de
GPS para el seguimiento en ruta.

### 3. Dejar la base lista

La noche anterior o esa misma mañana:

```bash
AGROGOOD_BANCO=si .venv/Scripts/python.exe odoo-18.0/odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/preparar_banco_pruebas.py
```

Borra los restos de ensayos anteriores y monta tres pedidos con clientes y
productos reales. Se detiene a propósito **antes** de asignar Picker: repartir
el trabajo es de Felipe y es parte de lo que hay que ensayar.

Para hacer el recorrido entero desde cero —incluida la parte de compras—, usar
`AGROGOOD_BANCO=vaciar`: deja el stock a cero, de modo que el primer pedido
genera faltante, el faltante llega a Compras, Compras compra, Bodega recibe y
solo entonces hay algo que preparar.

### 4. Limpiar los permisos de más

Ocho cuentas pueden hoy administrar empleados, vacaciones, asistencias y
proyectos. No se lo dio nadie: Odoo suma a la plantilla de usuario nuevo un
grupo de cada aplicación que se instala, y esa plantilla se copia en cada alta.

Uno de los criterios del ensayo es que **nadie vea lo que no le toca**, así que
conviene quitarlo antes:

```bash
AGROGOOD_PERMISOS=limpiar .venv/Scripts/python.exe odoo-18.0/odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/limpiar_permisos_sobrantes.py
```

Sin la variable solo informa: conviene mirarlo antes de aplicarlo.

### 5. Quién observa

Una persona que **no participa**: solo mira y anota. Si el que observa también
opera, deja de mirar en cuanto tiene algo que hacer, y lo que se pierde son
justo los segundos de duda.

---

## El día

Las horas son orientativas. Lo que importa es el orden, porque cada paso
necesita el anterior.

### 08:00 — Ventas toma pedidos

Sebastián y Yere, cada uno con su teléfono, toman **tres pedidos reales** de
clientes que llamen esa mañana. Si no llama nadie, se toman de mentira con
clientes reales y se anulan al final.

Uno de los tres tiene que ser de un **cliente nuevo**, dado de alta desde el
teléfono. Y a los quince minutos, uno de los clientes «llama para agregar dos
kilos»: eso obliga a usar la pantalla de modificar.

> **Tiene que pasar:** los tres pedidos aparecen en la lista del día, con su
> total. El que tenía faltante lo dice.

### 09:00 — Compras ve el faltante

Johan abre su pizarra. Lo que Ventas no tenía en bodega tiene que estar ahí sin
que nadie se lo avise.

Anota proveedor y precio de pie, como si estuviera en la feria, y genera la
orden al proveedor.

> **Tiene que pasar:** la solicitud llega sola a la pizarra y la orden de
> compra sale agrupada por proveedor.

### 10:00 — Bodega recibe

La mercadería llega. Bodega la recibe desde el teléfono, con lote y fecha de
vencimiento en los productos que lo llevan.

Y **se cuenta un producto a propósito mal**: se recibe menos de lo que dice el
papel. Hay que ver si la persona se da cuenta de que puede corregirlo con el
ajuste de inventario, o si lo deja pasar.

> **Tiene que pasar:** el stock sube, y la diferencia queda anotada con su
> motivo.

### 11:00 — Logística reparte

Felipe asigna los pedidos a quien prepara, desde el teléfono, en bloque.

> **Tiene que pasar:** cada preparación aparece en el teléfono de su Picker sin
> que nadie le avise.

### 11:30 — Preparación

El Picker prepara los tres pedidos. Uno de ellos, **a propósito**:

* un producto de peso variable se prepara con una diferencia pequeña
  (19,4 kg de los 20 pedidos);
* otro producto **no está** y hay que marcarlo como faltante o sustituirlo.

> **Tiene que pasar:** los 0,6 kg de diferencia **no** generan un pedido en
> espera. El faltante sí llega a Ventas.

### 13:00 — La ruta sale

Felipe arma la ruta con las entregas preparadas y se la asigna al conductor.

El conductor, antes de salir, hace la **revisión del vehículo**. Uno de los
seis puntos se marca como malo a propósito, para ver que el sistema exige la
explicación y avisa a Logística.

> **Tiene que pasar:** sin revisión, la ruta no arranca.

### 14:00 — Reparto

Tres entregas, y cada una termina distinto **a propósito**:

1. **Entregada** con nombre de quien recibe y foto.
2. **No entregada** — el cliente no estaba.
3. **Reprogramada** para dentro de dos días.

> **Tiene que pasar:** la reprogramada vuelve a la lista de Logística del día
> nuevo. Ese es el paso que más conviene comprobar con los ojos: hasta hace
> poco no funcionaba.

### 16:00 — Cierre

Victor abre Dirección y mira las seis cifras. Tienen que cuadrar con lo que
pasó ese día, y **eso se comprueba a mano**, no confiando en la pantalla.

Después, cobranza: se anota una llamada a un cliente que deba, con lo que dijo.

> **Tiene que pasar:** lo vendido, lo por entregar y lo por cobrar coinciden
> con la realidad del día.

---

## Qué anotar

Una hoja por persona. Lo que se busca **no** son los errores del sistema: son
las dudas.

| Hora | Quién | Qué intentaba hacer | Qué buscó | Cuánto tardó | Qué preguntó |
|---|---|---|---|---|---|

Tres cosas valen más que cualquier otra:

1. **Dónde puso el dedo primero**, si no era el botón correcto. Un botón que
   nadie encuentra está mal puesto, no mal explicado.
2. **Qué palabra buscó**, si no encontró la pantalla. Si busca «pedidos» y la
   pantalla dice «órdenes de compra», el nombre está mal.
3. **Qué hizo cuando algo salió mal.** Un mensaje de error que no dice qué
   hacer después manda a la persona a preguntarle a otra, y eso multiplica el
   costo de cada fallo por dos personas.

---

## Cuándo se puede decir que salió bien

No es «no se cayó». Es esto:

- [ ] Los tres pedidos llegaron **de punta a punta** sin que nadie abriera el
      escritorio de Odoo.
- [ ] Cada persona entró con su cuenta y **no vio nada que no le tocaba**.
- [ ] Nadie necesitó preguntarle a Victor **más de una vez** por la misma
      pantalla.
- [ ] Las cifras de Dirección al cierre cuadran con lo que pasó.
- [ ] La entrega reprogramada apareció en el día nuevo.
- [ ] Nadie perdió trabajo hecho por un error de la aplicación.

Si falla el último, se para todo y se arregla eso antes que nada: perder
trabajo hecho es lo único que hace que la gente deje de usar un sistema para
siempre.

---

## Después

Con las hojas de observación delante, la lista de arreglos se ordena por
**cuánta gente tropezó con lo mismo**, no por lo grave que parezca cada cosa.
Un botón que tres personas no encontraron cuesta más al año que un error que
apareció una vez.

Lo que salga de ahí se arregla **antes** de que la empresa dependa del sistema,
no después. Después ya no hay ensayo: hay pedidos de verdad.
