# Respaldo en Firebase

Los respaldos de Agroapp se copian a un bucket de **Firebase Storage**. Se
configura una vez y despues no hay que tocarlo: el script de respaldo diario lo
sube solo.

---

## Por que, si ya hay copia en OneDrive

La carpeta de OneDrive cuelga de la **cuenta personal** de quien tiene el
equipo. Si esa persona se va de la empresa, cambia de cuenta o llena su
espacio, los respaldos se van con ella y nadie se entera hasta el dia que hacen
falta.

El bucket es del **proyecto**, no de una persona. Las dos copias conviven:
OneDrive es lo que esta a mano, Firebase es lo que sobrevive.

---

## Configurarlo (una vez, unos diez minutos)

### 1. Crear el proyecto

En <https://console.firebase.google.com>, **Crear un proyecto**. El nombre da
igual; algo como `agrogood-respaldos` se reconoce solo.

### 2. Activar Storage

Menu **Compilacion > Storage > Comenzar**.

Puede pedir activar la facturacion (plan Blaze). Conviene mirar el numero antes
de decir que si: un respaldo completo de Agroapp pesa hoy **unos 15 MB** -8,8
de base y 6,1 de adjuntos-, y se conservan 30 copias, o sea **menos de medio
giga**. Para ese tamano el coste es de centavos al mes, pero es una decision de
la empresa y no del sistema.

Cuando pregunte por las reglas de seguridad, dejar el **modo bloqueado**. Nadie
tiene que leer este bucket desde una aplicacion: solo lo escribe el script del
respaldo, con su propia credencial.

### 3. Descargar la credencial

**Configuracion del proyecto** (la rueda dentada) **> Cuentas de servicio >
Generar nueva clave privada**. Descarga un archivo `.json`.

Guardarlo como:

```
C:\dev\agrogood\config\firebase-clave.json
```

> **Ese archivo es una llave.** Quien lo tenga puede leer y borrar todos los
> respaldos. Esta en `.gitignore`, asi que no se sube al repositorio, y no se
> manda por correo ni por WhatsApp. Si alguna vez se filtra, se revoca desde
> esa misma pantalla y se genera otra.

### 4. Comprobar

```bash
.venv/Scripts/python.exe tools/subir_respaldo.py
```

Sin argumentos **solo informa**: dice a que proyecto y bucket se conecto y que
hay guardado. Para subir el ultimo respaldo:

```bash
AGROGOOD_FIREBASE=subir .venv/Scripts/python.exe tools/subir_respaldo.py
```

A partir de aqui `config\respaldar_local.ps1` lo hace solo cada dia. Si el
bucket se llama de otra forma que la deducida, se le dice:

```bash
AGROGOOD_FIREBASE_BUCKET=nombre-exacto.firebasestorage.app
```

---

## Que comprueba, y por que esas cosas

**Que llego entero.** Despues de subir vuelve a leer el archivo del bucket y
compara tamano y hash MD5 contra el local. Subir y dar por hecho que llego es
la forma habitual de descubrir el dia malo que el respaldo estaba a medias.

**Que no quedo publico.** Pide el archivo como lo pediria un desconocido, sin
credenciales, y comprueba que le dicen que no. Un bucket mal configurado
publica en internet los RUT, telefonos, direcciones y deudas de 157 clientes, y
no avisa de nada.

**Que no es viejo.** Al informar avisa si la copia mas reciente tiene mas de
dos dias: casi siempre significa que la tarea programada dejo de correr, y un
respaldo viejo que sigue ahi tranquiliza a todo el mundo mientras no sirve.

---

## Restaurar desde la nube

Se descarga el `.dump` y el zip de adjuntos desde la consola de Firebase
(**Storage > respaldos > ano > mes**), se dejan en `respaldos\` y se sigue con
el simulacro de siempre:

```bash
powershell -ExecutionPolicy Bypass -File config\simulacro_restauracion.ps1
```

Ese simulacro restaura en una base aparte, compara tabla por tabla contra la
viva, comprueba que los adjuntos estan de verdad en el zip y arranca Odoo
contra la base restaurada. **Conviene correrlo una vez al mes sin excusa**: un
respaldo que nadie ha restaurado nunca no es un respaldo, es un archivo del que
se supone algo.

---

## En el servidor de produccion

`despliegue/respaldar.sh` hace lo mismo despues del respaldo diario. Los
archivos ahi se llaman `agroapp-*.dump` y `adjuntos-*.tar.gz`; la herramienta
reconoce los dos juegos de nombres a proposito, para que no acaben existiendo
dos versiones de esto que se van separando.

Hace falta la misma credencial en el servidor:

```bash
scp config/firebase-clave.json usuario@servidor:/opt/agroapp/config/
chmod 600 /opt/agroapp/config/firebase-clave.json
pip3 install firebase-admin
```
