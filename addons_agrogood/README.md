# Addons Agrogood

Modulos propios de la plataforma Agrogood sobre Odoo 18.0 Community.

**Este repositorio contiene unicamente codigo propio.** El nucleo de Odoo vive
fuera, en `../odoo-18.0/`, y nunca se versiona ni se modifica: toda extension se
hace por herencia desde estos modulos, de forma que actualizar Odoo no destruya
el trabajo.

## Modulos

| Modulo | Estado | Responsabilidad |
|---|---|---|
| `agrogood_base` | En desarrollo | Lineas comerciales y grupos de seguridad transversales |
| `agrogood_pricing` | Pendiente | Carga semanal de precios con vigencias e historial |
| `agrogood_sales` | Pendiente | Captura rapida de pedidos, estados y reposicion |
| `agrogood_procurement_board` | Pendiente | Pizarra de solicitudes de compra |
| `agrogood_picking_ops` | Pendiente | Picking con metricas, incidencias y peso real |
| `agrogood_logistics` | Pendiente | Rutas, paradas, conductores y evidencia de entrega |
| `agrogood_crm_reactivation` | Pendiente | Metricas de cliente y lista de recontacto |
| `agrogood_pwa` | Pendiente | Aplicacion movil de Picker y Conductor |
| `agrogood_edi_cl` | Pendiente | Facturacion electronica chilena |

## Entorno de desarrollo

```
python -m venv C:\dev\agrogood\.venv
C:\dev\agrogood\.venv\Scripts\activate
pip install -r C:\dev\agrogood\odoo-18.0\requirements.txt
```

Arranque:

```
python C:\dev\agrogood\odoo-18.0\odoo-bin -c C:\dev\agrogood\config\odoo.conf
```
