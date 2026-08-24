# Poner Agroapp en produccion

Guia completa. Asume un servidor Linux limpio (Ubuntu 22.04 o 24.04) y un
dominio propio. Lleva alrededor de una hora la primera vez.

---

## 1. Antes de empezar

**Un servidor.** 2 nucleos, 4 GB de RAM, 60 GB de disco. Con 157 clientes y
196 productos sobra de largo; el limite lo pondra el numero de fotos de entrega
que se acumulen, no la operacion.

**Un dominio.** Por ejemplo `app.agrogood.cl`. Hay que crear un registro **A**
apuntando a la IP del servidor **antes** de arrancar: Caddy pide el certificado
al iniciar y falla si el dominio todavia no resuelve.

**Windows no sirve para esto.** No es prejuicio: Odoo en Windows no puede usar
multiproceso, asi que atiende de una peticion en una. Con seis personas
trabajando a la vez se nota, y no hay ajuste que lo arregle.

---

## 2. Preparar el servidor

```bash
# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# Cortafuegos: solo web y SSH
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw --force enable
```

---

## 3. Subir el proyecto

```bash
sudo mkdir -p /opt/agroapp && sudo chown $USER /opt/agroapp
cd /opt/agroapp
git clone <url-del-repositorio> .
cd despliegue
```

Si el repositorio aun no esta en ningun servidor Git, se puede copiar por SCP
desde el equipo de desarrollo. Pero conviene ponerlo en uno: es lo que permite
desplegar una correccion con `git pull` en lugar de copiar archivos a mano.

---

## 4. Configurar

```bash
cp .env.ejemplo .env
openssl rand -base64 24    # una clave para DB_PASSWORD
openssl rand -base64 24    # otra distinta para ADMIN_PASSWD
nano .env
```

Rellenar dominio, correo y las dos claves. **Que sean distintas entre si**: si
alguien consigue una, no debe servirle para la otra.

---

## 5. Arrancar

```bash
docker compose up -d
docker compose logs -f odoo     # Ctrl+C para salir del seguimiento
```

Caddy pide el certificado solo. En un minuto `https://app.agrogood.cl` responde.

---

## 6. Cargar los datos

Desde el equipo de desarrollo:

```bash
# Exportar lo que hay hoy
pg_dump -U odoo -Fc agrogood_dev > agroapp.dump
tar czf adjuntos.tar.gz -C C:/dev/agrogood/filestore .

# Subirlos
scp agroapp.dump adjuntos.tar.gz usuario@servidor:/opt/agroapp/despliegue/respaldos/
```

En el servidor:

```bash
cd /opt/agroapp/despliegue
mv respaldos/agroapp.dump respaldos/agroapp-inicial.dump
mv respaldos/adjuntos.tar.gz respaldos/adjuntos-inicial.tar.gz
./restaurar.sh respaldos/agroapp-inicial.dump
```

**Antes de exportar, limpiar los datos de prueba:**

```bash
AGROGOOD_LIMPIAR=si odoo-bin shell -c config/odoo.conf -d agrogood_dev --no-http \
    < tools/limpiar_datos_prueba.py
```

Borra pedidos, rutas y usuarios de ensayo. Conserva los 153 clientes, los 196
productos, las tarifas y los usuarios del equipo.

---

## 7. Respaldos automaticos

```bash
crontab -e
```

Anadir:

```
0 3 * * * /opt/agroapp/despliegue/respaldar.sh >> /var/log/agroapp-respaldo.log 2>&1
```

**Y probar la restauracion.** Un respaldo que nunca se ha restaurado no es un
respaldo: es una suposicion. Hacerlo una vez, con calma, antes de necesitarlo.

**Sacar las copias del servidor.** El script deja preparadas dos lineas
comentadas al final, para `rclone` o S3. Un respaldo que vive en la misma
maquina que los datos se pierde con ella.

---

## 8. Ajustar la aplicacion movil

En `movil/www/index.html`, fijar el servidor y quitar el campo de la pantalla
de acceso: el conductor no deberia teclear una direccion nunca.

```js
const SERVIDOR_FIJO = "https://app.agrogood.cl";
```

Y en `movil/android/app/src/main/AndroidManifest.xml`, **quitar**
`android:usesCleartextTraffic="true"`. Existia para permitir HTTP en la red
local; con HTTPS ya no hace falta, y dejarlo permite conexiones sin cifrar que
no deberian ocurrir.

Recompilar:

```bash
cd movil && npx cap sync android
cd android && ./gradlew assembleRelease
```

---

## Mantenimiento

| Que | Como |
|---|---|
| Ver que pasa | `docker compose logs -f odoo` |
| Reiniciar | `docker compose restart odoo` |
| Desplegar un cambio | `git pull && docker compose restart odoo` |
| Actualizar un modulo | `docker compose exec odoo odoo -c /etc/odoo/odoo.conf -d agroapp -u agrogood_sales --stop-after-init` |
| Respaldo manual | `./respaldar.sh` |
| Restaurar | `./restaurar.sh respaldos/agroapp-FECHA.dump` |
| Consola de Odoo | `docker compose exec odoo odoo shell -c /etc/odoo/odoo.conf -d agroapp` |

### Actualizar Odoo

Cambiar `image: odoo:18` a la version nueva, y despues:

```bash
./respaldar.sh          # SIEMPRE antes
docker compose pull && docker compose up -d
docker compose exec odoo odoo -c /etc/odoo/odoo.conf -d agroapp -u all --stop-after-init
```

Las actualizaciones **menores** dentro de la 18 son seguras. Saltar a la 19
exige probar los once modulos propios en una copia antes de tocar produccion:
es un proyecto pequeño, no un comando.

---

## Que NO hacer

**No abrir el puerto 5432.** La base solo debe hablar con Odoo, por la red
interna de Docker. Exponerla es la forma mas rapida de perder los datos.

**No activar `list_db`.** Deja que cualquiera desde Internet vea y, con la
clave maestra, borre bases.

**No editar archivos dentro de los contenedores.** Se pierden al reiniciar. Los
cambios van al repositorio y se despliegan con `git pull`.

**No restaurar en produccion sin respaldar antes.** Restaurar borra lo actual;
si el respaldo estaba mal, no hay vuelta atras.
