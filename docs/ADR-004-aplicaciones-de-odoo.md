# ADR-004 - Que aplicaciones de Odoo se instalan y cuales no

Fecha: 2026-08-24
Estado: aceptado
Decide: alcance funcional apoyado en Odoo estandar

## Contexto

Agrogood es propietaria de los trece modulos construidos para ella, pero se
apoya en Odoo Community para todo lo que Odoo ya resuelve bien. Cada
aplicacion estandar que se activa es capacidad nueva sin costo de licencia ni
codigo que mantener.

Eso invita a instalar de mas, y ahi esta el problema. Una aplicacion instalada
no es gratis: anade menus que el equipo tiene que ignorar, campos en formularios
que ya usaban, y grupos de permisos que se reparten solos (ver mas abajo). El
criterio no es "puede servir algun dia" sino "alguien la va a abrir esta
semana".

Estado al cerrar esta decision: **145 modulos, 20 aplicaciones, 13 propias.**

## En uso

| Aplicacion | Para que en Agrogood |
|---|---|
| Ventas, Compras, Inventario, Facturacion | El ciclo del negocio |
| Contactos, Conversaciones, Calendario | Clientes y el hilo de cada pedido |
| Flotilla | Camiones, con mantencion asociada |
| Mantenimiento | Camara de frio, balanza, transpaleta y flota |
| Empleados, Asistencias, Vacaciones | Quien trabaja y con quien se cuenta manana |
| Proyectos | Trabajo interno que no es un pedido |
| Marketing por correo | Una lista por linea comercial |

## Instaladas y todavia sin uso

Se dejan porque el costo de tenerlas es bajo y el de reinstalar mas tarde,
tambien. Pero no se les invento contenido de ejemplo: una aplicacion llena de
datos falsos se ve peor que una vacia.

* **Encuestas** y **Promociones y descuentos**: esperan a que Ventas tenga algo
  concreto que preguntar y una politica comercial decidida.
* **Gastos**: cero gastos registrados. Sus permisos quedaron reducidos a un
  unico aprobador (Victor) en lugar de los nueve usuarios que los tenian.
* **CRM**: instalada, pero el seguimiento comercial de Agrogood no usa
  oportunidades. Vive en `agrogood_crm_reactivation`, que mide comportamiento
  de compra real en vez de un embudo que nadie iba a mantener al dia.

## Descartadas

### Punto de Venta - desinstalada

Estaba instalada y **los nueve usuarios eran administradores** de ella. Cero
sesiones de caja, cero ventas, cero metodos de pago configurados.

Agrogood reparte, no vende en mostrador. Se desinstalo con sus ocho modulos
satelite (154 -> 145 modulos) previo respaldo completo. Ningun modulo propio
dependia de ella y `sale_loyalty` sobrevivio intacto.

Si algun dia abren local, se reinstala en minutos y hay que volver a anadir sus
grupos a `tools/limpiar_permisos_sobrantes.py`.

### Fabricacion (mrp) - no se instala

Confirmado con Agrogood: **no arman cajas mixtas ni packs.** Cada producto se
vende tal como entra.

`mrp` anade listas de materiales y ordenes de produccion a **todos** los
productos, no solo a los que se fabrican. Instalarla para no usarla obliga a
todo el equipo a convivir con conceptos que no existen en su negocio.

Si algun dia arman cajas de regalo o mezclas, se instala y se define la lista
de materiales de esos productos concretos.

### Sitio web y comercio electronico - fuera de alcance

Los pedidos entran por WhatsApp y telefono. Una tienda en linea es un proyecto
comercial, no una casilla que marcar.

## Consecuencia operativa: instalar son tres pasos

Odoo anade el grupo de **administrador** de cada aplicacion recien instalada al
usuario plantilla `base.default_user`, que es el molde del que nacen los
usuarios nuevos. Instalar seis aplicaciones dejo la plantilla con administrador
de Ventas, Inventario, Proyectos, Punto de Venta, Gastos y Vacaciones.

El efecto no se ve el dia de la instalacion. Se ve el dia que se da de alta a un
conductor y nace pudiendo cambiar precios y ajustar stock. Nadie lo relaciona,
porque ese permiso no se pidio: se heredo.

Por eso instalar una aplicacion son tres pasos y el tercero no es opcional:

1. Instalar el modulo.
2. Dejarla utilizable (`tools/configurar_apps_nuevas.py`).
3. **Devolver los permisos a su sitio** (`tools/limpiar_permisos_sobrantes.py`).

`tools/verificar_permisos.py` comprueba la plantilla y falla si vuelve a
ensuciarse, con la orden de correccion en el propio mensaje de error.
