# GESECIT

Prototipo académico independiente para orientar y hacer seguimiento de solicitudes simuladas de citas médicas. Usa Django, PostgreSQL y un asistente guiado por reglas. No se conecta con Coosalud ni con plataformas de IPS; no guarda diagnósticos ni historias clínicas, y no confirma citas reales.

## Interfaz y módulos

La interfaz sigue la organización de las láminas del proyecto: acceso centrado, barra lateral azul, chat con opciones rápidas, seguimiento, notificaciones y panel administrativo con métricas y tabla.

El registro público crea cuentas de pacientes con nombre, apellido, correo, teléfono, nombre de usuario y contraseña; también permite guardar un código de afiliado ficticio opcional. El paciente puede actualizar esos datos desde **Mi perfil**. Las contraseñas se guardan con el mecanismo seguro de Django.

Cada solicitud de cita tiene una relación obligatoria con la cuenta autenticada que la creó. En **Mis solicitudes** el paciente solo consulta sus propios registros; el personal autorizado puede revisar las solicitudes desde Gestión.

`load_demo_data` carga únicamente el catálogo ficticio necesario para probar solicitudes: cinco servicios, una IPS académica de Cartagena, cinco profesionales inventados y horarios futuros. No crea cuentas ni solicitudes de pacientes. En la demostración no se deben ingresar diagnósticos ni datos clínicos reales.

`load_demo_data` carga cinco servicios, una IPS académica ficticia de Cartagena, cinco profesionales inventados y horarios futuros. No usa datos reales de Coosalud.

## pgAdmin 4 y PostgreSQL local

pgAdmin es el programa para administrar bases; **no instala ni ejecuta el servidor PostgreSQL**. Si quieres una base local, instala PostgreSQL Server para Windows y verifica que esté iniciado. Si solo vas a usar la nube, puedes omitir el servidor local: pgAdmin puede conectarse directamente a Neon.

Para crear una base local desde pgAdmin:

1. Abre pgAdmin y conecta el servidor PostgreSQL local, normalmente `localhost:5432`.
2. En **Login/Group Roles → Create → Login/Group Role**, crea el usuario `gesecit_app`, asigna una contraseña y activa **Can login?**.
3. En **Databases → Create → Database**, crea `gesecit_db` y selecciona `gesecit_app` como propietario.
4. No crees las tablas a mano. Django las genera con las migraciones.

## Ejecutar localmente

Desde esta carpeta, en PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Abre `.env`. Para usar Neon como base, pega la cadena completa de conexión en `DATABASE_URL`; para usar PostgreSQL local, deja `DATABASE_URL` vacío y completa `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGHOST` y `PGPORT`. Luego ejecuta:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py load_demo_data
python manage.py runserver
```

`migrate` aplica las tablas y cambios pendientes. `load_demo_data` agrega servicios, profesionales e instancias ficticias para que el chat tenga opciones; no crea pacientes. Los pacientes se registran desde `/registro/` y quedan asociados automáticamente a las solicitudes que creen. Abre `http://127.0.0.1:8000/`. La administración está en `/admin/`.

## Publicar gratis en internet

La configuración incluida propone **Neon para PostgreSQL + Render para Django**. El plan gratuito actual de Render duerme el servidor web después de 15 minutos sin visitas, y su base PostgreSQL gratuita vence a los 30 días. Neon ofrece una base gratuita con cuotas de cómputo y almacenamiento para una demo académica. Revisa los límites vigentes antes de subir datos.

### 1. Crear la base PostgreSQL en Neon

1. Crea una cuenta gratuita en Neon y crea un proyecto PostgreSQL llamado `gesecit`.
2. Elige una región cercana a la región que usarás en Render.
3. En **Connect**, copia la cadena de conexión de PostgreSQL. Si seleccionas conexión pooled, guarda la cadena completa, incluyendo `sslmode=require`.
4. Conserva la cadena en privado. Es la contraseña de la base; no la pegues en un archivo del repositorio ni en un mensaje público.

Si quieres administrar esa base con pgAdmin, crea una conexión de servidor nueva:

- **Host name/address:** hostname incluido en la cadena, sin `https://`.
- **Port:** el puerto de la cadena, normalmente `5432`.
- **Maintenance database:** nombre de la base incluido en la cadena.
- **Username / Password:** usuario y contraseña de la cadena.
- **SSL mode:** `Require`.

### 2. Subir el proyecto a GitHub

Render despliega desde un repositorio. Crea un repositorio para el contenido de esta carpeta `gesecit` y súbelo desde VS Code o Git. El `.gitignore` ya excluye `.env`, bases SQLite, entornos virtuales y archivos compilados. Verifica que `.env` no aparezca entre los archivos que vas a subir.

### 3. Crear el servicio web en Render

1. En Render, elige **New → Blueprint** y conecta el repositorio de GESECIT.
2. Render leerá `render.yaml`, instalará las dependencias, recogerá los archivos estáticos y aplicará las migraciones.
3. Cuando Render solicite `DATABASE_URL`, pega la cadena de conexión de Neon. Render generará `DJANGO_SECRET_KEY`; el archivo ya le indica que `DJANGO_DEBUG=0`.
4. Espera a que termine el despliegue y abre la URL `*.onrender.com` que Render muestra para el servicio.

El archivo `render.yaml` usa estos comandos:

```text
Build:  pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
Start:  python -m gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

### 4. Crear el administrador y datos ficticios en Neon

Después de instalar las dependencias localmente, copia `.env.example` como `.env` y coloca la cadena de Neon en `DATABASE_URL`. Ejecuta desde PowerShell; estos comandos escribirán en la base de Neon:

```powershell
python manage.py createsuperuser
python manage.py load_demo_data
```

Usa únicamente cuentas y datos ficticios para la demostración.

### Límites del plan gratuito

- Render suspende el servicio tras 15 minutos sin tráfico. La primera visita después de dormir puede tardar cerca de un minuto en cargar.
- Render no conserva cambios en el disco local del servicio; los datos deben permanecer en PostgreSQL.
- Neon escala el cómputo a cero cuando queda inactivo y limita cómputo, almacenamiento y transferencia en el plan gratuito.
- Estos planes sirven para aprendizaje y demostraciones; no los uses para datos reales de salud.

## Datos que quedan por definir

La base puede conectarse con estos nombres iniciales: `gesecit_db`, usuario `gesecit_app`, host `127.0.0.1` y puerto `5432`. La contraseña se escribe únicamente en `.env` o en el panel privado del proveedor.

Para ajustar el esquema, confirma si mantendremos la IPS preferida y fecha preferida en cada solicitud, si el código ficticio de afiliado basta, y qué catálogo ficticio de servicios, IPS, profesionales y horarios quieren mostrar.
