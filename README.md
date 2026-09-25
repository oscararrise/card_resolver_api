# Card Resolver API

Traduce el decimal RAW emitido por la lectora HID OMNIKEY y resuelve una tarjeta a EID usando un roster importado. El formato `auto` reproduce el algoritmo de Lunch Control, incluida su excepción para Serbia. Una configuración conocida de la lectora puede enviarse como `format` (`h10301`, `h10304-reversed`, `h10304-serbia`) para evitar la heurística por rango decimal.

## Endpoints

- `GET /health`: disponibilidad del proceso.
- `POST /api/v1/cards/decode`: requiere `Authorization: Bearer <SERVICE_TOKEN>`; body `{"raw":"89910480577"}`. Solo devuelve `raw` y `decoder`.
- `POST /api/v1/cards/resolve`: mismo body y autenticación; devuelve `employee.hibob_id`, `employee.name`, `decoder` y `dataset_id`. Respuestas: 404 desconocida, 409 ambigua, 503 sin dataset.
- `GET /admin`: panel protegido con HTTP Basic. Se recomienda restringir `/admin` por VPN/IP además de TLS.
- `POST /admin/imports`: carga CSV/XLSX, valida y crea una versión inactiva.
- `GET /admin/imports/{id}/report`: Excel descargable con `SUMMARY`, `LOADED`, `WARNINGS`, `ERRORS`, `DUPLICATES`.
- `POST /admin/imports/{id}/activate`: formulario `reviewed=true`, activa o restaura esa versión.

**Importante:** `EID` se trata como ID de HiBob según la base recibida, pero el propietario de la base debe confirmar esta equivalencia antes de producción. El par `(facility_code, card_number)` es la clave del lookup. Tarjetas de varios empleados con la misma clave quedan excluidas del dataset, sin elegir un empleado al azar. El reporte enumera las filas cargadas, excluidas y las incidencias; activar un lote con errores implica aceptar las filas excluidas. La activación bloquea lotes con más de 30 % menos tarjetas que el activo.

Se admiten los encabezados del CSV recibido, incluido EID sin título en columna B cuando A es `Nro`. Los campos `No TARJETA` y `No TARJETA SEC` se asocian con `Facility Code WFM` y `Facility Code SE`, respectivamente. No se importan documento, teléfono, RH, EPS ni placas. Las columnas `REPOSICIÓN` y `SEGUNDA REPOSICIÓN` se reportan como advertencia y **no se activan como tarjetas** hasta acordar si sustituyen o coexisten con las actuales.

## Ejecución local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env  # generar secretos propios y configurar PostgreSQL
set -a; . ./.env; set +a
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010
.venv/bin/pytest -q
```

Para pruebas aisladas se puede usar `DATABASE_URL=sqlite:///./card_resolver.db`; producción debe usar PostgreSQL. No subir `.env` ni el roster a Git. La contraseña Basic y el token de servicio se toman del entorno y nunca se incluyen en JavaScript. Un navegador no debe invocar `/resolve` con el token incrustado: el backend consumidor debe añadirlo desde su servidor o usar un proxy autenticado y controlado en el mismo origen.

En la VM ARRISE, `DATABASE_URL_PARAMETER`, `SERVICE_TOKEN_PARAMETER` y `ADMIN_PASSWORD_PARAMETER` son nombres de parámetros SSM SecureString cifrados con KMS; el rol IAM de la instancia requiere `ssm:GetParameter` y `kms:Decrypt` limitados a esos parámetros y su clave. El proceso resuelve los secretos al iniciarse o en el primer uso, los conserva en memoria y necesita reiniciarse tras rotarlos. `ADMIN_USER` no es secreto. Los valores directos de `.env.example` son solo para desarrollo.

## Producción

1. Crear rol y base PostgreSQL privados, usuario Unix dedicado, instalación de dependencias en `/opt/card-resolver/.venv` y `/etc/card-resolver.env` legible solo por el servicio.
2. Instalar `deploy/card-resolver.service`, revisar rutas y habilitar systemd. Las tablas se crean al arrancar; para cambios de esquema futuros incorporar migraciones antes de actualizar producción.
3. Integrar `deploy/nginx.conf.example` dentro del servidor TLS existente de Appearance (puerto 443), declarar la zona `limit_req` en `http`, validar `nginx -t` y recargar. Los endpoints públicos quedan bajo `/card-resolver/`: panel `/card-resolver/admin` y API `/card-resolver/api/v1/cards/resolve`. El proxy quita ese prefijo para FastAPI y evita pisar el `/admin` de Django. Restringir el panel a la VPN/red de confianza según la política de la VM.
4. Subir el CSV al panel, descargar y revisar incidencias, confirmar con Data Analytics las reglas de reposición y el significado de EID, activar el lote y probar `89910480577` → facility `1761`, card `167794`, EID `48251`.
5. Restringir acceso a los reportes (contienen nombres), configurar backups PostgreSQL, retención y supervisión; evitar registrar cuerpos de escaneo y credenciales.

La identificación `auto` por umbral de 100 millones reproduce los sistemas actuales, pero no prueba el formato Wiegand ni su paridad. Para lectores con otra configuración, fijar `format` explícitamente y validar tarjetas reales antes de activar la integración.
