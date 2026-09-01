# Agroapp

Plataforma operativa de **Agrogood**, distribuidora de frutas, verduras y
abarrotes en el Gran Concepción. Construida sobre Odoo 18 Community.

Conecta el ciclo completo del negocio: cliente → venta → pedido → reposición →
inventario → picking → ruta → entrega → facturación → seguimiento comercial.

---

## Estructura

| Carpeta | Qué contiene |
|---|---|
| `addons_agrogood/` | Los trece módulos propios |
| `movil/` | App Android (Capacitor) para conductores |
| `despliegue/` | Docker Compose, HTTPS y respaldos para producción |
| `tools/` | Importación, verificación y pruebas |
| `docs/` | Registros de decisiones de arquitectura (ADR) |
| `config/` | Configuración de desarrollo |

El núcleo de Odoo **no está aquí** y no debe estarlo: se clona aparte y nunca
se modifica. Toda extensión se hace por herencia desde estos módulos, de forma
que actualizar Odoo no destruya el trabajo.

---

## Los módulos

| Módulo | Qué resuelve |
|---|---|
| `agrogood_base` | Líneas comerciales, los ocho roles, peso variable y formatos |
| `agrogood_security` | Conecta los roles con los grupos estándar de Odoo |
| `agrogood_pricing` | Versiones semanales de precios con vigencia e historial |
| `agrogood_sales` | Captura rápida, estados operativos y detección de faltantes |
| `agrogood_procurement_board` | Pizarra de solicitudes de compra |
| `agrogood_picking_ops` | Preparación con tiempos, peso real y mermas tipificadas |
| `agrogood_logistics` | Rutas, conductores, capacidad y evidencia de entrega |
| `agrogood_tracking` | Ubicación del conductor y mapa de seguimiento |
| `agrogood_pwa` | Aplicación móvil de Picker y Conductor |
| `agrogood_crm_reactivation` | Comportamiento de compra y lista de recontacto |
| `agrogood_alerts` | Avisos automáticos hacia el responsable de cada cosa |
| `agrogood_dashboards` | Un panel por rol |
| `agrogood_branding` | La aplicación se presenta como Agroapp |

---

## Desarrollo

```bash
git clone --depth 1 --branch 18.0 https://github.com/odoo/odoo.git odoo-18.0
python -m venv .venv && .venv/Scripts/activate
pip install -r odoo-18.0/requirements.txt
cp config/odoo.conf.example config/odoo.conf   # y rellenar las claves
powershell -ExecutionPolicy Bypass -File config/configurar_base_datos.ps1
.venv/Scripts/python odoo-18.0/odoo-bin -c config/odoo.conf -d agrogood_dev
```

## Producción

Ver [`despliegue/README.md`](despliegue/README.md).

---

## Herramientas

```bash
# Prueba integral: el criterio de aceptacion completo, con rollback al final
odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/prueba_integral.py

# Matriz de permisos, ejecutando cada operacion con cada usuario real
odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http < tools/verificar_permisos.py
```

Ambas se ejecutan tras cualquier cambio. Las demás herramientas informan por
defecto y solo escriben cuando se les pasa una variable de entorno explícita:

| Herramienta | Para qué |
|---|---|
| `importar_datos_maestros.py` | Cargar clientes y productos desde planilla |
| `cruzar_ruts.py` | Completar RUT cruzando con la base de Agrogood |
| `configurar_perecibles.py` | Caducidad, lotes y FEFO |
| `configurar_costos_y_asistencia.py` | Costos de traída y fichas de empleado |
| `configurar_apps_nuevas.py` | Datos mínimos de las aplicaciones añadidas |
| `limpiar_permisos_sobrantes.py` | **Obligatoria tras instalar cualquier aplicación** |
| `limpiar_datos_prueba.py` | Borrar lo que dejaron las pruebas |

---

## Instalar una aplicación de Odoo

Instalar no son dos pasos, son tres, y el tercero se olvida siempre:

```bash
# 1. Instalar
odoo-bin -c config/odoo.conf -d agrogood_dev -i nombre_del_modulo --stop-after-init

# 2. Dejarla utilizable (datos mínimos, si le corresponde)
AGROGOOD_APPS=si odoo-bin shell ... < tools/configurar_apps_nuevas.py

# 3. Devolver los permisos a su sitio
AGROGOOD_PERMISOS=limpiar odoo-bin shell ... < tools/limpiar_permisos_sobrantes.py
```

El tercero no es opcional. Odoo añade el grupo de **administrador** de cada
aplicación al usuario plantilla del que nacen los usuarios nuevos. Instalar seis
aplicaciones dejó la plantilla con administrador de Ventas, Inventario,
Proyectos, Punto de Venta, Gastos y Vacaciones: el siguiente conductor dado de
alta habría nacido pudiendo cambiar precios y ajustar stock.

El efecto no se ve el día de la instalación. Se ve semanas después, y para
entonces nadie relaciona una cosa con la otra. `verificar_permisos.py` lo
comprueba y falla si vuelve a ocurrir.

---

## Cómo se trabaja aquí

**El núcleo de Odoo no se toca.** Ni un archivo. Todo por herencia.

**Reutilizar antes que construir.** Buena parte del alcance la resuelve Odoo
estándar bien configurado. Antes de escribir un modelo se comprueba si ya
existe: así se descartaron `purchase.requisition` y un sistema de *catchweight*
propio, y así se resolvieron FEFO y "facturar lo entregado" sin una línea de
código.

**Los estados se derivan, no se guardan.** Las once etapas del pedido se
calculan de sus albaranes, rutas y facturas. Un campo de estado que alguien
debe mantener al día acaba mintiendo.

**Cómo se llaman las cosas.** En Chile el cliente emite una *orden de compra*,
y así la nombra Agrogood. Pero Odoo llama igual a lo que se le pide a un
proveedor, y confundir una entrada con una salida en bodega es caro. Por eso:

| Documento | En Agroapp se llama |
|---|---|
| Lo que manda el **cliente** (`sale.order`) | **Orden de compra** — abreviada *OC* |
| Lo que se pide al **proveedor** (`purchase.order`) | **Orden al proveedor** |

Los identificadores internos no cambian: siguen siendo `sale.order` y
`purchase.order`. Lo que se ajusta es lo que lee el equipo.

**Las decisiones importantes van en `docs/`,** y el porqué va en el mensaje del
commit. Si algo parece raro, la explicación está en su historia.

**Nada se da por bueno sin ejecutarlo.** Cada módulo se prueba contra datos
reales antes de darlo por terminado. Casi todos los errores serios de este
proyecto aparecieron ahí y no en la revisión del código.

---

## Datos que no viven aquí

Las planillas con RUT, teléfonos y direcciones de clientes están **fuera del
repositorio** a propósito. Son datos de origen, no código, y en Git quedarían
en el historial de forma permanente aunque se borraran después.

Tampoco se versionan `config/odoo.conf` ni `despliegue/.env`, que contienen
claves reales. De ambos hay un `.example` con la estructura.
