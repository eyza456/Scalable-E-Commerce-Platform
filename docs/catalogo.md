# Categorias y busqueda de productos

## Categorias

Lectura publica:

- `GET /categories?skip=0&limit=100`
- `GET /categories/{id}`

Administracion con JWT de rol `admin`:

- `POST /categories`: `{"name":"Tecnologia","description":"Equipos y accesorios"}`
- `PUT /categories/{id}`: reemplaza nombre y descripcion; descripcion es opcional.
- `DELETE /categories/{id}`: devuelve 204 si la categoria esta vacia. Si tiene productos devuelve 409; primero deben reasignarse o desvincularse.

Los nombres se recortan y deben tener entre 1 y 100 caracteres. No se permiten nombres duplicados aunque cambien mayusculas/minusculas; la restriccion se aplica tambien en PostgreSQL. Clientes y vendedores pueden leer categorias, pero no administrarlas.

## Asignacion a productos

Crear o actualizar productos sigue requiriendo rol `admin` o `seller`:

```json
{"name":"Laptop","price":"850.50","stock":10,"category_id":1}
```

Las respuestas incluyen `category_id` y `category`, el nombre de la categoria. Renombrar una categoria se refleja en sus productos sin duplicar nombres almacenados.

Para desvincularla: `PUT /products/{id}` con `{"category_id":null}`. Omitir el campo mantiene la relacion actual.

Por compatibilidad, se acepta `category` como nombre de una categoria **existente**, ignorando espacios externos y mayusculas. No crea categorias implicitamente. Enviar `category` y `category_id` juntos devuelve 422. Una categoria inexistente devuelve 404.

## Busqueda y filtros

```text
GET /products/?name=laptop&category_id=1&available=true&skip=0&limit=20
```

- `name`: coincidencia parcial en el nombre, sin distinguir mayusculas. `%`, `_` y barra inversa se buscan literalmente.
- `category_id`: identificador positivo de categoria.
- `available=true`: producto activo con stock disponible mayor que cero.
- `available=false`: producto inactivo o sin stock.
- `skip`: entero mayor o igual a cero.
- `limit`: entre 1 y 100, por defecto 100.

Todos los filtros se combinan. Las respuestas siguen siendo listas y se ordenan por ID para paginar de forma estable. Sin filtros se conserva el listado general, incluidos los productos inactivos. Sin coincidencias se devuelve una lista vacia.

## Migracion

Se aplico localmente la revision Alembic `9b72ca103d45`, posterior a reservas. Crea `categories`, relaciona `products.category_id` y reemplaza la antigua columna de texto. Conserva los productos y agrupa categorias que solo difieren en espacios externos o mayusculas. Valores vacios quedan sin categoria.

Para otra instalacion, actualizar la imagen de Product y ejecutar `alembic upgrade head` antes de admitir trafico con el nuevo codigo. La revision tambien admite downgrade, reconstruyendo el texto desde los nombres normalizados de categorias.

## Verificacion

- 12 pruebas PostgreSQL de CRUD, integridad, nombres duplicados, compatibilidad, combinacion de filtros y paginacion.
- Upgrade y downgrade probados con datos antiguos en un esquema separado.
- Prueba HTTP de permisos, filtros, nombres duplicados, limites de paginacion y eliminacion de categorias en uso.
- Regresion de inventario y compra completa con el esquema nuevo.

Ejecutar todo con `powershell -ExecutionPolicy Bypass -File tests/run_stability.ps1`.
